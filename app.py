import os
import time
import logging
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response

app = Flask(__name__)

# ==================== МАКСИМАЛЬНЫЕ ИСТОЧНИКИ ====================
SOURCES = [
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

# Глобальный кэш и защита от состояния гонки
playlist_cache = "#EXTM3U\n# IPTV Russia Pro - Плейлист генерируется, подождите...\n"
cache_time = 0
cache_lock = threading.Lock()
is_updating = False  # Флаг, чтобы не запускать дублирующие проверки

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def check_stream_status(channel):
    """
    Проверяет работоспособность одной стрим-ссылки.
    Принимает словарь {'inf': ..., 'url': ...}
    Возвращает тот же словарь, если канал работает, или None, если он мертв.
    """
    url = channel['url']
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        # Способ 1: Быстрая проверка заголовков методом HEAD (без скачивания самого видео)
        response = requests.head(url, timeout=3.0, headers=headers, allow_redirects=True)
        if response.status_code in [200, 201, 206, 301, 302]:
            return channel
    except Exception:
        pass

    try:
        # Способ 2: Если сервер не поддерживает HEAD, пробуем короткий GET-запрос (скачиваем только кусочек)
        response = requests.get(url, timeout=3.0, headers=headers, stream=True, allow_redirects=True)
        if response.status_code in [200, 201, 206]:
            return channel
    except Exception:
        pass
        
    return None

def update_cache():
    global playlist_cache, cache_time, is_updating
    
    if is_updating:
        logger.info("⏳ Проверка уже запущена другим потоком. Пропускаем.")
        return
        
    is_updating = True
    logger.info("🔄 Начало сборки и проверки плейлиста...")
    
    raw_channels = []
    seen_urls = set()
    
    # Шаг 1: Скачиваем все плейлисты и собираем уникальные каналы
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
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
            logger.warning(f"Ошибка при скачивании источника {url}: {e}")

    logger.info(f"Собрано {len(raw_channels)} уникальных ссылок. Начинаем валидацию каналов...")

    # Шаг 2: Многопоточная проверка каналов на доступность
    valid_channels = []
    # 50 воркеров — оптимально для быстрой проверки без экстремальной нагрузки на сеть
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(check_stream_status, ch) for ch in raw_channels]
        
        for future in as_completed(futures):
            result = future.result()
            if result:
                valid_channels.append(result)

    # Шаг 3: Сборка финального плейлиста
    lines = ["#EXTM3U", f"# IPTV Russia Pro - Проверено {time.strftime('%Y-%m-%d %H:%M')}"]
    for ch in valid_channels:
        lines.append(ch['inf'])
        lines.append(ch['url'])
        
    with cache_lock:
        playlist_cache = "\n".join(lines)
        cache_time = time.time()
        
    is_updating = False
    logger.info(f"✅ Проверка завершена! Работает: {len(valid_channels)} из {len(raw_channels)} каналов.")

def background_update():
    """Фоновый цикл обновления каждые 30 минут"""
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Критическая ошибка в фоновом цикле: {e}")
        time.sleep(1800)

# Запуск фонового потока проверки
threading.Thread(target=background_update, daemon=True).start()

# ==================== ROUTES ====================
@app.route('/')
def home():
    return "<h1>🇷🇺 IPTV Russia Pro</h1><p><a href='/playlist.m3u'>Скачать проверенный плейлист</a></p>"

@app.route('/playlist.m3u')
def playlist():
    global cache_time
    # Если кэш старше 10 минут, запускаем фоновую перепроверку (не блокируя выдачу текущего кэша)
    if time.time() - cache_time > 600:
        threading.Thread(target=update_cache, daemon=True).start()
        
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    # Приложение стартует моментально, не ожидая завершения первой тяжелой проверки
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск Flask на порту {port}...")
    app.run(host='0.0.0.0', port=port, threaded=True)
