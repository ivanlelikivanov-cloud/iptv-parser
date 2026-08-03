import os
import re
import time
import math
import logging
import threading
import sqlite3
import pickle
import requests
import urllib3
from urllib.parse import urlparse, unquote
from collections import Counter
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify

try:
    from sklearn.linear_model import SGDClassifier
    HAS_SKLEARN = True
except Exception:
    HAS_SKLEARN = False

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
    "https://iptv-org.github.io/iptv/languages/bel.m3u",
    "https://iptv-org.github.io/iptv/languages/kaz.m3u",
    "https://iptv-org.github.io/iptv/languages/uzb.m3u",
    "https://iptv-org.github.io/iptv/languages/kir.m3u",
    "https://iptv-org.github.io/iptv/languages/tgk.m3u",
    "https://iptv-org.github.io/iptv/languages/arm.m3u",
    "https://iptv-org.github.io/iptv/languages/aze.m3u",
    "https://iptv-org.github.io/iptv/languages/rum.m3u",
    "https://iptv-org.github.io/iptv/languages/kat.m3u",
    "https://iptv-org.github.io/iptv/countries/by.m3u",
    "https://iptv-org.github.io/iptv/countries/kz.m3u",
    "https://iptv-org.github.io/iptv/countries/kg.m3u",
    "https://iptv-org.github.io/iptv/countries/uz.m3u",
    "https://iptv-org.github.io/iptv/countries/am.m3u",
    "https://iptv-org.github.io/iptv/countries/az.m3u",
    "https://iptv-org.github.io/iptv/countries/ge.m3u",
    "https://iptv-org.github.io/iptv/countries/md.m3u",
    "https://iptv-org.github.io/iptv/countries/tj.m3u",
    "https://iptv-org.github.io/iptv/countries/il.m3u",
    "https://iptv-org.github.io/iptv/countries/de.m3u",
    "https://iptv-org.github.io/iptv/countries/us.m3u",
    "https://iptv-org.github.io/iptv/index.m3u",
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
    "https://iptv-org.github.io/iptv/categories/religious.m3u",
    "https://iptv-org.github.io/iptv/categories/cooking.m3u",
    "https://iptv-org.github.io/iptv/categories/health.m3u",
    "https://iptv-org.github.io/iptv/categories/hobby.m3u",
    "https://iptv-org.github.io/iptv/categories/home.m3u",
    "https://iptv-org.github.io/iptv/categories/business.m3u",
    "https://iptv-org.github.io/iptv/categories/relax.m3u",
    "https://iptv-org.github.io/iptv/categories/science.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/index.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_russia.m3u8",
    "https://raw.githubusercontent.com/smolnp/IPTVru/main/IPTVru.m3u",
    "https://smolnp.github.io/IPTVru/IPTVru.m3u",
    "http://iptv-list.mart.ru/playlist.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://webarmen.com/my/iptv/auto.m3u",
]

HTML_SOURCES = [
    "https://m3u.su/",
    "https://m3u.su/m3u/",
    "https://sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026",
    "https://sat-portal.com/plejlisty/",
    "https://6x6.msk.ru/",
    "https://homtv.ru/",
    "https://iptv-rus.com/",
    "https://iptv-rus.com/playlists/",
    "https://pikniktv.info/viewtopic.php?t=6737",
    "https://pikniktv.info/viewforum.php?f=328",
    "https://webarmen.com/my/iptv/",
    "https://go2tv.top/",
    "https://iptv.one/",
    "https://iptv.best/",
    "https://iptv-channels.net/",
    "https://iptv-live.ru/",
    "https://iptv-tv.ru/",
    "https://iptv-russia.online/",
    "https://vse-tv.net/",
    "https://vse-tv.net/playlists.html",
    "https://forumtv.org/",
    "https://webos-forums.ru/post167674.html",
    "https://www.free-codecs.com/guides/free-popular-iptv-playlist.htm",
    "https://github.com/iptv-org/iptv",
    "https://github.com/Free-iptv/iptv",
    "https://github.com/4mirror/iptv",
    "https://github.com/hmlendea/iptv-playlist-aggregator",
    "https://pskovline.tv/tvm3u.php",
    "https://onlinetv.ru/",
    "https://smotret-tv.online/",
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

GITHUB_QUERIES = ['iptv ru', 'iptv russia', 'm3u ru', 'iptv playlist', 'topic:iptv', 'iptv m3u8 ru']
GH_COMMON_PATHS = ['ru.m3u', 'playlist.m3u', 'iptv.m3u', 'tv.m3u', 'main.m3u',
                   'index.m3u', 'channels/ru.m3u', 'playlist.m3u8', 'ru.m3u8']
PROBE_PATHS = ['ru.m3u', 'playlist.m3u', 'iptv.m3u', 'tv.m3u']
WEB_QUERIES = ['iptv m3u ru', 'плейлист iptv m3u россия', 'iptv playlist m3u8 russia',
               'iptv m3u8 ru бесплатно', 'site:t.me iptv m3u',
               'iptv плейлист форум бесплатно 2026',
               'm3u плейлист тв бесплатно скачать', 'агрегатор iptv плейлистов сайт']
TG_CHANNELS = ['iptvru', 'iptv_russia', 'russian_iptv', 'iptv_m3u', 'freeiptv_ru',
               'iptv_playlist', 'm3u_playlist', 'iptvfree', 'tv_playlist',
               'iptv_rf', 'playlist_iptv', 'iptv_su', 'free_iptv_ru',
               'iptv_list', 'ru_iptv', 'iptv_tv_ru', 'russia_iptv',
               'iptv_2026', 'm3u8ru', 'iptv_playlist_ru', 'tv_m3u', 'iptvhub_ru']

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS = 20000
MAX_EXTRA_SOURCES = 200
MAX_CHECK_POOL = 5000
SOURCE_WORKERS = 20
CHECK_WORKERS = 80
CHECK_TIMEOUT = 40.0
SOURCE_PHASE_MAX = 240
CHECK_PHASE_MAX = 1500
UPDATE_EVERY = 86400
RETRY_IF_EMPTY = 600
FLUSH_EVERY = 15
HEARTBEAT_SEC = 20
KEEPALIVE_SEC = 300

CIS_COUNTRIES = {'RU', 'BY', 'KZ', 'KG', 'UZ', 'AM', 'AZ', 'GE', 'MD', 'TJ'}

CAT_ORDER = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 'Детские',
             'Музыка', 'Познавательные', 'Развлекательные', 'Региональные', 'Общие']

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
    "ml_samples": 0,
    "ml_accuracy": 0.0,
    "ml_on": HAS_SKLEARN,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}
GOOD_CT = ('video/', 'audio/', 'mpegurl', 'octet-stream', 'mp2t')

# ИСПРАВЛЕНО: обычные строки (НЕ bytes!) — кириллица теперь легальна
BLOCK_MARKERS = ['roskomnadzor', 'zablokirovan', 'blocked', 'restricted',
                 'forbidden', 'captcha', 'cloudflare', 'access denied',
                 'denied', 'trebuetsya', 'оплат', 'заблокирован',
                 'ограничен', 'недоступен', 'роскомнадзор']

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'playlist_disk.m3u')
DB_FILE = os.path.join(BASE_DIR, 'ml_history.db')
MODEL_FILE = os.path.join(BASE_DIR, 'ml_model.pkl')

# ==================== ML-МОЗГ ====================
class MLBrain:
    """Онлайн-обучение: приоритизация кандидатов + репутация хостов"""

    def __init__(self):
        self.host_alive = {}
        self.host_total = {}
        self.model = None
        self.trained_samples = 0
        self.last_accuracy = 0.0
        self.db = None
        self.lock = threading.Lock()
        try:
            self.db = sqlite3.connect(DB_FILE, check_same_thread=False)
            with self.lock:
                self.db.execute('CREATE TABLE IF NOT EXISTS checks '
                                '(id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT, alive INTEGER, ts REAL)')
                self.db.commit()
                rows = self.db.execute('SELECT host, SUM(alive), COUNT(*) FROM checks GROUP BY host').fetchall()
            for host, s, c in rows:
                self.host_alive[host] = int(s)
                self.host_total[host] = int(c)
            logger.info(f"🧠 ML: история из БД: {len(rows)} хостов")
        except Exception as e:
            logger.error(f"🧠 ML: БД недоступна: {e}")
            self.db = None
        try:
            if HAS_SKLEARN and os.path.exists(MODEL_FILE):
                with open(MODEL_FILE, 'rb') as f:
                    self.model = pickle.load(f)
                logger.info("🧠 ML: модель загружена с диска")
        except Exception:
            self.model = None

    def host_stats(self, host):
        t = self.host_total.get(host, 0)
        a = self.host_alive.get(host, 0)
        if t == 0:
            return 0.5, 0
        return (a + 1.0) / (t + 2.0), t

    def record(self, host, alive):
        self.host_total[host] = self.host_total.get(host, 0) + 1
        self.host_alive[host] = self.host_alive.get(host, 0) + (1 if alive else 0)
        if self.db is None:
            return
        try:
            with self.lock:
                self.db.execute('INSERT INTO checks (host, alive, ts) VALUES (?,?,?)',
                                (host, 1 if alive else 0, time.time()))
                self.db.commit()
        except Exception:
            pass

    def model_prob(self, feats):
        if self.model is None:
            return None
        try:
            z = self.model.decision_function([feats])[0]
            return 1.0 / (1.0 + math.exp(-z))
        except Exception:
            return None

    def score(self, feats, host):
        rep, cnt = self.host_stats(host)
        heur = 0.5 * feats[2] + 0.3 * feats[3] + 0.2 * (1.0 - feats[5])
        p = self.model_prob(feats)
        if p is None:
            return 0.55 * rep + 0.25 * heur + 0.2 * min(cnt / 10.0, 1.0)
        return 0.5 * p + 0.35 * rep + 0.15 * heur

    def train(self, samples):
        if not HAS_SKLEARN or not samples or len(samples) < 20:
            return
        X = [s[0] for s in samples]
        y = [s[1] for s in samples]
        if len(set(y)) < 2:
            return
        acc = None
        if self.model is not None:
            try:
                preds = []
                for x in X[:200]:
                    p = self.model_prob(x)
                    preds.append(1 if (p is not None and p > 0.5) else 0)
                acc = sum(1 for p, t in zip(preds, y[:200]) if p == t) / max(1, len(preds))
            except Exception:
                acc = None
        try:
            if self.model is None:
                self.model = SGDClassifier(loss='log_loss', learning_rate='optimal', random_state=42)
            self.model.partial_fit(X, y, classes=[0, 1])
            self.trained_samples += len(samples)
            if acc is not None:
                self.last_accuracy = acc
            with open(MODEL_FILE, 'wb') as f:
                pickle.dump(self.model, f)
            logger.info(f"🧠 ML: дообучено на {len(samples)} примерах "
                        f"(всего {self.trained_samples}), acc до обучения: {acc if acc is not None else 'н/д'}")
        except Exception as e:
            logger.error(f"🧠 ML: ошибка обучения: {e}")
        if self.db is not None:
            try:
                with self.lock:
                    self.db.execute('DELETE FROM checks WHERE id NOT IN '
                                    '(SELECT id FROM checks ORDER BY ts DESC LIMIT 20000)')
                    self.db.commit()
            except Exception:
                pass

brain = MLBrain()

def extract_features(ch):
    url = ch['url']
    name = (ch.get('name') or '').lower()
    u = url.lower()
    rep, cnt = brain.host_stats(urlparse(url).netloc)
    return [
        min(len(u) / 300.0, 1.0),
        min(u.count('/') / 8.0, 1.0),
        1.0 if u.startswith('https') else 0.0,
        1.0 if '.m3u8' in u else 0.0,
        1.0 if re.search(r'\.(ts|mp4|mkv|flv)(\?|$)', u) else 0.0,
        1.0 if any(t in u for t in ['token', 'key=', 'auth', 'session', 'sig=']) else 0.0,
        1.0 if ('hd' in name or '4k' in name) else 0.0,
        min(len(name) / 40.0, 1.0),
        rep,
        min(cnt / 20.0, 1.0),
        1.0 if (ch.get('ua') or ch.get('ref')) else 0.0,
        1.0 if 'iptv-org' in u else 0.0,
    ]

# ==================== ДИСКОВЫЙ КЭШ / KEEPALIVE ====================
def load_disk_cache():
    global playlist_cache
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = f.read()
            n = data.count('\nhttp')
            if n > 0:
                with cache_lock:
                    playlist_cache = data
                    stats['alive_channels'] = n
                logger.info(f"💾 Восстановлен плейлист с диска: {n} каналов")
    except Exception as e:
        logger.error(f"Дисковый кэш не читается: {e}")

def save_disk_cache(data):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            f.write(data)
    except Exception:
        pass

SELF_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://iptv-parser.onrender.com')

def keepalive_worker():
    while True:
        time.sleep(KEEPALIVE_SEC)
        try:
            requests.get(SELF_URL + '/health', timeout=10)
        except Exception:
            pass

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

# ==================== СЛОВАРИ ФИЛЬТРОВ ====================
def _clean(lst):
    return [w for w in lst if isinstance(w, str) and len(w.strip()) >= 2]

ADULT_WORDS = _clean(['xxx', 'adult', 'porn', 'sex', 'hentai', '18+',
                      'эротика', 'порно', 'nude', 'playboy'])

UA_WORDS = _clean(['україн', 'украина', 'україна', 'kyiv', 'kiev', 'київ',
                   'львів', 'львов', 'харків', 'дніпро', 'одеса', 'суспільне',
                   'суспильне', 'прямий', 'тсн', '1+1', '2+2', 'інтер',
                   'inter ua', 'верес', 'тоніс', 'тонис', 'ua: ', 'ua |',
                   '| ua', ' ukraine', 'украинск', '5 kanal'])

PAYWALL_WORDS = _clean(['подписк', 'subscription', 'оплат', 'payment', 'купить',
                        'продаж', 'whatsapp', 'telegram', 't.me', 'promo',
                        'реклам', 'advert', 'магазин', 'shop', 'store',
                        'premium', 'премиум', 'vip', 'вип', 'ppv',
                        'pay per view', 'активация', 'iptv', 'fifa',
                        'world cup', 'чемпионат мира', 'плей-офф', 'тариф',
                        'абонент'])

BLACKLIST_WORDS = _clean(['fifa', 'world cup', 'чемпионат мира', 'плей-офф'])

RADIO_WORDS = _clean([
    'радио', 'radio', 'fm', 'ржд', 'дорожное', 'авторадио', 'ретро fm',
    'europa plus', 'европа плюс', 'шансон', 'dfm', 'monte carlo', 'maximum',
    'record', 'energy', 'relax fm', 'детское радио', 'юмор fm', 'azadliq',
    'radiola', 'dorognoe', 'nashe radio', 'наше радио', 'kommersant fm'])

LATIN_RU_WORDS = _clean([
    'rt ', 'rt.', 'rt doc', 'rtr', 'planeta', 'pervyi', 'pervy', 'channel one',
    'match tv', 'match!', 'zvezda', 'karusel', 'carousel', 'muz-tv', 'muz tv',
    'ru.tv', 'rutv', 'tv1000', 'tv 1000', 'ren tv', 'ntv', 'sts', 'tnt',
    'rossiya', 'rossia', 'russia', 'vesti', 'izvestia', 'kultura', 'soyuz',
    'spas', 'domashniy', 'pyatnitsa', 'subbota', 'mir tv', 'otr', 'tv centr',
    'tv center', 'telekanal', '360', '8 kanal', 'shanson tv', 'retro tv',
    'amedia', 'moscow 24', 'moskva 24', 'peterburg', 'petersburg', 'len tv',
    'kinopoisk', 'illuzion'])

# ==================== РАЗВЕДКА ====================
def fetch_dynamic():
    found = set()
    for page in HTML_SOURCES:
        try:
            r = get_session().get(page, headers=HEADERS_WEB, timeout=(5, 10), verify=False)
            if r.status_code == 200:
                found.update(re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text, re.I))
        except Exception:
            pass
    return list(found)

def fetch_ru_regions():
    try:
        r = get_session().get("https://iptv-org.github.io/api/regions.json",
                              timeout=(5, 10), headers=HEADERS_WEB)
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
                         params={'q': q, 'per_page': 15, 'sort': 'stars', 'order': 'desc'},
                         headers=gh_headers, timeout=(5, 15))
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    full = item.get('full_name')
                    branch = item.get('default_branch') or 'main'
                    if full:
                        repos.append((full, branch))
        except Exception:
            continue
    repos = list(dict.fromkeys(repos))[:40]
    logger.info(f"GitHub: репозиториев: {len(repos)}")

    found = set()

    def read_readme(repo_branch):
        full, branch = repo_branch
        try:
            r = get_session().get('https://raw.githubusercontent.com/' + full + '/' + branch + '/README.md',
                                  headers=HEADERS_WEB, timeout=(5, 10))
            if r.status_code == 200:
                return re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', r.text, re.I)
        except Exception:
            pass
        return []

    ex = ThreadPoolExecutor(max_workers=15)
    try:
        for links in ex.map(read_readme, repos, timeout=90):
            found.update(links)
    except Exception:
        pass
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            ex.shutdown(wait=False)

    for full, branch in repos:
        base = 'https://raw.githubusercontent.com/' + full + '/' + branch
        for path in GH_COMMON_PATHS:
            found.add(base + '/' + path)
    return list(found)

def fetch_gitlab():
    found = set()
    try:
        r = get_session().get('https://gitlab.com/api/v4/projects',
                              params={'search': 'iptv', 'per_page': 15},
                              headers=HEADERS_WEB, timeout=(5, 15))
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
                              params={'q': 'name ~ "iptv"', 'pagelen': 15},
                              headers=HEADERS_WEB, timeout=(5, 15))
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
        ('https://codeberg.org/api/v1/repos/search?q=iptv&limit=10',
         'https://codeberg.org/', '/raw/branch/'),
        ('https://gitea.com/api/v1/repos/search?q=iptv&limit=10',
         'https://gitea.com/', '/raw/'),
    ]
    for url, base, rawfmt in apis:
        try:
            r = get_session().get(url, headers=HEADERS_WEB, timeout=(5, 15))
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
                                  params={'q': q}, headers=HEADERS_WEB, timeout=(5, 15))
            if r.status_code != 200:
                continue
            m3u.update(re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', r.text, re.I))
            for enc in re.findall(r'uddg=([^&"]+)', r.text):
                pages.append(unquote(enc))
        except Exception:
            continue

    def scrape(page):
        try:
            r = get_session().get(page, headers=HEADERS_WEB, timeout=(5, 10), verify=False)
            if r.status_code == 200:
                return re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', r.text, re.I)
        except Exception:
            pass
        return []

    ex = ThreadPoolExecutor(max_workers=10)
    try:
        for links in ex.map(scrape, pages[:25], timeout=90):
            m3u.update(links)
    except Exception:
        pass
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            ex.shutdown(wait=False)
    logger.info(f"Веб-поиск: ссылок: {len(m3u)}")
    return list(m3u)

def fetch_telegram():
    found = set()
    for ch in TG_CHANNELS:
        try:
            r = get_session().get('https://t.me/s/' + ch, headers=HEADERS_WEB, timeout=(5, 10))
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
                        timeout=(10, 60), headers=HEADERS_WEB)
        st_r = sess.get("https://iptv-org.github.io/api/streams.json",
                        timeout=(10, 60), headers=HEADERS_WEB)
        if ch_r.status_code != 200 or st_r.status_code != 200:
            return []
        names = {}
        for ch in ch_r.json():
            if ch.get('is_nsfw'):
                continue
            if ch.get('country') == 'UA':
                continue
            if ch.get('category') == 'radio':
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
        r = get_session().get(url, timeout=(5, 10), headers=HEADERS_WEB, verify=False)
        if r.status_code == 200 and r.text:
            return r.text
    except Exception:
        pass
    return None

# ==================== КАТЕГОРИИ И ФИЛЬТРЫ ====================
def get_category(name):
    n = name.lower()
    if any(w in n for w in ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney', 'gulli', 'аниме', 'anime', 'nick', 'tiji', 'baby']):
        return 'Детские'
    if any(w in n for w in ['новост', 'вести', 'информ', 'news', '24', 'известия', 'ртд', 'euronews', 'bbc', 'cnn', 'политик', 'эконом', 'бизнес', 'business']):
        return 'Новости'
    if any(w in n for w in ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'khl', 'ufc', 'бокс', 'киберспорт', 'esport', 'автоспорт', 'баскетбол', 'теннис', 'биатлон', 'лыжн']):
        return 'Спорт'
    if any(w in n for w in ['кино', 'kino', 'movie', 'film', 'фильм', 'сериал', 'series', 'serial', 'cinema', 'tv1000', 'амедиа', 'дом кино', 'иллюзион', 'премьера', 'боевик', 'детектив', 'мелодрама', 'комедия', 'ужас', 'фантастика', 'киномикс', 'киносемья', 'кинокомедия', 'киносвидание', 'киноужас', 'кинопоказ']):
        return 'Кино и сериалы'
    if any(w in n for w in ['музык', 'music', 'mtv', 'bridge', 'шансон', 'рутв', 'ru.tv', 'ретро', 'хит', 'жара', 'блюз', 'jazz', 'классик', 'classic', 'муз', 'tnt music', 'о2тв', 'o2tv', 'first music', 'музсоюз']):
        return 'Музыка'
    if any(w in n for w in ['докум', 'doc', 'познав', 'истори', 'history', 'discovery', 'science', 'наука', 'природ', 'animal', 'животн', 'океан', 'космос', 'культур', 'искусств', 'театр', 'музей', 'образов', 'школ', 'язык', 'travel', 'путешеств', 'религ', 'relig', 'спас', 'союз', 'техник', 'техно', 'авто', 'auto', 'дача', 'сад', 'огород', 'рыбал', 'охота', 'кулинар', 'еда', 'food', 'здоров', 'health', 'медицин']):
        return 'Познавательные'
    if any(w in n for w in ['развлек', 'entertainment', 'юмор', 'comedy', 'камеди', 'квн', 'шоу', 'мода', 'fashion', 'стиль', 'lifestyle', 'лайфстайл', 'дом', 'home', 'семья', 'family', 'игры', 'game', 'лотерея', 'анекдот']):
        return 'Развлекательные'
    if any(w in n for w in ['москва', 'moscow', 'петербург', 'petersburg', 'лен тв', 'len tv', 'екатеринбург', 'новосибирск', 'казань', 'татарстан', 'уфа', 'башкортостан', 'самара', 'нижний новгород', 'краснодар', 'кубань', 'ростов', 'пермь', 'челябинск', 'омск', 'красноярск', 'владивосток', 'хабаровск', 'иркутск', 'тюмень', 'томск', 'барнаул', 'алтай', 'кемерово', 'кузбасс', 'удмуртия', 'ижевск', 'чувашия', 'чебоксары', 'мордовия', 'осетия', 'дагестан', 'грозный', 'чечня', 'кавказ', 'ставрополь', 'волгоград', 'саратов', 'тверь', 'тула', 'ярославль', 'воронеж', 'липецк', 'тамбов', 'брянск', 'курск', 'белгород', 'калуга', 'рязань', 'владимир', 'иваново', 'кострома', 'вологда', 'череповец', 'архангельск', 'мурманск', 'карелия', 'коми', 'калининград', 'псков', 'новгород', 'смоленск', 'якутск', 'якутия', 'бурятия', 'улан-удэ', 'чита', 'забайкаль', 'сахалин', 'магадан', 'камчатка', 'чукотка', 'сургут', 'югра', 'ямал', 'крым', 'севастополь', 'симферополь', 'сочи', 'минск', 'беларусь', 'гомель', 'брест', 'алматы', 'астана', 'ташкент', 'бишкек', 'душанбе', 'баку', 'ереван', 'кишинев', 'регион', 'regional', 'губерния', 'городской']):
        return 'Региональные'
    if any(w in n for w in ['первый канал', 'россия 1', 'россия к', 'нтв', 'тнт', 'стс', 'рен тв', 'пятый канал', 'тв центр', 'звезда', 'отр', 'пятница', 'суббота', 'домашний', 'муз-тв', '2x2', 'мир', 'channel one', 'pervyi', 'rossiya', 'russia 1', 'russia k', 'russia 24', 'ntv', 'ren tv', 'fifth channel', 'tv centr']):
        return 'Федеральные'
    return 'Общие'

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
    if any(w.lower() in n for w in BLACKLIST_WORDS):
        return True
    return False

def is_radio(name):
    n = name.lower()
    if any(w in n for w in RADIO_WORDS):
        return True
    if re.search(r'\bfm\b', n) or 'радиостанция' in n:
        return True
    return False

def is_russian_like(name):
    if re.search(r'[\u0400-\u04FF]', name):
        return True
    n = name.lower()
    return any(w in n for w in LATIN_RU_WORDS)

def reject_reason(name):
    if not is_russian_like(name):
        return 'not_ru'
    if is_adult(name):
        return 'adult'
    if is_ukrainian(name):
        return 'ua'
    if is_paywall(name):
        return 'paywall'
    if is_radio(name):
        return 'radio'
    return None

def norm_name(name):
    n = name.lower().strip()
    n = re.sub(r'[\(\[].*?[\)\]]', '', n)
    n = re.sub(r'\b(hd|fhd|uhd|4k|sd|hevc|h265|h264)\b', '', n)
    return re.sub(r'\s+', ' ', n).strip(' -_|')

def is_hd(name):
    n = name.lower()
    return 'hd' in n or '4k' in n or 'uhd' in n or 'fhd' in n

# ==================== ПРОВЕРКА ====================
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
        if b'<html' in low or b'<!doctype' in low or b'<script' in low:
            return False
        # ИСПРАВЛЕНО: декодируем байты в строку и ищем маркеры блокировок
        try:
            txt_low = low.decode('utf-8', errors='ignore')
        except Exception:
            txt_low = ''
        if any(m in txt_low for m in BLOCK_MARKERS):
            return False
        return True

    return False

# ==================== ПАРСЕР ====================
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

# ==================== СБОРКА + ДИСК ====================
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
        '# IPTV Russia Pro MAX + ML | ' + time.strftime('%Y-%m-%d %H:%M'),
        '# Живых каналов: ' + str(len(alive_sorted)) + ' | без 18+ | без UA | без радио | без подписок',
    ]
    for ch in alive_sorted:
        lines.append(ch['inf'])
        lines.append(ch['url'])
    data = '\n'.join(lines)
    with cache_lock:
        playlist_cache = data
        stats['alive_channels'] = len(alive_sorted)
        stats['categories'] = dict(cat_counts)
        if elapsed is not None:
            stats['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
            stats['duration_sec'] = round(elapsed, 1)
    save_disk_cache(data)

# ==================== ОБНОВЛЕНИЕ ====================
def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    start = time.time()
    logger.info("🔄 Старт: разведка ВСЕХ платформ + форумы + TG + ML-приоритизация...")

    try:
        api_channels = fetch_iptv_org_api()
        logger.info(f"API iptv-org: потоков РФ/СНГ (без UA/радио): {len(api_channels)}")

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
        ex = ThreadPoolExecutor(max_workers=SOURCE_WORKERS)
        futs = [ex.submit(fetch_source_text, u) for u in sources]
        try:
            for f in as_completed(futs, timeout=SOURCE_PHASE_MAX):
                try:
                    txt = f.result()
                except Exception:
                    txt = None
                if txt:
                    texts.append(txt)
        except TimeoutError:
            logger.warning(f"⏳ Таймаут фазы источников ({SOURCE_PHASE_MAX}с), беру что успело: {len(texts)}")
        except Exception as e:
            logger.error(f"Ошибка фазы источников: {e}")
        finally:
            try:
                ex.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                ex.shutdown(wait=False)
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

        # 🧠 ML: скоринг и умная сортировка — лучшие кандидаты проверяются первыми
        for ch in raw:
            ch['feats'] = extract_features(ch)
            ch['host'] = urlparse(ch['url']).netloc
            ch['ml_score'] = brain.score(ch['feats'], ch['host'])
        raw.sort(key=lambda c: -c['ml_score'])

        if len(raw) > MAX_CHECK_POOL:
            logger.info(f"Кандидатов {len(raw)}, ML выбрал топ-{MAX_CHECK_POOL}")
            raw = raw[:MAX_CHECK_POOL]
        if not raw:
            logger.error("⚠️ ВСЕ каналы отфильтрованы! Проверь списки слов!")
        with cache_lock:
            stats['sources_total'] = len(sources)
            stats['playlists_loaded'] = len(texts)
            stats['api_streams'] = len(api_channels)
            stats['parsed_channels'] = len(raw)
        logger.info(f"Уникальных каналов: {len(raw)}. Проверка (<= 40 сек, {CHECK_WORKERS} потоков)...")

        alive = []
        samples = []
        since_flush = 0
        checked = 0
        last_beat = time.time()
        ex = ThreadPoolExecutor(max_workers=CHECK_WORKERS)
        futs = {ex.submit(check_one, ch): ch for ch in raw}
        try:
            for f in as_completed(futs.keys(), timeout=CHECK_PHASE_MAX):
                checked += 1
                ch = futs[f]
                try:
                    ok = bool(f.result())
                except Exception:
                    ok = False
                if ok:
                    alive.append(ch)
                    since_flush += 1
                    if since_flush >= FLUSH_EVERY:
                        flush_playlist(alive)
                        since_flush = 0
                samples.append((ch['feats'], 1 if ok else 0))
                brain.record(ch['host'], ok)
                if time.time() - last_beat > HEARTBEAT_SEC:
                    logger.info(f"Прогресс проверки: {checked}/{len(raw)}, живых: {len(alive)}")
                    last_beat = time.time()
        except TimeoutError:
            logger.warning(f"⏳ Таймаут фазы проверки ({CHECK_PHASE_MAX}с), фиксирую: {len(alive)} живых")
        except Exception as e:
            logger.error(f"Ошибка фазы проверки: {e}")
        finally:
            try:
                ex.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                ex.shutdown(wait=False)

        # 🧠 ML: дообучение на свежих данных
        brain.train(samples)
        with cache_lock:
            stats['ml_samples'] = brain.trained_samples
            stats['ml_accuracy'] = round(brain.last_accuracy, 3)

        elapsed = time.time() - start
        flush_playlist(alive, elapsed=elapsed)
        logger.info(f"✅ Готово: {len(alive)} живых из {len(raw)} за {elapsed:.0f} сек")

    except Exception as e:
        logger.exception(f"КРИТИЧЕСКАЯ ошибка обновления: {e}")
    finally:
        is_updating = False

def background_worker():
    global is_updating
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.exception(f"Фоновая ошибка: {e}")
            is_updating = False
        with cache_lock:
            alive_n = stats['alive_channels']
        wait = UPDATE_EVERY if alive_n > 0 else RETRY_IF_EMPTY
        logger.info(f"Следующая попытка через {wait // 60} мин")
        time.sleep(wait)

load_disk_cache()
threading.Thread(target=background_worker, daemon=True).start()
threading.Thread(target=keepalive_worker, daemon=True).start()

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
<title>IPTV Russia Pro MAX + ML</title>
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
<h1>🇷 IPTV Russia Pro MAX 🧠</h1>
<div class="sub">80+ источников • ML-приоритизация • Онлайн-обучение • 10 категорий</div>
<a class="btn" href="/playlist.m3u">📥 Скачать плейлист</a>
<a class="btn blue" href="/refresh">🔄 Обновить</a>
<a class="btn gray" href="/status">📊 JSON</a>
<div class="stats">
<div class="stat"><b>__ALIVE__</b><span>живых каналов</span></div>
<div class="stat"><b>__PARSED__</b><span>проверено</span></div>
<div class="stat"><b>__MLS__</b><span>ML примеров</span></div>
<div class="stat"><b>__MLA__</b><span>ML точность</span></div>
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
    page = page.replace('__MLS__', str(s.get('ml_samples', 0)))
    page = page.replace('__MLA__', str(s.get('ml_accuracy', 0)))
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