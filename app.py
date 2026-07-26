import os
import re
import time
import logging
import threading
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response

# Отключаем предупреждения о самоподписанных SSL-сертификатах (частая проблема IPTV)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== ИСТОЧНИКИ (МАКСИМАЛЬНЫЙ ОХВАТ) ====================
STATIC_SOURCES = [
    # iptv-org (основные)
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    # Категории (отфильтруем по языку позже)
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    # Альтернативные GitHub-репозитории
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    # Прямые ссылки на плейлисты
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://raw.githubusercontent.com/Assoziation/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/luongz/iptv/main/ru.m3u",
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
]

# ==================== НАСТРОЙКИ МОЩНОСТИ ====================
MAX_CHANNELS_TO_PARSE = 4000   # Собираем с запасом, чтобы после фильтрации осталось 500-800+
MAX_WORKERS = 50               # 50 потоков для молниеносной I/O проверки
CHECK_TIMEOUT = 3.0            # 3 секунды на канал (оптимальный баланс)
UPDATE_EVERY = 1800            # Обновление каждые 30 минут

playlist_cache = "#EXTM3U\n# IPTV Russia Pro MAX — идёт жёсткая проверка каналов...\n"
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Заголовки: VLC для проверки (чтобы не блокировали как бота), Mozilla для скачивания списков
HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {
    'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20',
    'Connection': 'close', # Важно: закрывать соединение сразу после проверки
    'Accept': 'video/*, application/vnd.apple.mpegurl, application/x-mpegurl, */*'
}

# ==================== ЛОГИКА ПРОВЕРКИ ====================
def fetch_dynamic():
    """Скрапинг M3U-ссылок со страниц-агрегаторов"""
    found = set()
    for page in HTML_SOURCES:
        try:
            r = requests.get(page, headers=HEADERS_WEB, timeout=10, verify=False)
            if r.status_code == 200:
                # Ищем любые ссылки на .m3u или .m3u8
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
    if any(x in n for x in ['музыка', 'music', 'хит', 'radio', 'mtv', 'bridge', 'ru']:
        return 'Музыка'
    if any(x in n for x in ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'khl', 'nfhl']):
        return 'Спорт'
    if any(x in n for x in ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'gulli', 'nick']):
        return 'Детские'
    if any(x in n for x in ['докум', 'doc', 'познав', 'history', 'discovery', 'science']):
        return 'Познавательные'
    return 'Общие'

def is_adult(name):
    n = name.lower()
    bad = ['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'эротика', 'порно', 'nude', 'playboy']
    return any(w in n for w in bad)

def is_russian(name):
    # Проверяем наличие кириллицы в названии
    return bool(re.search(r'[\u0400-\u04FF]', name))

def check_one(url):
    """
    Жёсткая двухэтапная проверка канала.
    Отсеивает HTML-заглушки провайдеров по Content-Type.
    """
    valid_content_types = ['video/', 'mpegurl', 'octet-stream', 'audio/', 'application/x-mpegurl']
    
    # Этап 1: Быстрый HEAD
    try:
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(valid in ct for valid in valid_content_types):
                return True
    except:
        pass
    
    # Этап 2: Короткий GET (если HEAD заблокирован или неинформативен)
    try:
        r = requests.get(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, stream=True, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(valid in ct for valid in valid_content_types):
                # Читаем первый килобайт, чтобы убедиться, что поток не обрывается мгновенно
                next(r.iter_content(chunk_size=1024), None)
                return True
    except:
        pass
        
    return False

# ==================== ОБНОВЛЕНИЕ КЭША ====================
def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        logger.info("Обновление уже выполняется, пропускаем.")
        return
    
    is_updating = True
    logger.info("🔄 Запуск мощной проверки каналов...")
    start_time = time.time()

    try:
        # 1. Собираем все источники
        sources = list(set(STATIC_SOURCES + fetch_dynamic()))
        logger.info(f"Найдено уникальных источников: {len(sources)}")

        raw = []
        seen_urls = set()
        
        # 2. Парсим источники
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
                                
                                # Аккуратно добавляем group-title, если его нет
                                if 'group-title=' not in current_inf:
                                    cat = get_category(current_name)
                                    # Вставляем после #EXTINF:-1 или #EXTINF:0
                                    current_inf = re.sub(r'(#EXTINF:-?\d+\s*)', rf'\1group-title="{cat}" ', current_inf, count=1)
                                
                                raw.append({'inf': current_inf, 'url': line})
                                
                                if len(raw) >= MAX_CHANNELS_TO_PARSE:
                                    break
                        
                        # Сброс состояния после обработки URL
                        current_inf = ""
                        current_name = ""
                        
                if len(raw) >= MAX_CHANNELS_TO_PARSE:
                    break
            except Exception as e:
                logger.debug(f"Ошибка чтения источника {src}: {e}")
                continue

        logger.info(f"Собрано {len(raw)} уникальных русских каналов. Запускаю проверку {MAX_WORKERS} потоками...")

        # 3. Многопоточная проверка
        alive = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Передаем только URL, чтобы не держать в памяти лишние словари в futures
            future_to_data = {executor.submit(check_one, ch['url']): ch for ch in raw}
            
            for future in as_completed(future_to_data):
                ch = future_to_data[future]
                try:
                    if future.result():
                        alive.append(ch)
                except Exception:
                    pass

        # 4. Формирование итогового плейлиста
        lines = [
            "#EXTM3U",
            f"# 🇷🇺 IPTV Russia Pro MAX — {time.strftime('%Y-%m-%d %H:%M')}",
            f"# Проверено и работает: {len(alive)} каналов",
            "# Только русские | Без 18+ | Автоматические категории | Жёсткая фильтрация"
        ]
        for ch in alive:
            lines.append(ch['inf'])
            lines.append(ch['url'])

        with cache_lock:
            playlist_cache = "\n".join(lines)

        elapsed = time.time() - start_time
        logger.info(f"✅ Готово! Живых каналов: {len(alive)} из {len(raw)}. Затрачено времени: {elapsed:.1f} сек.")

    except Exception as e:
        logger.error(f"Критическая ошибка обновления: {e}")
    finally:
        is_updating = False

def background_worker():
    """Фоновый поток для периодического обновления"""
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Фоновая ошибка: {e}")
            global is_updating
            is_updating = False
        time.sleep(UPDATE_EVERY)

# Запускаем фоновый поток при старте
threading.Thread(target=background_worker, daemon=True).start()

# ==================== FLASK РОУТЫ ====================
@app.route('/')
def home():
    return """
    <h1>🇷🇺 IPTV Russia Pro MAX</h1>
    <p>Максимально мощный агрегатор с жёсткой проверкой каждого канала.</p>
    <p>Отфильтровано: только кириллица, без 18+, с автоматическими категориями.</p>
    <p><a href="/playlist.m3u" style="font-size:22px; color: #007bff; text-decoration: none;">📥 Скачать рабочий плейлист (.m3u)</a></p>
    <p><a href="/playlist.m3u8" style="font-size:18px; color: #28a745; text-decoration: none;">🔗 Прямая ссылка для плеера (.m3u8)</a></p>
    """

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    with cache_lock:
        response = Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')
        response.headers['Content-Disposition'] = 'attachment; filename="iptv_russia_pro_max.m3u"'
        # Кэшируем на стороне клиента на 15 минут, чтобы не нагружать сервер повторными запросами
        response.headers['Cache-Control'] = 'public, max-age=900'
        return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск сервера на порту {port}")
    
    # Для продакшена используем waitress (если установлен), иначе fallback на встроенный сервер
    try:
        from waitress import serve
        logger.info("Используется production-сервер Waitress")
        serve(app, host='0.0.0.0', port=port, threads=10)
    except ImportError:
        logger.warning("Waitress не найден, используется встроенный сервер Flask (только для тестов)")
        app.run(host='0.0.0.0', port=port, threaded=True)
