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
from collections import Counter

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== 350+ ИСТОЧНИКОВ (РАСШИРЕННЫЙ СПИСОК) ====================
def generate_sources():
    """Генерация 350+ источников"""
    sources = []
    
    # --- 1. iptv-org (все возможные) ---
    iptv_base = "https://iptv-org.github.io/iptv"
    langs = ['rus', 'tat', 'che', 'bak', 'chv', 'udm', 'sah', 'bel', 'kaz', 'uzb', 'kir', 'tgk', 'arm', 'aze', 'rum', 'kat']
    categories = ['news', 'sports', 'movies', 'kids', 'music', 'documentary', 'entertainment', 
                  'family', 'culture', 'education', 'travel', 'comedy', 'series', 'animation',
                  'religious', 'cooking', 'health', 'hobby', 'home', 'business', 'relax', 'science']
    regions = ['mow', 'spe', 'len', 'kda', 'sam', 'sve', 'ros', 'kgd', 'ta', 'ba', 'che', 'nvs', 
               'kya', 'pri', 'kha', 'amu', 'sak', 'mag', 'kam', 'chu', 'sta', 'vgg', 'ud', 'per', 
               'tyu', 'oms', 'kem', 'alt', 'irk', 'bu', 'sa', 'zab', 'yar', 'krs', 'lip', 'tam', 
               'bry', 'krs', 'bel', 'klu', 'rzn', 'vla', 'iva', 'kos', 'vlg', 'ark', 'mur', 'krl', 
               'kom', 'kgd', 'psk', 'nov', 'smo', 'ykt', 'yku', 'bur', 'sah', 'mag', 'kam', 'chu']
    
    for lang in langs:
        sources.append(f"{iptv_base}/languages/{lang}.m3u")
    for cat in categories:
        sources.append(f"{iptv_base}/categories/{cat}.m3u")
    for reg in regions:
        sources.append(f"{iptv_base}/regions/ru-{reg}.m3u")
    
    # --- 2. GitHub репозитории ---
    github_repos = [
        '4mirror/iptv', 'smolnp/IPTVru', 'iptv-org/iptv', 'Free-iptv/iptv',
        'Free-TV/IPTV', 'DenMSU/tv', 'aksy007/iptv', 'tv-lists/tv-lists',
        'malyys/iptv', 'fanfare/iptv', 'iptv-ru/iptv', 'k0ba/iptv', 'zubax/iptv',
        'iptvlist/iptv', 'iptv-world/iptv', 'm3u4u/iptv', 'iptv-source/iptv',
        'iptv-stream/iptv', 'iptv-list/iptv', 'iptv-org/iptv'
    ]
    github_paths = ['ru.m3u', 'playlist.m3u', 'iptv.m3u', 'tv.m3u', 'main.m3u', 
                    'index.m3u', 'channels/ru.m3u', 'playlist.m3u8', 'streams/ru.m3u',
                    'russia.m3u', 'russian.m3u', 'rus.m3u']
    
    for repo in github_repos:
        for path in github_paths:
            sources.append(f"https://raw.githubusercontent.com/{repo}/master/{path}")
            sources.append(f"https://raw.githubusercontent.com/{repo}/main/{path}")
    
    # --- 3. Агрегаторы и сайты (РАСШИРЕННЫЙ БЛОК m3u.su) ---
    m3u_domains = [
        'm3u.su',
        'new.m3u.su',
        'status.m3u.su',
        'cdn.m3u.su',
        'api.m3u.su',
        'play.m3u.su'
    ]
    m3u_paths = [
        '/m3u/ru.m3u', '/m3u/sng.m3u', '/m3u/ua.m3u', '/m3u/by.m3u',
        '/playlist.m3u', '/iptv.m3u', '/tv.m3u', '/index.m3u',
        '/list.m3u', '/channels.m3u', '/russia.m3u', '/rus.m3u',
        '/m3u/ru.m3u8', '/m3u/sng.m3u8', '/playlist.m3u8'
    ]
    for domain in m3u_domains:
        for path in m3u_paths:
            sources.append(f"https://{domain}{path}")
            sources.append(f"http://{domain}{path}")
    
    # Другие агрегаторы
    aggregators = [
        'webarmen.com/my/iptv/auto.nogeo.m3u', 'webarmen.com/my/iptv/auto.m3u',
        'smolnp.github.io/IPTVru/IPTVru.m3u', 'pskovline.tv/tvm3u.php',
        '6x6.msk.ru/tv/m3u', 'homtv.ru/playlist.m3u',
        'iptv-archive.com/playlists/ru.m3u', 'iptv-playlist.org/playlists/russian.m3u',
        'iptv-list.ru/playlist.m3u', 'iptv-m3u.ru/playlist.m3u',
        'iptv4u.ru/playlist.m3u', 'tv-list.ru/playlist.m3u',
        'iptv.su/playlist.m3u', 'iptv.m3u/playlist.m3u',
        'iptv.ru/playlist.m3u', 'iptvpro.ru/playlist.m3u', 'iptvx.ru/playlist.m3u'
    ]
    for agg in aggregators:
        sources.append(f"https://{agg}")
        sources.append(f"http://{agg}")
    
    # --- 4. Telegram каналы ---
    tg_channels = [
        'iptvru', 'iptv_russia', 'russian_iptv', 'freeiptv_ru', 'iptv_playlist',
        'm3u_playlist', 'iptvfree', 'tv_playlist', 'iptv_rf', 'playlist_iptv',
        'iptv_su', 'free_iptv_ru', 'iptv_list', 'ru_iptv', 'iptv_tv_ru',
        'russia_iptv', 'iptv_2026', 'm3u8ru', 'iptv_playlist_ru', 'tv_m3u'
    ]
    for ch in tg_channels:
        sources.append(f"https://t.me/s/{ch}")
    
    # --- 5. Форумы и сайты ---
    forums = [
        'sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026',
        'sat-portal.com/plejlisty/', 'pikniktv.info/viewtopic.php?t=6737',
        'pikniktv.info/viewforum.php?f=328', 'iptv-rus.com/playlists/',
        'vse-tv.net/playlists.html', 'forumtv.org/viewforum.php?f=4',
        'webos-forums.ru/post167674.html', 'go2tv.top/', 'iptv.one/',
        'iptv.best/', 'iptv-channels.net/', 'iptv-live.ru/', 'iptv-tv.ru/',
        'iptv-russia.online/', 'vse-tv.net/', 'forumtv.org/', '6x6.msk.ru/',
        'homtv.ru/', 'pskovline.tv/', 'onlinetv.ru/', 'smotret-tv.online/'
    ]
    for forum in forums:
        sources.append(f"https://{forum}")
        sources.append(f"http://{forum}")
    
    # Удаляем дубли и сортируем
    sources = sorted(list(set(sources)))
    logger.info(f"📡 Сгенерировано {len(sources)} источников")
    return sources

SOURCES = generate_sources()

playlist_cache = "#EXTM3U\n# Загрузка...\n"
channel_count = 0
is_loading = False
load_lock = threading.Lock()

# ==================== КАТЕГОРИИ (РАСШИРЕННЫЕ) ====================
CATEGORIES = {
    'Новости': [
        'новост', 'news', '24', 'вести', 'известия', 'информ', 'события', 'факты',
        'репортаж', 'интервью', 'обзор', 'итоги', 'главное', 'сегодня', 'сейчас',
        'прямой эфир', 'live', 'breaking', 'экстрен', 'чп', 'происшеств',
        'euronews', 'bbc', 'cnn', 'политик', 'эконом', 'бизнес', 'business'
    ],
    'Спорт': [
        'спорт', 'sport', 'футбол', 'хоккей', 'матч', 'ufc', 'бокс', 
        'киберспорт', 'esport', 'баскетбол', 'теннис', 'биатлон', 'лыжн',
        'khl', 'nhl', 'nba', 'формула', 'racing', 'волейбол', 'гандбол',
        'фигурное катание', 'гимнастика', 'плавание', 'легкая атлетика',
        'mma', 'единоборства', 'экстрим', 'скейт', 'сноуборд',
        'match tv', 'match!', 'спорт-1', 'спорт-2', 'спорт 1', 'спорт 2'
    ],
    'Кино и сериалы': [
        'кино', 'kino', 'movie', 'film', 'фильм', 'сериал', 'series', 
        'serial', 'cinema', 'tv1000', 'амедиа', 'дом кино', 'иллюзион',
        'премьера', 'боевик', 'детектив', 'мелодрама', 'комедия',
        'триллер', 'драма', 'приключение', 'вестерн', 'мюзикл',
        'фэнтези', 'фантастика', 'ужас', 'horror', 'криминал',
        'исторический', 'военный', 'мосфильм', 'золотая коллекция',
        'золотой', 'коллекция', 'kinopoisk', 'киномикс', 'киносемья',
        'кинокомедия', 'кинохит', 'кинопремьера', 'filmbox', 'киноклуб'
    ],
    'Детские': [
        'дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney', 'gulli', 
        'аниме', 'nick', 'tiji', 'baby', 'малыш', 'маленький', 'дошкольн',
        'развивай', 'обучай', 'сказк', 'игруш', 'кукл', 'лего',
        'детский', 'children', 'animation', 'anime', 'мультик',
        'мультфильм', 'мультсериал', 'детское кино', 'союзмультфильм'
    ],
    'Музыка': [
        'музык', 'music', 'mtv', 'bridge', 'шансон', 'рутв', 'ru.tv', 
        'ретро', 'хит', 'жара', 'блюз', 'jazz', 'классик', 'classic',
        'поп', 'рок', 'рэп', 'хип-хоп', 'эстрада', 'фолк', 'кантри',
        'джаз', 'опера', 'симфони', 'оркестр', 'хор', 'вокал',
        'muz-tv', 'муз-тв', 'муз тв', 'music box'
    ],
    'Познавательные': [
        'докум', 'doc', 'познав', 'истори', 'history', 'discovery', 
        'science', 'наука', 'природ', 'animal', 'животн', 'океан', 
        'космос', 'культур', 'искусств', 'театр', 'музей',
        'географи', 'биолог', 'астроном', 'физик', 'химия', 'экологи',
        'техник', 'техно', 'авто', 'auto', 'дача', 'сад', 'огород',
        'рыбал', 'охота', 'кулинар', 'еда', 'food', 'здоров', 'health',
        'документальн', 'познавательн', 'образовательн',
        'national geographic', 'ngc', 'animal planet'
    ],
    'Развлекательные': [
        'развлек', 'entertainment', 'юмор', 'comedy', 'камеди', 
        'квн', 'шоу', 'мода', 'fashion', 'стиль', 'lifestyle',
        'лайфстайл', 'дом', 'home', 'семья', 'family', 'игры', 'game',
        'лотерея', 'анекдот', 'талант', 'конкурс', 'викторина',
        'ток-шоу', 'интервью', 'звезд', 'знаменитост',
        'развлекательн', 'юмористическ', 'прикол', 'смех', 'улыбка'
    ],
    'Региональные': [
        'москва', 'moscow', 'петербург', 'petersburg', 'лен тв', 'len tv', 
        'екатеринбург', 'новосибирск', 'казань', 'татарстан', 'уфа',
        'башкортостан', 'самара', 'нижний новгород', 'краснодар', 'кубань',
        'ростов', 'пермь', 'челябинск', 'омск', 'красноярск', 'владивосток',
        'хабаровск', 'иркутск', 'тюмень', 'томск', 'барнаул', 'алтай',
        'кемерово', 'кузбасс', 'удмуртия', 'ижевск', 'чувашия', 'чебоксары',
        'мордовия', 'осетия', 'дагестан', 'грозный', 'чечня', 'кавказ',
        'ставрополь', 'волгоград', 'саратов', 'тверь', 'тула', 'ярославль',
        'воронеж', 'липецк', 'тамбов', 'брянск', 'курск', 'белгород',
        'калуга', 'рязань', 'владимир', 'иваново', 'кострома', 'вологда',
        'архангельск', 'мурманск', 'карелия', 'коми', 'калининград',
        'псков', 'новгород', 'смоленск', 'якутск', 'якутия', 'бурятия',
        'сахалин', 'магадан', 'камчатка', 'чукотка', 'сургут', 'югра',
        'ямал', 'крым', 'севастополь', 'симферополь', 'сочи', 'минск',
        'беларусь', 'гомель', 'брест', 'алматы', 'астана', 'ташкент',
        'бишкек', 'душанбе', 'баку', 'ереван', 'кишинев',
        'региональн', 'местн', 'городск', 'губерния', 'областн', 'краев'
    ],
    'Федеральные': [
        'первый канал', 'россия 1', 'россия к', 'нтв', 'тнт', 'стс', 
        'рен тв', 'пятый канал', 'тв центр', 'звезда', 'отр', 'пятница',
        'суббота', 'домашний', 'муз-тв', '2x2', 'мир', 'channel one',
        'pervyi', 'rossiya', 'russia 1', 'russia k', 'russia 24',
        'телеканал', 'федеральн', 'общероссийск',
        'канал один', 'канал 1', '1 канал', 'channel 1'
    ]
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
        ua_words = ['україн', 'украин', 'київ', 'kyiv', 'львів', 'харків', 'суспільне']
        if any(w in name.lower() for w in ua_words):
            return False
        return True
    domain = urlparse(url).netloc.lower()
    if any(d in domain for d in ['.ru', '.su', '.рф', 'russian', 'russia']):
        return True
    return False

def normalize_url(url):
    return url.rstrip('/').lower()

def get_channel_priority(name, url):
    """Умная сортировка: приоритет качественным каналам"""
    score = 0
    n = name.lower()
    u = url.lower()
    
    if 'hd' in n or 'fhd' in n or '4k' in n or 'uhd' in n:
        score += 10
    if 'full hd' in n:
        score += 8
    if '720' in n or '1080' in n:
        score += 5
    
    if 'первый канал' in n or 'россия 1' in n or 'нтв' in n:
        score += 15
    if 'match' in n or 'спорт' in n:
        score += 10
    if 'кино' in n or 'сериал' in n:
        score += 8
    
    if 'https' in u:
        score += 5
    if '.m3u8' in u:
        score += 3
    
    if 'iptv-org' in u or 'github' in u:
        score += 5
    if '.ru' in u or '.su' in u:
        score += 2
    
    return score

# ==================== ПАРСИНГ ФОРУМОВ ====================
def parse_forums_for_sources():
    """Парсит форумы для поиска новых источников"""
    logger.info("🔍 Парсинг форумов...")
    found = []
    forum_urls = [
        "https://sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026",
        "https://sat-portal.com/plejlisty/",
        "https://pikniktv.info/viewtopic.php?t=6737",
        "https://pikniktv.info/viewforum.php?f=328",
        "https://iptv-rus.com/playlists/",
        "https://vse-tv.net/playlists.html",
        "https://forumtv.org/viewforum.php?f=4",
        "https://webos-forums.ru/post167674.html",
        "https://new.m3u.su",  # Добавил новый сайт
        "https://m3u.su",      # И основной
    ]
    
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    for url in forum_urls:
        try:
            r = session.get(url, timeout=10, verify=False)
            if r.status_code != 200:
                continue
            
            text = r.text
            m3u_links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)\b', text, re.I)
            clean_links = [link.rstrip('.,);') for link in m3u_links]
            
            for link in clean_links:
                if any(kw in link.lower() for kw in ['iptv', 'playlist', 'm3u', 'tv']):
                    found.append(link)
            
            if clean_links:
                logger.info(f"✅ С {url} найдено {len(clean_links)} ссылок")
        except Exception as e:
            logger.debug(f"Ошибка парсинга {url}: {e}")
    
    return list(set(found))

# ==================== ЗАГРУЗКА ПЛЕЙЛИСТА ====================
def load_playlist():
    global playlist_cache, channel_count, is_loading
    
    if not load_lock.acquire(blocking=False):
        logger.info("⏳ Загрузка уже идет, пропускаем...")
        return
    
    is_loading = True
    logger.info("🚀 НАЧАЛО ЗАГРУЗКИ (350+ источников)")
    start_time = time.time()
    
    try:
        all_sources = list(SOURCES)
        
        # Добавляем источники с форумов
        forum_sources = parse_forums_for_sources()
        for src in forum_sources:
            if src not in all_sources:
                all_sources.append(src)
                logger.info(f"🔍 Добавлен новый источник: {src[:80]}")
        
        logger.info(f"📊 ВСЕГО ИСТОЧНИКОВ: {len(all_sources)}")
        
        entries = {}
        seen = set()
        loaded = 0
        failed = 0
        
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        
        retry_strategy = Retry(total=1, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=50, pool_maxsize=50)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = {executor.submit(session.get, url, timeout=15, verify=False): url for url in all_sources}
            
            for future in as_completed(futures):
                url = futures[future]
                try:
                    r = future.result()
                    if r.status_code == 200 and r.text:
                        loaded += 1
                        if loaded % 20 == 0:
                            logger.info(f"✅ Загружено {loaded} источников...")
                        
                        if '<html' in r.text[:500].lower():
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
                                
                                normalized_url = normalize_url(url_ch)
                                if normalized_url in seen:
                                    current_name = ''
                                    continue
                                
                                if not is_russian_channel(current_name, url_ch):
                                    current_name = ''
                                    continue
                                
                                paywall = ['wink', 'rt.ru', 'tvigle', 'megogo', 'okko', 'ivi', 'start.ru', 'more.tv']
                                if any(x in url_ch.lower() for x in paywall):
                                    current_name = ''
                                    continue
                                
                                if any(x in current_name.lower() for x in ['радио', 'radio', 'fm']):
                                    current_name = ''
                                    continue
                                
                                seen.add(normalized_url)
                                cat = get_category(current_name)
                                priority = get_channel_priority(current_name, url_ch)
                                key = re.sub(r'\s+', ' ', current_name.lower().strip())
                                
                                if key not in entries or entries[key]['priority'] < priority:
                                    entries[key] = {
                                        'url': url_ch,
                                        'name': current_name,
                                        'cat': cat,
                                        'priority': priority,
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
        
        # Умная сортировка: сначала по приоритету, потом по категориям
        cat_order = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 
                     'Детские', 'Музыка', 'Познавательные', 'Развлекательные', 
                     'Региональные', 'Общие']
        
        sorted_channels = sorted(entries.values(), 
                                key=lambda ch: (-ch['priority'], cat_order.index(ch['cat']) if ch['cat'] in cat_order else 99, ch['name']))
        
        # Ограничиваем до 15000 лучших
        if len(sorted_channels) > 15000:
            sorted_channels = sorted_channels[:15000]
        
        cat_counts = {}
        for ch in sorted_channels:
            cat_counts[ch['cat']] = cat_counts.get(ch['cat'], 0) + 1
        
        lines = [
            '#EXTM3U',
            f'# IPTV Russia AI ULTIMATE — {time.strftime("%Y-%m-%d %H:%M")}',
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
        
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        if playlist_cache == "#EXTM3U\n# Загрузка...\n":
            playlist_cache = "#EXTM3U\n# Ошибка загрузки. Попробуйте /refresh\n"
    finally:
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

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>IPTV Russia ULTIMATE</title>
        <style>
            body {{ font-family: system-ui; background: linear-gradient(135deg, #0f2027, #203a43, #2c5364); color: #fff; min-height: 100vh; margin: 0; display: flex; align-items: center; justify-content: center; }}
            .card {{ background: rgba(255,255,255,.1); backdrop-filter: blur(10px); border-radius: 20px; padding: 40px; max-width: 500px; width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,.4); }}
            h1 {{ margin: 0; font-size: 28px; }}
            .sub {{ opacity: .7; margin: 5px 0 20px; }}
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
            <div class="sub">🧠 ULTIMATE • 350+ источников • Умная сортировка</div>
            <div class="stat">{channel_count}</div>
            <p style="margin: -10px 0 20px;">каналов</p>
            <div>
                <a href="/playlist.m3u" class="btn green">📥 Скачать</a>
                <a href="/refresh" class="btn blue">🔄 Обновить</a>
                <a href="/status" class="btn gray">📊 Статус</a>
            </div>
            <div class="info">{'🔄 Загрузка...' if is_loading else '✅ Готово'} • Источников: {len(SOURCES)}</div>
        </div>
    </body>
    </html>
    """

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                   headers={'Content-Disposition': 'attachment; filename="iptv_russia_ultimate.m3u"'})

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

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск ULTIMATE версии на порту {port}")
    logger.info(f"📡 Источников: {len(SOURCES)}")
    
    threading.Thread(target=load_playlist, daemon=True).start()
    threading.Thread(target=background_worker, daemon=True).start()
    
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)