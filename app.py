import os
import re
import time
import logging
import threading
import requests
import urllib3
from flask import Flask, Response, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== 80+ ИСТОЧНИКОВ ====================
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/languages/tat.m3u",
    "https://iptv-org.github.io/iptv/languages/che.m3u",
    "https://iptv-org.github.io/iptv/languages/bak.m3u",
    "https://iptv-org.github.io/iptv/languages/chv.m3u",
    "https://iptv-org.github.io/iptv/languages/udm.m3u",
    "https://iptv-org.github.io/iptv/languages/sah.m3u",
    "https://iptv-org.github.io/iptv/languages/bel.m3u",
    "https://iptv-org.github.io/iptv/languages/kaz.m3u",
    "https://iptv-org.github.io/iptv/languages/uzb.m3u",
    "https://iptv-org.github.io/iptv/languages/kir.m3u",
    "https://iptv-org.github.io/iptv/languages/tgk.m3u",
    "https://iptv-org.github.io/iptv/languages/arm.m3u",
    "https://iptv-org.github.io/iptv/languages/aze.m3u",
    "https://iptv-org.github.io/iptv/languages/rum.m3u",
    "https://iptv-org.github.io/iptv/languages/kat.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
    "https://iptv-org.github.io/iptv/categories/family.m3u",
    "https://iptv-org.github.io/iptv/categories/culture.m3u",
    "https://iptv-org.github.io/iptv/categories/education.m3u",
    "https://iptv-org.github.io/iptv/categories/travel.m3u",
    "https://iptv-org.github.io/iptv/categories/comedy.m3u",
    "https://iptv-org.github.io/iptv/categories/series.m3u",
    "https://iptv-org.github.io/iptv/categories/animation.m3u",
    "https://iptv-org.github.io/iptv/categories/religious.m3u",
    "https://iptv-org.github.io/iptv/categories/cooking.m3u",
    "https://iptv-org.github.io/iptv/categories/health.m3u",
    "https://iptv-org.github.io/iptv/categories/hobby.m3u",
    "https://iptv-org.github.io/iptv/categories/home.m3u",
    "https://iptv-org.github.io/iptv/categories/business.m3u",
    "https://iptv-org.github.io/iptv/categories/relax.m3u",
    "https://iptv-org.github.io/iptv/categories/science.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mow.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spe.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-len.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kda.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sam.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sve.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ros.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kgd.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ta.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ba.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-che.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-nvs.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kya.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-pri.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kha.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-amu.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sak.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mag.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kam.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-chu.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sta.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-vgg.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ud.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-per.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-tyu.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-oms.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kem.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-alt.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-irk.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-bu.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sa.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-zab.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/smolnp/IPTVru/main/IPTVru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/ru.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_russia.m3u8",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/index.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://m3u.su/m3u/ru.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://webarmen.com/my/iptv/auto.m3u",
    "https://smolnp.github.io/IPTVru/IPTVru.m3u",
    "https://pskovline.tv/tvm3u.php",
    "https://6x6.msk.ru/tv/m3u",
    "https://homtv.ru/playlist.m3u",
]

playlist_cache = "#EXTM3U\n# Загрузка...\n"
channel_count = 0
is_loading = False
load_lock = threading.Lock()

# ==================== КАТЕГОРИИ ====================
CATEGORIES = {
    'Новости': ['новост', 'news', '24', 'вести', 'известия', 'информ', 'события', 'репортаж', 'прямой эфир', 'live'],
    'Спорт': ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'ufc', 'бокс', 'киберспорт', 'баскетбол', 'теннис', 'биатлон', 'khl', 'nhl', 'nba', 'формула', 'mma'],
    'Кино и сериалы': ['кино', 'kino', 'movie', 'film', 'фильм', 'сериал', 'series', 'serial', 'cinema', 'tv1000', 'амедиа', 'дом кино', 'иллюзион', 'премьера', 'боевик', 'детектив', 'мелодрама', 'комедия', 'триллер', 'драма', 'фэнтези', 'фантастика', 'ужас', 'horror', 'мосфильм', 'золотая коллекция', 'коллекция', 'filmbox', 'киноклуб'],
    'Детские': ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney', 'gulli', 'аниме', 'nick', 'tiji', 'baby', 'малыш', 'сказк', 'детский', 'children', 'animation'],
    'Музыка': ['музык', 'music', 'mtv', 'шансон', 'рутв', 'ретро', 'хит', 'жара', 'блюз', 'jazz', 'классик', 'classic', 'поп', 'рок', 'рэп', 'эстрада'],
    'Познавательные': ['докум', 'doc', 'познав', 'истори', 'history', 'discovery', 'science', 'наука', 'природ', 'animal', 'космос', 'культур', 'искусств', 'театр', 'музей'],
    'Развлекательные': ['развлек', 'entertainment', 'юмор', 'comedy', 'камеди', 'квн', 'шоу', 'мода', 'fashion', 'стиль', 'lifestyle', 'игры', 'ток-шоу'],
    'Региональные': ['москва', 'moscow', 'петербург', 'petersburg', 'лен тв', 'len tv', 'екатеринбург', 'новосибирск', 'казань', 'татарстан', 'уфа', 'башкортостан', 'самара', 'краснодар', 'ростов', 'пермь', 'челябинск', 'омск', 'красноярск', 'владивосток', 'хабаровск', 'иркутск', 'тюмень', 'томск', 'барнаул', 'алтай', 'кемерово', 'кузбасс', 'удмуртия', 'ижевск', 'чувашия', 'чебоксары', 'дагестан', 'грозный', 'кавказ', 'ставрополь', 'волгоград', 'саратов', 'тверь', 'тула', 'ярославль', 'воронеж', 'белгород', 'калуга', 'рязань', 'владимир', 'иваново', 'кострома', 'вологда', 'архангельск', 'мурманск', 'карелия', 'коми', 'калининград', 'псков', 'новгород', 'смоленск', 'якутск', 'якутия', 'бурятия', 'сахалин', 'магадан', 'камчатка', 'чукотка', 'сургут', 'югра', 'ямал', 'крым', 'севастополь', 'сочи', 'минск', 'беларусь', 'алматы', 'астана', 'ташкент', 'бишкек'],
    'Федеральные': ['первый канал', 'россия 1', 'россия к', 'нтв', 'тнт', 'стс', 'рен тв', 'пятый канал', 'тв центр', 'звезда', 'отр', 'пятница', 'суббота', 'домашний', 'муз-тв', '2x2', 'мир', 'channel one', 'pervyi', 'rossiya', 'russia 1', 'russia k', 'russia 24']
}

def get_category(name):
    n = name.lower()
    for cat, keywords in CATEGORIES.items():
        if any(kw in n for kw in keywords):
            return cat
    if re.search(r'[\u0400-\u04FF]', name):
        return 'Общие'
    return 'Общие'

def is_russian_channel(name, url):
    if re.search(r'[а-яёА-ЯЁ]', name):
        ua_words = ['україн', 'украин', 'київ', 'kyiv', 'львів']
        if any(w in name.lower() for w in ua_words):
            return False
        return True
    domain = urlparse(url).netloc.lower()
    if any(d in domain for d in ['.ru', '.su', '.рф', 'russian', 'russia']):
        return True
    return False

def load_playlist():
    global playlist_cache, channel_count, is_loading
    
    if not load_lock.acquire(blocking=False):
        logger.info("⏳ Загрузка уже идет, пропускаем...")
        return
        
    is_loading = True
    logger.info("🚀 НАЧАЛО ЗАГРУЗКИ (80+ источников)")
    start_time = time.time()
    
    entries = {}
    seen = set()
    loaded = 0
    failed = 0
    
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    # Добавляем повторные попытки
    retry_strategy = Retry(total=2, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=30, pool_maxsize=30)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    try:
        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = {executor.submit(session.get, url, timeout=40, verify=False): url for url in SOURCES}
            
            for future in as_completed(futures):
                url = futures[future]
                try:
                    r = future.result()
                    if r.status_code == 200 and r.text:
                        loaded += 1
                        if loaded % 10 == 0:
                            logger.info(f"✅ Загружено {loaded} источников...")
                        
                        lines = r.text.splitlines()
                        current_name = ''
                        
                        for line in lines:
                            line = line.strip()
                            if not line:
                                continue
                                
                            if line.startswith('#EXTINF:'):
                                parts = line.split(',')
                                current_name = parts[-1].strip() if len(parts) > 1 else ''
                            elif not line.startswith('#') and current_name:
                                url_ch = line
                                
                                if url_ch in seen or not is_russian_channel(current_name, url_ch):
                                    current_name = ''
                                    continue
                                
                                paywall = ['wink', 'rt.ru', 'tvigle', 'megogo', 'okko', 'ivi', 'start.ru', 'more.tv', 'kion.ru']
                                if any(x in url_ch.lower() for x in paywall):
                                    current_name = ''
                                    continue
                                
                                if any(x in current_name.lower() for x in ['радио', 'radio', 'fm', 'эфир']):
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
                except Exception as e:
                    failed += 1
                    logger.debug(f"Source failed {url}: {e}")
        
        logger.info(f"📊 ЗАГРУЖЕНО: {loaded} источников, ошибок: {failed}")
        logger.info(f"📊 НАЙДЕНО: {len(entries)} уникальных каналов")
        
        if not entries:
            playlist_cache = "#EXTM3U\n# Нет каналов\n"
            channel_count = 0
            return
        
        cat_order = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 
                     'Детские', 'Музыка', 'Познавательные', 'Развлекательные', 
                     'Региональные', 'Общие']
        
        sorted_channels = sorted(entries.values(), 
                                key=lambda ch: (cat_order.index(ch['cat']) if ch['cat'] in cat_order else 99, ch['name']))
        
        if len(sorted_channels) > 5000:
            sorted_channels = sorted_channels[:5000]
        
        cat_counts = {}
        for ch in sorted_channels:
            cat_counts[ch['cat']] = cat_counts.get(ch['cat'], 0) + 1
        
        lines = [
            '#EXTM3U',
            f'# IPTV Russia AI PRO MAX — {time.strftime("%Y-%m-%d %H:%M")}',
            f'# Всего: {len(sorted_channels)} каналов',
            f'# Источников: {loaded}',
            f'# Категории: {", ".join(f"{k}:{v}" for k,v in cat_counts.items())}'
        ]
        
        for ch in sorted_channels:
            lines.append(ch['inf'])
            lines.append(ch['url'])
        
        playlist_cache = '\n'.join(lines)
        channel_count = len(sorted_channels)
        
    finally:
        elapsed = time.time() - start_time
        logger.info(f"✅ ГОТОВО: {channel_count} каналов за {elapsed:.1f}с (Успех: {loaded}, Ошибок: {failed})")
        logger.info(f"📊 КАТЕГОРИИ: {cat_counts}")
        is_loading = False
        load_lock.release()

def background_worker():
    while True:
        try:
            load_playlist()
        except Exception as e:
            logger.error(f"💥 Фоновая ошибка: {e}")
        logger.info(f"⏰ Следующее обновление через 6 часов")
        time.sleep(21600)

# ==================== ВЕБ ====================
@app.route('/')
def home():
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>IPTV Russia PRO MAX</title>
        <style>
            body {{ font-family: system-ui; background: linear-gradient(135deg, #0f2027, #203a43, #2c5364); color: #fff; min-height: 100vh; margin: 0; display: flex; align-items: center; justify-content: center; }}
            .card {{ background: rgba(255,255,255,.1); backdrop-filter: blur(10px); border-radius: 20px; padding: 40px; max-width: 500px; width: 90%; }}
            h1 {{ margin: 0; }}
            .stat {{ font-size: 72px; font-weight: bold; margin: 10px 0; background: rgba(255,255,255,.05); border-radius: 15px; padding: 20px; }}
            .btn {{ display: inline-block; padding: 12px 24px; border-radius: 10px; text-decoration: none; font-weight: 600; margin: 5px; }}
            .green {{ background: #4caf50; color: #fff; }}
            .blue {{ background: #2196f3; color: #fff; }}
            .gray {{ background: #607d8b; color: #fff; }}
            .info {{ font-size: 12px; opacity: .6; margin-top: 15px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🇷🇺 IPTV Russia</h1>
            <div class="stat">{channel_count}</div>
            <p style="margin: -10px 0 20px;">каналов</p>
            <div>
                <a href="/playlist.m3u" class="btn green">📥 Скачать</a>
                <a href="/refresh" class="btn blue">🔄 Обновить</a>
                <a href="/status" class="btn gray">📊 Статус</a>
            </div>
            <div class="info">Источников: {len(SOURCES)} | {'🔄 Загрузка...' if is_loading else '✅ Готово'}</div>
        </div>
    </body>
    </html>
    """

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                   headers={'Content-Disposition': 'attachment; filename="iptv_russia_pro_max.m3u"'})

@app.route('/status')
def status():
    return jsonify({
        'channels': channel_count,
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

@app.route('/stats/categories')
def categories_stats():
    lines = playlist_cache.split('\n')
    cats = {}
    for line in lines:
        if line.startswith('#EXTINF:'):
            match = re.search(r'group-title="([^"]+)"', line)
            if match:
                cat = match.group(1)
                cats[cat] = cats.get(cat, 0) + 1
    return jsonify(cats)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск на порту {port}")
    threading.Thread(target=load_playlist, daemon=True).start()
    threading.Thread(target=background_worker, daemon=True).start()
    
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)