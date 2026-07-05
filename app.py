import os
import re
import time
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response

app = Flask(__name__)

# ==================== СТРАНИЦЫ ДЛЯ СКАНИРОВАНИЯ ====================
HTML_SOURCES = [
    "https://homtv.ru/",
    "https://sat-portal.com/plejlisty",
    "https://pikniktv.info/viewtopic.php?t=6737",
    "https://6x6.msk.ru/",
    "https://iptv-rus.com/",
    "https://sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026",
]

# ==================== СТАТИЧЕСКИЕ ИСТОЧНИКИ ====================
STATIC_SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-volga.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://m3u.su/dit",
    "https://m3u.su/kit",
    "https://m3u.su/d5",
]

playlist_cache = "#EXTM3U\n# IPTV Russia Pro - Идет сборка...\n"
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def fetch_dynamic_sources():
    dynamic = set()
    for page in HTML_SOURCES:
        try:
            r = requests.get(page, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text)
                for link in links:
                    dynamic.add(link)
                logger.info(f"✅ Найдено {len(links)} ссылок на {page}")
        except Exception as e:
            logger.error(f"Ошибка {page}: {e}")
    return list(dynamic)

def check_stream_status(channel):
    try:
        r = requests.head(channel['url'], timeout=3, headers=HEADERS, allow_redirects=True)
        if r.status_code < 400:
            return channel
    except:
        pass
    return None

def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    logger.info("🔄 Сборка плейлиста...")

    dynamic = fetch_dynamic_sources()
    all_sources = list(set(STATIC_SOURCES + dynamic))

    raw_channels = []
    seen = set()
    for url in all_sources:
        try:
            r = requests.get(url, timeout=12, headers=HEADERS)
            if r.status_code == 200:
                inf = None
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        inf = line
                    elif inf and line.startswith('http'):
                        stream = line.split()[0]
                        if stream not in seen:
                            seen.add(stream)
                            raw_channels.append({'inf': inf, 'url': stream})
                        inf = None
        except:
            pass

    # Проверка каналов
    valid = []
    with ThreadPoolExecutor(max_workers=40) as executor:
        futures = [executor.submit(check_stream_status, ch) for ch in raw_channels]
        for future in as_completed(futures):
            if result := future.result():
                valid.append(result)

    lines = ["#EXTM3U", f"# IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}"]
    lines.append(f"# Рабочих каналов: {len(valid)}")
    for ch in valid:
        lines.append(ch['inf'])
        lines.append(ch['url'])

    with cache_lock:
        playlist_cache = "\n".join(lines)
    is_updating = False
    logger.info(f"✅ Готово! {len(valid)} рабочих каналов")

def background_update():
    while True:
        update_cache()
        time.sleep(1800)

threading.Thread(target=background_update, daemon=True).start()
time.sleep(15)

@app.route('/')
def home():
    return "<h1>🇷🇺 IPTV Russia Pro</h1><p><a href='/playlist.m3u'>Скачать плейлист</a></p>"

@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
