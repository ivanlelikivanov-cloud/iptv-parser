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

# ==================== ТОЛЬКО РУССКИЕ ИСТОЧНИКИ ====================
SOURCES = [
    # IPTV-ORG — РФ регионы
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
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    
    # Community
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
CHECK_TIMEOUT = 3
MAX_WORKERS = 30
ALIVE_LIMIT = 500
UPDATE_INTERVAL = 1800

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('iptv.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
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
        if not line:
            continue
        if line.startswith('#EXTINF:'):
            match = re.search(r'#EXTINF:(?P<dur>-?\d+)(?P<attr>.*),(?P<name>.*)', line)
            if match:
                attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', match.group('attr')))
                attrs.update(dict(re.findall(r'([a-zA-Z0-9-]+)=(\S+)', match.group('attr'))))
                current = {
                    'name': match.group('name').strip(),
                    'attrs': attrs,
                    'url': None,
                    'is_alive': False,
                    'latency_ms': None
                }
        elif current and line.startswith('http'):
            current['url'] = line.split()[0]
            # Если нет категории, пробуем определить из названия
            if 'group-title' not in current['attrs']:
                current['attrs']['group-title'] = categorize_channel(current['name'])
            channels.append(current)
            current = None
    return channels

def categorize_channel(name):
    """Автоматическая категоризация канала по названию"""
    name_lower = name.lower()
    
    if any(kw in name_lower for kw in ['новости', 'news', 'информ', '24', 'vesti']):
        return 'Новости'
    elif any(kw in name_lower for kw in ['кино', 'movie', 'film', 'сериал', 'кинопоказ']):
        return 'Кино'
    elif any(kw in name_lower for kw in ['музыка', 'music', 'хит', 'radio', 'клип']):
        return 'Музыка'
    elif any(kw in name_lower for kw in ['спорт', 'sport', 'футбол', 'хоккей']):
        return 'Спорт'
    elif any(kw in name_lower for kw in ['дет', 'kids', 'детский', 'мульт', 'cartoon']):
        return 'Детские'
    elif any(kw in name_lower for kw in ['докум', 'doc', 'познав', 'nature', 'animal']):
        return 'Документальные'
    elif any(kw in name_lower for kw in ['развлек', 'entertain', 'юмор', 'comedy', 'тнт', 'стс']):
        return 'Развлекательные'
    elif any(kw in name_lower for kw in ['кухня', 'еда', 'food', 'cook', 'охота', 'рыбалка']):
        return 'Досуг'
    elif any(kw in name_lower for kw in ['авто', 'auto', 'motor', 'drive']):
        return 'Авто'
    else:
        return 'Общие'

# ==================== ПРОВЕРКА КАНАЛА ====================
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
        logger.info(f"🔄 Обновление RU-плейлиста ({len(SOURCES)} источников)...")
        
        all_ch = []
        for url in SOURCES:
            try:
                r = requests.get(url, timeout=20, headers=HEADERS)
                if r.status_code == 200:
                    channels = parse_m3u(r.text)
                    all_ch.extend(channels)
                    logger.debug(f"  +{len(channels)} из {url.split('/')[-1][:40]}")
            except Exception as e:
                logger.error(f"❌ {url[:50]}: {e}")
        
        logger.info(f"📊 Загружено каналов: {len(all_ch)}")
        
        # Дедупликация
        seen = {}
        for ch in all_ch:
            key = ch['attrs'].get('tvg-id') or ch['attrs'].get('tvg-name') or ch['url']
            if key not in seen:
                seen[key] = ch
            elif not seen[key].get('attrs', {}).get('tvg-logo') and ch.get('attrs', {}).get('tvg-logo'):
                seen[key] = ch
        
        unique = list(seen.values())
        logger.info(f"✅ Уникальных: {len(unique)}")
        
        # Проверка живости
        sample = unique[:800] if len(unique) > 800 else unique
        logger.info(f"🔍 Проверка {len(sample)} каналов...")
        
        alive = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            results = list(ex.map(check_channel, sample))
            alive = [ch for ch in results if ch and ch.get('is_alive')]
        
        logger.info(f"🟢 Живых: {len(alive)}")
        
        # Сортировка
        def score(ch):
            s = 0
            if ch.get('is_alive'): s += 1000
            lat = ch.get('latency_ms', 9999)
            if lat < 200: s += 500
            elif lat < 500: s += 200
            if ch.get('attrs', {}).get('tvg-logo'): s += 50
            if 'hd' in ch.get('name', '').lower(): s += 30
            if '4k' in ch.get('name', '').lower(): s += 60
            return s
        
        sorted_ch = sorted(unique, key=score, reverse=True)
        final = [ch for ch in sorted_ch if ch.get('is_alive')][:ALIVE_LIMIT] + \
                [ch for ch in sorted_ch if not ch.get('is_alive')][:2000]
        
        # Категории
        cats = set()
        for ch in final:
            group = ch.get('attrs', {}).get('group-title', 'Другое')
            if group:
                cats.add(group)
        
        with state_lock:
            global_channels = final
            stats_cache = {
                "total": len(unique),
                "alive": len(alive),
                "categories": len(cats),
                "last_update": datetime.now().strftime("%H:%M:%S"),
                "memory": round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1),
                "sources": len(SOURCES),
                "update_duration": round(time.time() - start, 1)
            }
        
        logger.info(f"✨ Готово за {stats_cache['update_duration']}с | Всего: {stats_cache['total']} | 🟢: {stats_cache['alive']} | Категорий: {stats_cache['categories']} | RAM: {stats_cache['memory']}MB")
        time.sleep(UPDATE_INTERVAL)

threading.Thread(target=update_playlist, daemon=True).start()

# ==================== HTML ====================
HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>🇷🇺 IPTV RU Pro</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
<style>
body{background:#0d1117;color:#c9d1d9;font-family:system-ui,sans-serif}
.card{background:#161b22;border-color:#30363d}
.stat{font-size:2.5rem;font-weight:bold}
.alive{border-left:4px solid #2ea043}.dead{border-left:4px solid #da3633;opacity:.7}
.ch-list{max-height:70vh;overflow-y:auto}
.ch-item{padding:1rem;border-bottom:1px solid #30363d;cursor:pointer;transition:.2s}
.ch-item:hover{background:#21262d}
.badge-4k{background:linear-gradient(135deg,#667eea,#764ba2)}.badge-hd{background:linear-gradient(135deg,#f093fb,#f5576c)}
.logo{width:60px;height:34px;object-fit:contain;background:#21262d;border-radius:4px}
</style></head><body>
<nav class="navbar navbar-dark border-bottom border-secondary"><div class="container">
<a class="navbar-brand" href="#">🇷🇺 IPTV RU Pro <span class="badge bg-success">v3.1</span></a>
<div class="navbar-nav ms-auto">
<a class="nav-link" href="/playlist.m3u"><i class="bi bi-download"></i> M3U</a>
<a class="nav-link" href="#" onclick="refresh()"><i class="bi bi-arrow-clockwise"></i> Обновить</a>
</div></div></nav>
<div class="container py-4">
<div class="row g-3 mb-4">
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat text-info" id="total">0</div><div>Всего</div></div></div>
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat text-success" id="alive">0</div><div>Рабочих</div></div></div>
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat text-warning" id="cats">0</div><div>Категорий</div></div></div>
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat" id="mem">0</div><div>RAM MB</div></div></div>
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat text-primary" id="time">--:--</div><div>Обновлено</div></div></div>
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat text-light" id="src">0</div><div>Источников</div></div></div>
</div>
<div class="card mb-3"><div class="card-body">
<input type="text" id="search" class="form-control bg-dark text-light border-secondary mb-2" placeholder="🔍 Поиск канала..." oninput="filter()">
<select id="cat" class="form-select bg-dark text-light border-secondary mb-2" onchange="filter()"><option value="">Все категории</option></select>
<div><button class="btn btn-sm btn-outline-success" onclick="toggleAlive()"><i class="bi bi-toggle-on" id="tgl"></i> Только рабочие</button>
<button class="btn btn-sm btn-outline-primary" onclick="refresh()"><i class="bi bi-arrow-clockwise"></i> Обновить</button>
<span class="ms-2 text-muted" id="cnt">0 каналов</span></div>
</div></div>
<div class="card"><div class="card-header d-flex justify-content-between"><span>📺 Каналы</span><span class="badge bg-secondary" id="count">0</span></div>
<div class="ch-list" id="list"></div></div>
</div>
<script>
let chs=[],filt=[],aliveOnly=false;
async function loadStats(){
    const r=await fetch('/api/stats'),s=await r.json();
    document.getElementById('total').textContent=s.total;
    document.getElementById('alive').textContent=s.alive;
    document.getElementById('cats').textContent=s.categories;
    document.getElementById('mem').textContent=s.memory;
    document.getElementById('time').textContent=s.last_update;
    document.getElementById('src').textContent=s.sources;
}
async function loadCh(){
    document.getElementById('list').innerHTML='<div class="text-center p-4">Загрузка...</div>';
    const r=await fetch('/api/channels');chs=await r.json();
    const cats=[...new Set(chs.map(c=>c.attrs?.['group-title']||'Другое').filter(Boolean))].sort();
    const sel=document.getElementById('cat');sel.innerHTML='<option value="">Все категории</option>';
    cats.forEach(c=>{const o=document.createElement('option');o.value=c.toLowerCase();o.textContent=c;sel.appendChild(o);});
    filter();
}
function filter(){
    const srch=document.getElementById('search').value.toLowerCase();
    const cat=document.getElementById('cat').value;
    filt=chs.filter(c=>{
        const n=(c.name+' '+(c.attrs?.['tvg-name']||'')).toLowerCase();
        const g=(c.attrs?.['group-title']||'Другое').toLowerCase();
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
    if(!filt.length){lst.innerHTML='<div class="text-center p-4 text-muted">Каналы не найдены</div>';return;}
    lst.innerHTML=filt.slice(0,500).map(c=>{
        const logo=c.attrs?.['tvg-logo']||'https://via.placeholder.com/60x34/21262d/764ba2?text=TV';
        const grp=c.attrs?.['group-title']||'Другое';
        const lat=c.latency_ms?'<span class="badge bg-secondary ms-2">'+c.latency_ms+'ms</span>':'';
        const q=c.name.toLowerCase().includes('4k')||c.name.toLowerCase().includes('uhd')?'<span class="badge badge-4k ms-1">4K</span>':
                 c.name.toLowerCase().includes('hd')?'<span class="badge badge-hd ms-1">HD</span>':'';
        return '<div class="ch-item '+(c.is_alive?'alive':'dead')+'" onclick="copy(\''+c.url+'\')"><div class="d-flex align-items-center">'+
            '<img src="'+logo+'" class="logo me-3" onerror="this.src=\'https://via.placeholder.com/60x34/21262d/764ba2?text=TV\'">'+
            '<div class="flex-grow-1"><strong>'+c.name+'</strong><small class="text-muted d-block">'+grp+q+lat+'</small></div>'+
            '<i class="bi '+(c.is_alive?'bi-check-circle-fill text-success':'bi-x-circle-fill text-danger')+' fs-4"></i></div></div>';
    }).join('');
}
function copy(url){navigator.clipboard.writeText(url);const t=document.createElement('div');
t.className='position-fixed bottom-0 end-0 m-3 alert alert-success';t.textContent='✅ URL скопирован!';
document.body.appendChild(t);setTimeout(()=>t.remove(),2000);}
function toggleAlive(){aliveOnly=!aliveOnly;document.getElementById('tgl').className=aliveOnly?'bi bi-toggle-on':'bi bi-toggle-off';filter();}
function refresh(){fetch('/api/refresh',{method:'POST'});setTimeout(()=>{loadStats();loadCh();},2000);}
setInterval(loadStats,30000);loadStats();loadCh();
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
    return jsonify({'status': 'refreshing'})

@app.route('/playlist.m3u')
def playlist():
    search = request.args.get('search', '').lower()
    alive_only = request.args.get('alive', 'false').lower() == 'true'
    with state_lock:
        chs = global_channels.copy()
    filtered = [c for c in chs if (not search or search in c['name'].lower()) and (not alive_only or c.get('is_alive'))]
    lines = ['#EXTM3U', f'# 🇷🇺 IPTV RU Pro', f'# Обновлено: {datetime.now().strftime("%Y-%m-%d %H:%M")}']
    for c in filtered:
        attr = ' '.join(f'{k}="{v}"' for k,v in c['attrs'].items() if v)
        lines.append(f"#EXTINF:-1 {attr},{c['name']}")
        lines.append(c['url'])
    return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl')

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'channels': stats_cache.get('total', 0)})

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("🚀 🇷🇺 IPTV RU Pro запускается...")
    logger.info(f"📡 Источников: {len(SOURCES)}")
    logger.info(f"⚙️ Порт: 10000")
    time.sleep(2)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
