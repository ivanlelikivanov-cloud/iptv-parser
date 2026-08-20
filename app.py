import os
import re
import time
import math
import zlib
import json
import queue
import random
import logging
import threading
import sqlite3
import requests
import urllib3
from urllib.parse import urlparse, unquote, quote
from collections import Counter
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify, request

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

VERSION = '4.0'

# ==================== CONFIG: все «магические числа» в одном месте ====================
CONFIG = {
    'MAX_CHANNELS': 20000, 'MAX_EXTRA_SOURCES': 200, 'MAX_CHECK_POOL': 9000,
    'SOURCE_WORKERS': 12, 'CHECK_WORKERS': 40, 'CHECK_TIMEOUT': 40.0,
    'SEED_TIMEOUT': 8.0, 'SOURCE_PHASE_MAX': 300, 'CHECK_PHASE_MAX': 1500,
    'UPDATE_EVERY': 86400, 'RETRY_IF_EMPTY': 600, 'FLUSH_EVERY': 10,
    'KEEPALIVE_SEC': 60, 'SWEEP_EVERY': 21600, 'SWEEP_TIMEOUT': 15.0,
    'SWEEP_WORKERS': 30, 'DEAD_LIMIT': 3,
    'MAX_PLAYLIST_BYTES': 2000000, 'MAX_HTML_BYTES': 524288,
    'NET_P_MIN': 0.45, 'NET_MARGIN': 0.12, 'GEO_P_MIN': 0.6, 'GEO_MARGIN': 0.2,
    'HOST_REP_MIN': 0.15, 'HOST_REP_CNT': 10,
    'SCORE_W_MODEL': 0.5, 'SCORE_W_REP': 0.35, 'SCORE_W_HEUR': 0.15,
    'SCORE_W_REP_COLD': 0.55, 'SCORE_W_HEUR_COLD': 0.25, 'SCORE_W_SEEN_COLD': 0.2,
}

CIS_COUNTRIES = {'RU', 'BY', 'KZ', 'KG', 'UZ', 'AM', 'AZ', 'GE', 'MD', 'TJ'}

CAT_ORDER = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 'Детские',
             'Музыка', 'Познавательные', 'Развлекательные', 'Региональные',
             'Радио', 'Общие']

EPG_URLS = ("https://iptv-org.github.io/epg/guides/ru.xml.gz,"
            "https://iptv-org.github.io/epg/guides/by.xml.gz,"
            "https://iptv-org.github.io/epg/guides/kz.xml.gz")

API_CAT_MAP = [
    (['radio'], 'Радио'),
    (['kids', 'animation'], 'Детские'),
    (['news', 'business'], 'Новости'),
    (['sports'], 'Спорт'),
    (['movies', 'series'], 'Кино и сериалы'),
    (['music'], 'Музыка'),
    (['documentary', 'science', 'culture', 'education', 'history', 'travel',
      'food', 'cooking', 'health', 'hobby', 'home', 'auto', 'outdoor',
      'weather', 'religious', 'lifestyle'], 'Познавательные'),
    (['comedy', 'entertainment', 'family', 'relax', 'general'], 'Развлекательные'),
]

def api_category(cats):
    if not cats:
        return None
    low = [str(c).lower() for c in cats]
    for keys, cat in API_CAT_MAP:
        if any(k in low for k in keys):
            return cat
    return None

playlist_cache = "#EXTM3U\n# IPTV Russia Pro — идёт первая проверка каналов...\n"
alive_list = []
DEAD_STRIKES = {}
cache_lock = threading.Lock()
is_updating = False
stats = {
    "version": VERSION, "last_update": None, "duration_sec": 0, "sources_total": 0,
    "playlists_loaded": 0, "api_streams": 0, "parsed_channels": 0,
    "alive_channels": 0, "filtered": {}, "categories": {},
    "ml_samples": 0, "ml_accuracy": 0.0, "ml_on": True, "nb_moved": 0,
    "last_sweep": None, "sweep_removed": 0, "host_blacklisted": 0, "geo_pairs": 0,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}
GOOD_CT = ('video/', 'audio/', 'octet-stream', 'mp2t')

UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36 Edg/125.0',
]
_host_sems = {}
_host_sems_lock = threading.Lock()

def host_sem(host):
    with _host_sems_lock:
        s = _host_sems.get(host)
        if s is None:
            s = threading.BoundedSemaphore(2)
            _host_sems[host] = s
        return s

def polite_headers():
    return {'User-Agent': random.choice(UA_POOL), 'Accept': '*/*'}

BLOCK_MARKERS = ['roskomnadzor', 'zablokirovan', 'blocked', 'restricted',
                 'forbidden', 'captcha', 'cloudflare', 'access denied',
                 'denied', 'trebuetsya', 'оплат', 'заблокирован',
                 'ограничен', 'недоступен', 'роскомнадзор',
                 'не показывает', 'на этой территории', 'territory']

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'playlist_disk.m3u')
DB_FILE = os.path.join(BASE_DIR, 'ml_history.db')
MODEL_JSON = os.path.join(BASE_DIR, 'ml_model.json')

SELF_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://iptv-parser.onrender.com')

# ==================== ИСТОЧНИКИ: sources.json + встроенный минимум ====================
FALLBACK_SOURCES = {
    'static': ["https://iptv-org.github.io/iptv/countries/ru.m3u",
               "https://iptv-org.github.io/iptv/languages/rus.m3u",
               "https://iptv-org.github.io/iptv/index.m3u"],
    'html': ["https://m3u.su/", "https://new.m3u.su/"],
    'github_queries': ['iptv ru', 'iptv russia', 'm3u ru', 'iptv playlist'],
    'web_queries': ['iptv m3u ru', 'плейлист iptv m3u россия'],
    'tg': ['iptvru', 'iptv_russia', 'russian_iptv'],
}

def load_sources():
    cfg = {k: list(v) for k, v in FALLBACK_SOURCES.items()}
    try:
        with open(os.path.join(BASE_DIR, 'sources.json'), encoding='utf-8') as f:
            d = json.load(f)
        for k in cfg:
            if isinstance(d.get(k), list) and d[k]:
                cfg[k] = d[k]
        logger.info(f"📚 sources.json: {len(cfg['static'])} статики, {len(cfg['html'])} html, "
                    f"{len(cfg['tg'])} tg")
    except Exception as e:
        logger.warning(f"📚 sources.json недоступен, встроенный минимум: {e}")
    return cfg

SOURCES = load_sources()

def proxy_url(u, ua=None, ref=None):
    q = SELF_URL + '/proxy?url=' + quote(u, safe='')
    if ua:
        q += '&ua=' + quote(ua, safe='')
    if ref:
        q += '&ref=' + quote(ref, safe='')
    return q

def _sig(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)

# ==================== 🛡 СМОТРИТЕЛЬ (веса в JSON, без pickle) ====================
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
    def save(self, path):
        try:
            with open(path, 'w') as f:
                json.dump({'w': self.w, 'b': self.b}, f)
        except Exception:
            pass
    @staticmethod
    def load(path):
        try:
            with open(path) as f:
                d = json.load(f)
            m = TinyLR(len(d['w']))
            m.w = d['w']
            m.b = d['b']
            return m
        except Exception:
            return None

class CategoryNet:
    def __init__(self, dim=4096):
        self.dim = dim
        self.W = {}
        self.b = {}
    @staticmethod
    def _h(t):
        return zlib.crc32(t.encode('utf-8')) & 0x7fffffff
    def feats(self, name):
        words = re.findall(r'[a-zа-яё0-9]+', name.lower())
        idx = set()
        for w in words:
            idx.add(self._h(w) % self.dim)
            if len(w) >= 4:
                for i in range(len(w) - 1):
                    idx.add(self._h(w[i:i+2]) % self.dim)
            if len(w) >= 5:
                for i in range(len(w) - 2):
                    idx.add(self._h(w[i:i+3]) % self.dim)
        return list(idx)
    def scores(self, x):
        s = {c: self.b.get(c, 0.0) for c in self.b}
        for c in list(s):
            Wc = self.W.get(c)
            if Wc:
                s[c] += sum(Wc.get(h, 0.0) for h in x)
        return s
    def predict(self, name):
        if not self.b:
            return None, 0.0, 0.0
        s = self.scores(self.feats(name))
        if not s:
            return None, 0.0, 0.0
        mx = max(s.values())
        exps = {c: math.exp(v - mx) for c, v in s.items()}
        tot = sum(exps.values())
        order = sorted(((exps[c] / tot, c) for c in s), reverse=True)
        p1 = order[0][0]
        p2 = order[1][0] if len(order) > 1 else 0.0
        return order[0][1], p1, p2
    def train(self, pairs, epochs=4, lr=0.15):
        if not pairs:
            return
        for _ in range(epochs):
            for name, cat in pairs:
                x = self.feats(name)
                if not x:
                    continue
                s = self.scores(x)
                if cat not in s:
                    s[cat] = 0.0
                mx = max(s.values())
                exps = {c: math.exp(v - mx) for c, v in s.items()}
                tot = sum(exps.values())
                for c, e in exps.items():
                    g = (e / tot) - (1.0 if c == cat else 0.0)
                    if abs(g) < 1e-6:
                        continue
                    self.b[c] = self.b.get(c, 0.0) - lr * g
                    Wc = self.W.setdefault(c, {})
                    for h in x:
                        Wc[h] = Wc.get(h, 0.0) - lr * g

cat_net = CategoryNet()
geo_net = CategoryNet(dim=2048)

def apply_net(ch_list):
    moved = 0
    for ch in ch_list:
        if ch['cat'] == 'Общие':
            pred, p1, p2 = cat_net.predict(ch['name'])
            if pred and p1 >= CONFIG['NET_P_MIN'] and (p1 - p2) >= CONFIG['NET_MARGIN']:
                ch['cat'] = pred
                ch['inf'] = ch['inf'].replace('group-title="Общие"', 'group-title="' + pred + '"')
                moved += 1
    return moved

# ==================== SQLite: WAL + очередь записи одним потоком ====================
class CheckDB:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS checks '
                        '(id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT, alive INTEGER, ts REAL)')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.commit()
        self.q = queue.Queue()
        self.lock = threading.RLock()
        threading.Thread(target=self._writer, daemon=True).start()
    def _writer(self):
        buf = []
        last = time.time()
        while True:
            try:
                buf.append(self.q.get(timeout=1.0))
            except queue.Empty:
                pass
            try:
                while True:
                    buf.append(self.q.get_nowait())
            except queue.Empty:
                pass
            if buf and (len(buf) >= 50 or time.time() - last >= 2.0):
                try:
                    with self.lock:
                        self.db.executemany('INSERT INTO checks (host, alive, ts) VALUES (?,?,?)', buf)
                        self.db.execute('DELETE FROM checks WHERE id NOT IN '
                                        '(SELECT id FROM checks ORDER BY ts DESC LIMIT 20000)')
                        self.db.commit()
                except Exception:
                    pass
                buf = []
                last = time.time()
    def record(self, host, alive):
        self.q.put((host, 1 if alive else 0, time.time()))
    def load_history(self):
        with self.lock:
            return self.db.execute('SELECT host, SUM(alive), COUNT(*) FROM checks '
                                   'GROUP BY host').fetchall()

class MLBrain:
    def __init__(self):
        self.host_alive, self.host_total = {}, {}
        self.model = None
        self.trained_samples = 0
        self.last_accuracy = 0.0
        self.db = None
        self.lock = threading.RLock()
        try:
            self.db = CheckDB(DB_FILE)
            for host, s, c in self.db.load_history():
                self.host_alive[host] = int(s)
                self.host_total[host] = int(c)
            logger.info(f"🧠 ML: история из БД: {len(self.host_total)} хостов")
        except Exception as e:
            logger.error(f"🧠 ML: БД недоступна: {e}")
            self.db = None
        self.model = TinyLR.load(MODEL_JSON)
        if self.model:
            logger.info("🧠 ML: нейрон загружен из JSON")
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
        if self.db is not None:
            self.db.record(host, alive)
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
            return (CONFIG['SCORE_W_REP_COLD'] * rep + CONFIG['SCORE_W_HEUR_COLD'] * heur +
                    CONFIG['SCORE_W_SEEN_COLD'] * min(cnt / 10.0, 1.0))
        return (CONFIG['SCORE_W_MODEL'] * p + CONFIG['SCORE_W_REP'] * rep +
                CONFIG['SCORE_W_HEUR'] * heur)
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
            self.model.save(MODEL_JSON)
            logger.info(f"🧠 ML: дообучено на {len(samples)} примерах "
                        f"(всего {self.trained_samples}), acc до: {acc if acc is not None else 'н/д'}")
        except Exception as e:
            logger.error(f"🧠 ML: ошибка обучения: {e}")

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

def _parse_cached(data):
    chans = []
    cur_inf = ''
    cur_name = ''
    cur_cat = 'Общие'
    for line in data.splitlines():
        line = line.strip()
        if line.startswith('#EXTINF:'):
            cur_inf = line
            m = re.search(r'group-title="([^"]*)"', line)
            cur_cat = m.group(1) if m else 'Общие'
            m2 = re.search(r',\s*(.+)$', line)
            cur_name = m2.group(1).strip() if m2 else ''
        elif line.startswith('#'):
            continue
        elif line.startswith('http'):
            if cur_name:
                chans.append({'inf': cur_inf, 'url': line, 'cat': cur_cat,
                              'name': cur_name, 'ua': '', 'ref': ''})
            cur_inf = ''
            cur_name = ''
            cur_cat = 'Общие'
    return chans

def load_disk_cache():
    global playlist_cache, alive_list
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                data = f.read()
            n = data.count('\nhttp')
            if n > 0:
                with cache_lock:
                    playlist_cache = data
                    alive_list = _parse_cached(data)
                    stats['alive_channels'] = len(alive_list)
                logger.info(f"💾 Восстановлен плейлист с диска: {len(alive_list)} каналов")
    except Exception as e:
        logger.error(f"Дисковый кэш не читается: {e}")

def save_disk_cache(data):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            f.write(data)
    except Exception:
        pass

def keepalive_worker():
    n = 0
    while True:
        time.sleep(CONFIG['KEEPALIVE_SEC'])
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

def _clean(lst):
    return [w for w in lst if isinstance(w, str) and len(w.strip()) >= 2]

ADULT_WORDS = _clean(['xxx', 'adult', 'porn', 'sex', 'hentai', '18+',
                      'эротика', 'порно', 'nude', 'playboy'])
UA_WORDS = _clean(['україн', 'украина', 'україна', 'kyiv', 'kiev', 'київ',
                   'львів', 'львов', 'харків', 'дніпро', 'одеса', 'суспільне',
                   'суспильне', 'прямий', 'тсн', '1+1', '2+2', 'інтер',
                   'inter ua', 'верес', 'тоніс', 'тонис', 'ua: ', 'ua |',
                   '| ua', ' ukraine', 'украинск', '5 kanal',
                   'надія', 'новий', 'перший', 'ранок', 'мова', 'тб',
                   'нація', 'світ тв', 'люд', 'країна'])
PAYWALL_WORDS = _clean(['подписк', 'subscription', 'оплат', 'payment', 'купить',
                        'продаж', 'whatsapp', 'telegram', 't.me', 'promo',
                        'реклам', 'advert', 'магазин', 'shop', 'store',
                        'premium', 'премиум', 'vip', 'вип', 'ppv',
                        'pay per view', 'активация', 'iptv', 'fifa', 'wink',
                        'world cup', 'чемпионат мира', 'плей-офф', 'тариф',
                        'абонент'])
BLACKLIST_WORDS = _clean(['fifa', 'world cup', 'чемпионат мира', 'плей-офф'])
RADIO_WORDS = _clean([
    'радио', 'radio', 'fm', 'ржд', 'дорожное', 'авторадио', 'ретро fm',
    'europa plus', 'европа плюс', 'шансон', 'dfm', 'monte carlo', 'maximum',
    'record', 'energy', 'relax fm', 'детское радио', 'юмор fm', 'azadliq',
    'radiola', 'dorognoe', 'nashe radio', 'наше радио', 'kommersant fm',
    'маяк', 'вестей fm', 'эхо', 'love radio', 'хит fm', 'радио дача'])
LATIN_RU_WORDS = _clean([
    'rt ', 'rt.', 'rt doc', 'rtr', 'planeta', 'pervyi', 'pervy', 'channel one',
    'match tv', 'match!', 'zvezda', 'karusel', 'carousel', 'muz-tv', 'muz tv',
    'ru.tv', 'rutv', 'tv1000', 'tv 1000', 'ren tv', 'ntv', 'sts', 'tnt',
    'rossiya', 'rossia', 'russia', 'vesti', 'izvestia', 'kultura', 'soyuz',
    'spas', '