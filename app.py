import os
import re
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from flask import Flask, Response, jsonify, request, render_template_string
import requests
import psutil

# ==================== ИСТОЧНИКИ (МАКСИМУМ КАНАЛОВ) ====================
SOURCES = [
    # IPTV-ORG - Россия
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    
    # ВСЕ РЕГИОНЫ РОССИИ (разные часовые пояса)
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",      # MSK (UTC+3)
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",      # MSK (UTC+3)
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",     # YEKT (UTC+5)
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",      # NOVT (UTC+7)
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u", # VLAT (UTC+10)
    "https://iptv-org.github.io/iptv/regions/ru-northwest.m3u",# MSK (UTC+3)
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",    # MSK (UTC+3)
    "https://iptv-org.github.io/iptv/regions/ru-volga.m3u",    # SAMT (UTC+4)
    "https://iptv-org.github.io/iptv/regions/ru-crimea.m3u",   # MSK (UTC+3)
    
    # КАТЕГОРИИ
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/general.m3u",
    
    # ДОПОЛНИТЕЛЬНЫЕ ИСТОЧНИКИ
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/sat-iptv/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/playlist-for-free/IPTV/main/ru.m3u",
    "https://raw.githubusercontent.com/KissyDK/free-iptv/main/ru.m3u",
    
    # M3U.SU
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
    "https://m3u.su/m3u/ru_deti.m3u",
    "https://m3u.su/m3u/ru_music.m3u",
    "https://m3u.su/m3u/ru_news.m3u",
    
    # ДРУГИЕ
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
CHECK_TIMEOUT = 2
MAX_WORKERS = 30
MAX_CHANNELS = 3000  # Увеличили лимит
UPDATE_INTERVAL = 3600

# ==================== ЧАСОВЫЕ ПОЯСА РОССИИ ====================
TIME_ZONES = {
    'MSK': 'UTC+3 (Москва)',
    'MSK+1': 'UTC+4 (Самара)',
    'YEKT': 'UTC+5 (Екатеринбург)',
    'OMST': 'UTC+6 (Омск)',
    'NOVT': 'UTC+7 (Новосибирск)',
    'KRAT': 'UTC+8 (Красноярск)',
    'IRKT': 'UTC+9 (Иркутск)',
    'YAKT': 'UTC+10 (Якутск)',
    'VLAT': 'UTC+11 (Владивосток)',
    'SRET': 'UTC+12 (Среднеколымск)',
    'PETT': 'UTC+12 (Камчатка)'
}

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================
app = Flask(__name__)
state_lock = threading.Lock()
global_channels = []
stats_cache = {"total": 0, "alive": 0, "categories": 0, "timezones": 0, "last_update": "", "memory": 0}

# ==================== ПАРСИНГ ====================
def parse_m3u(content):
    channels = []
    current = None
    for line in content.splitlines():
        line = line.strip()
        if line.startswith('#EXTINF:'):
            match = re.search(r'#EXTINF:-?\d+\s*(.*),(.+)', line)
            if match:
                attrs_str = match.group(1)
                name = match.group(2).strip()
                attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', attrs_str))
                attrs.update(dict(re.findall(r'([a-zA-Z0-9-]+)=(\S+)', attrs_str)))
                current = {'name': name, 'attrs': attrs, 'url': None, 'is_alive': True}
        elif current and line.startswith('http'):
            current['url'] = line.split()[0]
            
            # Определяем категорию и часовой пояс
            if 'group-title' not in current['attrs']:
                current['attrs']['group-title'] = get_category(current['name'])
            
            # Добавляем часовой пояс если есть в названии
            tz = detect_timezone(current['name'], current['attrs'])
            if tz:
                current['attrs']['tvg-chno'] = tz  # Используем как метку
            
            channels.append(current)
            current = None
    return channels

def get_category(name):
    name_lower = name.lower()
    if any(k in name_lower for k in ['новости', 'news', '24', 'vesti', 'информ']): 
        return 'Новости'
    elif any(k in name_lower for k in ['кино', 'movie', 'film', 'сериал', 'кинопоказ']): 
        return 'Кино'
    elif any(k in name_lower for k in ['музыка', 'music', 'хит', 'radio', 'клип']): 
        return 'Музыка'
    elif any(k in name_lower for k in ['спорт', 'sport', 'футбол', 'хоккей']): 
        return 'Спорт'
    elif any(k in name_lower for k in ['дет', 'kids', 'мульт', 'cartoon', 'ребёнок']): 
        return 'Детские'
    elif any(k in name_lower for k in ['докум', 'doc', 'познав', 'nature']): 
        return 'Документальные'
    elif any(k in name_lower for k in ['развлек', 'entertain', 'юмор', 'comedy']): 
        return 'Развлекательные'
    else: 
        return 'Общие'

def detect_timezone(name, attrs):
    """Определяем часовой пояс по названию канала или атрибутам"""
    name_lower = name.lower()
    group = attrs.get('group-title', '').lower()
    
    # Ищем упоминания городов/регионов
    if any(city in name_lower or city in group for city in ['москва', 'msk', 'moscow', 'спб', 'spb', 'питер']):
        return 'MSK (UTC+3)'
    elif any(city in name_lower or city in group for city in ['самара', 'samara']):
        return 'MSK+1 (UTC+4)'
    elif any(city in name_lower or city in group for city in ['екатеринбург', 'ekb', 'yekaterinburg', 'урал', 'ural']):
        return 'YEKT (UTC+5)'
    elif any(city in name_lower or city in group for city in ['омск', 'omsk']):
        return 'OMST (UTC+6)'
    elif any(city in name_lower or city in group for city in ['новосибирск', 'novosibirsk', 'сибирь', 'siberia', 'sib']):
        return 'NOVT (UTC+7)'
    elif any(city in name_lower or city in group for city in ['красноярск', 'krasnoyarsk']):
        return 'KRAT (UTC+8)'
    elif any(city in name_lower or city in group for city in ['иркутск', 'irkutsk']):
        return 'IRKT (UTC+9)'
    elif any(city in name_lower or city in group for city in ['якутск', 'yakutsk']):
        return 'YAKT (UTC+10)'
    elif any(city in name_lower or city in group for city in ['владивосток', 'vladivostok', 'дальний восток', 'far east']):
        return 'VLAT (UTC+11)'
    elif any(city in name_lower or city in group for city in ['камчатка', 'kamchatka', 'petropavlovsk']):
        return 'PETT (UTC+12)'
    
    return None

def check_single(ch):
    try:
        r = requests.head(ch['url'], timeout=CHECK_TIMEOUT, headers=HEADERS, allow_redirects=True)
        ch['is_alive'] = r.status_code < 400
    except:
        ch['is_alive'] = False
    return ch

def update_playlist():
    global global_channels, stats_cache
    
    while True:
        try:
            start = time.time()
            logger.info(f"🔄 Обновление ({len(SOURCES)} источников)...")
            
            all_ch = []
            for url in SOURCES:
                try:
                    r = requests.get(url, timeout=15, headers=HEADERS)
                    if r.status_code == 200:
                        parsed = parse_m3u(r.text)
                        all_ch.extend(parsed)
                        logger.debug(f"+{len(parsed)} из {url.split('/')[-1][:30]}")
                except Exception as e:
                    logger.error(f"❌ {url[:40]}: {e}")
            
            logger.info(f"📊 Загружено: {len(all_ch)} каналов")
            
            # Дедупликация
            seen = {}
            for ch in all_ch:
                key = ch['attrs'].get('tvg-id') or ch['attrs'].get('tvg-name') or ch['url']
                if key and key not in seen:
                    seen[key] = ch
                elif key and not seen[key].get('attrs', {}).get('tvg-logo') and ch.get('attrs', {}).get('tvg-logo'):
                    seen[key] = ch
            
            unique = list(seen.values())
            logger.info(f"✅ Уникальных: {len(unique)}")
            
            # Проверка живости (первые 500)
            sample = unique[:500] if len(unique) > 500 else unique
            logger.info(f"🔍 Проверка {len(sample)} каналов...")
            
            alive_count = 0
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                results = list(ex.map(check_single, sample))
                alive_count = sum(1 for ch in results if ch.get('is_alive'))
            
            logger.info(f"🟢 Живых: {alive_count}/{len(sample)}")
            
            # Сортировка: с лого → HD → по алфавиту
            unique.sort(key=lambda x: (
                1 if x.get('attrs', {}).get('tvg-logo') else 0,
                1 if 'hd' in x['name'].lower() else 0,
                1 if '4k' in x['name'].lower() else 0
            ), reverse=True)
            
            # Ограничиваем
            final = unique[:MAX_CHANNELS]
            
            # Категории и часовые пояса
            cats = set(ch.get('attrs', {}).get('group-title', 'Другое') for ch in final)
            timezones = set(ch.get('attrs', {}).get('tvg-chno') for ch in final if ch.get('attrs', {}).get('tvg-chno'))
            
            with state_lock:
                global_channels = final
                stats_cache = {
                    "total": len(unique),
                    "alive": alive_count,
                    "categories": len(cats),
                    "timezones": len(timezones),
                    "last_update": datetime.now().strftime("%H:%M"),
                    "memory": round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1)
                }
            
            logger.info(f"✨ Готово! {len(final)} каналов, {len(cats)} категорий, {len(timezones)} часовых поясов")
            
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
        
        time.sleep(UPDATE_INTERVAL)

# Запуск
threading.Thread(target=update_playlist, daemon=True).start()
time.sleep(5)

# ==================== HTML ====================
HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>🇷 IPTV Россия</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
<style>
body{background:#0d1117;color:#c9d1d9;font-family:system-ui,sans-serif}
.card{background:#161b22;border-color:#30363d}
.stat{font-size:2rem;font-weight:bold}
.alive{border-left:4px solid #2ea043}.dead{border-left:4px solid #da3633;opacity:.6}
.ch-list{max-height:70vh;overflow-y:auto}
.ch-item{padding:.75rem;border-bottom:1px solid #30363d;cursor:pointer;transition:.2s}
.ch-item:hover{background:#21262d}
.logo{width:50px;height:28px;object-fit:contain;background:#21262d;border-radius:3px;margin-right:10px}
.tz-badge{font-size:.65rem;margin-left:5px}
</style></head><body>
<nav class="navbar navbar-dark border-bottom border-secondary"><div class="container">
<a class="navbar-brand" href="#">🇷🇺 IPTV Россия <span class="badge bg-success">v4.0</span></a>
<div class="navbar-nav ms-auto">
<a class="nav-link" href="/playlist.m3u">📥 M3U</a>
<a class="nav-link" href="#" onclick="refresh()">🔄</a>
</div></div></nav>
<div class="container py-4">
<div class="row g-3 mb-4">
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat text-info" id="total">0</div><div>Всего</div></div></div>
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat text-success" id="alive">0</div><div>Живых</div></div></div>
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat text-warning" id="cats">0</div><div>Категорий</div></div></div>
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat text-primary" id="tz">0</div><div>Час.поясов</div></div></div>
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat" id="mem">0</div><div>RAM MB</div></div></div>
<div class="col-md-2 col-6"><div class="card text-center p-3"><div class="stat text-light" id="time">--:--</div><div>Обновлено</div></div></div>
</div>
<div class="card mb-3"><div class="card-body">
<input type="text" id="search" class="form-control bg-dark text-light border-secondary mb-2" placeholder="🔍 Поиск канала..." oninput="filter()">
<div class="row g-2">
<div class="col-md-6"><select id="cat" class="form-select bg-dark text-light border-secondary" onchange="filter()"><option value="">Все категории</option></select></div>
<div class="col-md-6"><select id="tzFilter" class="form-select bg-dark text-light border-secondary" onchange="filter()"><option value="">Все часовые пояса</option></select></div>
</div>
<div class="mt-2">
<button class="btn btn-sm btn-outline-success" onclick="toggleAlive()"><i class="bi bi-toggle-on" id="tgl"></i> Только рабочие</button>
<button class="btn btn-sm btn-outline-primary" onclick="refresh()">🔄 Обновить</button>
<span class="ms-2 text-muted" id="cnt">0</span>
</div>
</div></div>
<div class="card"><div class="card-header d-flex justify-content-between"><span>📺 Каналы</span><span class="badge bg-secondary" id="count">0</span></div>
<div class="ch-list" id="list"><div class="text-center p-4">Загрузка...</div></div></div>
</div>
<script>
let chs=[],filt=[],aliveOnly=false;
async function load(){
    const r=await fetch('/api/stats'),s=await r.json();
    document.getElementById('total').textContent=s.total;
    document.getElementById('alive').textContent=s.alive;
    document.getElementById('cats').textContent=s.categories;
    document.getElementById('tz').textContent=s.timezones||0;
    document.getElementById('mem').textContent=s.memory;
    document.getElementById('time').textContent=s.last_update||'--:--';
}
async function loadCh(){
    const r=await fetch('/api/channels');
    chs=await r.json();
    console.log('Loaded:',chs.length);
    if(!chs.length){
        document.getElementById('list').innerHTML='<div class="text-center p-4 text-warning">⌛ Загрузка каналов... Подождите 10-15 сек</div>';
        setTimeout(loadCh,5000);
        return;
    }
    const cats=[...new Set(chs.map(c=>c.attrs?.['group-title']||'Другое'))].sort();
    const tzs=[...new Set(chs.map(c=>c.attrs?.['tvg-chno']).filter(Boolean))].sort();
    
    const catSel=document.getElementById('cat');
    catSel.innerHTML='<option value="">Все категории</option>'+cats.map(c=>`<option value="${c.toLowerCase()}">${c}</option>`).join('');
    
    const tzSel=document.getElementById('tzFilter');
    tzSel.innerHTML='<option value="">Все часовые пояса</option>'+tzs.map(t=>`<option value="${t}">${t}</option>`).join('');
    
    filter();
}
function filter(){
    const s=document.getElementById('search').value.toLowerCase();
    const c=document.getElementById('cat').value;
    const tz=document.getElementById('tzFilter').value;
    filt=chs.filter(ch=>{
        const n=(ch.name+' '+(ch.attrs?.['tvg-name']||'')).toLowerCase();
        const g=(ch.attrs?.['group-title']||'').toLowerCase();
        const chtz=ch.attrs?.['tvg-chno']||'';
        if(s&&!n.includes(s))return false;
        if(c&&!g.includes(c))return false;
        if(tz&&chtz!==tz)return false;
        if(aliveOnly&&!ch.is_alive)return false;
        return true;
    });
    render();
    document.getElementById('cnt').textContent=filt.length+' каналов';
    document.getElementById('count').textContent=filt.length;
}
function render(){
    const lst=document.getElementById('list');
    if(!filt.length){lst.innerHTML='<div class="text-center p-4 text-muted">Не найдено</div>';return;}
    lst.innerHTML=filt.slice(0,1000).map(ch=>{
        const logo=ch.attrs?.['tvg-logo']||'https://via.placeholder.com/50x28/21262d/764ba2?text=TV';
        const tz=ch.attrs?.['tvg-chno']?`<span class="badge bg-info tz-badge">${ch.attrs['tvg-chno']}</span>`:'';
        return '<div class="ch-item '+(ch.is_alive?'alive':'dead')+'" onclick="copy(\''+ch.url+'\')"><div class="d-flex align-items-center">'+
            '<img src="'+logo+'" class="logo" onerror="this.src=\'https://via.placeholder.com/50x28/21262d/764ba2?text=TV\'">'+
            '<div class="flex-grow-1"><strong>'+ch.name+'</strong><small class="text-muted d-block">'+(ch.attrs?.['group-title']||'')+tz+'</small></div>'+
            '<i class="bi '+(ch.is_alive?'bi-check-circle-fill text-success':'bi-x-circle-fill text-danger')+'"></i></div></div>';
    }).join('');
}
function copy(url){navigator.clipboard.writeText(url);const t=document.createElement('div');
t.className='position-fixed bottom-0 end-0 m-3 alert alert-success';t.textContent='✅ URL скопирован!';
document.body.appendChild(t);setTimeout(()=>t.remove(),2000);}
function toggleAlive(){aliveOnly=!aliveOnly;document.getElementById('tgl').className=aliveOnly?'bi bi-toggle-on':'bi bi-toggle-off';filter();}
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
    search = request.args.get('search', '').lower()
    alive_only = request.args.get('alive', 'false').lower() == 'true'
    tz = request.args.get('timezone', '').lower()
    
    with state_lock: chs = global_channels.copy()
    
    filtered = [c for c in chs if 
                (not search or search in c['name'].lower()) and 
                (not alive_only or c.get('is_alive')) and
                (not tz or (c.get('attrs', {}).get('tvg-chno', '').lower() == tz))]
    
    lines = ['#EXTM3U', f'# 🇷 IPTV Россия - {len(filtered)} каналов', f'# Обновлено: {datetime.now().strftime("%Y-%m-%d %H:%M")}']
    for ch in filtered:
        attr = ' '.join(f'{k}="{v}"' for k,v in ch['attrs'].items() if v)
        lines.append(f"#EXTINF:-1 {attr},{ch['name']}")
        lines.append(ch['url'])
    
    return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl')

@app.route('/health')
def health(): return jsonify({'ok':True,'channels':len(global_channels)})

if __name__ == '__main__':
    logger.info("🚀  IPTV Россия запускается...")
    logger.info(f"📡 Источников: {len(SOURCES)}")
    logger.info(f" Часовых поясов: {len(TIME_ZONES)}")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
