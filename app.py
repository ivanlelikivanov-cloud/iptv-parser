import os
import re
import time
import logging
import threading
import requests
import urllib3
from flask import Flask, Response, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== БАЗОВЫЕ ИСТОЧНИКИ (ТОЛЬКО ДЛЯ СТАРТА) ====================
BASE_SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/smolnp/IPTVru/main/IPTVru.m3u",
]

# ==================== ФОРУМЫ ДЛЯ ПАРСИНГА (ОСНОВНОЙ ИСТОЧНИК) ====================
FORUM_URLS = [
    "https://sat-portal.com/plejlisty/",
    "https://sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026",
    "https://pikniktv.info/viewforum.php?f=328",
    "https://pikniktv.info/viewtopic.php?t=6737",
    "https://iptv-rus.com/playlists/",
    "https://vse-tv.net/playlists.html",
    "https://forumtv.org/viewforum.php?f=4",
    "https://webos-forums.ru/post167674.html",
    "https://go2tv.top/",
    "https://iptv.one/",
    "https://iptv.best/",
    "https://6x6.msk.ru/",
    "https://homtv.ru/",
]

# ==================== TELEGRAM КАНАЛЫ (ПУБЛИЧНЫЕ) ====================
TELEGRAM_CHANNELS = [
    "iptvru", "iptv_russia", "russian_iptv", "freeiptv_ru",
    "iptv_playlist", "m3u_playlist", "iptvfree", "tv_playlist",
    "iptv_rf", "playlist_iptv", "iptv_su", "free_iptv_ru",
    "iptv_list", "ru_iptv", "iptv_tv_ru", "russia_iptv",
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

# ==================== ПАРСИНГ ФОРУМОВ ====================
def parse_forum_for_playlists():
    """Парсит форумы и извлекает ссылки на плейлисты"""
    logger.info("🔍 Парсинг форумов...")
    found = []
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    for url in FORUM_URLS:
        try:
            r = session.get(url, timeout=15, verify=False)
            if r.status_code != 200:
                continue
            
            text = r.text
            # Ищем ссылки на .m3u и .m3u8
            m3u_links = re.findall(r'(https?://[^\s"\'<>]+\.m3u8?)', text, re.I)
            for link in m3u_links:
                if 'iptv' in link.lower() or 'playlist' in link.lower() or 'm3u' in link.lower():
                    found.append(link)
            
            # Ищем ссылки на страницы с плейлистами
            page_links = re.findall(r'href=["\']([^"\']+\.(?:html?|php|asp|aspx|htm))["\']', text, re.I)
            for link in page_links:
                full_url = urljoin(url, link)
                if any(kw in full_url.lower() for kw in ['playlist', 'm3u', 'iptv', 'tv']):
                    found.append(full_url)
            
            logger.info(f"✅ С форума {url.split('/')[2]} найдено {len(m3u_links)} ссылок")
        except Exception as e:
            logger.debug(f"Ошибка парсинга {url}: {e}")
    
    return list(set(found))

# ==================== ПАРСИНГ TELEGRAM ====================
def parse_telegram_for_playlists():
    """Парсит Telegram каналы для поиска плейлистов"""
    logger.info("📱 Парсинг Telegram...")
    found = []
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    for channel in TELEGRAM_CHANNELS:
        try:
            url = f"https://t.me/s/{channel}"
            r = session.get(url, timeout=15, verify=False)
            if r.status_code != 200:
                continue
            
            # Ищем ссылки на плейлисты
            links = re.findall(r'(https?://[^\s"\'<>]+\.m3u8?)', r.text, re.I)
            for link in links:
                if 'iptv' in link.lower() or 'playlist' in link.lower():
                    found.append(link)
            
            if links:
                logger.info(f"✅ С канала {channel} найдено {len(links)} ссылок")
        except Exception as e:
            logger.debug(f"Ошибка парсинга {channel}: {e}")
    
    return list(set(found))

# ==================== ПОИСК ЧЕРЕЗ ПОИСКОВИКИ ====================
def search_duckduckgo():
    """Поиск плейлистов через DuckDuckGo"""
    logger.info("🔍 Поиск через DuckDuckGo...")
    found = []
    queries = [
        'iptv m3u russia 2026',
        'плейлист iptv россия бесплатно',
        'iptv playlist russian channels',
        'm3u playlist russia free',
        'актуальный плейлист iptv 2026',
        'iptv ru m3u8 список каналов',
        'свежий плейлист iptv 2026',
        'iptv каналы россия m3u',
    ]
    
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    for q in queries[:4]:
        try:
            r = session.get('https://html.duckduckgo.com/html/', 
                           params={'q': q}, 
                           timeout=10)
            if r.status_code == 200:
                links = re.findall(r'(https?://[^\s"\'<>]+\.m3u8?)', r.text, re.I)
                for link in links:
                    if 'iptv' in link.lower():
                        found.append(link)
        except:
            pass
    
    return list(set(found))

# ==================== ЗАГРУЗКА ПЛЕЙЛИСТА ====================
def load_playlist():
    global playlist_cache, channel_count, is_loading
    
    if not load_lock.acquire(blocking=False):
        logger.info("⏳ Загрузка уже идет, пропускаем...")
        return
        
    is_loading = True
    logger.info("🚀 НАЧАЛО ЗАГРУЗКИ (парсинг форумов + Telegram + поиск)")
    start_time = time.time()
    
    # 1. Собираем ВСЕ возможные источники
    all_sources = set(BASE_SOURCES)
    
    # Парсим форумы
    forum_sources = parse_forum_for_playlists()
    all_sources.update(forum_sources)
    logger.info(f"📊 Найдено на форумах: {len(forum_sources)} источников")
    
    # Парсим Telegram
    tg_sources = parse_telegram_for_playlists()
    all_sources.update(tg_sources)
    logger.info(f"📊 Найдено в Telegram: {len(tg_sources)} источников")
    
    # Поиск через DuckDuckGo
    search_sources = search_duckduckgo()
    all_sources.update(search_sources)
    logger.info(f"📊 Найдено через поиск: {len(search_sources)} источников")
    
    sources_list = list(all_sources)
    logger.info(f"📊 ВСЕГО ИСТОЧНИКОВ: {len(sources_list)}")
    
    # 2. Загружаем все источники
    entries = {}
    seen = set()
    loaded = 0
    failed = 0
    
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    retry_strategy = Retry(total=1, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=30, pool_maxsize=30)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(session.get, url, timeout=20, verify=False): url for url in sources_list[:100]}
        
        for future in as_completed(futures):
            url = futures[future]
            try:
                r = future.result()
                if r.status_code == 200 and r.text:
                    loaded += 1
                    if loaded % 10 == 0:
                        logger.info(f"✅ Загружено {loaded} источников...")
                    
                    # Проверяем HTML
                    if '<html' in r.text[:1000].lower():
                        # Извлекаем ссылки из HTML
                        html_links = re.findall(r'(https?://[^\s"\'<>]+\.m3u8?)', r.text, re.I)
                        for link in html_links:
                            if 'iptv' in link.lower() and link not in sources_list:
                                sources_list.append(link)
                        continue
                    
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
                            
                            paywall = ['wink', 'rt.ru', 'tvigle', 'megogo', 'okko', 'ivi', 'start.ru', 'more.tv']
                            if any(x in url_ch.lower() for x in paywall):
                                current_name = ''
                                continue
                            
                            if any(x in current_name.lower() for x in ['радио', 'radio', 'fm']):
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
        f'# IPTV Russia AI — {time.strftime("%Y-%m-%d %H:%M")}',
        f'# Всего: {len(sorted_channels)} каналов',
        f'# Источников: {loaded}',
        f'# Категории: {", ".join(f"{k}:{v}" for k,v in cat_counts.items())}'
    ]
    
    for ch in sorted_channels:
        lines.append(ch['inf'])
        lines.append(ch['url'])
    
    playlist_cache = '\n'.join(lines)
    channel_count = len(sorted_channels)
    
    elapsed = time.time() - start_time
    logger.info(f"✅ ГОТОВО: {channel_count} каналов за {elapsed:.1f}с")
    logger.info(f"📊 КАТЕГОРИИ: {cat_counts}")
    is_loading = False
    load_lock.release()

# ==================== ФОНОВЫЙ ПРОЦЕСС ====================
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
        <title>IPTV Russia AI</title>
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
            <div class="info">🔄 Загрузка...' if is_loading else '✅ Готово</div>
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
    return jsonify({
        'channels': channel_count,
        'is_loading': is_loading,
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
    threading.Thread(target=background_worker, daemon=True).start()
    
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)