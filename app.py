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
    # Основные + Региональные Россия (часовые пояса)
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/countries/ru_general.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    
    # Часовые пояса России
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",      # Москва (MSK)
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",      # Санкт-Петербург
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",     # Урал (+2..+3)
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",      # Сибирь
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u", # Дальний Восток
    "https://iptv-org.github.io/iptv/regions/ru-northwest.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-volga.m3u",

    # Дополнительные сильные источники
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/world.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/channels.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/tkashkin/iptv/master/ru.m3u",
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

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
# ПАРСИНГ
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
        key = ch['attrs'].get('tvg-id') or ch['attrs'].get('tvg-name') or ch.get('url')
        if key and key not in seen:
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

    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [executor.submit(check, ch) for ch in channels[:400]]
        for future in as_completed(futures):
            res = future.result()
            if res:
                alive.append(res)
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
                global_channels = alive + unique[:1200]
                stats_cache.update({
                    "total_channels": len(unique),
                    "alive_channels": len(alive),
                    "last_update": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "update_duration": round(time.time() - start, 1),
                    "memory_usage_mb": round(psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024, 1)
                })
            logger.info(f"Обновлено: {len(unique)} каналов | Живых: {len(alive)}")
        except Exception as e:
            logger.error(f"Ошибка обновления: {e}")
        
        time.sleep(1800)  # 30 минут

# Запуск обновления
threading.Thread(target=background_updater, daemon=True).start()

# ==========================================
# ДАШБОРД
# ==========================================
@app.route('/')
def dashboard():
    with state_lock:
        stats = stats_cache.copy()
    html = f"""
    <h1>IPTV Aggregator Pro</h1>
    <p><strong>Всего каналов:</strong> {stats['total_channels']}</p>
    <p><strong>Живых стримов:</strong> {stats['alive_channels']}</p>
    <p><strong>Последнее обновление:</strong> {stats['last_update']}</p>
    <hr>
    <a href="/playlist.m3u" style="font-size:20px">📥 Скачать плейлист</a>
    """
    return html

@app.route('/playlist.m3u')
def get_playlist():
    with state_lock:
        channels = global_channels[:1500]
    
    lines = ["#EXTM3U"]
    for ch in channels:
        attrs_str = " ".join([f'{k}="{v}"' for k, v in ch['attrs'].items() if v])
        lines.append(f"#EXTINF:{ch['duration']} {attrs_str},{ch['name']}")
        lines.append(ch['url'])
    
    return Response("\n".join(lines), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
