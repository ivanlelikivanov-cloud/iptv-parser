import os
import re
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from flask import Flask, Response, jsonify, request, render_template_string
import requests
import psutil

app = Flask(__name__)
state_lock = threading.Lock()

# ==================== МАКСИМАЛЬНЫЕ ИСТОЧНИКИ (2000+ RU) ====================
SOURCES = [
    # Основные мощные источники
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    
    # Все регионы России (часовые пояса)
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",      # Москва +3
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",      # СПб +3
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",     # Урал +5
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",      # Сибирь +7
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u", # Дальний Восток +10/+11
    "https://iptv-org.github.io/iptv/regions/ru-northwest.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-volga.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-crimea.m3u",

    # Дополнительные крупные сборки
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

global_channels = []
stats_cache = {
    "total": 0,
    "alive": 0,
    "last_update": "Загрузка...",
    "memory": 0
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== ПАРСИНГ + ЧАСОВЫЕ ПОЯСА ====================
def detect_timezone(name):
    name = name.lower()
    if any(x in name for x in ['москва', 'msk', 'мск', 'ostankino']):
        return 'MSK (UTC+3)'
    if any(x in name for x in ['спб', 'питер', 'санкт-петербург']):
        return 'MSK (UTC+3)'
    if any(x in name for x in ['екатеринбург', 'урал', 'ural', 'первоуральск']):
        return 'YEKT (UTC+5)'
    if any(x in name for x in ['новосибирск', 'сибирь', 'siberia', 'омск']):
        return 'NOVT (UTC+7)'
    if any(x in name for x in ['владивосток', 'хабаровск', 'дальний восток']):
        return 'VLAT (UTC+10)'
    return 'MSK (UTC+3)'  # По умолчанию московское время

def parse_m3u(content):
    channels = []
    current = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('#EXTINF:'):
            match = re.search(r'#EXTINF:(?P<dur>-?\d+)(?P<attr>.*),(?P<name>.*)', line)
            if match:
                attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', match.group('attr')))
                current = {
                    'name': match.group('name').strip(),
                    'attrs': attrs,
                    'url': None,
                    'is_alive': False
                }
        elif current and line.startswith('http'):
            current['url'] = line.split()[0]
            if 'group-title' not in current['attrs']:
                current['attrs']['group-title'] = 'Общие'
            current['attrs']['timezone'] = detect_timezone(current['name'])
            channels.append(current)
            current = None
    return channels

# ==================== ОБНОВЛЕНИЕ ====================
def update_playlist():
    global global_channels, stats_cache
    while True:
        start = time.time()
        logger.info("🔄 Загрузка российских каналов...")

        all_ch = []
        for url in SOURCES:
            try:
                r = requests.get(url, timeout=20, headers=HEADERS)
                if r.status_code == 200:
                    all_ch.extend(parse_m3u(r.text))
            except:
                continue

        # Дедупликация
        seen = {}
        for ch in all_ch:
            key = ch['attrs'].get('tvg-id') or ch['attrs'].get('tvg-name') or ch['url']
            if key not in seen:
                seen[key] = ch

        unique = list(seen.values())
        
        # Проверка живости (ограничено)
        sample = unique[:700]
        alive = []
        with ThreadPoolExecutor(max_workers=20) as ex:
            results = list(ex.map(lambda ch: ch if requests.head(ch['url'], timeout=3, headers=HEADERS, allow_redirects=True).status_code < 400 else None, sample))
            alive = [ch for ch in results if ch]

        # Сортировка: живые + московское время в приоритете
        final = sorted(unique, key=lambda x: (
            x.get('is_alive', False),
            x['attrs'].get('timezone', '') == 'MSK (UTC+3)',
            x['name']
        ), reverse=True)[:3000]

        with state_lock:
            global_channels = final
            stats_cache = {
                "total": len(unique),
                "alive": len(alive),
                "last_update": datetime.now().strftime("%H:%M"),
                "memory": round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1)
            }
        
        logger.info(f"✅ Загружено {len(unique)} российских каналов | Живых: {len(alive)}")
        time.sleep(3600)  # Обновление раз в час

# Запуск
threading.Thread(target=update_playlist, daemon=True).start()

# ==================== РОУТЫ ====================
@app.route('/')
def home():
    with state_lock:
        s = stats_cache.copy()
    return f"""
    <h1>🇷🇺 IPTV Россия Pro</h1>
    <p>Всего каналов: <b>{s['total']}</b></p>
    <p>Живых: <b>{s['alive']}</b></p>
    <p>Обновлено: {s['last_update']}</p>
    <a href="/playlist.m3u" style="font-size:22px">📥 Скачать плейлист</a>
    """

@app.route('/playlist.m3u')
def get_playlist():
    with state_lock:
        chs = global_channels.copy()
    
    lines = ["#EXTM3U", "# IPTV Россия Pro — 2000+ каналов"]
    for ch in chs:
        attr = ' '.join(f'{k}="{v}"' for k,v in ch['attrs'].items() if v)
        lines.append(f"#EXTINF:-1 {attr},{ch['name']}")
        lines.append(ch['url'])
    
    return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
