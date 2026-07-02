import os
import re
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime
from flask import Flask, Response, jsonify, request, render_template_string
import requests
import psutil

# ==================== ИСТОЧНИКИ ====================
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
]

HEADERS = {'User-Agent': 'Mozilla/5.0'}
CHECK_TIMEOUT = 2
MAX_WORKERS = 20
UPDATE_INTERVAL = 3600

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
            match = re.search(r'#EXTINF:-?\d+(.*),(.+)', line)
            if match:
                attrs_str = match.group(1)
                name = match.group(2).strip()
                attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', attrs_str))
                current = {'name': name, 'attrs': attrs, 'url': None, 'is_alive': True}  # Считаем живым по умолчанию
        elif current and line.startswith('http'):
            current['url'] = line.split()[0]
            if 'group-title' not in current['attrs']:
                current['attrs']['group-title'] = get_category(current['name'])
            channels.append(current)
            current = None
    return channels

def get_category(name):
    name_lower = name.lower()
    if any(k in name_lower for k in ['новости', 'news', '24', 'vesti']): return 'Новости'
    elif any(k in name_lower for k in ['кино', 'movie', 'film']): return 'Кино'
    elif any(k in name_lower for k in ['музыка', 'music']): return 'Музыка'
    elif any(k in name_lower for k in ['спорт', 'sport']): return 'Спорт'
    elif any(k in name_lower for k in ['дет', 'kids', 'мульт']): return 'Детские'
    else: return 'Общие'

def check_single(ch):
    try:
        r = requests.head(ch['url'], timeout=CHECK_TIMEOUT, headers=HEADERS)
        ch['is_alive'] = r.status_code < 400
    except:
        ch['is_alive'] = False
    return ch

def update_playlist():
    global global_channels, stats_cache
    
    while True:
        try:
            start = time.time()
            logger.info("🔄 Начало обновления...")
            
            all_ch = []
            for url in SOURCES:
                try:
                    r = requests.get(url, timeout=15, headers=HEADERS)
                    if r.status_code == 200:
                        all_ch.extend(parse_m3u(r.text))
                except Exception as e:
                    logger.error(f"Ошибка {url[:40]}: {e}")
            
            # Дедупликация
            seen = {}
            for ch in all_ch:
                key = ch['attrs'].get('tvg-id') or ch['attrs'].get('tvg-name') or ch['url']
                if key and key not in seen:
                    seen[key] = ch
            
            unique = list(seen.values())
            logger.info(f"✅ Загружено {len(unique)} каналов")
            
            # Быстрая проверка только первых 200
            logger.info("🔍 Проверка каналов...")
            sample = unique[:200]
            alive_count = 0
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                results = list(ex.map(check_single, sample))
                alive_count = sum(1 for ch in results if ch.get('is_alive'))
            
            logger.info(f"🟢 Живых: {alive_count}/{len(sample)}")
            
            # Сортировка: сначала с логотипами и HD
            unique.sort(key=lambda x: (1 if x.get('attrs', {}).get('tvg-logo') else 0) + \
                               (1 if 'hd' in x['name'].lower() else 0), reverse=True)
            
            # Ограничиваем 2000 каналами
            final = unique[:2000]
            
            # Категории
            cats = set(ch.get('attrs', {}).get('group-title', 'Другое') for ch in final)
            
            with state_lock:
                global_channels = final
                stats_cache = {
                    "total": len(unique),
                    "alive": alive_count,
                    "categories": len(cats),
                    "last_update": datetime.now().strftime("%H:%M"),
                    "memory": round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1),
                    "sources": len(SOURCES)
                }
            
            logger.info(f"✨ Готово! {len(final)} каналов, {len(cats)} категорий")
            
        except Exception as e:
            logger.error(f"❌ Ошибка обновления: {e}")
        
        time.sleep(UPDATE_INTERVAL)

# Запуск обновления
threading.Thread(target=update_playlist, daemon=True).start()
time.sleep(3)  # Ждём первую загрузку

# ==================== HTML ====================
HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>🇷🇺 IPTV</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
body{background:#0d1117;color:#c9d1d9;font-family:system-ui,sans-serif}
.card{background:#161b22;border-color:#30363d}
.stat{font-size:2rem;font-weight:bold}
.alive{border-left:4px solid #2ea043}.dead{border-left:4px solid #da3633;opacity:.6}
.ch-list{max-height:70vh;overflow-y:auto}
.ch-item{padding:.75rem;border-bottom:1px solid #30363d;cursor:pointer}
.ch-item:hover{background:#21262d}
.logo{width:50px;height:28px;object-fit:contain;background:#21262d;border-radius:3px;margin-right:10px}
</style></head><body>
<nav class="navbar navbar-dark border-bottom border-secondary"><div class="container">
<a class="navbar-brand" href="#">🇷🇺 IPTV Pro</a>
<a href="/playlist.m3u" class="btn btn-outline-light btn-sm">📥 M3U</a>
</div></nav>
<div class="container py-4">
<div class="row g-3 mb-4">
<div class="col-md-3 col-6"><div class="card text-center p-3"><div class="stat text-info" id="total">0</div><div>Всего</div></div></div>
<div class="col-md-3 col-6"><div class="card text-center p-3"><div class="stat text-success" id="alive">0</div><div>Живых</div></div></div>
<div class="col-md-3 col-6"><div class="card text-center p-3"><div class="stat text-warning" id="cats">0</div><div>Категорий</div></div></div>
<div class="col-md-3 col-6"><div class="card text-center p-3"><div class="stat text-primary" id="time">--:--</div><div>Обновлено</div></div></div>
</div>
<div class="card mb-3"><div class="card-body">
<input type="text" id="search" class="form-control bg-dark text-light border-secondary mb-2" placeholder="🔍 Поиск..." oninput="filter()">
<select id="cat" class="form-select bg-dark text-light border-secondary mb-2" onchange="filter()"><option value="">Все категории</option></select>
<button class="btn btn-sm btn-outline-primary" onclick="refresh()">🔄 Обновить</button>
<span class="ms-2 text-muted" id="cnt">0</span>
</div></div>
<div class="card"><div class="card-header">Каналы <span class="badge bg-secondary" id="count">0</span></div>
<div class="ch-list" id="list"><div class="text-center p-4">Загрузка...</div></div></div>
</div>
<script>
let chs=[],filt=[];
async function load(){
    const r=await fetch('/api/stats'),s=await r.json();
    document.getElementById('total').textContent=s.total;
    document.getElementById('alive').textContent=s.alive;
    document.getElementById('cats').textContent=s.categories;
    document.getElementById('time').textContent=s.last_update||'--:--';
}
async function loadCh(){
    const r=await fetch('/api/channels');
    chs=await r.json();
    console.log('Channels:',chs.length);
    if(!chs.length){
        document.getElementById('list').innerHTML='<div class="text-center p-4 text-warning">⌛ Каналы загружаются... Подождите 10-20 секунд</div>';
        setTimeout(loadCh,5000);
        return;
    }
    const cats=[...new Set(chs.map(c=>c.attrs?.['group-title']||'Другое'))].sort();
    const sel=document.getElementById('cat');
    sel.innerHTML='<option value="">Все категории</option>'+cats.map(c=>`<option value="${c.toLowerCase()}">${c}</option>`).join('');
    filter();
}
function filter(){
    const s=document.getElementById('search').value.toLowerCase();
    const c=document.getElementById('cat').value;
    filt=chs.filter(ch=>{
        const n=(ch.name+' '+(ch.attrs?.['tvg-name']||'')).toLowerCase();
        const g=(ch.attrs?.['group-title']||'').toLowerCase();
        return (!s||n.includes(s))&&(!c||g.includes(c));
    });
    render();
    document.getElementById('cnt').textContent=filt.length+' каналов';
    document.getElementById('count').textContent=filt.length;
}
function render(){
    const lst=document.getElementById('list');
    if(!filt.length){lst.innerHTML='<div class="text-center p-4 text-muted">Не найдено</div>';return;}
    lst.innerHTML=filt.slice(0,500).map(ch=>{
        const logo=ch.attrs?.['tvg-logo']||'https://via.placeholder.com/50x28/21262d/764ba2?text=TV';
        return '<div class="ch-item '+(ch.is_alive?'alive':'dead')+'" onclick="copy(\''+ch.url+'\')"><div class="d-flex align-items-center">'+
            '<img src="'+logo+'" class="logo" onerror="this.src=\'https://via.placeholder.com/50x28/21262d/764ba2?text=TV\'">'+
            '<div class="flex-grow-1"><strong>'+ch.name+'</strong><small class="text-muted d-block">'+(ch.attrs?.['group-title']||'')+'</small></div>'+
            '<i class="bi '+(ch.is_alive?'bi-check-circle-fill text-success':'bi-x-circle-fill text-danger')+'"></i></div></div>';
    }).join('');
}
function copy(url){navigator.clipboard.writeText(url);alert('URL скопирован!');}
function refresh(){fetch('/api/refresh',{method:'POST'});setTimeout(()=>{load();loadCh();},3000);}
load();loadCh();setInterval(load,30000);
</script></body></html>"""

@app.route('/')
def home(): return render_template_string(HTML)

@app.route('/api/stats')
def api_stats():
    with state_lock: return jsonify(stats_cache)

@app.route('/api/channels')
def api_channels():
    with state_lock: return jsonify(global_channels)

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    threading.Thread(target=update_playlist, daemon=True).start()
    return jsonify({'status':'ok'})

@app.route('/playlist.m3u')
def playlist():
    with state_lock: chs = global_channels.copy()
    lines = ['#EXTM3U', f'# IPTV Pro - {datetime.now().strftime("%Y-%m-%d %H:%M")}']
    for ch in chs:
        attr = ' '.join(f'{k}="{v}"' for k,v in ch['attrs'].items() if v)
        lines.append(f"#EXTINF:-1 {attr},{ch['name']}")
        lines.append(ch['url'])
    return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl')

@app.route('/health')
def health(): return jsonify({'ok':True,'channels':len(global_channels)})

if __name__ == '__main__':
    logger.info("🚀 Запуск...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
