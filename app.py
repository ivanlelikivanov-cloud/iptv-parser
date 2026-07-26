import os
import re
import time
import logging
import threading
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response

# Отключаем предупреждения о самоподписанных SSL-сертификатах
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== ИСТОЧНИКИ ====================
STATIC_SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
]

HTML_SOURCES = [
    "https://sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026",
    "https://6x6.msk.ru/",
    "https://homtv.ru/",
    "https://iptv-rus.com/",
    "https://pikniktv.info/viewtopic.php?t=6737",
    "https://m3u.su/",
    "https://webarmen.com/my/iptv/",
]

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS_TO_PARSE = 4000
MAX_WORKERS = 50
CHECK_TIMEOUT = 3.0
UPDATE_EVERY = 1800

playlist_cache = "#EXTM3U\n# IPTV Russia Pro — идёт проверка каналов...\n"
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {
    'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20',
    'Connection': 'close',
}

# ==================== ФУНКЦИИ ====================
def fetch_dynamic():
    found = set()
    for page in HTML_SOURCES:
        try:
            r = requests.get(page, headers=HEADERS_WEB, timeout=10, verify=False)
            if r.status_code == 200:
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text, re.I)
                found.update(links)
        except Exception as e:
            logger.debug(f"Пропуск {page}: {e}")
    return list(found)

def get_category(name):
    n = name.lower()
    if any(x in n for x in ['новости', 'news', '24', 'вести', 'информ', 'дождь', 'мир']):
        return 'Новости'
    if any(x in n for x in ['кино', 'movie', 'film', 'сериал', 'hd', 'fox', 'tv1000']):
        return 'Кино'
    if any(x in n for x in ['музыка', 'music', 'хит', 'radio', 'mtv', 'bridge', 'ru']):
        return 'Музыка'
    if any(x in n for x in ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'khl']):
        return 'Спорт'
    if any(x in n for x in ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'gulli']):
        return 'Детские'
    if any(x in n for x in ['докум', 'doc', 'познав', 'history', 'discovery']):
        return 'Познавательные'
    return 'Общие'

def is_adult(name):
    n = name.lower()
    bad = ['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'эротика', 'порно', 'nude', 'playboy']
    return any(w in n for w in bad)

def is_russian(name):
    return bool(re.search(r'[\u0400-\u04FF]', name))

def check_one(url):
    valid_content_types = ['video/', 'mpegurl', 'octet-stream', 'audio/', 'application/x-mpegurl']
    
    try:
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(valid in ct for valid in valid_content_types):
                return True
    except:
        pass
    
    try:
        r = requests.get(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, stream=True, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(valid in ct for valid in valid_content_types):
                next(r.iter_content(chunk_size=1024), None)
                return True
    except:
        pass
        
    return False

def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    
    is_updating = True
    logger.info("🔄 Запуск проверки каналов...")
    start_time = time.time()

    try:
        sources = list(set(STATIC_SOURCES + fetch_dynamic()))
        logger.info(f"Источников: {len(sources)}")

        raw = []
        seen_urls = set()
        
        for src in sources:
            try:
                r = requests.get(src, timeout=10, headers=HEADERS_WEB, verify=False)
                if r.status_code != 200:
                    continue
                
                current_inf = ""
                current_name = ""
                
                for line in r.text.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                        
                    if line.startswith('#EXTINF:'):
                        current_inf = line
                        match = re.search(r',\s*(.+)$', line)
                        current_name = match.group(1).strip() if match else ""
                    elif line.startswith('http'):
                        if current_name and is_russian(current_name) and not is_adult(current_name):
                            if line not in seen_urls:
                                seen_urls.add(line)
                                
                                if 'group-title=' not in current_inf:
                                    cat = get_category(current_name)
                                    current_inf = re.sub(r'(#EXTINF:-?\d+\s*)', rf'\1group-title="{cat}" ', current_inf, count=1)
                                
                                raw.append({'inf': current_inf, 'url': line})
                                
                                if len(raw) >= MAX_CHANNELS_TO_PARSE:
                                    break
                        
                        current_inf = ""
                        current_name = ""
                        
                if len(raw) >= MAX_CHANNELS_TO_PARSE:
                    break
            except Exception as e:
                logger.debug(f"Ошибка {src}: {e}")
                continue

        logger.info(f"Собрано {len(raw)} каналов. Проверка...")

        alive = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_data = {executor.submit(check_one, ch['url']): ch for ch in raw}
            
            for future in as_completed(future_to_data):
                ch = future_to_data[future]
                try:
                    if future.result():
                        alive.append(ch)
                except:
                    pass

        lines = [
            "#EXTM3U",
            f"# 🇺 IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}",
            f"# Работает: {len(alive)} каналов",
        ]
        for ch in alive:
            lines.append(ch['inf'])
            lines.append(ch['url'])

        with cache_lock:
            playlist_cache = "\n".join(lines)

        elapsed = time.time() - start_time
        logger.info(f"✅ Готово! Каналов: {len(alive)}. Время: {elapsed:.1f} сек")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        is_updating = False

def background_worker():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Фоновая ошибка: {e}")
            global is_updating
            is_updating = False
        time.sleep(UPDATE_EVERY)

threading.Thread(target=background_worker, daemon=True).start()

@app.route('/')
def home():
    return """
    <h1>🇷🇺 IPTV Russia Pro</h1>
    <p>Проверка каналов в реальном времени</p>
    <p><a href="/playlist.m3u" style="font-size:22px">📥 Скачать плейлист</a></p>
    """

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    with cache_lock:
        response = Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')
        response.headers['Content-Disposition'] = 'attachment; filename="iptv_russia_pro.m3u"'
        response.headers['Cache-Control'] = 'public, max-age=900'
        return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск на порту {port}")
    
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=10)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)
