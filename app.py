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

# ==================== МОЩНЫЕ SOURCES ====================
SOURCES = [ ... ]  # ← вставь список выше

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

playlist_cache = "#EXTM3U\n# IPTV Aggregator Pro — Максимальная версия\n"
cache_timestamp = 0
stats = {"total_channels": 0, "last_update": ""}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# (остальной код оставь как есть из предыдущей версии)

def fetch_one(url, priority):
    try:
        r = requests.get(url, timeout=30, headers=HEADERS)
        if r.status_code != 200:
            return []
        return parse_m3u(r.text, priority)
    except Exception as e:
        logger.warning(f"Error {url}: {e}")
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
                channels.append({"inf": inf, "url": url, "priority": priority})
        i += 1
    return channels

# update_cache, background_updater, routes — оставь как в последней версии

if __name__ == '__main__':
    logger.info("🚀 Starting Powerful IPTV Aggregator...")
    threading.Thread(target=background_updater, daemon=True).start()
    time.sleep(12)
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
