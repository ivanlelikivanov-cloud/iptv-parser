import os, re, time, logging, threading, psutil, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from flask import Flask, Response, jsonify, request, render_template_string

# ==========================================
# 🚀 ULTIMATE CONFIGURATION
# ==========================================
SOURCES = [
    # Федеральные и общие
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/countries/ru_general.m3u",
    "https://m3u.su/m3u/sng.m3u",
    # Региональные хабы (самая ценная часть)
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u"
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}
app = Flask(__name__)
state_lock = threading.Lock()
global_channels = []
stats_cache = {"total": 0, "alive": 0, "last": "Ожидание...", "mem": 0}

# ==========================================
# ЯДРО ПАРСИНГА
# ==========================================
def parse_m3u(text):
    channels = []
    # Быстрый regex для захвата INF и URL
    items = re.findall(r'(#EXTINF:-?\d+.*?),(.*)\n(http[^\s]+)', text)
    for inf, name, url in items:
        attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', inf))
        channels.append({'name': name.strip(), 'attrs': attrs, 'url': url.strip(), 'is_alive': False})
    return channels

def update_loop():
    global global_channels, stats_cache
    while True:
        start = time.time()
        raw = []
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(requests.get, url, timeout=15, headers=HEADERS) for url in SOURCES]
            for f in as_completed(futures):
                try:
                    r = f.result()
                    if r.status_code == 200: raw.extend(parse_m3u(r.text))
                except: pass
        
        # Мощная дедупликация
        unique = {ch['url']: ch for ch in raw}.values()
        
        # Проверка "живости"
        alive = []
        def check(ch):
            try:
                if requests.head(ch['url'], timeout=3, headers=HEADERS).status_code < 400:
                    ch['is_alive'] = True
                    return ch
            except: pass
            return ch if not ch.get('is_alive') else None

        with ThreadPoolExecutor(max_workers=30) as ex:
            results = list(ex.map(check, list(unique)[:1000]))
            alive = [r for r in results if r]

        with state_lock:
            global_channels = alive
            stats_cache.update({
                "total": len(raw), "alive": len(alive), 
                "last": datetime.now().strftime("%H:%M"),
                "mem": round(psutil.Process(os.getpid()).memory_info().rss/1024**2, 1)
            })
        time.sleep(3600)

threading.Thread(target=update_loop, daemon=True).start()

@app.route('/playlist.m3u')
def get_playlist():
    with state_lock: chs = global_channels
    lines = ["#EXTM3U"]
    for ch in chs:
        attrs = " ".join([f'{k}="{v}"' for k,v in ch['attrs'].items()])
        lines.append(f"#EXTINF:-1 {attrs},{ch['name']}\n{ch['url']}")
    return Response("\n".join(lines), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
