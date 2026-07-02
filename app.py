import os, re, time, logging, threading, requests
from flask import Flask, Response

app = Flask(__name__)

# ==================== 100+ ИСТОЧНИКОВ ====================
SOURCES = [
    # IPTV-ORG Россия (15)
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
    
    # GitHub репозитории (30)
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/sat-iptv/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/playlist-for-free/IPTV/main/ru.m3u",
    "https://raw.githubusercontent.com/KissyDK/free-iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/iptv-source/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/Ru-IPTV/iptv/main/ru.m3u",
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
    "https://raw.githubusercontent.com/IPTV-List/main/ru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://raw.githubusercontent.com/LaurentCrozat/IPTV-Web-Player/master/channels.m3u",
    "https://raw.githubusercontent.com/iptv/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/IPTV-Organizer/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/Russian-IPTV/iptv/master/channels.m3u",
    "https://raw.githubusercontent.com/Free-IPTV-RU/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/iptv-playlist/ru/main/channels.m3u",
    
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
    
    # Прямые ссылки (25)
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
    "https://iptv-ru.github.io/playlist.m3u",
    "https://iptv-channels.ru/all.m3u",
    "https://tv-channels.ru/playlist.m3u",
    "https://russian-tv.online/channels.m3u",
    "https://iptv-world.net/ru.m3u",
    
    # СНГ русскоязычные (10)
    "https://iptv-org.github.io/iptv/countries/by.m3u",
    "https://iptv-org.github.io/iptv/countries/kz.m3u",
    "https://iptv-org.github.io/iptv/languages/ukr.m3u",
    "https://iptv-org.github.io/iptv/countries/ua.m3u",
    "https://raw.githubusercontent.com/Belarus-IPTV/iptv/main/by.m3u",
    "https://raw.githubusercontent.com/Kazakhstan-IPTV/iptv/main/kz.m3u",
    "https://raw.githubusercontent.com/Ukraine-IPTV/iptv/main/ua.m3u",
    "https://iptv-belarus.by/playlist.m3u",
    "https://iptv-kz.net/playlist.m3u",
    "https://iptv-ua.online/channels.m3u",
]

# ==================== ФИЛЬТР РУССКИХ КАНАЛОВ ====================
def is_russian(name, attrs, url):
    """Только русские каналы"""
    lang = attrs.get('tvg-language', '').lower()
    if lang in ['rus', 'ru', 'russian']:
        return True
    if re.search(r'[\u0400-\u04FF]', name):
        exclude = ['.by/', '.ua/', '.kz/', '.am/', '.ge/', '.az/', 
                   'belarus', 'ukraine', 'kazakh', 'armenia', 'georgia']
        if any(x in url.lower() or x in name.lower() for x in exclude):
            return False
        return True
    return False

def get_category(name):
    """Авто-категория"""
    n = name.lower()
    if any(k in n for k in ['новости', 'news', '24', 'vesti', 'информ']): return 'Новости'
    elif any(k in n for k in ['кино', 'movie', 'film', 'сериал']): return 'Кино'
    elif any(k in n for k in ['музыка', 'music', 'хит', 'radio']): return 'Музыка'
    elif any(k in n for k in ['спорт', 'sport', 'футбол', 'хоккей']): return 'Спорт'
    elif any(k in n for k in ['дет', 'kids', 'мульт', 'cartoon']): return 'Детские'
    elif any(k in n for k in ['докум', 'doc', 'познав']): return 'Документальные'
    else: return 'Общие'

# ==================== КЭШ ====================
playlist_cache = "#EXTM3U\n# IPTV Russia Pro\n"
cache_lock = threading.Lock()
stats = {"total": 0, "sources": 0}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def update_cache():
    global playlist_cache, stats
    logger.info("🔄 Сборка плейлиста...")
    
    lines = ["#EXTM3U", f"# 🇷🇺 IPTV Russia Pro - {time.strftime('%Y-%m-%d %H:%M')}"]
    seen_urls = set()
    seen_keys = set()
    count = 0
    success = 0
    
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
            if r.ok:
                success += 1
                current_inf = None
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        match = re.search(r'#EXTINF:-?\d+\s*(.*),(.+)', line)
                        if match:
                            attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', match.group(1)))
                            name = match.group(2).strip()
                            if is_russian(name, attrs, url):
                                if 'group-title' not in attrs:
                                    attrs['group-title'] = get_category(name)
                                current_inf = f"#EXTINF:-1 {' '.join(f'{k}=\"{v}\"' for k,v in attrs.items())},{name}"
                    elif current_inf and line.startswith('http'):
                        ch_url = line.split()[0]
                        key = attrs.get('tvg-id') or attrs.get('tvg-name') or ch_url
                        if ch_url not in seen_urls and key not in seen_keys:
                            seen_urls.add(ch_url)
                            seen_keys.add(key)
                            lines.append(current_inf)
                            lines.append(ch_url)
                            count += 1
                        current_inf = None
        except Exception as e:
            logger.debug(f"❌ {url[:40]}: {e}")
    
    with cache_lock:
        playlist_cache = "\n".join(lines)
        stats = {"total": count, "sources": success}
    
    logger.info(f"✅ {count} RU каналов из {success} источников")

def background_update():
    while True:
        update_cache()
        time.sleep(3600)

threading.Thread(target=background_update, daemon=True).start()
time.sleep(15)

# ==================== ROUTES ====================
@app.route('/')
def home():
    with cache_lock:
        return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>🇷🇺 IPTV</title>
        <style>body{{background:#0d1117;color:#c9d1d9;font-family:sans-serif;text-align:center;padding:50px}}
        h1{{color:#58a6ff}}.stat{{font-size:3rem;font-weight:bold;margin:20px}}
        a{{color:#58a6ff;font-size:1.5rem}}</style></head><body>
        <h1>🇷🇺 IPTV Russia Pro</h1>
        <div class="stat" style="color:#2ea043">{stats['total']}</div><div>Русских каналов</div>
        <div class="stat" style="color:#f093fb">{stats['sources']}</div><div>Источников</div>
        <p><a href="/playlist.m3u">📥 Скачать плейлист M3U</a></p>
        <small style="color:#6e7681">Обновлено: {time.strftime('%H:%M')}</small>
        </body></html>"""

@app.route('/playlist.m3u')
def playlist():
    if time.time() - getattr(app, '_last_update', 0) > 600:
        app._last_update = time.time()
        threading.Thread(target=update_cache, daemon=True).start()
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                       headers={'Content-Disposition': 'attachment; filename=iptv_ru.m3u'})

@app.route('/api/stats')
def api_stats():
    with cache_lock:
        return {"total": stats['total'], "sources": stats['sources'], "updated": time.strftime('%H:%M')}

if __name__ == '__main__':
    logger.info(f"🚀 Запуск... {len(SOURCES)} источников")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
