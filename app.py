import os
import re
import time
import logging
import threading
import requests
from flask import Flask, Response, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== 80+ ИСТОЧНИКОВ (СПЕЦИАЛЬНО ДЛЯ КИНО) ====================
SOURCES = [
    # iptv-org основные
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
    
    # КАТЕГОРИИ (все возможные)
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
    
    # Регионы РФ (все)
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
    
    # GitHub
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/smolnp/IPTVru/main/IPTVru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/ru.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_russia.m3u8",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/index.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    
    # Дополнительные
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
is_loading = False

# ==================== МАКСИМАЛЬНО РАСШИРЕННЫЕ КАТЕГОРИИ ====================
CATEGORIES = {
    'Новости': [
        'новост', 'news', '24', 'вести', 'известия', 'информ', 'события', 'факты',
        'репортаж', 'интервью', 'обзор', 'итоги', 'главное', 'сегодня', 'сейчас',
        'прямой эфир', 'live', 'breaking', 'экстрен', 'чп', 'происшеств',
        'euronews', 'bbc', 'cnn', 'политик', 'эконом', 'бизнес', 'business',
        'utro', 'утро', 'день', 'вечер', 'ночь', 'время', 'новости 24',
        'события', 'факт', 'информ-тв', 'вести-24'
    ],
    'Спорт': [
        'спорт', 'sport', 'футбол', 'хоккей', 'матч', 'ufc', 'бокс', 
        'киберспорт', 'esport', 'баскетбол', 'теннис', 'биатлон', 'лыжн',
        'khl', 'nhl', 'nba', 'формула', 'racing', 'волейбол', 'гандбол',
        'фигурное катание', 'гимнастика', 'плавание', 'легкая атлетика',
        'mma', 'единоборства', 'экстрим', 'скейт', 'сноуборд',
        'match tv', 'match!', 'спорт-1', 'спорт-2', 'спорт 1', 'спорт 2',
        'sport-1', 'sport-2', 'sport1', 'sport2', 'наш спорт', 'pro спорт',
        'поединок', 'боец', 'чемпион', 'турнир', 'кубок'
    ],
    'Кино и сериалы': [
        'кино', 'kino', 'movie', 'film', 'фильм', 'сериал', 'series', 
        'serial', 'cinema', 'tv1000', 'амедиа', 'дом кино', 'иллюзион',
        'премьера', 'боевик', 'детектив', 'мелодрама', 'комедия',
        'триллер', 'драма', 'приключение', 'вестерн', 'мюзикл',
        'фэнтези', 'фантастика', 'ужас', 'horror', 'криминал',
        'исторический', 'военный', 'киносвидание', 'киноужас',
        'kinopoisk', 'киномикс', 'киносемья', 'кинокомедия',
        'кинохит', 'кинопремьера', 'киношедевр', 'film zone',
        'кинотеатр', 'кинозал', 'киностудия', 'мосфильм', 'золотая коллекция',
        'золотой', 'коллекция', 'film', 'movie', 'канал кино', 'кино канал',
        'cinemax', 'hollywood', 'hd cinema', 'кино-тв', 'tv1000 action',
        'tv1000 русское', 'tv1000 comedy', 'tv1000 drama', 'tv1000 mega',
        'amedia', 'amedia premium', 'ame dia', 'filmbox', 'film box',
        'киноклуб', 'кинокомедия', 'кинороман', 'киносага', 'киноэпопея',
        'золотая серия', 'коллекция фильмов', 'русский фильм', 'советский фильм'
    ],
    'Детские': [
        'дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney', 'gulli', 
        'аниме', 'nick', 'tiji', 'baby', 'малыш', 'маленький', 'дошкольн',
        'развивай', 'обучай', 'сказк', 'игруш', 'кукл', 'лего',
        'peppa', 'папа', 'мама', 'няня', 'школа', 'класс',
        'детский', 'children', 'animation', 'anime', 'gulli',
        'познавай', 'учись', 'расти', 'малыши', 'карапуз', 'кроха',
        'мультик', 'мультфильм', 'мультсериал', 'детское кино'
    ],
    'Музыка': [
        'музык', 'music', 'mtv', 'bridge', 'шансон', 'рутв', 'ru.tv', 
        'ретро', 'хит', 'жара', 'блюз', 'jazz', 'классик', 'classic',
        'поп', 'рок', 'рэп', 'хип-хоп', 'эстрада', 'фолк', 'кантри',
        'джаз', 'опера', 'симфони', 'оркестр', 'хор', 'вокал',
        'muz-tv', 'муз-тв', 'муз тв', 'music box', 'звук', 'песня',
        'клип', 'хит-тв', 'музыкальный', 'песенный', 'вокальный'
    ],
    'Познавательные': [
        'докум', 'doc', 'познав', 'истори', 'history', 'discovery', 
        'science', 'наука', 'природ', 'animal', 'животн', 'океан', 
        'космос', 'культур', 'искусств', 'театр', 'музей',
        'географи', 'биолог', 'астроном', 'физик', 'химия', 'экологи',
        'техник', 'техно', 'авто', 'auto', 'дача', 'сад', 'огород',
        'рыбал', 'охота', 'кулинар', 'еда', 'food', 'здоров', 'health',
        'документальн', 'познавательн', 'образовательн',
        'national geographic', 'ngc', 'animal planet',
        'история', 'археология', 'палеонтолог', 'антрополог'
    ],
    'Развлекательные': [
        'развлек', 'entertainment', 'юмор', 'comedy', 'камеди', 
        'квн', 'шоу', 'мода', 'fashion', 'стиль', 'lifestyle',
        'лайфстайл', 'дом', 'home', 'семья', 'family', 'игры', 'game',
        'лотерея', 'анекдот', 'талант', 'конкурс', 'викторина',
        'ток-шоу', 'интервью', 'звезд', 'знаменитост',
        'развлекательн', 'юмористическ', 'прикол', 'смех', 'улыбка',
        'камеди-клаб', 'stand-up', 'стендап', 'юморина'
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
        'канал один', 'канал 1', '1 канал', 'channel 1',
        'россия ртр', 'ртр', 'rtr', 'ren', 'tnt', 'sts',
        'пульс', 'тв-3', 'тв3', 'че', 'четвертый канал', '4-й канал'
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
    """Проверка что канал русский"""
    if re.search(r'[а-яёА-ЯЁ]', name):
        ua_words = ['україн', 'украин', 'київ', 'kyiv', 'львів', 'харків', 'суспільне']
        if any(w in name.lower() for w in ua_words):
            return False
        return True
    
    domain = urlparse(url).netloc.lower()
    ru_domains = ['.ru', '.su', '.рф', 'russian', 'russia', 'ru-']
    if any(d in domain for d in ru_domains):
        return True
    
    ru_keywords = ['ru/', '/ru-', '-ru', 'russia', 'russian']
    if any(kw in url.lower() for kw in ru_keywords):
        return True
    
    return False

# ==================== ЗАГРУЗКА ====================
def load_playlist():
    global playlist_cache, is_loading
    if is_loading:
        return
    
    is_loading = True
    logger.info("🚀 НАЧАЛО ЗАГРУЗКИ (80+ источников)")
    start_time = time.time()
    
    entries = {}
    seen = set()
    loaded = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(requests.get, url, timeout=15, verify=False, headers={'User-Agent': 'Mozilla/5.0'}): url for url in SOURCES}
        
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
                            match = re.search(r',\s*(.+)$', line)
                            current_name = match.group(1).strip() if match else ''
                        elif line.startswith('http') and current_name:
                            url_ch = line
                            
                            if url_ch in seen:
                                current_name = ''
                                continue
                            
                            if not is_russian_channel(current_name, url_ch):
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
                            
                else:
                    failed += 1
            except Exception:
                failed += 1
    
    logger.info(f"📊 ЗАГРУЖЕНО: {loaded} источников, ошибок: {failed}")
    logger.info(f"📊 НАЙДЕНО: {len(entries)} уникальных каналов")
    
    if not entries:
        playlist_cache = "#EXTM3U\n# Нет каналов\n"
        is_loading = False
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
        f'# IPTV Russia AI PRO MAX 2.0 — {time.strftime("%Y-%m-%d %H:%M")}',
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

def background_worker():
    while True:
        try:
            logger.info("⏰ Плановое обновление...")
            load_playlist()
        except Exception as e:
            logger.error(f"💥 Фоновая ошибка: {e}")
        logger.info(f"⏰ Следующее обновление через 6 часов")
        time.sleep(21600)

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
        <title>IPTV Russia PRO MAX 2.0</title>
        <style>
            body {{ font-family: system-ui; background: linear-gradient(135deg, #0f2027, #203a43, #2c5364); color: #fff; min-height: 100vh; margin: 0; display: flex; align-items: center; justify-content: center; }}
            .card {{ background: rgba(255,255,255,.1); backdrop-filter: blur(10px); border-radius: 20px; padding: 40px; max-width: 550px; width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,.4); }}
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
            <div class="sub">🧠 AI PRO MAX 2.0 • 80+ источников</div>
            <div class="stat">{count}</div>
            <p style="margin: -10px 0 20px;">каналов</p>
            <div>
                <a href="/playlist.m3u" class="btn green">📥 Скачать</a>
                <a href="/refresh" class="btn blue">🔄 Обновить</a>
                <a href="/status" class="btn gray">📊 Статус</a>
            </div>
            <div class="info">
                Источников: {len(SOURCES)} | Загрузка: {'🔄 идёт...' if is_loading else '✅ завершена'}
            </div>
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
    logger.info(f"📡 Источников: {len(SOURCES)}")
    
    threading.Thread(target=load_playlist, daemon=True).start()
    threading.Thread(target=background_worker, daemon=True).start()
    
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)