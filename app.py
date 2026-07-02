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

# ==================== КОНФИГУРАЦИЯ ====================
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-northwest.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-volga.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
CHECK_TIMEOUT = 3
MAX_WORKERS = 30  # Уменьшил для стабильности
UPDATE_INTERVAL = 1800

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================
app = Flask(__name__)
state_lock = threading.Lock()
global_channels = []
stats_cache = {"total": 0, "alive": 0, "categories": 0, "last_update": "", "memory": 0, "sources": len(SOURCES)}

# ==================== ПАРСИНГ ====================
def parse_m3u(content):
    channels = []
    current = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('#EXTINF:'):
            match = re.search(r'#EXTINF:(?P<dur>-?\d+)(?P<attr>.*),(?P<name>.*)', line)
            if match:
                attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', match.group('attr')))
                current = {'name': match.group('name').strip(), 'attrs': attrs, 'url': None, 'is_alive': False, 'latency_ms': None}
        elif current and line.startswith('http'):
            current['url'] = line.split()[0]
            channels.append(current)
            current = None
    return channels

# ==================== ПРОВЕРКА КАНАЛА (синхронная) ====================
def check_channel(channel):
    url = channel.get('url')
    if not url:
        return None
    try:
        start = time.time()
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers=HEADERS, allow_redirects=True)
        latency = (time.time() - start) * 1000
        if r.status_code < 400:
            channel['is_alive'] = True
            channel['latency_ms'] = round(latency, 1)
            return channel
    except:
        pass
    channel['is_alive'] = False
    return None

# ==================== ОБНОВЛЕНИЕ ====================
def update_playlist():
    global global_channels, stats_cache
    while True:
        start = time.time()
        logger.info(f"🔄 Обновление ({len(SOURCES)} источников)...")
        
        all_ch = []
        for url in SOURCES:
            try:
                r = requests.get(url, timeout=20, headers=HEADERS)
                if r.status_code == 200:
                    all_ch.extend(parse_m3u(r.text))
            except Exception as e:
                logger.error(f"❌ {url[:50]}: {e}")
        
        # Дедупликация
        seen = {}
        for ch in all_ch:
            key = ch['attrs'].get('tvg-id') or ch['attrs'].get('tvg-name') or ch['url']
            if key not in seen:
                seen[key] = ch
        unique = list(seen.values())
        logger.info(f"✅ Уникальных: {len(unique)}")
        
        # Проверка живых ( ThreadPoolExecutor)
        logger.info(f"🔍 Проверка {min(500, len(unique))} каналов...")
        alive = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            results = list(ex.map(check_channel, unique[:500]))
            alive = [ch for ch in results if ch and ch.get('is_alive')]
        
        logger.info(f"🟢 Живых: {len(alive)}")
        
        # Сортировка
        def score(ch):
            s = 0
            if ch.get('is_alive'): s += 1000
            if ch.get('latency_ms', 9999) < 500: s += 200
            if ch.get('attrs', {}).get('tvg-logo'): s += 50
            if 'hd' in ch.get('name', '').lower(): s += 20
            return s
        
        sorted_ch = sorted(unique, key=score, reverse=True)
        final = [ch for ch in sorted_ch if ch.get('is_alive')][:500] + [ch for ch in sorted_ch if not ch.get('is_alive')][:2000]
        
        # Категории
        categories = set(ch.get('attrs', {}).get('group-title') for ch in final if ch.get('attrs', {}).get('group-title'))
        
        with state_lock:
            global_channels = final
            stats_cache = {
                "total": len(unique),
                "alive": len(alive),
                "categories": len(categories),
                "last_update": datetime.now().strftime("%H:%M:%S"),
                "memory": round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1),
                "sources": len(SOURCES),
                "update_duration": round(time.time() - start, 1)
            }
        
        logger.info(f"✨ Готово за {stats_cache['update_duration']}с | RAM: {stats_cache['memory']}MB")
        time.sleep(UPDATE_INTERVAL)

threading.Thread(target=update_playlist, daemon=True).start()

# ==================== HTML ====================
HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>IPTV Pro</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>body{background:#0d1117;color:#c9d1d9} .card{background:#161b22;border-color:#30363d}
.stat{font-size:2.5rem;font-weight:bold} .alive{border-left:4px solid #2ea043} .dead{border-left:4px solid #da3633}
.ch-list{max-height:70vh;overflow-y:auto} .ch-item{padding:1rem;border-bottom:1px solid #30363d;cursor:pointer}
.ch-item:hover{background:#21262d}</style></head><body>
<nav class="navbar navbar-dark border-bottom border-secondary"><div class="container">
<a class="navbar-brand" href="#">📺 IPTV Pro</a>
<a href="/playlist.m3u" class="btn btn-outline-light btn-sm"><i class="bi bi-download"></i> M3U</a>
</div></nav>
<div class="container py-4">
<div class="row g-3 mb-4">
<div class="col-md-2"><div class="card text-center p-3"><div class="stat text-info" id="total">0</div><div>Всего</div></div></div>
<div class="col-md-2"><div class="card text-center p-3"><div class="stat text-success" id="alive">0</div><div>Живых</div></div></div>
<div class="col-md-2"><div class="card text-center p-3"><div class="stat text-warning" id="cats">0</div><div>Категорий</div></div></div>
<div class="col-md-2"><div class="card text-center p-3"><div class="stat" id="mem">0</div><div>RAM MB</div></div></div>
<div class="col-md-2"><div class="card text-center p-3"><div class="stat text-primary" id="time">--:--</div><div>Обновлено</div></div></div>
<div class="col-md-2"><div class="card text-center p-3"><div class="stat text-light" id="src">0</div><div>Источников</div></div></div>
</div>
<div class="card mb-3"><div class="card-body">
<input type="text" id="search" class="form-control bg-dark text-light border-secondary mb-2" placeholder="🔍 Поиск..." oninput="filter()">
<select id="cat" class="form-select bg-dark text-light border-secondary mb-2" onchange="filter()"><option value="">Все категории</option></select>
<button class="btn btn-sm btn-outline-success" onclick="toggleAlive()"><i class="bi bi-toggle-on" id="tgl"></i> Только рабочие</button>
<button class="btn btn-sm btn-outline-primary" onclick="refresh()"><i class="bi bi-arrow-clockwise"></i> Обновить</button>
<span class="ms-2 text-muted" id="cnt">0</span>
</div></div>
<div class="card"><div class="card-header">Каналы <span class="badge bg-secondary" id="count">0</span></div>
<div class="ch-list" id="list"></div></div>
</div>
<script>
let chs=[],filt=[],aliveOnly=false;
async function load(){
    const r=await fetch('/api/stats'); const s=await r.json();
    document.getElementById('total').textContent=s.total;
    document.getElementById('alive').textContent=s.alive;
    document.getElementById('cats').textContent=s.categories;
    document.getElementById('mem').textContent=s.memory;
    document.getElementById('time').textContent=s.last_update;
    document.getElementById('src').textContent=s.sources;
}
async function loadCh(){
    const r=await fetch('/api/channels'); chs=await r.json();
    const cats=[...new Set(chs.map(c=>c.attrs?.['group-title']||'Other').filter(Boolean))].sort();
    const sel=document.getElementById('cat'); sel.innerHTML='<option value="">Все категории</option>';
    cats.forEach(c=>{const o=document.createElement('option');o.value=c.toLowerCase();o.textContent=c;sel.appendChild(o);});
    filter();
}
function filter(){
    const srch=document.getElementById('search').value.toLowerCase();
    const cat=document.getElementById('cat').value;
    filt=chs.filter(c=>{
        const n=(c.name+' '+(c.attrs?.['tvg-name']||'')).toLowerCase();
        const g=(c.attrs?.['group-title']||'').toLowerCase();
        if(srch&&!n.includes(srch))return false;
        if(cat&&!g.includes(cat))return false;
        if(aliveOnly&&!c.is_alive)return false;
        return true;
    });
    render();
    document.getElementById('cnt').textContent=filt.length+' каналов';
    document.getElementById('count').textContent=filt.length;
}
function render(){
    const lst=document.getElementById('list');
    lst.innerHTML=filt.slice(0,500).map(c=>{
        const logo=c.attrs?.['tvg-logo']||'https://via.placeholder.com/60x34/21262d/764ba2?text=TV';
        const grp=c.attrs?.['group-title']||'Other';
        const lat=c.latency_ms?'<span class="badge bg-secondary ms-2">'+c.latency_ms+'ms</span>':'';
        return '<div class="ch-item '+(c.is_alive?'alive':'dead')+'" onclick="copy(\''+c.url+'\')"><div class="d-flex align-items-center">'+
            '<img src="'+logo+'" class="rounded me-3" width="60" height="34" style="object-fit:contain;background:#21262d">'+
            '<div class="flex-grow-1"><strong>'+c.name+'</strong><small class="text-muted d-block">'+grp+lat+'</small></div>'+
            '<i class="bi '+(c.is_alive?'bi-check-circle-fill text-success':'bi-x-circle-fill text-danger')+' fs-4"></i></div></div>';
    }).join('');
}
function copy(url){navigator.clipboard.writeText(url);alert('URL скопирован!');}
function toggleAlive(){aliveOnly=!aliveOnly;document.getElementById('tgl').className=aliveOnly?'bi bi-toggle-on':'bi bi-toggle-off';filter();}
function refresh(){fetch('/api/refresh',{method:'POST'});setTimeout(()=>{load();loadCh();},2000);}
setInterval(load,30000);
load();loadCh();
</script></body></html>"""

# ==================== ROUTES ====================
@app.route('/')
def home():
    return render_template_string(HTML)

@app.route('/api/stats')
def api_stats():
    with state_lock:
        return jsonify(stats_cache)

@app.route('/api/channels')
def api_channels():
    with state_lock:
        return jsonify(global_channels)

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    threading.Thread(target=update_playlist, daemon=True).start()
    return jsonify({'status': 'ok'})

@app.route('/playlist.m3u')
def playlist():
    search = request.args.get('search', '').lower()
    alive_only = request.args.get('alive', 'false').lower() == 'true'
    with state_lock:
        chs = global_channels.copy()
    filtered = [c for c in chs if (not search or search in c['name'].lower()) and (not alive_only or c.get('is_alive'))]
    lines = ['#EXTM3U', f'# IPTV Pro - {datetime.now().strftime("%Y-%m-%d %H:%M")}']
    for c in filtered:
        attr = ' '.join(f'{k}="{v}"' for k,v in c['attrs'].items() if v)
        lines.append(f"#EXTINF:-1 {attr},{c['name']}")
        lines.append(c['url'])
    return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl')

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'channels': stats_cache.get('total', 0)})

if __name__ == '__main__':
    logger.info("🚀 IPTV Pro запускается...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
