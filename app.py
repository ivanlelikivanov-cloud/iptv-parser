import os
import re
import time
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response

app = Flask(__name__)

# ==================== ИСТОЧНИКИ ====================
HTML_SOURCES = [
    "https://sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026",
    "https://6x6.msk.ru/",
    "https://homtv.ru/",
    "https://iptv-rus.com/",
    "https://pikniktv.info/viewtopic.php?t=6737",
    "https://forum.ixbt.com/topic.php?id=123456",
    "https://forum.ru-board.com/topic.cgi?forum=5&topic=12345",
    "https://www.drive2.ru/b/728133159748642624/",
    "https://4pda.to/forum/index.php?showtopic=123456",
    "https://www.linux.org.ru/forum/general/123456",
    "https://habr.com/ru/search/?q=iptv+m3u",
    "https://www.reddit.com/r/IPTV/",
    "https://www.reddit.com/r/IPTVresellers/",
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://github.com/iptv-org/iptv",
    "https://github.com/Free-iptv/iptv",
    "https://github.com/4mirror/iptv",
    "https://github.com/DenMSU/tv",
    "https://github.com/sknk/iptv",
    "https://github.com/alexeyvaneev/iptv",
    "https://github.com/playlist-for-free/IPTV",
    "https://m3u.su/",
    "https://webarmen.com/my/iptv/",
    "https://iptv.best/",
    "https://iptv-channels.net/",
    "https://iptv-live.ru/",
    "https://iptv-tv.ru/",
    "https://iptv-russia.online/",
    "https://free-iptv.xyz/",
    "https://iptvsource.com/",
    "https://iptv-db.com/",
]

STATIC_SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
]

playlist_cache = "#EXTM3U\n# IPTV Russia Pro - Авто-поиск...\n"
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Раздельные заголовки: для сайтов и для самих видеопотоков
HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.16 LibVLC/3.0.16'}

def get_category(name):
    n = name.lower()
    if any(k in n for k in ['новости', 'news', '24', 'vesti', 'информ', 'россия 24']): return 'Новости'
    elif any(k in n for k in ['кино', 'movie', 'film', 'сериал']): return 'Кино'
    elif any(k in n for k in ['музыка', 'music', 'хит', 'radio']): return 'Музыка'
    elif any(k in n for k in ['спорт', 'sport', 'футбол', 'хоккей']): return 'Спорт'
    elif any(k in n for k in ['дет', 'kids', 'мульт']): return 'Детские'
    elif any(k in n for k in ['докум', 'doc', 'познав']): return 'Документальные'
    return 'Общие'

def is_adult(name):
    return any(w in name.lower() for w in ['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'порно'])

def check_channel(url):
    try:
        r = requests.head(url, timeout=3, headers=HEADERS_PLAYER, allow_redirects=True)
        return r.status_code < 400
    except: return False

def update_cache():
    global playlist_cache, is_updating
    if is_updating: return
    is_updating = True
    
    # 1. Сбор ссылок
    all_sources = list(set(STATIC_SOURCES + [link for page in HTML_SOURCES for link in re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', requests.get(page, headers=HEADERS_WEB, timeout=5).text or "")]))
    
    raw_channels = []
    seen = set()
    for url in all_sources:
        try:
            r = requests.get(url, timeout=10, headers=HEADERS_WEB)
            if r.status_code == 200:
                inf = ""
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'): inf = line
                    elif line.startswith('http') and line not in seen:
                        name = re.search(r',(.+)$', inf).group(1) if re.search(r',(.+)$', inf) else ""
                        if re.search(r'[\u0400-\u04FF]', name) and not is_adult(name):
                            seen.add(line)
                            raw_channels.append({'inf': inf, 'url': line})
            if len(raw_channels) >= 5000: break # Лимит памяти
        except: pass

    # 2. Проверка
    valid = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        future_to_ch = {executor.submit(check_channel, ch['url']): ch for ch in raw_channels}
        for future in as_completed(future_to_ch):
            ch = future_to_ch[future]
            if future.result():
                cat = get_category(ch['inf'])
                if 'group-title=' not in ch['inf']:
                    ch['inf'] = re.sub(r'(#EXTINF:-?\d+\s*)', f'\\1group-title="{cat}" ', ch['inf'], count=1)
                valid.append(ch)

    # 3. Сборка
    lines = ["#EXTM3U", f"# IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}"]
    for ch in valid:
        lines.append(ch['inf'])
        lines.append(ch['url'])

    with cache_lock: playlist_cache = "\n".join(lines)
    is_updating = False
    logger.info(f"✅ Готово: {len(valid)} каналов")

def background_update():
    while True:
        try: update_cache()
        except: global is_updating; is_updating = False
        time.sleep(1800)

threading.Thread(target=background_update, daemon=True).start()

@app.route('/')
def home():
    return "<h1>🇷🇺 IPTV Russia Pro</h1><p><a href='/playlist.m3u'>Скачать плейлист</a></p>"

@app.route('/playlist.m3u')
def playlist():
    with cache_lock: return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
