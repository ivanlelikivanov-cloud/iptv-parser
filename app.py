import os
import re
import time
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response

app = Flask(__name__)

# ==================== СТАТИЧЕСКИЕ ИСТОЧНИКИ ====================
STATIC_SOURCES = [
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
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
]

# ==================== ОГРОМНЫЙ СПИСОК САЙТОВ И ФОРУМОВ (150+) ====================
HTML_SOURCES = [
    # Основные агрегаторы
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
    "https://free-iptv.xyz/",
    "https://iptvsource.com/",
    "https://iptv-db.com/",
    "https://iptv-hd.ru/",
    "https://iptv-free.net/",
    "https://iptv-online.com/",
    "https://iptv-ru.com/",
    "https://russian-iptv.net/",
    "https://ru-tv.online/",
    "https://free-iptv-ru.com/",
    "https://iptv-playlist.ru/",
    "https://iptv-ru.github.io/",
    "https://iptv-channels.ru/",
    "https://tv-channels.ru/",
    "https://russian-tv.online/",
    "https://iptv-world.net/",
    "https://iptv-org.github.io/",
    
    # GitHub
    "https://github.com/iptv-org/iptv",
    "https://github.com/Free-iptv/iptv",
    "https://github.com/4mirror/iptv",
    "https://github.com/DenMSU/tv",
    "https://github.com/sknk/iptv",
    "https://github.com/alexeyvaneev/iptv",
    "https://github.com/playlist-for-free/IPTV",
    "https://github.com/Free-TV/IPTV",
    "https://github.com/iptv-org/database",
    "https://github.com/topics/iptv",
    "https://github.com/topics/m3u",
    "https://github.com/topics/iptv-playlist",
    "https://github.com/topics/russian-iptv",
    
    # Форумы
    "https://forum.ixbt.com/",
    "https://forum.ru-board.com/",
    "https://4pda.to/forum/",
    "https://www.linux.org.ru/forum/",
    "https://habr.com/ru/search/?q=iptv+m3u",
    "https://www.drive2.ru/",
    "https://www.reddit.com/r/IPTV/",
    "https://www.reddit.com/r/IPTVresellers/",
    "https://www.reddit.com/r/m3u8/",
    
    # Дополнительные
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    
    # Ещё больше
    "https://iptv-ru.net/",
    "https://ru-iptv.ru/",
    "https://iptvonline.ru/",
    "https://freeiptv.ru/",
    "https://iptvlist.ru/",
    "https://playlist-iptv.ru/",
    "https://m3u-playlist.ru/",
    "https://iptv-channels.online/",
    "https://tvplaylist.ru/",
    "https://russianiptv.com/",
]

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS = 1800
MAX_WORKERS = 10
CHECK_TIMEOUT = 3.8
UPDATE_INTERVAL = 1800

playlist_cache = "#EXTM3U\n# IPTV Russia Pro — жёсткая проверка...\n"
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}

def fetch_dynamic_sources():
    dynamic = set()
    for page in HTML_SOURCES:
        try:
            r = requests.get(page, headers=HEADERS_WEB, timeout=10)
            if r.status_code == 200:
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text, re.I)
                for link in links:
                    dynamic.add(link)
        except:
            pass
    return list(dynamic)

def get_category(name):
    n = name.lower()
    if any(k in n for k in ['новости', 'news', '24', 'вести', 'информ', 'россия 24']):
        return 'Новости'
    if any(k in n for k in ['кино', 'movie', 'film', 'сериал', 'tv 1000']):
        return 'Кино'
    if any(k in n for k in ['музыка', 'music', 'хит', 'radio', 'mtv', 'bridge']):
        return 'Музыка'
    if any(k in n for k in ['спорт', 'sport', 'футбол', 'хоккей', 'матч']):
        return 'Спорт'
    if any(k in n for k in ['дет', 'kids', 'мульт', 'cartoon', 'карусель']):
        return 'Детские'
    if any(k in n for k in ['докум', 'doc', 'познав', 'history', 'discovery']):
        return 'Познавательные'
    return 'Общие'

def is_adult(name):
    n = name.lower()
    words = ['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'эротика', 'порно', 'nude', 'erotic']
    return any(w in n for w in words)

def is_strict_russian(name, attrs=None):
    """Жёсткий фильтр только русских каналов"""
    if not name:
        return False
    # Должна быть кириллица
    if not re.search(r'[\u0400-\u04FF]', name):
        return False
    # Исключаем соседние страны
    exclude = ['украина', 'ukraine', 'беларусь', 'belarus', 'казахстан', 'kazakhstan',
               'армения', 'armenia', 'грузия', 'georgia', 'азербайджан', 'azerbaijan',
               '.ua/', '.by/', '.kz/', '.am/', '.ge/', '.az/']
    name_lower = name.lower()
    if any(x in name_lower for x in exclude):
        return False
    return True

def check_channel(url):
    """Тщательная проверка одного канала"""
    try:
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, allow_redirects=True)
        if r.status_code < 400:
            return True
    except:
        pass
    try:
        r = requests.get(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, stream=True, allow_redirects=True)
        if r.status_code < 400:
            next(r.iter_content(chunk_size=512), None)
            return True
    except:
        pass
    return False

def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    logger.info("🔄 Жёсткий сбор + проверка только русских каналов...")

    try:
        dynamic = fetch_dynamic_sources()
        all_sources = list(set(STATIC_SOURCES + dynamic))
        logger.info(f"Источников: {len(all_sources)}")

        raw = []
        seen = set()
        for url in all_sources:
            try:
                r = requests.get(url, timeout=10, headers=HEADERS_WEB)
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
                        if is_strict_russian(name) and not is_adult(name):
                            seen.add(line)
                            if 'group-title=' not in inf:
                                cat = get_category(name)
                                inf = re.sub(r'(#EXTINF:-?\d+)', rf'\1 group-title="{cat}"', inf, count=1)
                            raw.append({'inf': inf, 'url': line})
            except:
                continue
            if len(raw) >= MAX_CHANNELS:
                break

        logger.info(f"Собрано {len(raw)} русских каналов. Проверяю каждый...")

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
            f"# Только русские рабочие каналы: {len(alive)}",
            "# Без 18+ | Категории на русском"
        ]
        for ch in alive:
            lines.append(ch['inf'])
            lines.append(ch['url'])

        with cache_lock:
            playlist_cache = "\n".join(lines)

        logger.info(f"✅ Готово! Живых русских каналов: {len(alive)}")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        is_updating = False

def background_update():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Фоновая ошибка: {e}")
            global is_updating
            is_updating = False
        time.sleep(UPDATE_INTERVAL)

threading.Thread(target=background_update, daemon=True).start()

@app.route('/')
def home():
    return """
    <h1>🇷🇺 IPTV Russia Pro</h1>
    <p>Только русские каналы + жёсткая проверка</p>
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
