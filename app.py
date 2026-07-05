import os
import time
import logging
import threading
import requests
from flask import Flask, Response

app = Flask(__name__)

# ==================== МАКСИМАЛЬНЫЕ ИСТОЧНИКИ ====================
SOURCES = [
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
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
    # Твои новые
    "https://m3u.su/dit",
    "https://m3u.su/kit",
    "https://m3u.su/d5",
]

playlist_cache = "#EXTM3U\n# IPTV Russia Pro\n"
cache_lock = threading.Lock()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_channel(url):
    """Проверка работоспособности канала"""
    try:
        r = requests.head(url, timeout=4, headers={'User-Agent': 'Mozilla/5.0'}, allow_redirects=True)
        return r.status_code < 400
    except:
        return False

def update_cache():
    global playlist_cache
    logger.info("🔄 Сборка плейлиста...")
    lines = ["#EXTM3U", "# IPTV Russia Pro - С проверкой каналов"]
    seen = set()
    count = 0
    alive_count = 0

    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                inf = ""
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        inf = line
                    elif line.startswith('http') and line not in seen:
                        seen.add(line)
                        if check_channel(line):
                            lines.append(inf)
                            lines.append(line)
                            count += 1
                            alive_count += 1
                        else:
                            # Добавляем даже мёртвые, но с пометкой
                            lines.append(inf + " [DEAD]")
                            lines.append(line)
                            count += 1
        except Exception as e:
            logger.warning(f"Ошибка {url}: {e}")

    with cache_lock:
        playlist_cache = "\n".join(lines)
    logger.info(f"✅ Всего: {count} | Живых: {alive_count}")


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
