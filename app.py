import os
import re
import time
import logging
import threading
import requests
from flask import Flask, Response

app = Flask(__name__)

# ==================== ИСТОЧНИКИ ====================
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://m3u.su/dit",
    "https://m3u.su/kit",
    "https://m3u.su/d5",
]

playlist_cache = "#EXTM3U\n# IPTV Russia Pro\n"
cache_lock = threading.Lock()

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def get_category(name):
    n = name.lower()
    if any(k in n for k in ['новости', 'news', '24', 'vesti', 'информ']):
        return 'Новости'
    elif any(k in n for k in ['кино', 'movie', 'film', 'сериал']):
        return 'Кино'
    elif any(k in n for k in ['музыка', 'music', 'хит', 'radio']):
        return 'Музыка'
    elif any(k in n for k in ['спорт', 'sport', 'футбол']):
        return 'Спорт'
    elif any(k in n for k in ['дет', 'kids', 'мульт']):
        return 'Детские'
    elif any(k in n for k in ['докум', 'doc', 'познав']):
        return 'Документальные'
    return 'Общие'

def update_cache():
    global playlist_cache
    logger.info("🔄 Обновление плейлиста...")
    lines = ["#EXTM3U", "# IPTV Russia Pro"]
    seen = set()
    count = 0

    for url in SOURCES:
        try:
            r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                inf = ""
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

    with cache_lock:
        playlist_cache = "\n".join(lines)
    logger.info(f"✅ Загружено {count} каналов")


def background_update():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Ошибка обновления: {e}")
        time.sleep(1800)


threading.Thread(target=background_update, daemon=True).start()


@app.route('/')
def home():
    return "<h1>🇷🇺 IPTV Russia Pro</h1><p><a href='/playlist.m3u'>Скачать плейлист</a></p>"


@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
