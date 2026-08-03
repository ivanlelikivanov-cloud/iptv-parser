import os
import re
import time
import logging
import threading
import requests
import urllib3
from urllib.parse import unquote
from collections import Counter
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== СТАТИКА ====================
STATIC_SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/languages/tat.m3u",
    "https://iptv-org.github.io/iptv/languages/che.m3u",
    "https://iptv-org.github.io/iptv/languages/bak.m3u",
    "https://iptv-org.github.io/iptv/languages/chv.m3u",
    "https://iptv-org.github.io/iptv/languages/udm.m3u",
    "https://iptv-org.github.io/iptv/languages/sah.m3u",
    "https://iptv-org.github.io/iptv/countries/by.m3u",
    "https://iptv-org.github.io/iptv/countries/kz.m3u",
    "https://iptv-org.github.io/iptv/countries/kg.m3u",
    "https://iptv-org.github.io/iptv/countries/uz.m3u",
    "https://iptv-org.github.io/iptv/countries/am.m3u",
    "https://iptv-org.github.io/iptv/countries/az.m3u",
    "https://iptv-org.github.io/iptv/countries/ge.m3u",
    "https://iptv-org.github.io/iptv/countries/md.m3u",
    "https://iptv-org.github.io/iptv/countries/tj.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
    "https://iptv-org.github.io/iptv/categories/general.m3u",
    "https://iptv-org.github.io/iptv/categories/family.m3u",
    "https://iptv-org.github.io/iptv/categories/culture.m3u",
    "https://iptv-org.github.io/iptv/categories/education.m3u",
    "https://iptv-org.github.io/iptv/categories/food.m3u",
    "https://iptv-org.github.io/iptv/categories/travel.m3u",
    "https://iptv-org.github.io/iptv/categories/comedy.m3u",
    "https://iptv-org.github.io/iptv/categories/series.m3u",
    "https://iptv-org.github.io/iptv/categories/animation.m3u",
    "https://iptv-org.github.io/iptv/categories/lifestyle.m3u",
    "https://iptv-org.github.io/iptv/categories/outdoor.m3u",
    "https://iptv-org.github.io/iptv/categories/weather.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
]

HTML_SOURCES = [
    "https://sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026",
    "https://sat-portal.com/plejlisty/",
    "https://6x6.msk.ru/",
    "https://homtv.ru/",
    "https://iptv-rus.com/",
    "https://pikniktv.info/viewtopic.php?t=6737",
    "https://m3u.su/",
    "https://webarmen.com/my/iptv/",
    "https://go2tv.top/",
    "https://iptv.one/",
]

FALLBACK_REGIONS = [
    "ru-kgd", "ru-mow", "ru-mos", "ru-spe", "ru-len",
    "ru-kda", "ru-ros", "ru-vgg", "ru-sta", "ru-da",
    "ru-sam", "ru-ud", "ru-ta", "ru-ba", "ru-udm",
    "ru-per", "ru-sve", "ru-che", "ru-tyu",
    "ru-oms", "ru-nvs", "ru-tom", "ru-kem", "ru-alt",
    "ru-kya", "ru-irk", "ru-bu", "ru-sa", "ru-zab",
    "ru-pri", "ru-kha", "ru-amu", "ru-sak", "ru-mag", "ru-kam", "ru-chu",
]

GITHUB_QUERIES = ['iptv ru', 'iptv russia', 'm3u ru', 'iptv playlist',
                  'topic:iptv', 'm3u8 ru', 'iptv m3u russia']
GH_COMMON_PATHS = ['ru.m3u', 'playlist.m3u', 'iptv.m3u', 'tv.m3u', 'main.m3u',
                   'index.m3u', 'channels/ru.m3u', 'playlist.m3u8', 'ru.m3u8']
PROBE_PATHS = ['ru.m3u', 'playlist.m3u', 'iptv.m3u', 'tv.m3u']
WEB_QUERIES = ['iptv m3u ru', 'плейлист iptv m3u россия', 'iptv playlist m3u8 russia',
               'iptv m3u8 ru бесплатно', 'плейлист тв каналов m3u',
               'site:t.me iptv m3u', 'iptv плейлист форум бесплатно 2026',
               'telegram канал iptv плейлист m3u']
TG_CHANNELS = ['iptvru', 'iptv_russia', 'russian_iptv', 'iptv_m3u', 'freeiptv_ru',
               'iptv_playlist', 'm3u_playlist', 'iptvfree', 'tv_playlist',
               'iptv_rf', 'playlist_iptv', 'iptv_su', 'iptv_channel',
               'free_iptv_ru', 'iptv_list', 'ru_iptv', 'iptv_tv_ru',
               'iptv_playlists']

BLACKLIST_WORDS = ['fifa', 'world cup', 'чемпионат мира', 'плей-офф']

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS = 15000
MAX_EXTRA_SOURCES = 400
SOURCE_WORKERS = 40
CHECK_WORKERS = 100
CHECK_TIMEOUT = 40.0
UPDATE_EVERY = 86400
RETRY_IF_EMPTY = 600
FLUSH_EVERY = 15

CIS_COUNTRIES = {'RU', 'BY', 'KZ', 'KG', 'UZ', 'AM', 'AZ', 'GE', 'MD', 'TJ'}

CAT_ORDER = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт',
             'Детские', 'Музыка', 'Познавательные', 'Развлекательные', 'Общие']

playlist_cache = "#EXTM3U\n# IPTV Russia Pro — идёт первая проверка каналов...\n"
cache_lock = threading.Lock()
is_updating = False
stats = {
    "last_update": None,
    "duration_sec": 0,
    "sources_total": 0,
    "playlists_loaded": 0,
    "api_streams": 0,
    "parsed_channels": 0,
    "alive_channels": 0,
    "filtered": {},
    "categories": {},
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}
GOOD_CT = ('video/', 'audio/', 'mpegurl', 'octet-stream', 'mp2t')

_thread_local = threading.local()

def get_session():
    s = getattr(_thread_local, 'session', None)
    if s is None:
        s = requests.Session()
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=0)
        s.mount('http://', adapter)
        s.mount('https://', adapter)
        _thread_local.session = s
    return s

# ==================== РАЗВЕДКА ====================
def fetch_dynamic():
    found = set()
    for page in HTML_SOURCES:
        try:
            r = get_session().get(page, headers=HEADERS_WEB, timeout=10, verify=False)
            if r.status_code == 200:
                found.update(re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text, re.I))
        except Exception:
            pass
    return list(found)

def fetch_ru_regions():
    try:
        r = get_session().get("https://iptv-org.github.io/api/regions.json",
                              timeout=10, headers=HEADERS_WEB)
        if r.status_code != 200:
            return []
        urls = []
        for reg in r.json():
            code = str(reg.get('code', ''))
            if code.upper().startswith('RU-'):
                urls.append('https://iptv-org.github.io/iptv/regions/' + code.lower() + '.m3u')
        return urls
    except Exception:
        return []

def fetch_github():
    sess = get_session()
    gh_headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/vnd.github+json'}
    repos = []
    for q in GITHUB_QUERIES:
        try:
            r = sess.get('https://api.github.com/search/repositories',
                         params={'q': q, 'per_page': 20, 'sort': 'stars', 'order': 'desc'},
                         headers=gh_headers, timeout=15)
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    full = item.get('full_name')
                    branch = item.get('default_branch') or 'main'
                    if full:
                        repos.append((full, branch))
        except Exception:
            continue
    repos = list(dict.fromkeys(repos))[:60]
    logger.info(f"GitHub: репозиториев: {len(repos)}")

    found = set()

    def read_readme(repo_branch):
        full, branch = repo_branch
        try:
            r = get_session().get('https://raw.githubusercontent.com/' + full + '/' + branch + '/README.md',
                                  headers=HEADERS_WEB, timeout=10)
            if r.status_code == 200:
                return re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', r.text, re.I)
        except Exception:
            pass
        return []

    with ThreadPoolExecutor(max_workers=20) as ex:
        for links in ex.map(read_readme, repos):
            found.update(links)

    for full, branch in repos:
        base = 'https://raw.githubusercontent.com/' + full + '/' + branch
        for path in GH_COMMON_PATHS:
            found.add(base + '/' + path)
    return list(found)

def fetch_gitlab():
    found = set()
    try:
        r = get_session().get('https://gitlab.com/api/v4/projects',
                              params={'search': 'iptv', 'per_page': 20},
                              headers=HEADERS_WEB, timeout=15)
        if r.status_code == 200:
            for p in r.json():
                path = p.get('path_with_namespace')
                branch = p.get('default_branch') or 'main'
                if path:
                    for pth in PROBE_PATHS:
                        found.add('https://gitlab.com/' + path + '/-/raw/' + branch + '/' + pth)
    except Exception:
        pass
    return list(found)

def fetch_bitbucket():
    found = set()
    try:
        r = get_session().get('https://api.bitbucket.org/2.0/repositories',
                              params={'q': 'name ~ "iptv"', 'pagelen': 20},
                              headers=HEADERS_WEB, timeout=15)
        if r.status_code == 200:
            for v in r.json().get('values', []):
                full = v.get('full_name')
                branch = (v.get('mainbranch') or {}).get('name') or 'master'
                if full:
                    for pth in PROBE_PATHS:
                        found.add('https://bitbucket.org/' + full + '/raw/' + branch + '/' + pth)
    except Exception:
        pass
    return list(found)

def fetch_gitea_family():
    found = set()
    apis = [
        ('https://codeberg.org/api/v1/repos/search?q=iptv&limit=15',
         'https://codeberg.org/', '/raw/branch/'),
        ('https://gitea.com/api/v1/repos/search?q=iptv&limit=15',
         'https://gitea.com/', '/raw/'),
    ]
    for url, base, rawfmt in apis:
        try:
            r = get_session().get(url, headers=HEADERS_WEB, timeout=15)
            if r.status_code == 200:
                for repo in r.json().get('data', []):
                    full = repo.get('full_name')
                    branch = repo.get('default_branch') or 'main'
                    if full:
                        for pth in PROBE_PATHS:
                            found.add(base + full + rawfmt + branch + '/' + pth)
        except Exception:
            continue
    return list(found)

def fetch_web_search():
    m3u = set()
    pages = []
    for q in WEB_QUERIES:
        try:
            r = get_session().get('https://html.duckduckgo.com/html/',
                                  params={'q': q}, headers=HEADERS_WEB, timeout=15)
            if r.status_code != 200:
                continue
            m3u.update(re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', r.text, re.I))
            for enc in re.findall(r'uddg=([^&"]+)', r.text):
                pages.append(unquote(enc))
        except Exception:
            continue

    def scrape(page):
        try:
            r = get_session().get(page, headers=HEADERS_WEB, timeout=10, verify=False)
            if r.status_code == 200:
                return re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', r.text, re.I)
        except Exception:
            pass
        return []

    with ThreadPoolExecutor(max_workers=10) as ex:
        for links in ex.map(scrape, pages[:40]):
            m3u.update(links)
    logger.info(f"Веб-поиск: ссылок: {len(m3u)}")
    return list(m3u)

def fetch_telegram():
    found = set()
    for ch in TG_CHANNELS:
        try:
            r = get_session().get('https://t.me/s/' + ch, headers=HEADERS_WEB, timeout=10)
            if r.status_code == 200:
                found.update(re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', r.text, re.I))
        except Exception:
            continue
    logger.info(f"Telegram: ссылок: {len(found)}")
    return list(found)

def fetch_iptv_org_api():
    try:
        sess = get_session()
        ch_r = sess.get("https://iptv-org.github.io/api/channels.json",
                        timeout=60, headers=HEADERS_WEB)
        st_r = sess.get("https://iptv-org.github.io/api/streams.json",
                        timeout=60, headers=HEADERS_WEB)
        if ch_r.status_code != 200 or st_r.status_code != 200:
            return []
        names = {}
        for ch in ch_r.json():
            if ch.get('is_nsfw'):
                continue
            if ch.get('country') == 'UA':
                continue
            langs = []
            for lng in (ch.get('languages') or []):
                langs.append(lng.get('code') if isinstance(lng, dict) else lng)
            if ch.get('country') in CIS_COUNTRIES or 'rus' in langs:
                names[ch.get('id')] = ch.get('name', '')
        result = []
        for s in st_r.json():
            cid = s.get('channel')
            url = s.get('url')
            if cid in names and url and url.startswith('http'):
                result.append({
                    'url': url,
                    'name': names[cid],
                    'ua': s.get('user_agent') or '',
                    'ref': s.get('http_referrer') or '',
                })
        return result
    except Exception as e:
        logger.error(f"Ошибка API iptv-org: {e}")
        return []

def fetch_source_text(url):
    try:
        r = get_session().get(url, timeout=15, headers=HEADERS_WEB, verify=False)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return None

# ==================== ФИЛЬТРЫ (без пустых строк!) ====================
def get_category(name):
    n = name.lower()
    if any(w in n for w in ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney', 'gulli']):
        return 'Детские'
    if any(w in n for w in ['новост', 'вести', 'информ', 'news', '24', 'известия', 'ртд', 'euronews', 'bbc', 'cnn']):
        return 'Новости'
    if any(w in n for w in ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'khl', 'ufc', 'бокс', 'киберспорт']):
        return 'Спорт'
    if any(w in n for w in ['кино', 'movie', 'film', 'фильм', 'сериал', 'series', 'cinema', 'tv1000', 'амедиа', 'дом кино']):
        return 'Кино и сериалы'
    if any(w in n for w in ['музык', 'music', 'radio', 'радио', 'mtv', 'bridge', 'шансон', 'ретро']):
        return 'Музыка'
    if any(w in n for w in ['докум', 'doc', 'познав', 'истори', 'history', 'discovery', 'science', 'наука', 'природ', 'animal', 'культур', 'travel', 'путешеств']):
        return 'Познавательные'
    if any(w in n for w in ['развлек', 'entertainment', 'юмор', 'comedy', 'камеди', 'квн', 'шоу', 'кухн', 'еда', 'food', 'мода']):
        return 'Развлекательные'
    if any(w in n for w in ['первый канал', 'россия 1', 'россия к', 'нтв', 'тнт', 'стс', 'рен тв', 'пятый канал', 'тв центр', 'звезда', 'отр', 'пятница', 'суббота', 'домашний', 'муз-тв', '2x2']):
        return 'Федеральные'
    return 'Общие'

ADULT_WORDS = ['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'эротика', 'порно', 'nude', 'playboy']
UA_WORDS = ['україн', 'украина', 'україна', 'kyiv', 'kiev', 'київ', 'львів', 'львов',
            'харків', 'дніпро', 'одеса', 'суспільне', 'суспильне', 'прямий', 'тсн',
            '1+1', '2+2', 'інтер', 'inter ua', 'верес', 'тоніс', 'тонис',
            'ua: ', 'ua |', '| ua', ' ukraine', 'украинск']
PAYWALL_WORDS = ['подписк', 'subscription', 'оплат', 'payment', 'купить', 'продаж',
                 'whatsapp', 'telegram', 't.me', 'promo', 'реклам', 'advert',
                 'магазин', 'shop', 'store', 'premium', 'премиум', 'vip', 'вип',
                 'ppv', 'pay per view', 'активация', 'iptv', 'fifa', 'world cup',
                 'чемпионат мира', 'плей-офф', 'плей офф', 'тариф', 'абонент',
                 'цена', 'price', 'доступ', 'access',
                 '💳', '', '🛒', '💵', '💸', '💎', '🎁', '🔥', '⚽', '']

def is_adult(name):
    n = name.lower()
    return any(w in n for w in ADULT_WORDS)

def is_ukrainian(name):
    n = name.lower()
    return any(w in n for w in UA_WORDS)

def is_paywall(name):
    n = name.lower()
    if any(w in n for w in PAYWALL_WORDS):
        return True
    if BLACKLIST_WORDS and any(w.lower() in n for w in BLACKLIST_WORDS):
        return True
    return False

def is_russian(name):
    return bool(re.search(r'[\u0400-\u04FF]', name))

def reject_reason(name):
    """Почему канал отклонён, или None если канал годный"""
    if not is_russian(name):
        return 'not_ru'
    if is_adult(name):
        return 'adult'
    if is_ukrainian(name):
        return 'ua'
    if is_paywall(name):
        return 'paywall'
    return None

def norm_name(name):
    n = name.lower().strip()
    n = re.sub(r'[\(\[].*?[\)\]]', '', n)
    n = re.sub(r'\b(hd|fhd|uhd|4k|sd|hevc|h265|h264)\b', '', n)
    return re.sub(r'\s+', ' ', n).strip(' -_|')

def is_hd(name):
    n = name.lower()
    return 'hd' in n or '4k' in n or 'uhd' in n or 'fhd' in n

# ==================== ПРОВЕРКА (<= 40 сек) ====================
def check_one(ch):
    url = ch['url']
    headers = dict(HEADERS_PLAYER)
    if ch.get('ua'):
        headers['User-Agent'] = ch['ua']
    if ch.get('ref'):
        headers['Referer'] = ch['ref']

    session = get_session()
    start = time.monotonic()

    def remaining():
        return CHECK_TIMEOUT - (time.monotonic() - start)

    try:
        r = session.head(url, timeout=min(10, CHECK_TIMEOUT), headers=headers,
                         allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(g in ct for g in GOOD_CT):
                return True
    except Exception:
        pass

    for _ in range(2):
        if remaining() <= 1:
            return False
        try:
            r = session.get(url, timeout=remaining(), headers=headers,
                            stream=True, allow_redirects=True, verify=False)
        except Exception:
            continue

        if r.status_code >= 400:
            return False

        ct = r.headers.get('content-type', '').lower()
        try:
            chunk = next(r.iter_content(chunk_size=2048), b'')
        except Exception:
            continue
        finally:
            r.close()

        if not chunk:
            return False
        if any(g in ct for g in GOOD_CT):
            return True
        if chunk[:1] == b'\x47':
            return True
        low = chunk[:300].lower()
        if b'#extm3u' in low or b'#extinf' in low:
            return True
        if b'<html' in low or b'<!doctype' in low or b'access denied' in low:
            return False
        if b'\x00' in low:
            return True
        return False

    return False

# ==================== ПАРСЕР (со статистикой фильтров) ====================
def parse_m3u(text, entries, seen_urls, reasons):
    current_inf = ''
    current_name = ''
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#EXTINF:'):
            current_inf = line
            m = re.search(r',\s*(.+)$', line)
            current_name = m.group(1).strip() if m else ''
        elif line.startswith('http'):
            if current_name:
                reason = reject_reason(current_name)
                if reason:
                    reasons[reason] += 1
                elif line not in seen_urls:
                    seen_urls.add(line)
                    cat = get_category(current_name)
                    inf = re.sub(r'\s*group-title="[^"]*"', '', current_inf)
                    inf = re.sub(r'(#EXTINF:-?\d+)', r'\1 group-title="' + cat + '"', inf, count=1)
                    ch = {'inf': inf, 'url': line, 'cat': cat,
                          'name': current_name, 'ua': '', 'ref': ''}
                    key = norm_name(current_name)
                    if key in entries:
                        if is_hd(current_name) and not is_hd(entries[key]['name']):
                            entries[key] = ch
                    else:
                        entries[key] = ch
                        if len(entries) >= MAX_CHANNELS:
                            return True
            current_inf = ''
            current_name = ''
    return False

# ==================== ПОСТЕПЕННАЯ СБОРКА ====================
def flush_playlist(alive, elapsed=None):
    global playlist_cache

    def sort_key(ch):
        try:
            i = CAT_ORDER.index(ch['cat'])
        except ValueError:
            i = len(CAT_ORDER)
        return (i, ch['name'].lower())

    alive_sorted = sorted(alive, key=sort_key)
    cat_counts = Counter(ch['cat'] for ch in alive_sorted)
    lines = [
        '#EXTM3U',
        '# IPTV Russia Pro MAX | ' + time.strftime('%Y-%m-%d %H:%M'),
        '# Живых каналов: ' + str(len(alive_sorted)) + ' | без 18+ | без UA | без подписок',
    ]
    for ch in alive_sorted:
        lines.append(ch['inf'])
        lines.append(ch['url'])
    with cache_lock:
        playlist_cache = '\n'.join(lines)
        stats['alive_channels'] = len(alive_sorted)
        stats['categories'] = dict(cat_counts)
        if elapsed is not None:
            stats['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
            stats['duration_sec'] = round(elapsed, 1)

# ==================== ОБНОВЛЕНИЕ ====================
def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    start = time.time()
    logger.info("🔄 Старт: разведка ВСЕХ платформ + форумы + TG...")

    try:
        api_channels = fetch_iptv_org_api()
        logger.info(f"API iptv-org: потоков РФ/СНГ (без UA): {len(api_channels)}")

        regions = fetch_ru_regions()
        if not regions:
            regions = ['https://iptv-org.github.io/iptv/regions/' + r + '.m3u'
                       for r in FALLBACK_REGIONS]

        base = list(set(STATIC_SOURCES + regions))
        extra = list(set(fetch_dynamic() + fetch_github() + fetch_gitlab()
                         + fetch_bitbucket() + fetch_gitea_family()
                         + fetch_web_search() + fetch_telegram()) - set(base))
        sources = base + extra[:MAX_EXTRA_SOURCES]
        logger.info(f"ВСЕГО источников: {len(sources)}")

        texts = []
        with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as ex:
            for txt in ex.map(fetch_source_text, sources):
                if txt:
                    texts.append(txt)
        logger.info(f"Загружено плейлистов: {len(texts)}")

        entries = {}
        seen = set()
        reasons = Counter()

        for ach in api_channels:
            name = ach['name']
            if not name:
                continue
            reason = reject_reason(name)
            if reason:
                reasons[reason] += 1
                continue
            url = ach['url']
            if url in seen:
                continue
            seen.add(url)
            cat = get_category(name)
            inf = '#EXTINF:-1 group-title="' + cat + '",' + name
            key = norm_name(name)
            new_ch = {'inf': inf, 'url': url, 'cat': cat,
                      'name': name, 'ua': ach['ua'], 'ref': ach['ref']}
            if key in entries:
                if is_hd(name) and not is_hd(entries[key]['name']):
                    entries[key] = new_ch
            else:
                entries[key] = new_ch

        for txt in texts:
            if parse_m3u(txt, entries, seen, reasons):
                break

        logger.info(f"Фильтры вырезали: {dict(reasons)}")
        with cache_lock:
            stats['filtered'] = dict(reasons)

        raw = list(entries.values())
        if not raw:
            logger.error("⚠️ ВСЕ каналы отфильтрованы! Проверь списки слов!")
        with cache_lock:
            stats['sources_total'] = len(sources)
            stats['playlists_loaded'] = len(texts)
            stats['api_streams'] = len(api_channels)
            stats['parsed_channels'] = len(raw)
        logger.info(f"Уникальных каналов: {len(raw)}. Проверка (<= 40 сек, {CHECK_WORKERS} потоков)...")

        alive = []
        since_flush = 0
        with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as ex:
            futs = {ex.submit(check_one, ch): ch for ch in raw}
            for f in as_completed(futs):
                ch = futs[f]
                try:
                    if f.result():
                        alive.append(ch)
                        since_flush += 1
                        if since_flush >= FLUSH_EVERY:
                            flush_playlist(alive)
                            logger.info(f"Промежуточный флэш: {len(alive)} живых")
                            since_flush = 0
                except Exception:
                    pass

        elapsed = time.time() - start
        flush_playlist(alive, elapsed=elapsed)
        logger.info(f"✅ Готово: {len(alive)} живых из {len(raw)} за {elapsed:.0f} сек")

    except Exception as e:
        logger.error(f"Ошибка обновления: {e}")
    finally:
        is_updating = False

def background_worker():
    global is_updating
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Фоновая ошибка: {e}")
            is_updating = False
        with cache_lock:
            alive_n = stats['alive_channels']
        wait = UPDATE_EVERY if alive_n > 0 else RETRY_IF_EMPTY
        logger.info(f"Следующая попытка через {wait // 60} мин")
        time.sleep(wait)

threading.Thread(target=background_worker, daemon=True).start()

# ==================== ВЕБ ====================
def make_playlist_response():
    with cache_lock:
        data = playlist_cache
    resp = Response(data, mimetype='application/vnd.apple.mpegurl')
    resp.headers['Content-Disposition'] = 'attachment; filename="iptv_russia_max.m3u"'
    has_channels = '\nhttp' in data
    resp.headers['Cache-Control'] = 'public, max-age=3600' if has_channels else 'no-store'
    return resp

HOME_TEMPLATE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IPTV Russia Pro MAX</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:rgba(255,255,255,.08);backdrop-filter:blur(10px);border-radius:20px;padding:40px;max-width:640px;width:92%;box-shadow:0 20px 60px rgba(0,0,0,.4)}
h1{margin:0 0 8px;font-size:32px}
.sub{opacity:.7;margin-bottom:24px}
.btn{display:inline-block;background:#4caf50;color:#fff;text-decoration:none;padding:14px 28px;border-radius:12px;font-size:18px;font-weight:600;margin:8px 8px 8px 0}
.btn.blue{background:#2196f3}.btn.gray{background:#607d8b}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:24px 0}
.stat{background:rgba(255,255,255,.1);border-radius:12px;padding:14px;text-align:center}
.stat b{display:block;font-size:24px}
.stat span{opacity:.7;font-size:12px}
.chip{display:inline-block;background:rgba(255,255,255,.15);border-radius:20px;padding:6px 14px;margin:4px;font-size:13px}
</style></head><body><div class="card">
<h1>🇷 IPTV Russia Pro MAX</h1>
<div class="sub">Форумы + TG + 8 платформ • Без 18+ • Без UA • Без подписок</div>
<a class="btn" href="/playlist.m3u">📥 Скачать плейлист</a>
<a class="btn blue" href="/refresh">🔄 Обновить</a>
<a class="btn gray" href="/status">📊 JSON</a>
<div class="stats">
<div class="stat"><b>__ALIVE__</b><span>живых каналов</span></div>
<div class="stat"><b>__PARSED__</b><span>проверено</span></div>
<div class="stat"><b>__API__</b><span>потоков из API</span></div>
<div class="stat"><b>__DURATION__</b><span>сек. проверки</span></div>
</div>
<div class="sub">Обновлено: __UPDATED__</div>
<div>__CATS__</div>
</div></body></html>"""

def make_home_page():
    with cache_lock:
        s = dict(stats)
    cats = s.get('categories', {})
    cat_html = ''
    for k, v in sorted(cats.items(), key=lambda kv: -kv[1]):
        cat_html += '<span class="chip">' + k + ': ' + str(v) + '</span>'
    page = HOME_TEMPLATE
    page = page.replace('__ALIVE__', str(s.get('alive_channels', 0)))
    page = page.replace('__PARSED__', str(s.get('parsed_channels', 0)))
    page = page.replace('__API__', str(s.get('api_streams', 0)))
    page = page.replace('__DURATION__', str(s.get('duration_sec', 0)))
    page = page.replace('__UPDATED__', str(s.get('last_update') or 'ещё идёт первая проверка...'))
    page = page.replace('__CATS__', cat_html)
    return page

@app.route('/')
def home():
    return make_home_page()

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
@app.route('/playlist')
@app.route('/tv.m3u')
@app.route('/iptv.m3u')
def playlist():
    return make_playlist_response()

@app.route('/status')
def status():
    with cache_lock:
        data = dict(stats)
    data['is_updating'] = is_updating
    return jsonify(data)

@app.route('/refresh')
def refresh():
    if is_updating:
        return jsonify({'status': 'already_updating'})
    threading.Thread(target=update_cache, daemon=True).start()
    return jsonify({'status': 'refresh_started'})

@app.route('/<path:any_path>')
def fallback(any_path):
    p = any_path.lower()
    if p.endswith(('.m3u', '.m3u8')) or 'playlist' in p or 'm3u' in p:
        return make_playlist_response()
    return make_home_page()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск на порту {port}")
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)