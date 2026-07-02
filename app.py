import os
import time
import logging
import threading
import requests
from flask import Flask, Response

app = Flask(__name__)

# ==================== МАКСИМАЛЬНЫЕ ИСТОЧНИКИ ====================
SOURCES = [
    # IPTV-ORG (основные + регионы)
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
    "https://iptv-org.github.io/iptv/regions/ru-northwest.m3u",

    # GitHub + другие крупные сборки
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
    "https://m3u.su/m3u/ru_deti.m3u",
]

playlist_cache = "#EXTM3U\n# IPTV Russia Pro - Максимум каналов\n"
cache_time = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_cache():
    global playlist_cache, cache_time
    logger.info("🔄 Загрузка плейлиста...")
    lines = ["#EXTM3U", "# IPTV Russia Pro - Максимум"]
    seen = set()
    count = 0

    for url in SOURCES:
        try:
            r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        inf = line
                    elif line.startswith('http') and line not in seen:
                        seen.add(line)
                        lines.append(inf)
                        lines.append(line)
                        count += 1
        except Exception as e:
            logger.warning(f"Ошибка {url}: {e}")

    playlist_cache = "\n".join(lines)
    cache_time = time.time()
    logger.info(f"✅ Загружено {count} каналов")


def background_update():
    while True:
        update_cache()
        time.sleep(1800)


threading.Thread(target=background_update, daemon=True).start()
time.sleep(12)


@app.route('/')
def home():
    return "<h1>🇷🇺 IPTV Russia Pro</h1><p><a href='/playlist.m3u'>Скачать плейлист</a></p>"


@app.route('/playlist.m3u')
def playlist():
    if time.time() - cache_time > 600:
        threading.Thread(target=update_cache, daemon=True).start()
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
