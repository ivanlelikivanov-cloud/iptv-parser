import os
import re
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from flask import Flask, Response, jsonify, request, render_template_string
import requests
import psutil

# ==========================================
# КОНФИГУРАЦИЯ
# ==========================================
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/countries/ru_general.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/world.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/channels.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

UPDATE_INTERVAL = int(os.environ.get('UPDATE_INTERVAL', 1800))
MAX_WORKERS_FETCH = 6
MAX_CHANNELS_TO_CHECK = int(os.environ.get('MAX_CHANNELS_TO_CHECK', 300))

app = Flask(__name__)
state_lock = threading.Lock()

global_channels = []
stats_cache = {
    "total_channels": 0,
    "alive_channels": 0,
    "last_update": "Запуск...",
    "update_duration": 0,
    "memory_usage_mb": 0
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# ПАРСИНГ И ДЕДУПЛИКАЦИЯ
# ==========================================
def parse_m3u(content):
    channels = []
    lines = content.splitlines()
    current = None
    for line in lines:
        line = line.strip()
        if line.startswith('#EXTINF:'):
            match = re.search(r'#EXTINF:(?P<dur>-?\d+)(?P<attr>.*),(?P<name>.*)', line)
            if match:
                attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', match.group('attr')))
                current = {
                    'duration': match.group('dur'),
                    'name': match.group('name').strip(),
                    'attrs': attrs,
                    'url': None
                }
        elif current and line.startswith('http'):
            current['url'] = line
            channels.append(current)
            current = None
    return channels

def deduplicate_channels(channels):
    seen = {}
    for ch in channels:
        key = ch['attrs'].get('tvg-id') or ch['attrs'].get('tvg-name') or ch['url']
        if key and (key not in seen or ch.get('is_alive')):
            seen[key] = ch
    return list(seen.values())

# ==========================================
# HEALTH CHECK (облегчённый)
# ==========================================
def check_stream_health(channels):
    alive = []
    def check(ch):
        try:
            r = requests.get(ch['url'], stream=True, timeout=3, headers=HEADERS)
            if r.status_code in (200, 206, 301, 302):
                ch['is_alive'] = True
                return ch
        except:
            pass
        return None

    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(check, ch) for ch in channels[:MAX_CHANNELS_TO_CHECK]]
        for future in as_completed(futures):
            result = future.result()
            if result:
                alive.append(result)
    return alive

# ==========================================
# ФОНОВЫЙ ОБНОВЛЯТОР
# ==========================================
def background_updater():
    global global_channels, stats_cache
    while True:
        start = time.time()
        try:
            all_channels = []
            for url in SOURCES:
                try:
                    r = requests.get(url, timeout=20, headers=HEADERS)
                    if r.status_code == 200:
                        all_channels.extend(parse_m3u(r.text))
                except:
                    continue

            unique = deduplicate_channels(all_channels)
            alive = check_stream_health(unique)

            with state_lock:
                global_channels = alive + [ch for ch in unique if ch not in alive][:800]
                stats_cache.update({
                    "total_channels": len(unique),
                    "alive_channels": len(alive),
                    "last_update": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "update_duration": round(time.time() - start, 1),
                    "memory_usage_mb": round(psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024, 1)
                })
            logger.info(f"Обновлено: {len(unique)} каналов, живых: {len(alive)}")
        except Exception as e:
            logger.error(f"Updater error: {e}")
        
        time.sleep(UPDATE_INTERVAL)

# ==========================================
# ЗАПУСК
# ==========================================
threading.Thread(target=background_updater, daemon=True).start()

# ==========================================
# РОУТЫ
# ==========================================
@app.route('/')
def dashboard():
    with state_lock:
        stats = stats_cache.copy()
    return render_template_string(DASHBOARD_HTML, stats=stats)  # используй свой HTML

@app.route('/playlist.m3u')
def get_playlist():
    with state_lock:
        channels = global_channels[:1500]  # лимит для стабильности
    
    lines = ["#EXTM3U"]
    for ch in channels:
        attrs = " ".join([f'{k}="{v}"' for k,v in ch['attrs'].items() if v])
        lines.append(f"#EXTINF:{ch['duration']} {attrs},{ch['name']}")
        lines.append(ch['url'])
    
    return Response("\n".join(lines), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
