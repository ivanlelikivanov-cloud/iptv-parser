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
    "https://new.m3u.su/rusm",
    "https://new.m3u.su/so",
    "https://new.m3u.su/runtv",
    "https://new.m3u.su/rurt",
    "https://new.m3u.su/rut",
    "https://new.m3u.su/ruz",
    "https://new.m3u.su/lgu",
    "https://new.m3u.su/lgn",
    "https://new.m3u.su/tvoe",
    "https://new.m3u.su/h",
    "https://new.m3u.su/mult",
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
MAX_CHANNELS = 12000
MAX_EXTRA_SOURCES = 200
MAX_CHECK_POOL = 5000
SOURCE_WORKERS = 15
CHECK_WORKERS = 40
CHECK_TIMEOUT = 40.0
SEED_TIMEOUT = 8.0
SOURCE_PHASE_MAX = 240
CHECK_PHASE_MAX = 1500
UPDATE_EVERY = 86400
RETRY_IF_EMPTY = 600
FLUSH_EVERY = 10
HEARTBEAT_SEC = 20
KEEPALIVE_SEC = 60
MAX_PLAYLIST_BYTES = 2_000_000
MAX_HTML_BYTES = 524_288
NB_CONFIDENCE = 0.45

CIS_COUNTRIES = {'RU', 'BY', 'KZ', 'KG', 'UZ', 'AM', 'AZ', 'GE', 'MD', 'TJ'}

CAT_ORDER = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 'Детские',
             'Музыка', 'Познавательные', 'Развлекательные', 'Региональные', 'Общие']

playlist_cache = "#EXTM3U\n# IPTV Russia Pro — идёт первая проверка каналов...\n"
alive_list = []
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
    "ml_on": True,
    "nb_moved": 0,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}
GOOD_CT = ('video/', 'audio/', 'mpegurl', 'octet-stream', 'mp2t')

BLOCK_MARKERS = ['roskomnadzor', 'zablokirovan', 'blocked', 'restricted',
                 'forbidden', 'captcha', 'cloudflare', 'access denied',
                 'denied', 'trebuetsya', 'оплат', 'заблокирован',
                 'ограничен', 'недоступен', 'роскомнадзор']

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'playlist_disk.m3u')
DB_FILE = os.path.join(BASE_DIR, 'ml_history.db')
MODEL_FILE = os.path.join(BASE_DIR, 'ml_model.pkl')
CAT_MODEL_FILE = os.path.join(BASE_DIR, 'cat_model.pkl')

# ==================== НЕЙРОНКА ПРИОРИТЕТОВ ====================
def _sig(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)

class TinyLR:
    def __init__(self, n=12):
        self.w = [0.0] * n
        self.b = 0.0

    def prob(self, x):
        z = self.b + sum(wi * xi for wi, xi in zip(self.w, x))
        return _sig(z)

    def partial_fit(self, X, y, lr=0.3, epochs=2, l2=0.001):
        for _ in range(epochs):
            for x, t in zip(X, y):
                e = self.prob(x) - t
                for i, xi in enumerate(x):
                    self.w[i] = self.w[i] * (1.0 - l2) - lr * e * xi
                self.b -= lr * e

# ==================== ИРОЧКА: БАЙЕС ДЛЯ КАТЕГОРИЙ ====================
class CategoryNB:
    def __init__(self):
        self.tok = {}
        self.tot = {}
        self.docs = {}
        self.vocab = 0
        self.vset = set()

    def tokens(self, name):
        words = re.findall(r'[a-zа-яё0-9]+', name.lower())
        out = list(words)
        for w in words:
            if len(w) >= 5:
                out += [w[i:i+3] for i in range(len(w) - 2)]
        return out

    def fit(self, pairs):
        for name, cat in pairs:
            d = self.tok.setdefault(cat, {})
            self.docs[cat] = self.docs.get(cat, 0) + 1
            for t in self.tokens(name):
                d[t] = d.get(t, 0) + 1
                self.tot[cat] = self.tot.get(cat, 0) + 1
                if t not in self.vset:
                    self.vset.add(t)
                    self.vocab += 1

    def save(self):
        try:
            with open(CAT_MODEL_FILE, 'wb') as f:
                pickle.dump({'tok': self.tok, 'tot': self.tot,
                             'docs': self.docs, 'vocab': self.vocab}, f)
        except Exception:
            pass

    def load(self):
        try:
            if os.path.exists(CAT_MODEL_FILE):
                with open(CAT_MODEL_FILE, 'rb') as f:
                    d = pickle.load(f)
                self.tok, self.tot = d['tok'], d['tot']
                self.docs, self.vocab = d['docs'], d['vocab']
                logger.info(f"🧠 Ирочка: загружен опыт ({sum(self.docs.values())} меток)")
        except Exception:
            pass

    def predict(self, name):
        if not self.docs:
            return None, 0.0
        toks = self.tokens(name)
        if not toks:
            return None, 0.0
        V = self.vocab + 1
        total_docs = sum(self.docs.values())
        scores = {}
        for cat, docs in self.docs.items():
            s = math.log(docs / total_docs)
            tt = self.tot.get(cat, 0) + V
            d = self.tok.get(cat, {})
            acc = 0.0
            for t in toks:
                acc += math.log((d.get(t, 0) + 1) / tt)
            scores[cat] = s + acc / len(toks)
        mx = max(scores.values())
        exps = {c: math.exp(v - mx) for c, v in scores.items()}
        tot = sum(exps.values())
        best = max(exps, key=exps.get)
        return best, exps[best] / tot

cat_nb = CategoryNB()
cat_nb.load()

def apply_nb(ch_list):
    moved = 0
    for ch in ch_list:
        if ch['cat'] == 'Общие':
            pred, conf = cat_nb.predict(ch['name'])
            if pred and conf >= NB_CONFIDENCE:
                ch['cat'] = pred
                ch['inf'] = ch['inf'].replace('group-title="Общие"',
                                              'group-title="' + pred + '"')
                moved += 1
    return moved

# ==================== ML-МОЗГ ПРИОРИТЕТОВ ====================
class MLBrain:
    def __init__(self):
        self.host_alive = {}
        self.host_total = {}
        self.model = None
        self.trained_samples = 0
        self.last_accuracy = 0.0
        self.db = None
        self.lock = threading.RLock()
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
            if os.path.exists(MODEL_FILE):
                with open(MODEL_FILE, 'rb') as f:
                    self.model = pickle.load(f)
                logger.info("🧠 ML: нейрон загружен с диска")
        except Exception:
            self.model = None

    def host_stats(self, host):
        with self.lock:
            t = self.host_total.get(host, 0)
            a = self.host_alive.get(host, 0)
        if t == 0:
            return 0.5, 0
        return (a + 1.0) / (t + 2.0), t

    def record(self, host, alive):
        with self.lock:
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
            return self.model.prob(feats)
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
        if not samples or len(samples) < 20:
            return
        X = [s[0] for s in samples]
        y = [s[1] for s in samples]
        if len(set(y)) < 2:
            return
        acc = None
        if self.model is not None:
            try:
                preds = [1 if self.model.prob(x) > 0.5 else 0 for x in X[:300]]
                acc = sum(1 for p, t in zip(preds, y[:300]) if p == t) / max(1, len(preds))
            except Exception:
                acc = None
        try:
            if self.model is None:
                self.model = TinyLR(len(X[0]))
            self.model.partial_fit(X, y)
            self.trained_samples += len(samples)
            if acc is not None:
                self.last_accuracy = acc
            with open(MODEL_FILE, 'wb') as f:
                pickle.dump(self.model, f)
            logger.info(f"🧠 ML: дообучено на {len(samples)} примерах "
                        f"(всего {self.trained_samples}), acc до: {acc if acc is not None else 'н/д'}")
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

# ==================== ДИСК / ПУЛЬС ====================
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
    n = 0
    while True:
        time.sleep(KEEPALIVE_SEC)
        n += 1
        logger.info("💓 жив")
        if n % 5 == 0:
            try:
                requests.get(SELF_URL + '/health', timeout=10)
            except Exception:
                pass

_thread_local = threading.local()

def get_session():
    s = getattr(_thread_local, 'session', None)
    if s is None:
        s = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=0)
        s.mount('http://', adapter)
        s.mount('https://', adapter)
        _thread_local.session = s
    return s

# ==================== СЛОВАРИ ====================
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
def _read_capped(resp, cap):
    chunks = []
    total = 0
    for c in resp.iter_content(65536):
        chunks.append(c)
        total += len(c)
        if total >= cap:
            break
    resp.close()
    return b''.join(chunks).decode('utf-8', errors='ignore')

def fetch_dynamic():
    found = set()
    for page in HTML_SOURCES:
        try:
            r = get_session().get(page, headers=HEADERS_WEB, timeout=(5, 10),
                                  verify=False, stream=True)
            if r.status_code == 200:
                html = _read_capped(r, MAX_HTML_BYTES)
                found.update(re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', html, re.I))
            else:
                r.close()
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
                                  headers=HEADERS_WEB, timeout=(5, 10), stream=True)
            if r.status_code == 200:
                return re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)',
                                  _read_capped(r, MAX_HTML_BYTES), re.I)
            r.close()
        except Exception:
            pass
        return []

    ex = ThreadPoolExecutor(max_workers=10)
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
            r = get_session().get(page, headers=HEADERS_WEB, timeout=(5, 10),
                                  verify=False, stream=True)
            if r.status_code == 200:
                return re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)',
                                  _read_capped(r, MAX_HTML_BYTES), re.I)
            r.close()
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
            r = get_session().get('https://t.me/s/' + ch, headers=HEADERS_WEB,
                                  timeout=(5, 10), stream=True)
            if r.status_code == 200:
                found.update(re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)',
                                        _read_capped(r, MAX_HTML_BYTES), re.I))
            else:
                r.close()
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