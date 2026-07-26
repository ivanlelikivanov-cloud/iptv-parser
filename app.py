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

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS_TO_CHECK = 1800      # Лимит для бесплатного тарифа
MAX_WORKERS = 12                  # Не больше 12 потоков на free-tier
CHECK_TIMEOUT = 3.5
UPDATE_INTERVAL = 1800          # 30 минут

playlist_cache = "#EXTM3U\n# IPTV Russia Pro — идёт первичная проверка...\n"
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}

# ==================== ФУНКЦИИ ====================
def fetch_dynamic_sources():
    dynamic = set()
    for page in HTML_SOURCES:
        try:
            r = requests.get(page, headers=HEADERS_WEB, timeout=12)
            if r.status_code == 200:
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text, re.I)
                for link in links:
                    dynamic.add(link)
        except:
            pass
    return list(dynamic)

def get_category(name: str) -> str:
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

def is_adult(name: str) -> bool:
    n = name.lower()
    words = ['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'эротика', 'порно', 'nude', 'erotic']
    return any(w in n for w in words)

def is_russian(name: str) -> bool:
    return bool(re.search(r'[\u0400-\u04FF]', name))

def check_channel(url: str) -> bool:
    try:
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, allow_redirects=True)
        return r.status_code < 400
    except:
        return False

def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    logger.info("🔄 Начинаю мощный сбор и проверку каналов...")

    try:
        # 1. Собираем все источники
        dynamic = fetch_dynamic_sources()
        all_sources = list(set(STATIC_SOURCES + dynamic))
        logger.info(f"Найдено источников: {len(all_sources)}")

        # 2. Парсим каналы
        raw = []
        seen = set()
        for url in all_sources:
            try:
                r = requests.get(url, timeout=12, headers=HEADERS_WEB)
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
                            # Добавляем group-title если его нет
                            if 'group-title=' not in inf:
                                cat = get_category(name)
                                inf = re.sub(r'(#EXTINF:-?\d+)', rf'\1 group-title="{cat}"', inf, count=1)
                            raw.append({'inf': inf, 'url': line})
            except:
                continue

            if len(raw) >= MAX_CHANNELS_TO_CHECK:
                break

        logger.info(f"Собрано уникальных русских каналов: {len(raw)}. Начинаю проверку...")

        # 3. Многопоточная проверка (с правильной привязкой)
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

        # 4. Формируем плейлист
        lines = [
            "#EXTM3U",
            f"# 🇷🇺 IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}",
            f"# Рабочих каналов: {len(alive)}",
            "# Только русские | Без 18+ | Категории на русском"
        ]
        for ch in alive:
            lines.append(ch['inf'])
            lines.append(ch['url'])

        with cache_lock:
            playlist_cache = "\n".join(lines)

        logger.info(f"✅ Готово! Рабочих каналов: {len(alive)}")

    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
    finally:
        is_updating = False

def background_update():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Ошибка фонового цикла: {e}")
            global is_updating
            is_updating = False
        time.sleep(UPDATE_INTERVAL)

# Запускаем фон сразу (без sleep!)
threading.Thread(target=background_update, daemon=True).start()

@app.route('/')
def home():
    return """
    <h1>🇷🇺 IPTV Russia Pro</h1>
    <p>Мощный агрегатор с проверкой каждого канала</p>
    <p><a href="/playlist.m3u" style="font-size:22px">📥 Скачать плейлист</a></p>
    <p>Обновление каждые 30 минут</p>
    """

@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(
            playlist_cache,
            mimetype='application/vnd.apple.mpegurl',
            headers={'Content-Disposition': 'attachment; filename=iptv_russia_pro.m3u'}
        )

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск на порту {port}")
    app.run(host='0.0.0.0', port=port, threaded=True)
