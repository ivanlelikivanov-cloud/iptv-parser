import os
import re
import time
import logging
import threading
import requests
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify

# Пытаемся загрузить генератор User-Agent, если сервер недоступен — используем заглушку
try:
    from fake_useragent import UserAgent
    ua = UserAgent()
except Exception:
    class DummyUA:
        @property
        def random(self):
            return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    ua = DummyUA()

app = Flask(__name__)

# ==================== НАСТРОЙКИ (МЕЖДУНАРОДНЫЕ) ====================
SEARCH_QUERIES = [
    "free iptv playlist m3u github",
    "global iptv m3u8 links daily",
    "free live tv m3u playlist",
    "iptv channels m3u update"
]

SEED_SITES = [
    "https://github.com/iptv-org/iptv",
    "https://www.reddit.com/r/IPTV/",
    "https://www.reddit.com/r/m3u8/",
]

MAX_DISCOVERED = 50       # Лимит найденных плейлистов
MAX_CHANNELS = 3000       # Лимит обрабатываемых ссылок на каналы
CHECK_TIMEOUT = 4.0       # Таймаут проверки канала (сек)
MAX_WORKERS = 50          # Потоков для проверки каналов
REQUEST_DELAY = 1.5       # Задержка между запросами к сайтам
UPDATE_INTERVAL = 3600    # Интервал обновления (1 час)

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def get_session():
    """Сессия с рандомным UA для обхода базовых блокировок"""
    session = requests.Session()
    session.headers.update({'User-Agent': ua.random})
    return session

# ==================== УНИВЕРСАЛЬНЫЙ КАТЕГОРИЗАТОР ====================
def get_category(name):
    """Определяет категорию канала по ключевым словам (Англ + Рус)"""
    n = name.lower()
    if any(k in n for k in ['news', 'новости', '24', 'bbc', 'cnn', 'vesti']): return 'News'
    elif any(k in n for k in ['movie', 'film', 'кино', 'cinema', 'сериал']): return 'Movies'
    elif any(k in n for k in ['music', 'mtv', 'музыка', 'radio']): return 'Music'
    elif any(k in n for k in ['sport', 'футбол', 'espn', 'bein', 'match']): return 'Sports'
    elif any(k in n for k in ['kids', 'дет', 'cartoon', 'disney', 'nick']): return 'Kids'
    elif any(k in n for k in ['doc', 'докум', 'history', 'nat geo', 'discovery']): return 'Documentary'
    else: return 'General'

def is_playlist_link(url):
    """Простая проверка, что ссылка ведет на плейлист"""
    return '.m3u' in url.lower()

# ==================== ОБНАРУЖЕНИЕ ПЛЕЙЛИСТОВ ====================
def discover_playlists():
    """Находит .m3u/.m3u8 ссылки по всему миру"""
    found = set()
    session = get_session()
    
    # 1. Поиск через DuckDuckGo Lite
    for query in SEARCH_QUERIES:
        try:
            search_url = f"https://lite.duckduckgo.com/lite?q={quote(query)}"
            r = session.get(search_url, timeout=10)
            if r.ok:
                links = re.findall(r'href="(https?://[^"]+?\.m3u8?)"', r.text, re.I)
                for link in links:
                    if is_playlist_link(link):
                        found.add(link)
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            logger.debug(f"❌ Поиск '{query}': {e}")
    
    # 2. Сканирование стартовых сайтов
    for seed in SEED_SITES:
        try:
            r = session.get(seed, timeout=10)
            if r.ok:
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text, re.I)
                for link in links:
                    if is_playlist_link(link):
                        found.add(link)
            time.sleep(REQUEST_DELAY)
        except Exception as e:
            logger.debug(f"❌ Сканирование {seed[:40]}: {e}")
    
    result = list(found)[:MAX_DISCOVERED]
    logger.info(f"🎯 Найдено {len(result)} ссылок на плейлисты")
    return result

# ==================== ПРОВЕРКА КАНАЛОВ ====================
def check_channel(channel):
    """Проверяет, жив ли видеопоток (HEAD или короткий GET)"""
    url = channel['url']
    headers = {'User-Agent': 'VLC/3.0.16 LibVLC/3.0.16'}
    
    try:
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers=headers, allow_redirects=True)
        if r.status_code < 400:
            return channel
    except:
        pass
        
    try:
        r = requests.get(url, timeout=CHECK_TIMEOUT, headers=headers, stream=True, allow_redirects=True)
        if r.status_code < 400:
            return channel
    except:
        pass
        
    return None

# ==================== СБОРКА ПЛЕЙЛИСТА ====================
playlist_cache = "#EXTM3U\n# Global IPTV Pro - Generating playlist, please wait...\n"
cache_lock = threading.Lock()
stats = {"total_found": 0, "alive": 0, "sources": 0, "discovered": 0, "updated": "Building..."}
discovered_sources = []
is_updating = False

def update_cache():
    global playlist_cache, stats, discovered_sources, is_updating
    if is_updating:
        return
    is_updating = True
    
    try:
        logger.info("🔄 Запуск цикла обновления...")
        
        discovered_sources = discover_playlists()
        
        raw_channels = []
        seen_urls = set()
        ok_sources = 0
        session = get_session()
        
        for url in discovered_sources:
            try:
                r = session.get(url, timeout=10)
                if r.ok and '#EXTM3U' in r.text[:100]:
                    ok_sources += 1
                    current_inf = None
                    current_attrs = {}
                    
                    for line in r.text.splitlines():
                        line = line.strip()
                        if line.startswith('#EXTINF:'):
                            match = re.search(r'#EXTINF:-?\d+\s*(.*),(.+)', line)
                            if match:
                                attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', match.group(1)))
                                name = match.group(2).strip()
                                
                                # Больше нет фильтра по языку, добавляем все
                                if 'group-title' not in attrs:
                                    attrs['group-title'] = get_category(name)
                                current_attrs = attrs
                                current_inf = f"#EXTINF:-1 {' '.join(f'{k}=\"{v}\"' for k,v in attrs.items())},{name}"
                                
                        elif current_inf and line.startswith('http'):
                            ch_url = line.split()[0]
                            if ch_url not in seen_urls:
                                seen_urls.add(ch_url)
                                raw_channels.append({
                                    'inf': current_inf,
                                    'url': ch_url,
                                    'name': current_attrs.get('tvg-name') or name,
                                    'logo': bool(current_attrs.get('tvg-logo'))
                                })
                            current_inf = None
            except Exception as e:
                logger.debug(f"❌ Ошибка источника {url[:40]}: {e}")
                
            if len(raw_channels) >= MAX_CHANNELS:
                logger.info(f"🛑 Достигнут лимит {MAX_CHANNELS} каналов для парсинга.")
                break

        logger.info(f"🚀 Собрано {len(raw_channels)} уникальных ссылок. Начинаем многопоточную проверку...")

        alive_channels = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(check_channel, ch) for ch in raw_channels]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    alive_channels.append(result)

        # Сортировка: HD -> логотипы -> остальные
        alive_channels.sort(key=lambda x: (
            1 if 'hd' in x['name'].lower() else 0,
            1 if x['logo'] else 0
        ), reverse=True)

        lines = [
            "#EXTM3U", 
            f"# 🌍 Global IPTV Pro — Updated {time.strftime('%Y-%m-%d %H:%M')}",
            f"# Sources used: {ok_sources}",
            f"# Working channels: {len(alive_channels)}"
        ]
        
        for ch in alive_channels:
            lines.append(ch['inf'])
            lines.append(ch['url'])
        
        with cache_lock:
            playlist_cache = "\n".join(lines)
            stats = {
                "total_found": len(raw_channels),
                "alive": len(alive_channels),
                "sources": ok_sources,
                "discovered": len(discovered_sources),
                "updated": time.strftime('%H:%M')
            }
        
        logger.info(f"✨ Готово! Рабочих каналов: {len(alive_channels)} из {len(raw_channels)}.")
        
    finally:
        is_updating = False

def background_update():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"❌ Критическая ошибка обновления: {e}")
            global is_updating
            is_updating = False
        time.sleep(UPDATE_INTERVAL)

threading.Thread(target=background_update, daemon=True).start()

# ==================== МАРШРУТЫ FLASK ====================
@app.route('/')
def home():
    with cache_lock:
        s = stats.copy()
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>🌍 Global IPTV</title>
<style>body{{background:#0d1117;color:#c9d1d9;font-family:sans-serif;text-align:center;padding:30px}}
h1{{color:#58a6ff}}.stat{{font-size:2rem;font-weight:bold;margin:8px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;max-width:650px;margin:20px auto}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:12px}}
a{{color:#58a6ff}}small{{color:#6e7681}}</style></head><body>
<h1>🌍 Global IPTV Pro</h1>
<p style="color:#8b949e">Automatic Stream Aggregator & Validator</p>
<div class="grid">
<div class="card"><div class="stat" style="color:#58a6ff">{s['total_found']}</div><div>Links Scanned</div></div>
<div class="card"><div class="stat" style="color:#2ea043">{s['alive']}</div><div>Working Now</div></div>
<div class="card"><div class="stat" style="color:#f093fb">{s['sources']}</div><div>Sources</div></div>
<div class="card"><div class="stat" style="color:#a371f7">{s['updated']}</div><div>Last Update</div></div>
</div>
<br>
<p><a href="/playlist.m3u" style="font-size:1.4rem; font-weight:bold;">📥 Download M3U Playlist</a></p>
<br>
<small>
🔄 Auto-update & check: Every hour<br>
🔍 Sources: GitHub, Reddit, DuckDuckGo<br>
✅ Validation: 100% working streams at time of scan
</small>
</body></html>"""

@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                        headers={'Content-Disposition': 'attachment; filename=iptv_global.m3u'})

@app.route('/health')
def health():
    with cache_lock:
        ok = stats['updated'] != "Building..."
    return jsonify({'status': 'ready' if ok else 'initializing'}), (200 if ok else 503)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Сервер запущен на порту {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
