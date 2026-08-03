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
    # iptv-org: страна и язык
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    # Языки народов России
    "https://iptv-org.github.io/iptv/languages/tat.m3u",
    "https://iptv-org.github.io/iptv/languages/che.m3u",
    "https://iptv-org.github.io/iptv/languages/bak.m3u",
    "https://iptv-org.github.io/iptv/languages/chv.m3u",
    "https://iptv-org.github.io/iptv/languages/udm.m3u",
    "https://iptv-org.github.io/iptv/languages/sah.m3u",
    # СНГ с русскоязычным вещанием
    "https://iptv-org.github.io/iptv/countries/by.m3u",
    "https://iptv-org.github.io/iptv/countries/kz.m3u",
    "https://iptv-org.github.io/iptv/countries/kg.m3u",
    "https://iptv-org.github.io/iptv/countries/uz.m3u",
    "https://iptv-org.github.io/iptv/countries/am.m3u",
    "https://iptv-org.github.io/iptv/countries/az.m3u",
    "https://iptv-org.github.io/iptv/countries/ge.m3u",
    "https://iptv-org.github.io/iptv/countries/md.m3u",
    # Глобальные категории (кириллица отфильтрует русские)
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
    "https://iptv-org.github.io/iptv/categories/general.m3u",
    # Зеркала GitHub
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    # Прямые плейлисты
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

# Резервные регионы РФ по часовым поясам
FALLBACK_REGIONS = [
    "ru-kgd",
    "ru-mow", "ru-mos", "ru-spe", "ru-len",
    "ru-kda", "ru-ros", "ru-vgg", "ru-sta", "ru-da",
    "ru-sam", "ru-ud", "ru-ta", "ru-ba", "ru-udm",
    "ru-per", "ru-sve", "ru-che", "ru-tyu",
    "ru-oms", "ru-nvs", "ru-tom", "ru-kem", "ru-alt",
    "ru-kya", "ru-irk", "ru-bu",
    "ru-sa", "ru-zab",
    "ru-pri", "ru-kha", "ru-amu", "ru-sak",
    "ru-mag", "ru-kam", "ru-chu",
]

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS_TO_PARSE = 12000  # Огромный пул
SOURCE_WORKERS = 25            # Потоки загрузки источников
CHECK_WORKERS = 100            # Потоки проверки каналов
CHECK_TIMEOUT = 10.0           # До 10 секунд на канал
UPDATE_EVERY = 86400           # Раз в 24 часа

playlist_cache = "#EXTM3U\n# IPTV Russia Pro MAX — идёт первая проверка каналов...\n"
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

# ==================== СЕССИИ ====================
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
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text, re.I)
                found.update(links)
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

# ==================== ФИЛЬТРЫ ====================
def get_category(name):
    n = name.lower()
    if any(x in n for x in ['новости', 'news', '24', 'вести', 'информ', 'мир']):
        return 'Новости'
    if any(x in n for x in ['кино', 'movie', 'film', 'сериал', 'hd', 'fox', 'tv1000']):
        return 'Кино'
    if any(x in n for x in ['музыка', 'music', 'хит', 'radio', 'mtv', 'bridge']):
        return 'Музыка'
    if any(x in n for x in ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'khl']):
        return 'Спорт'
    if any(x in n for x in ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'gulli']):
        return 'Детские'
    if any(x in n for x in ['докум', 'doc', 'познав', 'history', 'discovery']):
        return 'Познавательные'
    return 'Общие'

def is_adult(name):
    n = name.lower()
    bad = ['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'эротика', 'порно', 'nude', 'playboy']
    return any(w in n for w in bad)

def is_russian(name):
    return bool(re.search(r'[\u0400-\u04FF]', name))

# ==================== УМНАЯ ПРОВЕРКА (<= 10 сек) ====================
def check_one(url):
    """
    Канал жив, если ответил за <= 10 сек и отдаёт реальный контент:
    TS-поток, HLS-плейлист или бинарные данные.
    В мусорку: 404/403 и HTML-заглушки провайдеров.
    """
    session = get_session()
    start = time.monotonic()

    def remaining():
        return CHECK_TIMEOUT - (time.monotonic() - start)

    # Быстрый путь: HEAD с хорошим Content-Type
    try:
        r = session.head(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER,
                         allow_redirects=True, verify=False)
        if r.status_code < 400 and remaining() > 0:
            ct = r.headers.get('content-type', '').lower()
            if any(g in ct for g in GOOD_CT):
                return True
    except Exception:
        pass

    # Основной путь: GET + анализ первых 2 КБ, до 2 попыток при сетевых ошибках
    for _ in range(2):
        if remaining() <= 0.5:
            return False
        try:
            r = session.get(url, timeout=remaining(), headers=HEADERS_PLAYER,
                            stream=True, allow_redirects=True, verify=False)
        except Exception:
            continue  # сетевая ошибка — пробуем ещё раз

        if r.status_code >= 400:
            return False  # 404/403/410 — мёртв однозначно

        ct = r.headers.get('content-type', '').lower()
        try:
            chunk = next(r.iter_content(chunk_size=2048), b'')
        except Exception:
            continue
        finally:
            r.close()

        if not chunk:
            return False

        # Хороший Content-Type — жив
        if any(g in ct for g in GOOD_CT):
            return True
        # TS-поток (sync byte 0x47) — жив
        if chunk[:1] == b'\x47':
            return True
        low = chunk[:300].lower()
        # HLS-плейлист — жив
        if b'#extm3u' in low or b'#extinf' in low:
            return True
        # HTML-заглушка провайдера — мёртв
        if b'<html' in low or b'<!doctype' in low or b'access denied' in low:
            return False
        # Бинарные данные без заголовков — жив
        if b'\x00' in low:
            return True
        return False

    return False

# ==================== ПАРСЕР M3U ====================
def parse_m3u(text, raw, seen_urls):
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
                gt = re.search(r'group-title="([^"]*)"', current_inf)
                if gt:
                    cat = gt.group(1)
                else:
                    cat = get_category(current_name)
                    current_inf = re.sub(r'(#EXTINF:-?\d+\s*)',
                                         r'\1group-title="' + cat + '" ',
                                         current_inf, count=1)
                raw.append({'inf': current_inf, 'url': line,
                            'cat': cat, 'name': current_name})
                if len(raw) >= MAX_CHANNELS_TO_PARSE:
                    return True
            current_inf = ''
            current_name = ''
    return False

# ==================== ОБНОВЛЕНИЕ ====================
def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        logger.info("Обновление уже идёт, пропуск.")
        return
    is_updating = True
    start = time.time()
    logger.info("🔄 Старт: сбор источников (все часовые пояса РФ + СНГ + категории)...")

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

        raw = []
        seen = set()
        for txt in texts:
            if parse_m3u(txt, raw, seen):
                break
        logger.info(f"Уникальных каналов с кириллицей: {len(raw)}. Проверка (<= 10 сек)...")

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

        alive.sort(key=lambda c: (c['cat'], c['name']))
        cat_counts = Counter(ch['cat'] for ch in alive)

        lines = [
            '#EXTM3U',
            '# IPTV Russia Pro MAX | ' + time.strftime('%Y-%m-%d %H:%M'),
            '# Живых каналов: ' + str(len(alive)) + ' | отклик каждого <= 10 сек',
            '# Регионы: все часовые пояса РФ + СНГ',
            '# Категории: ' + ', '.join(f'{k}: {v}' for k, v in sorted(cat_counts.items())),
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
        logger.info(f"Следующее обновление через {UPDATE_EVERY // 3600} ч")
        time.sleep(UPDATE_EVERY)

threading.Thread(target=background_worker, daemon=True).start()

# ==================== РОУТЫ ====================
@app.route('/')
def home():
    return """
    <h1>🇷🇺 IPTV Russia Pro MAX</h1>
    <p>Все часовые пояса РФ + СНГ | отклик &le; 10 сек | обновление раз в 24 ч</p>
    <p><a href="/playlist.m3u" style="font-size:22px">📥 Скачать плейлист</a></p>
    <p><a href="/status">📊 Статус</a> | <a href="/refresh">🔄 Обновить сейчас</a></p>
    """

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    with cache_lock:
        resp = Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')
        resp.headers['Content-Disposition'] = 'attachment; filename="iptv_russia_max.m3u"'
        resp.headers['Cache-Control'] = 'public, max-age=3600'
        return resp

@app.route('/status')
def status():
    with cache_lock:
        data = dict(stats)
    data['is_updating'] = is_updating
    data['update_every_hours'] = UPDATE_EVERY // 3600
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