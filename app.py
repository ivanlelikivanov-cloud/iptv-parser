import os, re, time, logging, threading, requests
from flask import Flask, Response

app = Flask(__name__)

# ==================== КАЧЕСТВЕННЫЕ ИСТОЧНИКИ ====================
SOURCES = [
    # IPTV-ORG — основной источник (ежедневное обновление)
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
    
    # Категории IPTV-ORG
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    
    # Free-TV IPTV — стабильные потоки
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    
    # IPTV-RUS — с EPG и регионами
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/sat-iptv/iptv/main/ru.m3u",
    
    # AndroidTVSoft / M3U.SU — федеральные и региональные
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
    "https://m3u.su/m3u/ru_news.m3u",
    "https://m3u.su/m3u/sng.m3u",
    
    # Дополнительные проверенные
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://raw.githubusercontent.com/playlist-for-free/IPTV/main/ru.m3u",
]

# EPG для плееров (отдельная ссылка)
EPG_URL = "https://iptv-org.github.io/epg/guides/ru/index.xml"

# ==================== ФИЛЬТР РУССКИХ КАНАЛОВ ====================
def is_russian_channel(name, attrs, url):
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
    if any(k in n for k in ['новости', 'news', '24', 'vesti']): return 'Новости'
    elif any(k in n for k in ['кино', 'movie', 'film', 'сериал']): return 'Кино'
    elif any(k in n for k in ['музыка', 'music', 'хит', 'radio']): return 'Музыка'
    elif any(k in n for k in ['спорт', 'sport', 'футбол']): return 'Спорт'
    elif any(k in n for k in ['дет', 'kids', 'мульт']): return 'Детские'
    elif any(k in n for k in ['докум', 'doc']): return 'Документальные'
    else: return 'Общие'

# ==================== КЭШ ====================
playlist_cache = "#EXTM3U\n"
cache_lock = threading.Lock()
stats = {"total": 0, "sources_ok": 0, "epg": EPG_URL}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def update_cache():
    global playlist_cache, stats
    logger.info("🔄 Сборка плейлиста...")
    
    lines = [
        "#EXTM3U",
        f"# 🇷🇺 IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}",
        f"# Источников: {len(SOURCES)}",
        f"# EPG: {EPG_URL}",
        "# Часовые пояса: настраиваются в плеере (TiviMate/OTT Navigator/Televizo)"
    ]
    seen_urls = set()
    seen_keys = set()
    count = 0
    ok_sources = 0

    for url in SOURCES:
        try:
            r = requests.get(url, timeout=12, headers={'User-Agent': 'Mozilla/5.0'})
            if r.ok:
                ok_sources += 1
                current_inf = None
                current_attrs = {}
                
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        match = re.search(r'#EXTINF:-?\d+\s*(.*),(.+)', line)
                        if match:
                            attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', match.group(1)))
                            name = match.group(2).strip()
                            if is_russian_channel(name, attrs, url):
                                if 'group-title' not in attrs:
                                    attrs['group-title'] = get_category(name)
                                current_attrs = attrs
                                current_inf = f"#EXTINF:-1 {' '.join(f'{k}=\"{v}\"' for k,v in attrs.items())},{name}"
                    elif current_inf and line.startswith('http'):
                        ch_url = line.split()[0]
                        key = current_attrs.get('tvg-id') or current_attrs.get('tvg-name') or ch_url
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
        stats = {"total": count, "sources_ok": ok_sources, "epg": EPG_URL}

    logger.info(f"✅ {count} RU каналов из {ok_sources} источников")


def background_update():
    while True:
        update_cache()
        time.sleep(1800)


threading.Thread(target=background_update, daemon=True).start()
time.sleep(15)


@app.route('/')
def home():
    with cache_lock:
        s = stats.copy()
    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>🇷🇺 IPTV</title>
<style>body{{background:#0d1117;color:#c9d1d9;font-family:sans-serif;text-align:center;padding:40px}}
h1{{color:#58a6ff}}.stat{{font-size:2.5rem;font-weight:bold;margin:15px}}
a{{color:#58a6ff}}.info{{color:#6e7681;font-size:0.9rem;margin-top:30px}}</style></head><body>
<h1>🇷🇺 IPTV Russia Pro</h1>
<div class="stat" style="color:#2ea043">{s['total']}</div><div>Русских каналов</div>
<div class="stat" style="color:#f093fb">{s['sources_ok']}</div><div>Рабочих источников</div>
<p><a href="/playlist.m3u" style="font-size:1.3rem">📥 Скачать плейлист M3U</a></p>
<div class="info">
<p>📺 EPG: <code>{s['epg']}</code></p>
<p>🕐 Часовые пояса: настраиваются в плеере (TiviMate / OTT Navigator / Televizo)</p>
<p>🔄 Автообновление: каждые 30 минут</p>
</div>
</body></html>"""


@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                       headers={'Content-Disposition': 'attachment; filename=iptv_ru.m3u'})


@app.route('/epg.xml')
def epg():
    """Проксирование EPG"""
    try:
        r = requests.get(EPG_URL, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        return Response(r.text, mimetype='application/xml')
    except:
        return Response("<!-- EPG unavailable -->", mimetype='application/xml')


@app.route('/api/stats')
def api_stats():
    with cache_lock:
        return stats


if __name__ == '__main__':
    logger.info(f"🚀 Запуск... {len(SOURCES)} качественных источников")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)), threaded=True)
