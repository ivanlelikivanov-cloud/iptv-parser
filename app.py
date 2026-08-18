import os
import re
import time
import logging
import threading
import requests
from flask import Flask, Response, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== 20+ ИСТОЧНИКОВ ====================
SOURCES = [
    # Основные
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/languages/tat.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
    
    # Регионы
    "https://iptv-org.github.io/iptv/regions/ru-mow.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spe.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-len.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kda.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sam.m3u",
    
    # GitHub
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/smolnp/IPTVru/main/IPTVru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/ru.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_russia.m3u8",
    
    # Дополнительные
    "https://m3u.su/m3u/ru.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
]

playlist_cache = "#EXTM3U\n# Загрузка...\n"
is_loading = False

# ==================== РАСШИРЕННЫЕ КАТЕГОРИИ ====================
CATEGORIES = {
    'Новости': ['новост', 'news', '24', 'вести', 'известия', 'информ', 'события', 'факты', 'репортаж', 'прямой эфир', 'live'],
    'Спорт': ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'ufc', 'бокс', 'киберспорт', 'esport', 'баскетбол', 'теннис', 'биатлон', 'khl', 'nhl', 'nba', 'формула', 'mma', 'единоборства'],
    'Кино и сериалы': ['кино', 'kino', 'movie', 'film', 'фильм', 'сериал', 'series', 'serial', 'cinema', 'tv1000', 'амедиа', 'дом кино', 'иллюзион', 'премьера', 'боевик', 'детектив', 'мелодрама', 'комедия', 'триллер', 'драма', 'фэнтези', 'фантастика', 'ужас', 'horror'],
    'Детские': ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney', 'gulli', 'аниме', 'nick', 'tiji', 'baby', 'малыш', 'школа', 'развивай', 'сказк'],
    'Музыка': ['музык', 'music', 'mtv', 'bridge', 'шансон', 'рутв', 'ru.tv', 'ретро', 'хит', 'жара', 'блюз', 'jazz', 'классик', 'classic', 'поп', 'рок', 'рэп', 'эстрада'],
    'Познавательные': ['докум', 'doc', 'познав', 'истори', 'history', 'discovery', 'science', 'наука', 'природ', 'animal', 'космос', 'культур', 'искусств', 'театр', 'музей', 'географи', 'техник', 'auto', 'дача', 'сад', 'огород', 'рыбал', 'кулинар', 'здоров'],
    'Развлекательные': ['развлек', 'entertainment', 'юмор', 'comedy', 'камеди', 'квн', 'шоу', 'мода', 'fashion', 'стиль', 'lifestyle', 'дом', 'home', 'семья', 'family', 'игры', 'ток-шоу', 'звезд'],
    'Региональные': ['москва', 'moscow', 'петербург', 'petersburg', 'лен тв', 'len tv', 'екатеринбург', 'новосибирск', 'казань', 'татарстан', 'уфа', 'башкортостан', 'самара', 'нижний новгород', 'краснодар', 'кубань', 'ростов', 'пермь', 'челябинск', 'омск', 'красноярск', 'владивосток', 'хабаровск', 'иркутск', 'тюмень', 'томск', 'барнаул', 'алтай', 'кемерово', 'кузбасс', 'удмуртия', 'ижевск', 'чувашия', 'чебоксары', 'дагестан', 'грозный', 'кавказ', 'ставрополь', 'волгоград', 'саратов', 'тверь', 'тула', 'ярославль', 'воронеж', 'белгород', 'калуга', 'рязань', 'владимир', 'иваново', 'кострома', 'вологда', 'архангельск', 'мурманск', 'карелия', 'коми', 'калининград', 'псков', 'новгород', 'смоленск', 'якутск', 'якутия', 'бурятия', 'сахалин', 'магадан', 'камчатка', 'чукотка', 'сургут', 'югра', 'ямал', 'крым', 'севастополь', 'сочи', 'минск', 'беларусь', 'алматы', 'астана', 'ташкент', 'бишкек'],
    'Федеральные': ['первый канал', 'россия 1', 'россия к', 'нтв', 'тнт', 'стс', 'рен тв', 'пятый канал', 'тв центр', 'звезда', 'отр', 'пятница', 'суббота', 'домашний', 'муз-тв', '2x2', 'мир', 'channel one', 'pervyi', 'rossiya', 'russia 1', 'russia k', 'russia 24', 'телеканал']
}

def get_category(name):
    n = name.lower()
    for cat, keywords in CATEGORIES.items():
        if any(kw in n for kw in keywords):
            return cat
    return 'Общие'

# ==================== ЗАГРУЗКА ====================
def load_playlist():
    global playlist_cache, is_loading
    if is_loading:
        return
    
    is_loading = True
    logger.info("🚀 НАЧАЛО ЗАГРУЗКИ")
    start_time = time.time()
    
    entries = {}
    seen = set()
    loaded = 0
    failed = 0
    
    # Загружаем все источники параллельно
    with ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(requests.get, url, timeout=20, verify=False, headers={'User-Agent': 'Mozilla/5.0'}): url for url in SOURCES}
        
        for future in as_completed(futures):
            url = futures[future]
            try:
                r = future.result()
                if r.status_code == 200 and r.text:
                    loaded += 1
                    logger.info(f"✅ [{loaded}] Загружен: {url}")
                    
                    # Парсим
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
                            
                            # Только русские
                            if not re.search(r'[а-яёА-ЯЁ]', current_name):
                                current_name = ''
                                continue
                            
                            # Блокировка платных
                            if any(x in url_ch.lower() for x in ['wink', 'rt.ru', 'tvigle', 'megogo', 'okko', 'ivi']):
                                current_name = ''
                                continue
                            
                            seen.add(url_ch)
                            
                            cat = get_category(current_name)
                            key = re.sub(r'\s+', ' ', current_name.lower().strip())
                            
                            if key not in entries:
                                entries[key] = {
                                    'url': url_ch,
                                    'name': current_name,
                                    'cat': cat,
                                    'inf': f'#EXTINF:-1 group-title="{cat}",{current_name}'
                                }
                            current_name = ''
                            
                else:
                    failed += 1
                    logger.warning(f"❌ [{failed}] Ошибка: {url} (статус {r.status_code})")
            except Exception as e:
                failed += 1
                logger.error(f"❌ [{failed}] Исключение: {url} - {str(e)}")
    
    logger.info(f"📊 ЗАГРУЖЕНО: {loaded} источников, ошибок: {failed}")
    logger.info(f"📊 НАЙДЕНО: {len(entries)} уникальных каналов")
    
    if not entries:
        playlist_cache = "#EXTM3U\n# Нет каналов\n"
        is_loading = False
        return
    
    # Сортируем
    cat_order = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 
                 'Детские', 'Музыка', 'Познавательные', 'Развлекательные', 
                 'Региональные', 'Общие']
    
    sorted_channels = sorted(entries.values(), 
                            key=lambda ch: (cat_order.index(ch['cat']) if ch['cat'] in cat_order else 99, ch['name']))
    
    # Ограничиваем до 5000
    if len(sorted_channels) > 5000:
        sorted_channels = sorted_channels[:5000]
    
    # Считаем категории
    cat_counts = {}
    for ch in sorted_channels:
        cat_counts[ch['cat']] = cat_counts.get(ch['cat'], 0) + 1
    
    lines = [
        '#EXTM3U',
        f'# IPTV Russia AI — {time.strftime("%Y-%m-%d %H:%M")}',
        f'# Всего: {len(sorted_channels)} каналов',
        f'# Источников: {loaded}',
        f'# Категории: {", ".join(f"{k}:{v}" for k,v in cat_counts.items())}'
    ]
    
    for ch in sorted_channels:
        lines.append(ch['inf'])
        lines.append(ch['url'])
    
    playlist_cache = '\n'.join(lines)
    
    elapsed = time.time() - start_time
    logger.info(f"✅ ГОТОВО: {len(sorted_channels)} каналов за {elapsed:.1f}с")
    logger.info(f"📊 КАТЕГОРИИ: {cat_counts}")
    is_loading = False

# ==================== ВЕБ ====================
@app.route('/')
def home():
    count = len([l for l in playlist_cache.split('\n') if l.startswith('http')])
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>IPTV Russia</title>
        <style>
            body {{ font-family: system-ui; background: #0f2027; color: #fff; min-height: 100vh; margin: 0; display: flex; align-items: center; justify-content: center; }}
            .card {{ background: rgba(255,255,255,.1); border-radius: 20px; padding: 40px; max-width: 500px; width: 90%; }}
            h1 {{ margin: 0; }}
            .btn {{ display: inline-block; padding: 12px 24px; border-radius: 10px; text-decoration: none; font-weight: 600; margin: 5px; }}
            .green {{ background: #4caf50; color: #fff; }}
            .blue {{ background: #2196f3; color: #fff; }}
            .stat {{ font-size: 48px; font-weight: bold; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🇷🇺 IPTV Russia AI</h1>
            <div class="stat">{count}</div>
            <p>каналов</p>
            <div>
                <a href="/playlist.m3u" class="btn green">📥 Скачать</a>
                <a href="/refresh" class="btn blue">🔄 Обновить</a>
            </div>
            <p style="font-size:12px;opacity:.7;">Источников: {len(SOURCES)} | Загрузка: {'🔄' if is_loading else '✅'}</p>
        </div>
    </body>
    </html>
    """

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                   headers={'Content-Disposition': 'attachment; filename="iptv_russia.m3u"'})

@app.route('/status')
def status():
    count = len([l for l in playlist_cache.split('\n') if l.startswith('http')])
    return jsonify({
        'channels': count,
        'is_loading': is_loading,
        'sources': len(SOURCES),
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/refresh')
def refresh():
    if is_loading:
        return jsonify({'status': 'already_loading'})
    threading.Thread(target=load_playlist, daemon=True).start()
    return jsonify({'status': 'refresh_started'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск на порту {port}")
    threading.Thread(target=load_playlist, daemon=True).start()
    app.run(host='0.0.0.0', port=port, threaded=True)