import os, re, time, logging, threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from flask import Flask, Response, jsonify, render_template_string
import requests

SOURCES = [
    # IPTV-ORG - основные
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
    
    # Категории
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/general.m3u",
    "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
    "https://iptv-org.github.io/iptv/categories/business.m3u",
    "https://iptv-org.github.io/iptv/categories/education.m3u",
    "https://iptv-org.github.io/iptv/categories/lifestyle.m3u",
    "https://iptv-org.github.io/iptv/categories/religion.m3u",
    "https://iptv-org.github.io/iptv/categories/science.m3u",
    "https://iptv-org.github.io/iptv/categories/series.m3u",
    "https://iptv-org.github.io/iptv/categories/fashion.m3u",
    
    # GitHub репозитории - большие коллекции
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/sat-iptv/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/playlist-for-free/IPTV/main/ru.m3u",
    "https://raw.githubusercontent.com/KissyDK/free-iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/iptv-source/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/IPTV-Organizer/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/iptv/iptv/master/ru.m3u",
    
    # M3U.SU - большие коллекции
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
    "https://m3u.su/m3u/ru_deti.m3u",
    "https://m3u.su/m3u/ru_music.m3u",
    "https://m3u.su/m3u/ru_news.m3u",
    "https://m3u.su/m3u/ru_obrazovanie.m3u",
    "https://m3u.su/m3u/ru_razvlecheniya.m3u",
    
    # Дополнительные источники
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://raw.githubusercontent.com/LaurentCrozat/IPTV-Web-Player/master/channels.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    
    # СНГ (русскоязычные)
    "https://iptv-org.github.io/iptv/countries/by.m3u",
    "https://iptv-org.github.io/iptv/countries/kz.m3u",
    "https://iptv-org.github.io/iptv/languages/ukr.m3u",
]

app = Flask(__name__)
channels = []
stats = {"total": 0, "alive": 0, "updated": ""}
lock = threading.Lock()

def is_russian(ch):
    """Проверка на русский канал"""
    name = ch.get('name', '')
    attrs = ch.get('attrs', {})
    url = ch.get('url', '')
    
    # Язык
    lang = attrs.get('tvg-language', '').lower()
    if lang in ['rus', 'ru', 'russian']:
        return True
    
    # Кириллица в названии
    if re.search(r'[\u0400-\u04FF]', name):
        # Исключаем страны
        exclude = ['belarus', 'ukraine', 'kazakh', 'armenia', 'georgia', 
                   'azerbaijan', 'moldova', 'estonia', 'latvia', 'lithuania']
        if any(x in url.lower() for x in ['.by/', '.ua/', '.kz/', '.am/', '.ge/', '.az/']):
            return False
        if any(x in name.lower() for x in exclude):
            return False
        return True
    
    return False

def parse_m3u(text):
    result = []
    current = None
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('#EXTINF:'):
            match = re.search(r'#EXTINF:-?\d+\s*(.*),(.+)', line)
            if match:
                attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', match.group(1)))
                attrs.update(dict(re.findall(r'([a-zA-Z0-9-]+)=(\S+)', match.group(1))))
                current = {'name': match.group(2).strip(), 'attrs': attrs, 'url': None, 'alive': True}
        elif current and line.startswith('http'):
            current['url'] = line.split()[0]
            
            if 'group-title' not in current['attrs']:
                current['attrs']['group-title'] = get_category(current['name'])
            
            if is_russian(current):
                result.append(current)
            
            current = None
    return result

def get_category(name):
    name_lower = name.lower()
    if any(k in name_lower for k in ['новости', 'news', '24', 'vesti', 'информ']): 
        return 'Новости'
    elif any(k in name_lower for k in ['кино', 'movie', 'film', 'сериал']): 
        return 'Кино'
    elif any(k in name_lower for k in ['музыка', 'music', 'хит', 'radio']): 
        return 'Музыка'
    elif any(k in name_lower for k in ['спорт', 'sport', 'футбол', 'хоккей']): 
        return 'Спорт'
    elif any(k in name_lower for k in ['дет', 'kids', 'мульт', 'cartoon']): 
        return 'Детские'
    elif any(k in name_lower for k in ['докум', 'doc', 'познав']): 
        return 'Документальные'
    elif any(k in name_lower for k in ['развлек', 'entertain', 'юмор']): 
        return 'Развлекательные'
    else: 
        return 'Общие'

def update():
    global channels, stats
    while True:
        try:
            all_ch = []
            for url in SOURCES:
                try:
                    r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                    if r.ok:
                        parsed = parse_m3u(r.text)
                        all_ch.extend(parsed)
                        print(f"+{len(parsed)} из {url.split('/')[-1][:35]}")
                except Exception as e:
                    print(f"❌ {url.split('/')[-1][:30]}: {e}")
            
            # Дедупликация
            seen = {}
            for ch in all_ch:
                key = ch['attrs'].get('tvg-id') or ch['attrs'].get('tvg-name') or ch['url']
                if key and key not in seen:
                    seen[key] = ch
                elif key and not seen[key].get('attrs', {}).get('tvg-logo') and ch.get('attrs', {}).get('tvg-logo'):
                    seen[key] = ch
            
            unique = list(seen.values())
            print(f"✅ Всего уникальных RU: {len(unique)}")
            
            # Проверка (первые 500)
            alive = 0
            print("🔍 Проверка каналов...")
            for ch in unique[:500]:
                try:
                    r = requests.head(ch['url'], timeout=2, headers={'User-Agent': 'Mozilla/5.0'})
                    ch['alive'] = r.status_code < 400
                    if ch['alive']: alive += 1
                except: ch['alive'] = False
            
            # Сортировка
            unique.sort(key=lambda x: (
                1 if x.get('attrs', {}).get('tvg-logo') else 0,
                1 if 'hd' in x['name'].lower() else 0,
                1 if '4k' in x['name'].lower() else 0
            ), reverse=True)
            
            with lock:
                channels = unique[:3000]  # 3000 каналов
                stats = {'total': len(unique), 'alive': alive, 'updated': datetime.now().strftime('%H:%M')}
            
            print(f"✨ Готово: {len(unique)} RU каналов, {alive} живых, показываем {len(channels)}")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        
        time.sleep(3600)

threading.Thread(target=update, daemon=True).start()
time.sleep(5)

HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>🇷🇺 IPTV Россия</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
<style>
body{background:#0d1117;color:#c9d1d9}
.card{background:#161b22;border-color:#30363d}
.stat{font-size:2.5rem;font-weight:bold}
.item{padding:10px;border-bottom:1px solid #30363d;cursor:pointer;transition:.2s}
.item:hover{background:#21262d}
.alive{border-left:4px solid #2ea043}
.dead{border-left:4px solid #da3633;opacity:0.6}
.badge-hd{background:linear-gradient(135deg,#f093fb,#f5576c);font-size:.7rem;padding:2px 6px;border-radius:3px;margin-left:5px}
.badge-4k{background:linear-gradient(135deg,#667eea,#764ba2);font-size:.7rem;padding:2px 6px;border-radius:3px;margin-left:5px}
</style></head><body>
<div class="container py-4">
<h2 class="mb-4">🇷🇺 IPTV Россия <small class="text-muted">Только русские каналы</small></h2>
<div class="row g-3 mb-4">
<div class="col-md-3 col-6"><div class="card text-center p-3"><div class="stat text-info" id="total">0</div><div>Всего RU</div></div></div>
<div class="col-md-3 col-6"><div class="card text-center p-3"><div class="stat text-success" id="alive">0</div><div>Рабочих</div></div></div>
<div class="col-md-3 col-6"><div class="card text-center p-3"><div class="stat text-warning" id="cats">0</div><div>Категорий</div></div></div>
<div class="col-md-3 col-6"><div class="card text-center p-3"><div class="stat" id="time">--:--</div><div>Обновлено</div></div></div>
</div>
<input type="text" id="q" class="form-control bg-dark text-light border-secondary mb-3" placeholder="🔍 Поиск канала..." oninput="f()">
<select id="c" class="form-select bg-dark text-light border-secondary mb-3" onchange="f()"><option>Все категории</option></select>
<div class="mb-3"><button class="btn btn-sm btn-outline-success" onclick="toggleAlive()"><i class="bi bi-toggle-on" id="tgl"></i> Только рабочие</button> <span class="text-muted ms-2" id="cnt">0</span></div>
<div id="list"></div>
</div>
<script>
let d=[],ftr=[],aliveOnly=false;
async function load(){
    const s=await fetch('/api/stats').then(r=>r.json());
    document.getElementById('total').textContent=s.total;
    document.getElementById('alive').textContent=s.alive;
    document.getElementById('time').textContent=s.updated;
    const cats=[...new Set((await fetch('/api/channels').then(r=>r.json())).map(x=>x.attrs?.['group-title']||'Другое'))].sort();
    document.getElementById('cats').textContent=cats.length;
}
async function loadCh(){
    d=await fetch('/api/channels').then(r=>r.json());
    console.log('RU channels:',d.length);
    if(!d.length){setTimeout(loadCh,3000);return;}
    const cats=[...new Set(d.map(x=>x.attrs?.['group-title']||'Другое'))].sort();
    document.getElementById('c').innerHTML='<option>Все категории</option>'+cats.map(c=>`<option>${c}</option>`).join('');
    filter();
}
function filter(){
    const q=document.getElementById('q').value.toLowerCase();
    const c=document.getElementById('c').value;
    ftr=d.filter(x=>(!q||x.name.toLowerCase().includes(q))&&(!c||x.attrs?.['group-title']===c)&&(aliveOnly?x.alive:true));
    render();
    document.getElementById('cnt').textContent=ftr.length+' каналов';
}
function render(){
    const l=document.getElementById('list');
    if(!ftr.length){l.innerHTML='<div class="text-center p-4 text-muted">Не найдено</div>';return;}
    l.innerHTML=ftr.slice(0,1000).map(x=>{
        const hd=x.name.toLowerCase().includes('4k')?'<span class="badge-4k">4K</span>':(x.name.toLowerCase().includes('hd')?'<span class="badge-hd">HD</span>':'');
        return '<div class="item '+(x.alive?'alive':'dead')+'" onclick="copy(\''+x.url+'\')"><b>'+x.name+hd+'</b> <small class="text-muted">'+(x.attrs?.['group-title']||'')+'</small></div>';
    }).join('');
}
function copy(url){navigator.clipboard.writeText(url);alert('✅ '+url);}
function toggleAlive(){aliveOnly=!aliveOnly;document.getElementById('tgl').className=aliveOnly?'bi bi-toggle-on':'bi bi-toggle-off';filter();}
load();loadCh();setInterval(load,30000);
</script></body></html>"""

@app.route('/')
def home(): return render_template_string(HTML)

@app.route('/api/stats')
def api_stats():
    with lock: return jsonify(stats)

@app.route('/api/channels')
def api_ch():
    with lock: return jsonify(channels)

@app.route('/playlist.m3u')
def m3u():
    with lock:
        lines = ['#EXTM3U', f'# 🇷 IPTV Россия - {len(channels)} каналов', f'# Обновлено: {datetime.now().strftime("%Y-%m-%d %H:%M")}']
        for ch in channels:
            attr = ' '.join(f'{k}="{v}"' for k,v in ch['attrs'].items() if v)
            lines.append(f'#EXTINF:-1 {attr},{ch["name"]}')
            lines.append(ch['url'])
    return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    print("🚀 🇺 IPTV Россия - запуск...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
