import os
import re
import time
import logging
import threading
import requests
from flask import Flask, Response, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== ИСТОЧНИКИ ====================
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
]

# ==================== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ====================
playlist_cache = "#EXTM3U\n# Loading...\n"
is_loading = False
total_channels = 0

# ==================== ФУНКЦИЯ ЗАГРУЗКИ С ПОДРОБНЫМИ ЛОГАМИ ====================
def load_playlist():
    global playlist_cache, is_loading, total_channels
    
    if is_loading:
        logger.info("⏳ Уже загружается, пропускаю")
        return
    
    is_loading = True
    logger.info("🚀 НАЧАЛО ЗАГРУЗКИ ПЛЕЙЛИСТА")
    start_time = time.time()
    
    entries = {}
    seen_urls = set()
    total_lines = 0
    loaded_sources = 0
    
    for idx, source_url in enumerate(SOURCES, 1):
        logger.info(f"📡 [{idx}/{len(SOURCES)}] Загружаю: {source_url}")
        try:
            response = requests.get(source_url, timeout=20, verify=False, headers={'User-Agent': 'Mozilla/5.0'})
            logger.info(f"   Статус: {response.status_code}")
            
            if response.status_code != 200:
                logger.warning(f"   ❌ Ошибка: статус {response.status_code}")
                continue
                
            if not response.text:
                logger.warning(f"   ❌ Пустой ответ")
                continue
            
            loaded_sources += 1
            lines = response.text.splitlines()
            total_lines += len(lines)
            logger.info(f"   📄 Строк: {len(lines)}")
            
            # Парсим
            current_name = ''
            parsed = 0
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith('#EXTINF:'):
                    match = re.search(r',\s*(.+)$', line)
                    current_name = match.group(1).strip() if match else ''
                elif line.startswith('http') and current_name:
                    url = line
                    
                    # Фильтры
                    if url in seen_urls:
                        current_name = ''
                        continue
                    
                    # Проверка на русский язык
                    has_russian = bool(re.search(r'[а-яёА-ЯЁ]', current_name))
                    if not has_russian:
                        current_name = ''
                        continue
                    
                    # Проверка на платные сервисы
                    if any(x in url.lower() for x in ['wink', 'rt.ru', 'tvigle']):
                        current_name = ''
                        continue
                    
                    seen_urls.add(url)
                    
                    # Определяем категорию (упрощенно)
                    cat = 'Общие'
                    name_lower = current_name.lower()
                    if any(w in name_lower for w in ['новост', 'news', '24']):
                        cat = 'Новости'
                    elif any(w in name_lower for w in ['спорт', 'sport', 'футбол']):
                        cat = 'Спорт'
                    elif any(w in name_lower for w in ['кино', 'kino', 'фильм']):
                        cat = 'Кино и сериалы'
                    elif any(w in name_lower for w in ['дет', 'kids', 'мульт']):
                        cat = 'Детские'
                    elif any(w in name_lower for w in ['музык', 'music']):
                        cat = 'Музыка'
                    elif any(w in name_lower for w in ['докум', 'discovery']):
                        cat = 'Познавательные'
                    elif any(w in name_lower for w in ['москва', 'петербург', 'регион']):
                        cat = 'Региональные'
                    elif any(w in name_lower for w in ['первый канал', 'россия 1', 'нтв']):
                        cat = 'Федеральные'
                    
                    key = re.sub(r'\s+', ' ', current_name.lower().strip())
                    if key not in entries:
                        entries[key] = {
                            'url': url,
                            'name': current_name,
                            'cat': cat,
                            'inf': f'#EXTINF:-1 group-title="{cat}",{current_name}'
                        }
                        parsed += 1
                    current_name = ''
            
            logger.info(f"   ✅ Добавлено каналов: {parsed} (всего: {len(entries)})")
            
        except Exception as e:
            logger.error(f"   ❌ Ошибка загрузки {source_url}: {str(e)}")
    
    # Формируем плейлист
    total_channels = len(entries)
    logger.info(f"📊 ИТОГО УНИКАЛЬНЫХ КАНАЛОВ: {total_channels}")
    logger.info(f"📊 Загружено источников: {loaded_sources}/{len(SOURCES)}")
    logger.info(f"📊 Всего строк в файлах: {total_lines}")
    
    if total_channels == 0:
        logger.error("⚠️ КРИТИЧНО: Нет каналов! Проверьте доступность источников.")
        playlist_cache = "#EXTM3U\n# Нет каналов. Проверьте логи.\n"
        is_loading = False
        return
    
    # Сортируем по категориям
    cat_order = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 
                 'Детские', 'Музыка', 'Познавательные', 'Развлекательные', 
                 'Региональные', 'Общие']
    
    def sort_key(ch):
        try:
            idx = cat_order.index(ch['cat'])
        except:
            idx = 9
        return (idx, ch['name'].lower())
    
    sorted_channels = sorted(entries.values(), key=sort_key)
    
    # Лимит для безопасности
    if len(sorted_channels) > 3000:
        sorted_channels = sorted_channels[:3000]
        logger.info(f"✂️ Ограничено до 3000 каналов")
    
    # Создаем плейлист
    lines = [
        '#EXTM3U',
        f'# IPTV Russia AI — {time.strftime("%Y-%m-%d %H:%M")}',
        f'# Всего каналов: {len(sorted_channels)}',
        f'# Категории: {", ".join(set(ch["cat"] for ch in sorted_channels))}'
    ]
    
    for ch in sorted_channels:
        lines.append(ch['inf'])
        lines.append(ch['url'])
    
    playlist_cache = '\n'.join(lines)
    
    elapsed = time.time() - start_time
    logger.info(f"✅ ГОТОВО: {len(sorted_channels)} каналов за {elapsed:.1f}с")
    logger.info(f"📝 Размер плейлиста: {len(playlist_cache)} байт")
    is_loading = False

# ==================== ФОНОВЫЙ ЗАПУСК ====================
def background_loader():
    while True:
        try:
            load_playlist()
        except Exception as e:
            logger.error(f"💥 Фоновая ошибка: {e}")
        logger.info(f"⏰ Следующая загрузка через 12 часов")
        time.sleep(43200)  # 12 часов

# ==================== ВЕБ-ЭНДПОИНТЫ ====================
@app.route('/')
def home():
    return """
    <h1>🇷🇺 IPTV Russia AI</h1>
    <p>📊 <a href="/status">Статус</a></p>
    <p>📥 <a href="/playlist.m3u">Скачать плейлист</a></p>
    <p>🔄 <a href="/refresh">Обновить</a></p>
    <p>🐛 <a href="/debug">Диагностика</a></p>
    """

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                   headers={'Content-Disposition': 'attachment; filename="iptv_russia_ai.m3u"'})

@app.route('/status')
def status():
    channels = len([l for l in playlist_cache.split('\n') if l.startswith('http')])
    return jsonify({
        'channels': channels,
        'is_loading': is_loading,
        'total_sources': len(SOURCES),
        'playlist_size': len(playlist_cache),
    })

@app.route('/debug')
def debug():
    """Подробная диагностика"""
    import sys
    info = {
        'python_version': sys.version,
        'sources': SOURCES,
        'is_loading': is_loading,
        'playlist_length': len(playlist_cache),
        'channels': len([l for l in playlist_cache.split('\n') if l.startswith('http')]),
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    
    # Проверяем доступность каждого источника
    source_status = {}
    for url in SOURCES:
        try:
            r = requests.head(url, timeout=10, verify=False)
            source_status[url] = {'status': r.status_code, 'ok': r.status_code < 400}
        except Exception as e:
            source_status[url] = {'error': str(e), 'ok': False}
    info['source_status'] = source_status
    
    return jsonify(info)

@app.route('/refresh')
def refresh():
    if is_loading:
        return jsonify({'status': 'already_loading'})
    threading.Thread(target=load_playlist, daemon=True).start()
    return jsonify({'status': 'refresh_started'})

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск на порту {port}")
    
    # Первая загрузка в фоне
    threading.Thread(target=load_playlist, daemon=True).start()
    
    # Фоновый воркер
    threading.Thread(target=background_loader, daemon=True).start()
    
    # Запускаем Flask
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)