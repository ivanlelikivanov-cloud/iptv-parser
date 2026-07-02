import os, re, time, threading
from datetime import datetime
from flask import Flask, Response, jsonify, render_template_string
import requests

# ==================== 100+ ИСТОЧНИКОВ ====================
SOURCES = [
    # IPTV-ORG - Россия (15)
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
    "https://iptv-org.github.io/iptv/regions/ru-crimea.m3u",
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
    "https://iptv-org.github.io/iptv/categories/food.m3u",
    "https://iptv-org.github.io/iptv/categories/travel.m3u",
    
    # GitHub репозитории (25)
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/sat-iptv/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/playlist-for-free/IPTV/main/ru.m3u",
    "https://raw.githubusercontent.com/KissyDK/free-iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/iptv-source/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/IPTV-Organizer/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/iptv/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/Ru-IPTV/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/Russian-IPTV/iptv/master/channels.m3u",
    "https://raw.githubusercontent.com/IPTV-RU/playlist/main/ru.m3u",
    "https://raw.githubusercontent.com/iptv-ru/iptv/master/channels.m3u",
    "https://raw.githubusercontent.com/free-iptv-ru/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/iptv-free/ru/master/channels.m3u",
    "https://raw.githubusercontent.com/RuTV/iptv/main/channels.m3u",
    "https://raw.githubusercontent.com/IPTV-Playlist/ru/main/channels.m3u",
    "https://raw.githubusercontent.com/TV-Channels/ru/master/playlist.m3u",
    "https://raw.githubusercontent.com/Russian-TV/iptv/main/channels.m3u",
    "https://raw.githubusercontent.com/Free-TV/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/IPTV-World/ru/main/channels.m3u",
    "https://raw.githubusercontent.com/TV-Playlist/ru/master/channels.m3u",
    "https://raw.githubusercontent.com/IPTV-Russia/main/channels.m3u",
    "https://raw.githubusercontent.com/Ru-Channels/iptv/master/playlist.m3u",
    "https://raw.githubusercontent.com/IPTV-Free-RU/main/channels.m3u",
    
    # M3U.SU коллекции (15)
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
    "https://m3u.su/m3u/ru_dokumentalnoe.m3u",
    "https://m3u.su/m3u/ru_avto.m3u",
    "https://m3u.su/m3u/ru_ohota_rybalka.m3u",
    "https://m3u.su/m3u/ru_zdorove.m3u",
    "https://m3u.su/m3u/ru_mir.m3u",
    
    # Прямые ссылки на плейлисты (20)
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://iptv.jatv.online/playlist.m3u",
    "https://iptv.best/playlist/ru.m3u",
    "https://iptv-lists.com/ru/channels.m3u",
    "https://iptvsource.com/ru/playlist.m3u",
    "https://iptvchannels.net/ru/all.m3u",
    "https://iptv-org.com/ru/channels.m3u",
    "https://free-iptv.xyz/ru/playlist.m3u",
    "https://iptv-db.com/ru/channels.m3u",
    "https://iptv-hd.ru/playlist.m3u",
    "https://iptv-free.net/ru/channels.m3u",
    "https://iptv-online.com/ru/playlist.m3u",
    "https://iptv-live.ru/channels.m3u",
    "https://iptv-tv.ru/playlist.m3u",
    "https://iptv-ru.com/channels.m3u",
    "https://russian-iptv.net/playlist.m3u",
    "https://ru-tv.online/channels.m3u",
    "https://iptv-russia.online/playlist.m3u",
    "https://free-iptv-ru.com/channels.m3u",
    "https://iptv-playlist.ru/ru.m3u",
    
    # СНГ русскоязычные (10)
    "https://iptv-org.github.io/iptv/countries/by.m3u",
    "https://iptv-org.github.io/iptv/countries/kz.m3u",
    "https://iptv-org.github.io/iptv/languages/ukr.m3u",
    "https://iptv-org.github.io/iptv/countries/ua.m3u",
    "https://iptv-org.github.io/iptv/languages/bel.m3u",
    "https://iptv-org.github.io/iptv/languages/kaz.m3u",
    "https://raw.githubusercontent.com/Belarus-IPTV/iptv/main/by.m3u",
    "https://raw.githubusercontent.com/Kazakhstan-IPTV/iptv/main/kz.m3u",
    "https://raw.githubusercontent.com/Ukraine-IPTV/iptv/main/ua.m3u",
    "https://iptv-belarus.by/playlist.m3u",
    
    # Дополнительные (15)
    "https://iptv-ru.github.io/playlist.m3u",
    "https://raw.githubusercontent.com/IPTV-List/main/ru.m3u",
    "https://iptv-channels.ru/all.m3u",
    "https://tv-channels.ru/playlist.m3u",
    "https://russian-tv.online/channels.m3u",
    "https://iptv-world.net/ru.m3u",
    "https://free-tv.ru/playlist.m3u",
    "https://iptv-hd.net/ru.m3u",
    "https://tv-online.ru/channels.m3u",
    "https://iptv-free.org/ru.m3u",
    "https://russian-channels.net/playlist.m3u",
    "https://iptv-live.net/ru.m3u",
    "https://tv-playlist.ru/channels.m3u",
    "https://iptv-db.net/ru.m3u",
    "https://free-channels.ru/playlist.m3u",
]

app = Flask(__name__)
channels = []
stats = {"total": 0, "alive": 0, "updated": "", "sources": 0}
lock = threading.Lock()

def is_russian(ch):
    name = ch.get('name', '')
    attrs = ch.get('attrs', {})
    url = ch.get('url', '')
    
    lang = attrs.get('tvg-language', '').lower()
    if lang in ['rus', 'ru', 'russian']:
        return True
    
    import re
    if re.search(r'[\u0400-\u04FF]', name):
        exclude = ['.by/', '.ua/', '.kz/', '.am/', '.ge/', '.az/', 'belarus', 'ukraine', 'kazakh']
        if any(x in url.lower() or x in name.lower() for x in exclude):
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
    if any(k in name_lower for k in ['новости', 'news', '24', 'vesti']): return 'Новости'
    elif any(k in name_lower for k in ['кино', 'movie', 'film', 'сериал']): return 'Кино'
    elif any(k in name_lower for k in ['музыка', 'music', 'хит']): return 'Музыка'
    elif any(k in name_lower for k in ['спорт', 'sport', 'футбол']): return 'Спорт'
    elif any(k in name_lower for k in ['дет', 'kids', 'мульт']): return 'Детские'
    elif any(k in name_lower for k in ['докум', 'doc']): return 'Документальные'
    else: return 'Общие'

def update():
    global channels, stats
    while True:
        try:
            all_ch = []
            success = 0
            for url in SOURCES:
                try:
                    r = requests.get(url, timeout=8, headers={'User-Agent': 'Mozilla/5.0'})
                    if r.ok:
                        parsed = parse_m3u(r.text)
                        all_ch.extend(parsed)
                        success += 1
                except: pass
            
            seen = {}
            for ch in all_ch:
                key = ch['attrs'].get('tvg-id') or ch['attrs'].get('tvg-name') or ch['url']
                if key and key not in seen:
                    seen[key] = ch
            
            unique = list(seen.values())
            
            alive = 0
            for ch in unique[:500]:
                try:
                    r = requests.head(ch['url'], timeout=2, headers={'User-Agent': 'Mozilla/5.0'})
                    ch['alive'] = r.status_code < 400
                    if ch['alive']: alive += 1
                except: ch['alive'] = False
            
            unique.sort(key=lambda x: (1 if x.get('attrs', {}).get('tvg-logo') else 0, 1 if 'hd' in x['name'].lower() else 0), reverse=True)
            
            with lock:
                channels = unique[:5000]
                stats = {'total': len(unique), 'alive': alive, 'updated': datetime.now().strftime('%H:%M'), 'sources': success}
            
            print(f"✅ {len(unique)} RU каналов из {success} источников, {alive} живых")
        except Exception as e:
            print(f"❌ Ошибка: {e}")
        
        time.sleep(3600)

threading.Thread(target=update, daemon=True).start()
time.sleep(5)

HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>🇷🇺 IPTV</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
body{background:#0d1117;color:#c9d1d9}
.card{background:#161b22;border-color:#30363d}
.stat{font-size:2rem;font-weight:bold}
.item{padding:10px;border-bottom:1px solid #30363d;cursor:pointer}
.item:hover{background:#21262d}
.alive{border-left:4px solid #2ea043}.dead{border-left:4px solid #da3633;opacity:0.6}
</style></head><body>
<div class="container py-4">
<h3>🇷🇺 IPTV Россия</h3>
<div class="row g-3 mb-4">
<div class="col-md-3"><div class="card text-center p-3"><div class="stat text-info" id="total">0</div><div>Всего</div></div></div>
<div class="col-md-3"><div class="card text-center p-3"><div class="stat text-success" id="alive">0</div><div>Живых</div></div></div>
<div class="col-md-3"><div class="card text-center p-3"><div class="stat text-warning" id="src">0</div><div>Источников</div></div></div>
<div class="col-md-3"><div class="card text-center p-3"><div class="stat" id="time">--:--</div><div>Обновлено</div></div></div>
</div>
<input type="text" id="q" class="form-control bg-dark text-light border-secondary mb-3" placeholder="Поиск..." oninput="f()">
<select id="c" class="form-select bg-dark text-light border-secondary mb-3" onchange="f()"><option>Все</option></select>
<div id="list"></div>
</div>
<script>
let d=[];
async function load(){const s=await fetch('/api/stats').then(r=>r.json());
document.getElementById('total').textContent=s.total;
document.getElementById('alive').textContent=s.alive;
document.getElementById('src').textContent=s.sources;
document.getElementById('time').textContent=s.updated;}
async function loadCh(){d=await fetch('/api/channels').then(r=>r.json());
if(!d.length){setTimeout(loadCh,3000);return;}
const cats=[...new Set(d.map(x=>x.attrs?.['group-title']||'Другое'))].sort();
document.getElementById('c').innerHTML='<option>Все</option>'+cats.map(c=>'<option>'+c+'</option>').join('');
filter();}
function filter(){const q=document.getElementById('q').value.toLowerCase();
const c=document.getElementById('c').value;
const f=d.filter(x=>(!q||x.name.toLowerCase().includes(q))&&(!c||x.attrs?.['group-title']===c));
document.getElementById('list').innerHTML=f.slice(0,1000).map(x=>'<div class="item '+(x.alive?'alive':'dead')+'" onclick="copy(\''+x.url+'\')"><b>'+x.name+'</b> <small class="text-muted">'+(x.attrs?.['group-title']||'')+'</small></div>').join('');}
function copy(url){navigator.clipboard.writeText(url);alert(url);}
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
        lines = ['#EXTM3U']
        for ch in channels:
            attr = ' '.join(f'{k}="{v}"' for k,v in ch['attrs'].items() if v)
            lines.append(f'#EXTINF:-1 {attr},{ch["name"]}')
            lines.append(ch['url'])
    return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    print(f"🚀 Запуск... {len(SOURCES)} источников")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
