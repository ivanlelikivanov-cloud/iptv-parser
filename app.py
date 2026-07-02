import os
import re
import time
import logging
import threading
import requests
from flask import Flask, Response

app = Flask(__name__)

# ==================== МАКСИМАЛЬНЫЕ ИСТОЧНИКИ ====================
SOURCES = [
    # IPTV-ORG (лучший проект)
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

    # GitHub репозитории
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://raw.githubusercontent.com/playlist-for-free/IPTV/main/ru.m3u",
    "https://raw.githubusercontent.com/KissyDK/free-iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/Ru-IPTV/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/IPTV-RU/playlist/main/ru.m3u",

    # M3U.SU коллекции
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
    "https://m3u.su/m3u/ru_deti.m3u",
    "https://m3u.su/m3u/ru_music.m3u",
    "https://m3u.su/m3u/ru_news.m3u",

    # Дополнительные
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://raw.githubusercontent.com/sat-iptv/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
]

playlist_cache = "#EXTM3U\n# IPTV Russia Pro\n"
cache_lock = threading.Lock()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def update_cache():
    global playlist_cache
    logger.info("🔄 Сборка плейлиста...")
    lines = ["#EXTM3U", "# IPTV Russia Pro"]
    seen = set()
    count = 0

    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                current_inf = None
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        current_inf = line
                    elif current_inf and line.startswith('http') and line not in seen:
                        seen.add(line)
                        lines.append(current_inf)
                        lines.append(line)
                        count += 1
                        current_inf = None
        except Exception as e:
            logger.warning(f"Ошибка {url}: {e}")

    with cache_lock:
        playlist_cache = "\n".join(lines)
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
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
