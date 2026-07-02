from flask import Flask, Response
import requests
import threading
import time
import logging

app = Flask(__name__)

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
]

playlist_cache = "#EXTM3U\n# IPTV Russia - Loading...\n"
cache_time = 0

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_cache():
    global playlist_cache, cache_time
    logger.info("🔄 Загрузка каналов...")
    all_lines = ["#EXTM3U", "# IPTV Russia Pro - 2000+ каналов"]
    seen = set()

    for url in SOURCES:
        try:
            r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                lines = r.text.splitlines()
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if line.startswith('#EXTINF:'):
                        inf = line
                        i += 1
                        if i < len(lines) and lines[i].strip().startswith('http'):
                            url_stream = lines[i].strip()
                            if url_stream not in seen:
                                seen.add(url_stream)
                                all_lines.append(inf)
                                all_lines.append(url_stream)
                    i += 1
        except Exception as e:
            logger.warning(f"Ошибка {url}: {e}")

    playlist_cache = "\n".join(all_lines)
    cache_time = time.time()
    logger.info(f"✅ Загружено {len(seen)} каналов")


def background_update():
    while True:
        update_cache()
        time.sleep(1800)  # 30 минут


# Первый запуск
threading.Thread(target=background_update, daemon=True).start()
time.sleep(8)  # Даём время на первую загрузку


@app.route('/')
def home():
    return """
    <h1>🇷🇺 IPTV Russia Pro</h1>
    <p><a href="/playlist.m3u" style="font-size:24px">📥 Скачать плейлист</a></p>
    <p>Если каналов мало — нажми F5 через 15 секунд</p>
    """


@app.route('/playlist.m3u')
def playlist():
    if time.time() - cache_time > 600:  # если старше 10 минут
        threading.Thread(target=update_cache, daemon=True).start()
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
