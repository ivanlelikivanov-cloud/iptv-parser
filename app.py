import os
import re
import time
import logging
import threading
import requests
import urllib3
from collections import Counter
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== ИСТОЧНИКИ ====================
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
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
    "https://iptv-org.github.io/iptv/categories/general.m3u",
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
    "https://6x6.msk.ru/",
    "https://homtv.ru/",
    "https://iptv-rus.com/",
    "https://pikniktv.info/viewtopic.php?t=6737",
    "https://m3u.su/",
    "https://webarmen.com/my/iptv/",
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

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS = 12000
SOURCE_WORKERS = 25
CHECK_WORKERS = 100
CHECK_TIMEOUT = 10.0
UPDATE_EVERY = 86400

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
    "parsed_channels": 0,
    "alive_channels": 0,
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

# ==================== СБОР ИСТОЧНИКОВ ====================
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
        logger.info(f"API iptv-org: регионов РФ: {len(urls)}")
        return urls
    except Exception:
        return []

def fetch_source_text(url):
    for _ in range(2):
        try:
            r = get_session().get(url, timeout=15, headers=HEADERS_WEB, verify=False)
            if r.status_code == 200 and r.text:
                return r.text
            if r.status_code in (404, 410):
                return None
        except Exception:
            continue
    return None

# ==================== ФИЛЬТРЫ И КАТЕГОРИИ ====================
def get_category(name):
    n = name.lower()
    if any(w in n for w in ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney', 'gulli', 'о!']):
        return 'Детские'
    if any(w in n for w in ['новост', 'вести', 'информ', 'news', '24', 'известия', 'ртд', 'euronews', 'bbc', 'cnn']):
        return 'Новости'
    if any(w in n for w in ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'khl', 'ufc', 'бокс', 'киберспорт']):
        return 'Спорт'
    if any(w in n for w in ['кино', 'movie', 'film', 'фильм', 'сериал', 'series', 'cinema', 'tv1000', 'амедиа', 'дом кино']):
        return 'Кино и сериалы'
    if any(w in n for w in ['музык', 'music', 'radio', 'радио', 'mtv', 'bridge', 'шансон', 'хит fm', 'ретро']):
        return 'Музыка'
    if any(w in n for w in ['докум', 'doc', 'познав', 'истори', 'history', 'discovery', 'science', 'наука', 'природ', 'animal', 'культур', 'travel', 'путешеств']):
        return 'Познавательные'
    if any(w in n for w in ['развлек', 'entertainment', 'юмор', 'comedy', 'камеди', 'квн', 'шоу', 'кухн', 'еда', 'food', 'мода']):
        return 'Развлекательные'
    if any(w in n for w in ['первый канал', 'россия 1', 'россия к', 'нтв', 'тнт', 'стс', 'рен тв', 'пятый канал', 'тв центр', 'звезда', 'отр', 'пятница', 'суббота', 'домашний', 'муз-тв', '2x2']):
        return 'Федеральные'
    return 'Общие'

def is_adult(name):
    n = name.lower()
    bad = ['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'эротика', 'порно', 'nude', 'playboy']
    return any(w in n for w in bad)

def is_russian(name):
    return bool(re.search(r'[\u0400-\u04FF]', name))

def norm_name(name):
    n = name.lower().strip()
    n = re.sub(r'[\(\[].*?[\)\]]', '', n)
    n = re.sub(r'\b(hd|fhd|uhd|4k|sd|hevc|h265|h264)\b', '', n)
    return re.sub(r'\s+', ' ', n).strip(' -_|')

def is_hd(name):
    n = name.lower()
    return 'hd' in n or '4k' in n or 'uhd' in n or 'fhd' in n

# ==================== УМНАЯ ПРОВЕРКА (<= 10 сек) ====================
def check_one(url):
    session = get_session()
    start = time.monotonic()

    def remaining():
        return CHECK_TIMEOUT - (time.monotonic() - start)

    try:
        r = session.head(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER,
                         allow_redirects=True, verify=False)
        if r.status_code < 400 and remaining() > 0:
            ct = r.headers.get('content-type', '').lower()
            if any(g in ct for g in GOOD_CT):
                return True
    except Exception:
        pass

    for _ in range(2):
        if remaining() <= 0.5:
            return False
        try:
            r = session.get(url, timeout=remaining(), headers=HEADERS_PLAYER,
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

# ==================== ПАРСЕР (категории ВСЕГДА русские) ====================
def parse_m3u(text, entries, seen_urls):
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
            if (current_name and is_russian(current_name)
                    and not is_adult(current_name) and line not in seen_urls):
                seen_urls.add(line)
                cat = get_category(current_name)
                # Вырезаем чужие group-title и ставим свой русский
                inf = re.sub(r'\s*group-title="[^"]*"', '', current_inf)
                inf = re.sub(r'(#EXTINF:-?\d+)', r'\1 group-title="' + cat + '"', inf, count=1)
                ch = {'inf': inf, 'url': line, 'cat': cat, 'name': current_name}
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

# ==================== ОБНОВЛЕНИЕ ====================
def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    start = time.time()
    logger.info("🔄 Старт: поиск потоков и сбор плейлистов...")

    try:
        regions = fetch_ru_regions()
        if not regions:
            regions = ['https://iptv-org.github.io/iptv/regions/' + r + '.m3u'
                       for r in FALLBACK_REGIONS]
        sources = list(set(STATIC_SOURCES + regions + fetch_dynamic()))
        logger.info(f"Всего источников: {len(sources)}")

        texts = []
        with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as ex:
            for txt in ex.map(fetch_source_text, sources):
                if txt:
                    texts.append(txt)
        logger.info(f"Загружено плейлистов: {len(texts)}")

        entries = {}
        seen = set()
        for txt in texts:
            if parse_m3u(txt, entries, seen):
                break
        raw = list(entries.values())
        logger.info(f"Уникальных каналов: {len(raw)}. Проверка (<= 10 сек)...")

        alive = []
        with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as ex:
            futs = {ex.submit(check_one, ch['url']): ch for ch in raw}
            for f in as_completed(futs):
                ch = futs[f]
                try:
                    if f.result():
                        alive.append(ch)
                except Exception:
                    pass

        def sort_key(ch):
            try:
                i = CAT_ORDER.index(ch['cat'])
            except ValueError:
                i = len(CAT_ORDER)
            return (i, ch['name'].lower())

        alive.sort(key=sort_key)
        cat_counts = Counter(ch['cat'] for ch in alive)

        lines = [
            '#EXTM3U',
            '# IPTV Russia Pro | ' + time.strftime('%Y-%m-%d %H:%M'),
            '# Живых каналов: ' + str(len(alive)) + ' | отклик <= 10 сек | без 18+',
        ]
        for ch in alive:
            lines.append(ch['inf'])
            lines.append(ch['url'])

        elapsed = time.time() - start
        with cache_lock:
            playlist_cache = '\n'.join(lines)
            stats.update({
                'last_update': time.strftime('%Y-%m-%d %H:%M:%S'),
                'duration_sec': round(elapsed, 1),
                'sources_total': len(sources),
                'playlists_loaded': len(texts),
                'parsed_channels': len(raw),
                'alive_channels': len(alive),
                'categories': dict(cat_counts),
            })
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
        time.sleep(UPDATE_EVERY)

threading.Thread(target=background_worker, daemon=True).start()

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
HOME_TEMPLATE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IPTV Russia Pro</title>
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
<h1>🇷🇺 IPTV Russia Pro</h1>
<div class="sub">Автопоиск потоков • проверка каждого канала • обновление раз в 24 ч</div>
<a class="btn" href="/playlist.m3u">📥 Скачать плейлист</a>
<a class="btn blue" href="/refresh">🔄 Обновить</a>
<a class="btn gray" href="/status">📊 JSON</a>
<div class="stats">
<div class="stat"><b>__ALIVE__</b><span>живых каналов</span></div>
<div class="stat"><b>__PARSED__</b><span>проверено</span></div>
<div class="stat"><b>__SOURCES__</b><span>источников</span></div>
<div class="stat"><b>__DURATION__</b><span>сек. проверки</span></div>
</div>
<div class="sub">Обновлено: __UPDATED__</div>
<div>__CATS__</div>
</div></body></html>"""

@app.route('/')
def home():
    with cache_lock:
        s = dict(stats)
    cats = s.get('categories', {})
    cat_html = ''
    for k, v in sorted(cats.items(), key=lambda kv: -kv[1]):
        cat_html += '<span class="chip">' + k + ': ' + str(v) + '</span>'
    page = HOME_TEMPLATE
    page = page.replace('__ALIVE__', str(s.get('alive_channels', 0)))
    page = page.replace('__PARSED__', str(s.get('parsed_channels', 0)))
    page = page.replace('__SOURCES__', str(s.get('sources_total', 0)))
    page = page.replace('__DURATION__', str(s.get('duration_sec', 0)))
    page = page.replace('__UPDATED__', str(s.get('last_update') or 'ещё идёт первая проверка...'))
    page = page.replace('__CATS__', cat_html)
    return page

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    with cache_lock:
        resp = Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')
        resp.headers['Content-Disposition'] = 'attachment; filename="iptv_russia_pro.m3u"'
        resp.headers['Cache-Control'] = 'public, max-age=3600'
        return resp

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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск на порту {port}")
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=12)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)