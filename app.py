import os
import re
import time
import logging
import threading
import requests
from flask import Flask, Response, jsonify

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
    "https://iptv-org.github.io/iptv/regions/ru-volga.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
]

playlist_cache = "#EXTM3U\n# IPTV Russia Pro\n"
cache_lock = threading.Lock()
stats = {"total": 0, "sources_ok": 0}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def is_russian_channel(name, attrs):
    name_lower = name.lower()
    if re.search(r'[\u0400-\u04FF]', name):  # Кириллица
        return True
    if attrs.get('tvg-language') in ['rus', 'ru']:
        return True
    return False

def update_cache():
    global playlist_cache, stats
    logger.info("🔄 Обновление плейлиста...")
    lines = ["#EXTM3U", "# IPTV Russia Pro"]
    seen = set()
    count = 0
    ok_sources = 0

    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                ok_sources += 1
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
            logger.warning(f"Ошибка {url[:50]}: {e}")

    with cache_lock:
        playlist_cache = "\n".join(lines)
        stats = {"total": count, "sources_ok": ok_sources}

    logger.info(f"✅ Загружено {count} каналов из {ok_sources} источников")


def background_update():
    while True:
        update_cache()
        time.sleep(1800)  # 30 минут


threading.Thread(target=background_update, daemon=True).start()
time.sleep(12)  # первая загрузка


@app.route('/')
def home():
    with cache_lock:
        s = stats.copy()
    return f"""
    <h1>🇷🇺 IPTV Russia Pro</h1>
    <p>Каналов: <b>{s['total']}</b></p>
    <p>Рабочих источников: <b>{s['sources_ok']}</b></p>
    <p><a href="/playlist.m3u">Скачать M3U</a></p>
    """


@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
