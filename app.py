import os, re, time, logging, threading, requests
from flask import Flask, Response

app = Flask(__name__)

# ==================== СТАТИЧЕСКИЕ ИСТОЧНИКИ ====================
STATIC_SOURCES = [
    # IPTV-ORG
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    
    # Free-TV / GitHub
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    
    # M3U.SU
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/sng.m3u",
]

# ==================== СТРАНИЦЫ ДЛЯ ДИНАМИЧЕСКОГО ПАРСИНГА ====================
HTML_SOURCES = [
    "https://sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026",
    "https://6x6.msk.ru/",
    "https://iptv-paris.ru/playlist/",
    "https://iptv-russia.tv/sources",
]

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

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

# ==================== ДИНАМИЧЕСКИЙ ПАРСИНГ ====================
def fetch_dynamic_sources(page_urls):
    """Сканирует веб-страницы и собирает ссылки на .m3u/.m3u8"""
    dynamic = set()
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/114.0.0.0 Safari/537.36'}
    
    for page in page_urls:
        try:
            logger.info(f"🔍 Сканирование: {page}")
            r = requests.get(page, headers=headers, timeout=15)
            if r.status_code == 200:
                # Ищем .m3u и .m3u8 ссылки
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text)
                for link in links:
                    # Фильтруем только русские источники
                    if any(x in link.lower() for x in ['ru', 'russia', 'moscow', 'spb', 'sib', 'ural']):
                        dynamic.add(link)
                logger.info(f"✅ +{len([l for l in links if 'ru' in l.lower()])} RU ссылок на {page.split('/')[-1][:20]}")
        except Exception as e:
            logger.debug(f"❌ {page[:40]}: {e}")
    
    return list(dynamic)

# ==================== ОБНОВЛЕНИЕ ПЛЕЙЛИСТА ====================
playlist_cache = "#EXTM3U\n"
cache_lock = threading.Lock()
stats = {"total": 0, "static": 0, "dynamic": 0, "sources": 0}

def update_cache():
    global playlist_cache, stats
    logger.info("🔄 Обновление плейлиста...")
    
    # 1. Собираем динамические источники
    dynamic_sources = fetch_dynamic_sources(HTML_SOURCES)
    all_sources = list(set(STATIC_SOURCES + dynamic_sources))
    
    lines = [
        "#EXTM3U",
        f"# 🇷🇺 IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}",
        f"# Статических источников: {len(STATIC_SOURCES)}",
        f"# Динамических источников: {len(dynamic_sources)}",
        f"# Всего каналов будет обновлено автоматически"
    ]
    
    seen_urls = set()
    seen_keys = set()
    count = 0
    ok_sources = 0
    static_count = 0
    dynamic_count = 0

    for url in all_sources:
        try:
            r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if r.ok:
                ok_sources += 1
                if url in STATIC_SOURCES:
                    static_count += 1
                else:
                    dynamic_count += 1
                    
                current_inf = None
                current_attrs = {}
                
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
                            lines.append(current_inf)
                            lines.append(ch_url)
                            count += 1
                        current_inf = None
        except Exception as e:
            logger.debug(f"❌ {url[:40]}: {e}")

    with cache_lock:
        playlist_cache = "\n".join(lines)
        stats = {
            "total": count,
            "static": static_count,
            "dynamic": dynamic_count,
            "sources": ok_sources
        }

    logger.info(f"✅ {count} каналов | Статика: {static_count} | Динамика: {dynamic_count} | Источников: {ok_sources}")


def background_update():
    while True:
        update_cache()
        time.sleep(1800)  # 30 минут


# Запуск фонового обновления
threading.Thread(target=background_update, daemon=True).start()
time.sleep(15)  # Ждём первую загрузку


# ==================== ROUTES ====================
@app.route('/')
def home():
    with cache_lock:
        s = stats.copy()
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>🇷🇺 IPTV</title>
<style>body{{background:#0d1117;color:#c9d1d9;font-family:sans-serif;text-align:center;padding:40px}}
h1{{color:#58a6ff}}.stat{{font-size:2rem;font-weight:bold;margin:10px}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:15px;margin:10px}}
a{{color:#58a6ff}}code{{background:#21262d;padding:2px 6px;border-radius:3px}}</style></head><body>
<h1>🇷🇺 IPTV Russia Pro</h1>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;max-width:600px;margin:20px auto">
<div class="card"><div class="stat" style="color:#2ea043">{s['total']}</div><div>Каналов</div></div>
<div class="card"><div class="stat" style="color:#58a6ff">{s['static']}</div><div>Статика</div></div>
<div class="card"><div class="stat" style="color:#f093fb">{s['dynamic']}</div><div>Динамика</div></div>
<div class="card"><div class="stat" style="color:#a371f7">{s['sources']}</div><div>Источников</div></div>
</div>
<p><a href="/playlist.m3u" style="font-size:1.2rem">📥 Скачать плейлист M3U</a></p>
<p style="color:#6e7681;font-size:0.9rem">
🔄 Автообновление: 30 мин<br>
🔍 Динамический парсинг: {len(HTML_SOURCES)} сайтов<br>
🇷🇺 Только русские каналы
</p>
</body></html>"""


@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                       headers={'Content-Disposition': 'attachment; filename=iptv_ru.m3u'})


@app.route('/api/stats')
def api_stats():
    with cache_lock:
        return stats


if __name__ == '__main__':
    logger.info(f"🚀 Запуск... {len(STATIC_SOURCES)} статических + {len(HTML_SOURCES)} динамических источников")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
