import os, re, time, logging, threading, psutil, requests
from datetime import datetime
from flask import Flask, Response, jsonify, request, render_template_string

# ==================== КОНФИГУРАЦИЯ ====================
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://m3u.su/m3u/sng.m3u"
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
UPDATE_INTERVAL = 3600 # Обновляем раз в час

app = Flask(__name__)
state = {"channels": [], "stats": {}}
state_lock = threading.Lock()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== ЯДРО ====================
def is_ru(ch):
    name = ch.get('name', '').lower()
    group = ch.get('attrs', {}).get('group-title', '').lower()
    return any(kw in name or kw in group for kw in ['россия', 'рус', 'новости', 'кино', 'тнт', 'стс', 'рен', 'звезда', 'мир'])

def parse_m3u(content):
    channels = []
    lines = content.splitlines()
    curr = None
    for line in lines:
        if line.startswith('#EXTINF:'):
            match = re.search(r'#EXTINF:.*,(.*)', line)
            attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', line))
            curr = {'name': match.group(1).strip() if match else "Unknown", 'attrs': attrs}
        elif curr and line.startswith('http'):
            curr['url'] = line.strip()
            if is_ru(curr): channels.append(curr)
            curr = None
    return channels

def background_task():
    global state
    while True:
        all_ch = []
        for url in SOURCES:
            try:
                r = requests.get(url, timeout=15, headers=HEADERS)
                if r.status_code == 200: all_ch.extend(parse_m3u(r.text))
            except: continue
        
        # Уникальные по URL
        unique = {ch['url']: ch for ch in all_ch}.values()
        
        with state_lock:
            state["channels"] = list(unique)
            state["stats"] = {
                "total": len(unique),
                "last": datetime.now().strftime("%H:%M:%S"),
                "mem": round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1)
            }
        time.sleep(UPDATE_INTERVAL)

threading.Thread(target=background_task, daemon=True).start()

# ==================== РОУТЫ ====================
@app.route('/')
def home():
    return render_template_string("<h1>IPTV RU Aggregator</h1><p>Каналов: {{s.total}}</p><p>RAM: {{s.mem}} MB</p><a href='/playlist.m3u'>Скачать M3U</a>", s=state["stats"])

@app.route('/playlist.m3u')
def get_m3u():
    lines = ["#EXTM3U"]
    for ch in state["channels"]:
        attr_str = ' '.join([f'{k}="{v}"' for k,v in ch['attrs'].items()])
        lines.append(f"#EXTINF:-1 {attr_str},{ch['name']}\n{ch['url']}")
    return Response("\n".join(lines), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
