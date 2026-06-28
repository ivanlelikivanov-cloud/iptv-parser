from flask import Flask, Response, render_template_string
import requests
import threading
import time
import os
import logging
from collections import OrderedDict
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ==================== НАСТРОЙКИ ====================
SOURCES = [
    ("https://iptv-org.github.io/iptv/countries/ru.m3u", 100),
    ("https://iptv-org.github.io/iptv/countries/ru_general.m3u", 95),
    ("https://m3u.su/m3u/sng.m3u", 90),
    ("https://m3u.su/m3u/world.m3u", 85),
    ("https://raw.githubusercontent.com/iptv-org/iptv/master/channels.m3u", 80),
    ("https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u", 75),
    ("https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u", 70),
    ("https://webarmen.com/my/iptv/auto.nogeo.m3u", 65),
    ("https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u", 60),
    ("https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u", 55),
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

playlist_cache = "#EXTM3U\n# IPTV Aggregator Pro by Ivan\n"
cache_timestamp = 0
stats = {"total_channels": 0, "last_update": ""}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_one(url, priority):
    try:
        r = requests.get(url, timeout=25, headers=HEADERS)
        if r.status_code != 200:
            return []
        return parse_m3u(r.text, priority)
    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
        return []


def parse_m3u(content, priority):
    channels = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            inf = line
            name = line.split(',')[-1].strip() if ',' in line else "Unknown"
            i += 1
            if i < len(lines) and lines[i].strip().startswith("http"):
                url = lines[i].strip()
                channels.append({"inf": inf, "url": url, "priority": priority, "name": name})
        i += 1
    return channels


def update_cache():
    global playlist_cache, cache_timestamp, stats
    seen = OrderedDict()
    
    for url, prio in SOURCES:
        for ch in fetch_one(url, prio):
            key = ch["url"]
            if key not in seen or ch["priority"] > seen[key].get("priority", 0):
                seen[key] = ch

    lines = [
        "#EXTM3U",
        f"# IPTV Aggregator Pro • {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"# Total channels: {len(seen)}"
    ]
    for ch in seen.values():
        lines.append(ch["inf"])
        lines.append(ch["url"])

    playlist_cache = "\n".join(lines)
    cache_timestamp = time.time()
    stats["total_channels"] = len(seen)
    stats["last_update"] = time.strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"✅ Updated cache: {len(seen)} channels")


def background_updater():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Updater error: {e}")
        time.sleep(1800)  # 30 минут


@app.route('/')
def home():
    return render_template_string('''
    <h1>IPTV Aggregator Pro</h1>
    <p><strong>Каналов в плейлисте:</strong> {{ total }}</p>
    <p><strong>Последнее обновление:</strong> {{ last_update }}</p>
    <hr>
    <p><a href="/playlist.m3u" style="font-size: 20px">📥 Скачать плейлист</a></p>
    <p><a href="/health">Health Check</a></p>
    ''', total=stats["total_channels"], last_update=stats["last_update"])


@app.route('/playlist.m3u')
def get_playlist():
    if time.time() - cache_timestamp > 3600:
        threading.Thread(target=update_cache, daemon=True).start()
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')


@app.route('/health')
def health():
    return {"status": "running", "channels": stats["total_channels"], "last_update": stats["last_update"]}


if __name__ == '__main__':
    logger.info("🚀 Starting IPTV Aggregator Pro...")
    threading.Thread(target=background_updater, daemon=True).start()
    time.sleep(10)  # время на первое обновление
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
