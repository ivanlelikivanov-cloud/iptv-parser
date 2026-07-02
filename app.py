import os
import re
import time
import logging
import threading
import requests
from flask import Flask, Response, request

app = Flask(__name__)

# ==================== ИСТОЧНИКИ С АКЦЕНТОМ НА РЕГИОНЫ ====================
SOURCES = [
    # Региональные (самые важные)
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",      # Москва +3
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",      # СПб +3
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",     # Урал +5
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",      # Сибирь +7
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u", # Дальний Восток +10/+11
    "https://iptv-org.github.io/iptv/regions/ru-volga.m3u",    # Поволжье +4
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",    # Юг
    "https://iptv-org.github.io/iptv/regions/ru-northwest.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-crimea.m3u",

    # Общие российские
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
]

playlist_cache = "#EXTM3U\n# IPTV Russia - Региональные каналы\n"
cache_time = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_cache():
    global playlist_cache, cache_time
    logger.info("🔄 Загрузка региональных каналов...")
    lines = ["#EXTM3U", "# IPTV Russia Pro - Регионы РФ"]
    seen = set()

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
        except:
            pass

    playlist_cache = "\n".join(lines)
    cache_time = time.time()
    logger.info(f"✅ Загружено {len(seen)} каналов")


def background_update():
    while True:
        update_cache()
        time.sleep(1800)


threading.Thread(target=background_update, daemon=True).start()
time.sleep(12)  # первая загрузка


@app.route('/')
def home():
    return """
    <h1>🇷🇺 IPTV Russia - Регионы</h1>
    <p><a href="/playlist.m3u">Скачать все</a></p>
    <p><a href="/playlist.m3u?region=mos">Москва</a> | 
       <a href="/playlist.m3u?region=ural">Урал</a> | 
       <a href="/playlist.m3u?region=sib">Сибирь</a></p>
    """


@app.route('/playlist.m3u')
def playlist():
    region = request.args.get('region', '').lower()
    if time.time() - cache_time > 600:
        threading.Thread(target=update_cache, daemon=True).start()
    
    # Простая фильтрация по ключевому слову в названии
    filtered_lines = playlist_cache.splitlines()
    if region:
        filtered = ["#EXTM3U", f"# Регион: {region.upper()}"]
        i = 0
        while i < len(filtered_lines):
            line = filtered_lines[i]
            if line.startswith('#EXTINF:') and region in line.lower():
                filtered.append(line)
                i += 1
                if i < len(filtered_lines):
                    filtered.append(filtered_lines[i])
            i += 1
        return Response('\n'.join(filtered), mimetype='application/vnd.apple.mpegurl')
    
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
