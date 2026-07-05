import os
import re
import time
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response

app = Flask(__name__)

# ==================== ИСТОЧНИКИ ПЛЕЙЛИСТОВ ====================

# Сайты, которые скрипт будет парсить сам, чтобы найти свежие ссылки
HTML_SOURCES = [
    "https://sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026",
    "https://6x6.msk.ru/"
]

# Постоянные прямые ссылки на плейлисты
STATIC_SOURCES = [
    # Новые добавленные плейлисты
    "https://m3u.su/dit",
    "https://m3u.su/kit",
    "https://m3u.su/d5",
    
    # IPTV-ORG (основные + регионы)
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
    
    # GitHub + другие крупные сборки
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
    "https://m3u.su/m3u/ru_deti.m3u",
]

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ И НАСТРОЙКИ ====================

playlist_cache = "#EXTM3U\n# IPTV Russia Pro - Идет первичная сборка и проверка каналов, подождите...\n"
cache_time = 0
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
}

# ==================== ФУНКЦИИ ПАРСИНГА И ПРОВЕРКИ ====================

def fetch_dynamic_sources(page_urls):
    """Сканирует веб-страницы и собирает все ссылки на .m3u / .m3u8"""
    dynamic_sources = set()
    for page in page_urls:
        try:
            logger.info(f"🔍 Сканирование сайта: {page}")
            r = requests.get(page, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text)
                for link in links:
                    dynamic_sources.add(link)
                logger.info(f"✅ Найдено {len(links)} m3u-ссылок на {page}")
        except Exception as e:
            logger.error(f"❌ Ошибка при сканировании {page}: {e}")
    return list(dynamic_sources)

def check_stream_status(channel):
    """Проверяет работоспособность одной стрим-ссылки."""
    url = channel['url']
    try:
        # Способ 1: Быстрая проверка заголовков
        response = requests.head(url, timeout=3.0, headers=HEADERS, allow_redirects=True)
        if response.status_code in [200, 201, 206, 301, 302]:
            return channel
    except Exception:
        pass

    try:
        # Способ 2: Короткий GET-запрос
        response = requests.get(url, timeout=3.0, headers=HEADERS, stream=True, allow_redirects=True)
        if response.status_code in [200, 201, 206]:
            return channel
    except Exception:
        pass
        
    return None

def update_cache():
    """Основной цикл обновления плейлиста"""
    global playlist_cache, cache_time, is_updating
    
    if is_updating:
        return
        
    is_updating = True
    logger.info("🔄 Начало сборки и проверки плейлиста...")
    
    # 1. Сбор источников (статика + динамика)
    parsed_sources = fetch_dynamic_sources(HTML_SOURCES)
    all_sources = list(set(STATIC_SOURCES + parsed_sources))
    
    raw_channels = []
    seen_urls = set()
    
    # 2. Скачивание всех плейлистов
    logger.info(f"⬇️ Скачивание каналов из {len(all_sources)} источников...")
    for url in all_sources:
        try:
            r = requests.get(url, timeout=15, headers=HEADERS)
            if r.status_code == 200:
                current_inf = None
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        current_inf = line
                    elif line.startswith('http') and current_inf:
                        stream_url = line.split()[0]
                        if stream_url not in seen_urls:
                            seen_urls.add(stream_url)
                            raw_channels.append({'inf': current_inf, 'url': stream_url})
                        current_inf = None
        except Exception as e:
            logger.debug(f"Пропуск источника {url}: {e}")

    logger.info(f"🚀 Собрано {len(raw_channels)} уникальных ссылок. Начинаем многопоточную валидацию...")

    # 3. Многопоточная проверка (50 потоков)
    valid_channels = []
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(check_stream_status, ch) for ch in raw_channels]
        for future in as_completed(futures):
            result = future.result()
            if result:
                valid_channels.append(result)

    # 4. Формирование и сохранение итогового плейлиста
    lines = ["#EXTM3U", f"# IPTV Russia Pro - Проверено {time.strftime('%Y-%m-%d %H:%M')}"]
    lines.append(f"# Всего рабочих каналов: {len(valid_channels)}")
    for ch in valid_channels:
        lines.append(ch['inf'])
        lines.append(ch['url'])
        
    with cache_lock:
        playlist_cache = "\n".join(lines)
        cache_time = time.time()
        
    is_updating = False
    logger.info(f"✅ Готово! Работает: {len(valid_channels)} из {len(raw_channels)} каналов.")

def background_update():
    """Фоновый цикл обновления (каждые 30 минут)"""
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Критическая ошибка в фоновом цикле: {e}")
            is_updating = False
        time.sleep(1800)

# ==================== ЗАПУСК ФОНОВОГО ПРОЦЕССА ====================
threading.Thread(target=background_update, daemon=True).start()

# ==================== МАРШРУТЫ FLASK ====================
@app.route('/')
def home():
    return """
    <body style="background:#111; color:#fff; font-family:sans-serif; text-align:center; padding:50px;">
        <h1>🇷🇺 IPTV Russia Pro</h1>
        <p>Плейлист собирается из множества источников и проверяется на работоспособность.</p>
        <a href='/playlist.m3u' style="color:#0f0; font-size:24px; text-decoration:none;">📥 Скачать плейлист</a>
    </body>
    """

@app.route('/playlist.m3u')
def playlist():
    global cache_time
    # Триггер фонового обновления, если кэш старше 15 минут
    if time.time() - cache_time > 900 and not is_updating:
        threading.Thread(target=update_cache, daemon=True).start()
        
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl', 
                        headers={'Content-Disposition': 'attachment; filename=iptv_ru.m3u'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск сервера на порту {port}...")
    app.run(host='0.0.0.0', port=port, threaded=True)
