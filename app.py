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
]

playlist_cache = "#EXTM3U\n# IPTV Russia Pro - Авто-поиск...\n"
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Заголовки для обхода блокировок
HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.16 LibVLC/3.0.16'}

def fetch_dynamic_sources():
    dynamic = set()
    for page in HTML_SOURCES:
        try:
            r = requests.get(page, headers=HEADERS_WEB, timeout=15)
            if r.status_code == 200:
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text)
                for link in links:
                    dynamic.add(link)
        except:
            pass
    return list(dynamic)

def get_category(name):
    """Определяет категорию канала по названию"""
    n = name.lower()
    if any(k in n for k in ['новости', 'news', '24', 'vesti', 'россия 24']): return 'Новости'
    elif any(k in n for k in ['кино', 'movie', 'film', 'сериал', 'tv 1000', 'ciné']): return 'Кино'
    elif any(k in n for k in ['музыка', 'music', 'хит', 'radio', 'mtv', 'bridge']): return 'Музыка'
    elif any(k in n for k in ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'боец']): return 'Спорт'
    elif any(k in n for k in ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney']): return 'Детские'
    elif any(k in n for k in ['докум', 'doc', 'познав', 'history', 'nat geo', 'discovery']): return 'Познавательные'
    else: return 'Общие'

def check_channel(url):
    """Проверка канала с User-Agent плеера"""
    try:
        r = requests.head(url, timeout=3, headers=HEADERS_PLAYER, allow_redirects=True)
        return r.status_code < 400
    except:
        return False

def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    logger.info("🔄 Авто-поиск русских каналов...")

    # 1. Сбор источников
    dynamic = fetch_dynamic_sources()
    all_sources = list(set(STATIC_SOURCES + dynamic))

    # 2. Скачивание
    raw_channels = []
    seen = set()
    for url in all_sources:
        try:
            r = requests.get(url, timeout=12, headers=HEADERS_WEB)
            if r.status_code == 200:
                inf = ""
                name = ""
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        inf = line
                        match = re.search(r',(.+)$', line)
                        name = match.group(1).strip() if match else "Неизвестный канал"
                        
                        # Если в источнике нет категории, добавляем её сами
                        if 'group-title=' not in inf:
                            cat = get_category(name)
                            inf = re.sub(r'(#EXTINF:-?\d+\s*)', f'\\1 group-title="{cat}" ', inf, count=1)
                            
                    elif line.startswith('http') and line not in seen:
                        if re.search(r'[\u0400-\u04FF]', name):  # Только русские (есть кириллица)
                            seen.add(line)
                            raw_channels.append({'inf': inf, 'url': line})
            
            # Защита от OOM (Out Of Memory) - берем максимум 6000 каналов на проверку
            if len(raw_channels) >= 6000:
                logger.info("🛑 Достигнут лимит памяти, переходим к проверке.")
                break
        except:
            pass

    # 3. Многопоточная проверка
    valid = []
    with ThreadPoolExecutor(max_workers=40) as executor:
        future_to_ch = {executor.submit(check_channel, ch['url']): ch for ch in raw_channels}
        for future in as_completed(future_to_ch):
            ch = future_to_ch[future]
            if future.result():
                valid.append(ch)

    # 4. Формирование плейлиста
    lines = ["#EXTM3U", f"# IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}"]
    lines.append(f"# Русских каналов: {len(valid)}")
    for ch in valid:
        lines.append(ch['inf'])
        lines.append(ch['url'])

    with cache_lock:
        playlist_cache = "\n".join(lines)
    is_updating = False
    logger.info(f"✅ {len(valid)} русских каналов успешно добавлено")

def background_update():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Ошибка обновления: {e}")
            global is_updating
            is_updating = False  # Сброс флага при ошибке
        time.sleep(1800)

threading.Thread(target=background_update, daemon=True).start()

@app.route('/')
def home():
    return "<h1>🇷🇺 IPTV Russia Pro (Авто-поиск)</h1><p><a href='/playlist.m3u'>Скачать плейлист</a></p>"

@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                        headers={'Content-Disposition': 'attachment; filename=iptv_ru.m3u'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
