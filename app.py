import os
import re
import time
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response

app = Flask(__name__)

# ==================== БОЛЬШОЙ СПИСОК ПРЯМЫХ ИСТОЧНИКОВ ====================
SOURCES = [
    # IPTV-ORG
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-volga.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-northwest.m3u",
    
    # GitHub
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    
    # m3u.su
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
    "https://m3u.su/m3u/ru_deti.m3u",
    
    # Другие
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
]

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS = 2500
MAX_WORKERS = 10
CHECK_TIMEOUT = 3.5
UPDATE_INTERVAL = 1800

playlist_cache = "#EXTM3U\n# IPTV Russia Pro — загрузка...\n"
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}

def get_category(name):
    n = name.lower()
    if any(k in n for k in ['новости', 'news', '24', 'вести', 'информ']):
        return 'Новости'
    if any(k in n for k in ['кино', 'movie', 'film', 'сериал']):
        return 'Кино'
    if any(k in n for k in ['музыка', 'music', 'хит', 'radio']):
        return 'Музыка'
    if any(k in n for k in ['спорт', 'sport', 'футбол', 'матч']):
        return 'Спорт'
    if any(k in n for k in ['дет', 'kids', 'мульт', 'карусель']):
        return 'Детские'
    return 'Общие'

def is_russian(name):
    if not name or not re.search(r'[\u0400-\u04FF]', name):
        return False
    bad = ['украина', 'ukraine', 'беларусь', 'belarus', 'казахстан', 'kazakhstan']
    return not any(x in name.lower() for x in bad)

def is_adult(name):
    n = name.lower()
    return any(w in n for w in ['xxx', 'adult', 'porn', 'sex', '18+', 'эротика', 'порно'])

def check_channel(url):
    try:
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers=HEADERS, allow_redirects=True)
        return r.status_code < 400
    except:
        return False

def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    logger.info("🔄 Сбор русских каналов...")

    try:
        raw = []
        seen = set()

        for url in SOURCES:
            try:
                r = requests.get(url, timeout=12, headers={'User-Agent': 'Mozilla/5.0'})
                if r.status_code != 200:
                    continue
                inf = name = ""
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        inf = line
                        m = re.search(r',(.+)$', line)
                        name = m.group(1).strip() if m else ""
                    elif line.startswith('http') and line not in seen:
                        if is_russian(name) and not is_adult(name):
                            seen.add(line)
                            if 'group-title=' not in inf:
                                cat = get_category(name)
                                inf = re.sub(r'(#EXTINF:-?\d+)', rf'\1 group-title="{cat}"', inf, count=1)
                            raw.append({'inf': inf, 'url': line})
            except:
                continue

            if len(raw) >= MAX_CHANNELS:
                break

        logger.info(f"Собрано {len(raw)}. Проверяю...")

        alive = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            future_map = {pool.submit(check_channel, ch['url']): ch for ch in raw}
            for future in as_completed(future_map):
                ch = future_map[future]
                try:
                    if future.result():
                        alive.append(ch)
                except:
                    pass

        lines = [
            "#EXTM3U",
            f"# 🇷🇺 IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}",
            f"# Рабочих русских каналов: {len(alive)}"
        ]
        for ch in alive:
            lines.append(ch['inf'])
            lines.append(ch['url'])

        with cache_lock:
            playlist_cache = "\n".join(lines)

        logger.info(f"✅ Готово! Живых: {len(alive)}")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        is_updating = False

def background():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Фон: {e}")
            global is_updating
            is_updating = False
        time.sleep(UPDATE_INTERVAL)

threading.Thread(target=background, daemon=True).start()

@app.route('/')
def home():
    return """
    <h1>🇷🇺 IPTV Russia Pro</h1>
    <p>Только русские рабочие каналы</p>
    <p><a href="/playlist.m3u" style="font-size:22px">📥 Скачать плейлист</a></p>
    """

@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)
