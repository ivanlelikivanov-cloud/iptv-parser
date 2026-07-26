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
STATIC_SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://m3u.su/m3u/sng.m3u",
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
    "https://iptv.best/",
    "https://iptv-channels.net/",
    "https://iptv-live.ru/",
    "https://iptv-tv.ru/",
    "https://iptv-russia.online/",
    "https://github.com/iptv-org/iptv",
    "https://github.com/Free-iptv/iptv",
    "https://github.com/4mirror/iptv",
    "https://github.com/DenMSU/tv",
]

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS = 1600          # Лимит под free-tier
MAX_WORKERS = 10             # Не больше 10 потоков
CHECK_TIMEOUT = 4.0
UPDATE_EVERY = 1800         # 30 минут

playlist_cache = "#EXTM3U\n# IPTV Russia Pro — идёт жёсткая проверка каналов...\n"
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}

def fetch_dynamic():
    found = set()
    for page in HTML_SOURCES:
        try:
            r = requests.get(page, headers=HEADERS_WEB, timeout=10)
            if r.status_code == 200:
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text, re.I)
                found.update(links)
        except:
            pass
    return list(found)

def get_category(name):
    n = name.lower()
    if any(x in n for x in ['новости', 'news', '24', 'вести', 'информ']):
        return 'Новости'
    if any(x in n for x in ['кино', 'movie', 'film', 'сериал']):
        return 'Кино'
    if any(x in n for x in ['музыка', 'music', 'хит', 'radio', 'mtv']):
        return 'Музыка'
    if any(x in n for x in ['спорт', 'sport', 'футбол', 'хоккей', 'матч']):
        return 'Спорт'
    if any(x in n for x in ['дет', 'kids', 'мульт', 'cartoon', 'карусель']):
        return 'Детские'
    if any(x in n for x in ['докум', 'doc', 'познав', 'history', 'discovery']):
        return 'Познавательные'
    return 'Общие'

def is_adult(name):
    n = name.lower()
    bad = ['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'эротика', 'порно', 'nude']
    return any(w in n for w in bad)

def is_russian(name):
    return bool(re.search(r'[\u0400-\u04FF]', name))

def check_one(url):
    """Жёсткая проверка одного канала"""
    try:
        # Сначала быстрый HEAD
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, allow_redirects=True)
        if r.status_code < 400:
            return True
    except:
        pass
    try:
        # Если HEAD не прошёл — пробуем короткий GET
        r = requests.get(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, stream=True, allow_redirects=True)
        if r.status_code < 400:
            # Читаем чуть-чуть данных, чтобы убедиться, что поток живой
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
    logger.info("🔄 Начинаю мощную проверку каждого канала...")

    try:
        sources = list(set(STATIC_SOURCES + fetch_dynamic()))
        logger.info(f"Источников: {len(sources)}")

        raw = []
        seen = set()
        for src in sources:
            try:
                r = requests.get(src, timeout=10, headers=HEADERS_WEB)
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

        logger.info(f"Собрано {len(raw)} каналов. Проверяю каждый...")

        alive = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_ch = {executor.submit(check_one, ch['url']): ch for ch in raw}
            for future in as_completed(future_to_ch):
                ch = future_to_ch[future]
                try:
                    if future.result():
                        alive.append(ch)
                except:
                    pass

        lines = [
            "#EXTM3U",
            f"# 🇷🇺 IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}",
            f"# Проверено и работает: {len(alive)} каналов",
            "# Только русские | Без 18+ | Категории на русском"
        ]
        for ch in alive:
            lines.append(ch['inf'])
            lines.append(ch['url'])

        with cache_lock:
            playlist_cache = "\n".join(lines)

        logger.info(f"✅ Готово! Живых каналов: {len(alive)}")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        is_updating = False

def background():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Фоновая ошибка: {e}")
            global is_updating
            is_updating = False
        time.sleep(UPDATE_EVERY)

threading.Thread(target=background, daemon=True).start()

@app.route('/')
def home():
    return """
    <h1>🇷🇺 IPTV Russia Pro</h1>
    <p>Жёсткая проверка каждого канала</p>
    <p><a href="/playlist.m3u" style="font-size:22px">📥 Скачать плейлист</a></p>
    """

@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                        headers={'Content-Disposition': 'attachment; filename=iptv_russia_pro.m3u'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, threaded=True)
