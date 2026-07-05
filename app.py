import os, re, time, logging, threading, requests
from urllib.parse import urljoin, urlparse, quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify
from fake_useragent import UserAgent

app = Flask(__name__)

# ==================== НАСТРОЙКИ ====================
SEARCH_QUERIES = [
    "iptv russia m3u",
    "русские каналы m3u8",
    "iptv playlist ru site:github.com",
]

SEED_SITES = [
    "https://github.com/iptv-org/iptv",
    "https://sat-portal.com/plejlisty",
    "https://homtv.ru/",
    "https://6x6.msk.ru/",
    "https://iptv-rus.com/",
]

MAX_DISCOVERED = 100      # Лимит найденных плейлистов
MAX_CHANNELS = 3000       # Лимит каналов в финальном плейлисте
CHECK_TIMEOUT = 3         # Таймаут проверки канала (сек)
MAX_WORKERS = 30          # Потоков для проверки каналов
REQUEST_DELAY = 2.0       # Задержка между запросами к сайтам
UPDATE_INTERVAL = 3600    # Интервал обновления (сек)

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== USER-AGENT & SCRAPER ====================
ua = UserAgent()

def get_session():
    """Сессия с рандомным UA и retry"""
    session = requests.Session()
    session.headers.update({'User-Agent': ua.random})
    session.mount('https://', requests.adapters.HTTPAdapter(max_retries=2))
    return session

# ==================== ФИЛЬТР РУССКИХ КАНАЛОВ ====================
def is_russian_channel(name, attrs, url):
    lang = attrs.get('tvg-language', '').lower()
    if lang in ['rus', 'ru', 'russian']:
        return True
    if re.search(r'[\u0400-\u04FF]', name):
        exclude = ['.by/', '.ua/', '.kz/', '.am/', '.ge/', '.az/',
                   'belarus', 'ukraine', 'kazakh', 'armenia', 'georgia']
        if any(x in url.lower() or x in name.lower() for x in exclude):
            return False
        return True
    return False

def get_category(name):
    n = name.lower()
    if any(k in n for k in ['новости', 'news', '24', 'vesti']): return 'Новости'
    elif any(k in n for k in ['кино', 'movie', 'film', 'сериал']): return 'Кино'
    elif any(k in n for k in ['музыка', 'music', 'хит', 'radio']): return 'Музыка'
    elif any(k in n for k in ['спорт', 'sport', 'футбол']): return 'Спорт'
    elif any(k in n for k in ['дет', 'kids', 'мульт']): return 'Детские'
    elif any(k in n for k in ['докум', 'doc']): return 'Документальные'
    else: return 'Общие'

# ==================== ОБНАРУЖЕНИЕ ПЛЕЙЛИСТОВ ====================
def discover_playlists():
    """Находит .m3u/.m3u8 ссылки (без банов)"""
    found = set()
    session = get_session()
    
    # 1. Поиск по запросам (ограничено, чтобы не забанили)
    for i, query in enumerate(SEARCH_QUERIES[:3]):  # Только 3 запроса
        try:
            # DuckDuckGo Lite — меньше защиты
            search_url = f"https://lite.duckduckgo.com/lite?q={quote(query)}"
            r = session.get(search_url, timeout=12)
            if r.ok:
                links = re.findall(r'href="(https?://[^"]+?\.m3u8?)"', r.text, re.I)
                for link in links:
                    if is_ru_source(link):
                        found.add(link)
            time.sleep(REQUEST_DELAY * 3)  # Дольше между поисковыми запросами
        except Exception as e:
            logger.debug(f"❌ Поиск '{query}': {e}")
    
    # 2. Сканирование стартовых сайтов
    for seed in SEED_SITES:
        try:
            r = session.get(seed, timeout=12)
            if r.ok:
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text, re.I)
                for link in links:
                    if is_ru_source(link):
                        found.add(link)
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            logger.debug(f"❌ Сканирование {seed[:40]}: {e}")
    
    result = list(found)[:MAX_DISCOVERED]
    logger.info(f"🎯 Найдено {len(result)} плейлистов")
    return result

def is_ru_source(url):
    url_lower = url.lower()
    return any(x in url_lower for x in ['ru', 'russia', 'moscow', 'spb', 'sib', 'ural']) and '.m3u' in url_lower

# ==================== ПРОВЕРКА КАНАЛОВ ====================
def check_channel(channel):
    """Проверяет, жив ли канал"""
    url = channel.get('url')
    if not url:
        return False
    try:
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers={'User-Agent': ua.random}, allow_redirects=True)
        return r.status_code < 400
    except:
        return False

def validate_channels(channels, sample_size=500):
    """Многопоточная проверка каналов"""
    sample = channels[:sample_size] if len(channels) > sample_size else channels
    alive = []
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ch = {executor.submit(check_channel, ch): ch for ch in sample}
        for future in as_completed(future_to_ch):
            ch = future_to_ch[future]
            if future.result():
                ch['alive'] = True
                alive.append(ch)
            else:
                ch['alive'] = False
    
    logger.info(f"✅ Проверено {len(sample)}, живых: {len(alive)}")
    return alive, len(alive)

# ==================== СБОРКА ПЛЕЙЛИСТА ====================
playlist_cache = "#EXTM3U\n"
cache_lock = threading.Lock()
stats = {"total": 0, "alive": 0, "sources": 0, "discovered": 0, "updated": ""}
discovered_sources = []  # Кэш найденных источников

def update_cache():
    global playlist_cache, stats, discovered_sources
    logger.info("🔄 Обновление плейлиста...")
    
    # 1. Обнаружение источников (если старые или пустые)
    if not discovered_sources or time.time() - getattr(app, '_last_discovery', 0) > UPDATE_INTERVAL:
        discovered_sources = discover_playlists()
        app._last_discovery = time.time()
    
    # 2. Загрузка и парсинг плейлистов
    lines = ["#EXTM3U", f"# 🇷🇺 IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}"]
    seen_urls = set()
    seen_keys = set()
    all_channels = []
    ok_sources = 0
    session = get_session()
    
    for url in discovered_sources:
        try:
            r = session.get(url, timeout=10)
            if r.ok and '#EXTM3U' in r.text[:100]:
                ok_sources += 1
                current_inf, current_attrs = None, {}
                
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        match = re.search(r'#EXTINF:-?\d+\s*(.*),(.+)', line)
                        if match:
                            attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', match.group(1)))
                            name = match.group(2).strip()
                            if is_russian_channel(name, attrs, url):
                                if 'group-title' not in attrs:
                                    attrs['group-title'] = get_category(name)
                                current_attrs = attrs
                                current_inf = f"#EXTINF:-1 {' '.join(f'{k}=\"{v}\"' for k,v in attrs.items())},{name}"
                    elif current_inf and line.startswith('http'):
                        ch_url = line.split()[0]
                        key = current_attrs.get('tvg-id') or current_attrs.get('tvg-name') or ch_url
                        if ch_url not in seen_urls and key not in seen_keys:
                            seen_urls.add(ch_url)
                            seen_keys.add(key)
                            all_channels.append({
                                'name': current_attrs.get('tvg-name') or current_inf.split(',')[-1],
                                'attrs': current_attrs,
                                'url': ch_url,
                                'alive': True  # По умолчанию считаем живым
                            })
                            lines.append(current_inf)
                            lines.append(ch_url)
                            if len(seen_urls) >= MAX_CHANNELS:
                                break
                        current_inf = None
        except Exception as e:
            logger.debug(f"❌ {url[:40]}: {e}")
        if len(seen_urls) >= MAX_CHANNELS:
            break
    
    # 3. Валидация каналов (выборочно)
    alive_channels, alive_count = validate_channels(all_channels, sample_size=400)
    
    # 4. Сортировка: живые → с лого → HD
    all_channels.sort(key=lambda x: (
        1 if x.get('alive') else 0,
        1 if x.get('attrs', {}).get('tvg-logo') else 0,
        1 if 'hd' in x.get('name', '').lower() else 0
    ), reverse=True)
    
    # 5. Сохранение в кэш
    with cache_lock:
        playlist_cache = "\n".join(lines[:MAX_CHANNELS*2+10])  # +заголовки
        stats = {
            "total": len(all_channels),
            "alive": alive_count,
            "sources": ok_sources,
            "discovered": len(discovered_sources),
            "updated": time.strftime('%H:%M')
        }
    
    logger.info(f"✨ Готово: {stats['total']} каналов, {stats['alive']} живых, {ok_sources} источников")


def background_update():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"❌ Ошибка обновления: {e}")
        time.sleep(UPDATE_INTERVAL)

# Запускаем фоновое обновление (НЕ блокируем основной поток!)
threading.Thread(target=background_update, daemon=True).start()
# ❌ НЕТ time.sleep() здесь — Flask должен запуститься мгновенно!


# ==================== ROUTES ====================
@app.route('/')
def home():
    with cache_lock:
        s = stats.copy()
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>🇷🇺 IPTV</title>
<style>body{{background:#0d1117;color:#c9d1d9;font-family:sans-serif;text-align:center;padding:30px}}
h1{{color:#58a6ff}}.stat{{font-size:2rem;font-weight:bold;margin:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;max-width:650px;margin:20px auto}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px}}
a{{color:#58a6ff}}small{{color:#6e7681}}</style></head><body>
<h1>🇷🇺 IPTV Russia Pro</h1>
<div class="grid">
<div class="card"><div class="stat" style="color:#2ea043">{s['total']}</div><div>Каналов</div></div>
<div class="card"><div class="stat" style="color:#2ea043">{s['alive']}</div><div>Живых</div></div>
<div class="card"><div class="stat" style="color:#58a6ff">{s['sources']}</div><div>Источников</div></div>
<div class="card"><div class="stat" style="color:#f093fb">{s['discovered']}</div><div>Найдено</div></div>
</div>
<p><a href="/playlist.m3u" style="font-size:1.1rem">📥 Скачать плейлист M3U</a></p>
<small>
🔄 Автообновление: 60 мин<br>
🔍 Поиск: DuckDuckGo Lite + форумы<br>
✅ Валидация: {MAX_WORKERS} потоков<br>
🇷🇺 Только русские каналы
</small>
</body></html>"""


@app.route('/playlist.m3u')
def playlist():
    # Триггер фонового обновления если кэш старый
    if time.time() - getattr(app, '_last_update', 0) > 1800:
        app._last_update = time.time()
        threading.Thread(target=update_cache, daemon=True).start()
    
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                       headers={'Content-Disposition': 'attachment; filename=iptv_ru.m3u'})


@app.route('/api/stats')
def api_stats():
    with cache_lock:
        return stats


@app.route('/health')
def health():
    """Health check для хостингов"""
    with cache_lock:
        ok = stats['total'] > 0 and time.time() - getattr(app, '_last_update', time.time()) < 7200
    return jsonify({'status': 'healthy' if ok else 'initializing', 'channels': stats.get('total', 0)}), (200 if ok else 503)


if __name__ == '__main__':
    logger.info("🚀 IPTV Russia Pro запущен")
    # ❌ НЕТ time.sleep() — Flask стартует сразу!
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)
