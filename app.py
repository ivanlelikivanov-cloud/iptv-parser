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

# ==================== ТОЛЬКО ПРОВЕРЕННЫЕ ИСТОЧНИКИ ====================
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
]

playlist_cache = "#EXTM3U\n# Загрузка...\n"
is_loading = False

def load_playlist():
    global playlist_cache, is_loading
    if is_loading:
        return
    
    is_loading = True
    logger.info("🚀 Начинаю загрузку...")
    
    entries = {}
    seen = set()
    
    for url in SOURCES:
        try:
            logger.info(f"📡 Загружаю: {url}")
            r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            
            if r.status_code != 200:
                logger.warning(f"❌ Статус {r.status_code}")
                continue
                
            logger.info(f"✅ Загружено {len(r.text)} байт")
            
            lines = r.text.splitlines()
            current_name = ''
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                if line.startswith('#EXTINF:'):
                    match = re.search(r',\s*(.+)$', line)
                    current_name = match.group(1).strip() if match else ''
                elif line.startswith('http') and current_name:
                    url_ch = line
                    
                    # Фильтры
                    if url_ch in seen:
                        current_name = ''
                        continue
                    
                    # Только русские каналы
                    if not re.search(r'[а-яёА-ЯЁ]', current_name):
                        current_name = ''
                        continue
                    
                    # Блокировка платных
                    if any(x in url_ch.lower() for x in ['wink', 'rt.ru', 'tvigle']):
                        current_name = ''
                        continue
                    
                    seen.add(url_ch)
                    
                    # Категория
                    cat = 'Общие'
                    name_lower = current_name.lower()
                    if any(w in name_lower for w in ['новост', 'news', '24', 'вести']):
                        cat = 'Новости'
                    elif any(w in name_lower for w in ['спорт', 'sport', 'футбол', 'хоккей']):
                        cat = 'Спорт'
                    elif any(w in name_lower for w in ['кино', 'kino', 'фильм', 'сериал']):
                        cat = 'Кино и сериалы'
                    elif any(w in name_lower for w in ['дет', 'kids', 'мульт', 'карусель']):
                        cat = 'Детские'
                    elif any(w in name_lower for w in ['музык', 'music', 'mtv']):
                        cat = 'Музыка'
                    elif any(w in name_lower for w in ['докум', 'discovery', 'наука']):
                        cat = 'Познавательные'
                    elif any(w in name_lower for w in ['москва', 'петербург', 'регион']):
                        cat = 'Региональные'
                    elif any(w in name_lower for w in ['первый канал', 'россия 1', 'нтв', 'тнт']):
                        cat = 'Федеральные'
                    
                    key = re.sub(r'\s+', ' ', current_name.lower().strip())
                    if key not in entries:
                        entries[key] = {
                            'url': url_ch,
                            'name': current_name,
                            'cat': cat,
                            'inf': f'#EXTINF:-1 group-title="{cat}",{current_name}'
                        }
                    current_name = ''
                    
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
    
    logger.info(f"📊 Найдено каналов: {len(entries)}")
    
    if not entries:
        playlist_cache = "#EXTM3U\n# Нет каналов\n"
        is_loading = False
        return
    
    # Сортируем
    cat_order = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 
                 'Детские', 'Музыка', 'Познавательные', 'Региональные', 'Общие']
    
    sorted_channels = sorted(entries.values(), key=lambda ch: (cat_order.index(ch['cat']) if ch['cat'] in cat_order else 99, ch['name']))
    
    lines = ['#EXTM3U', f'# IPTV Russia — {time.strftime("%Y-%m-%d %H:%M")}']
    for ch in sorted_channels[:3000]:
        lines.append(ch['inf'])
        lines.append(ch['url'])
    
    playlist_cache = '\n'.join(lines)
    logger.info(f"✅ Готово: {len(sorted_channels)} каналов")
    is_loading = False

@app.route('/')
def home():
    count = len([l for l in playlist_cache.split('\n') if l.startswith('http')])
    return f"""
    <h1>🇷🇺 IPTV Russia</h1>
    <p>Каналов: {count}</p>
    <p><a href="/playlist.m3u">📥 Скачать плейлист</a></p>
    <p><a href="/refresh">🔄 Обновить</a></p>
    """

@app.route('/playlist.m3u')
def playlist():
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')

@app.route('/refresh')
def refresh():
    if is_loading:
        return "Уже загружается..."
    threading.Thread(target=load_playlist, daemon=True).start()
    return "Обновление запущено!"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    threading.Thread(target=load_playlist, daemon=True).start()
    app.run(host='0.0.0.0', port=port, threaded=True)