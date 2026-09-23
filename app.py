import os, re, sys, time, math, zlib, json, random, logging, threading, sqlite3
import requests, urllib3
from collections import Counter, deque
from urllib.parse import urlparse, unquote, quote
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify, request

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)
VERSION = '7.1'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'playlist_disk.m3u')
DB_FILE = os.path.join(BASE_DIR, 'ml_history.db')
MODEL_FILE = os.path.join(BASE_DIR, 'ml_model.json')
SOURCES_FILE = os.path.join(BASE_DIR, 'sources.json')
LOG_FILE = os.path.join(BASE_DIR, 'server.log')
VERDICT_FILE = os.path.join(BASE_DIR, 'verdict.json')
GITHUB_RAW = "https://raw.githubusercontent.com/ivanlelikivanov-cloud/iptv-parser/main/app.py"
SELF_UPDATE_INTERVAL = 3600

STATIC_SOURCES = [
    "https://iptv-org.github.io/iptv/index.m3u",
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/countries/by.m3u",
    "https://iptv-org.github.io/iptv/countries/kz.m3u",
    "https://iptv-org.github.io/iptv/countries/kg.m3u",
    "https://iptv-org.github.io/iptv/countries/uz.m3u",
    "https://iptv-org.github.io/iptv/countries/am.m3u",
    "https://iptv-org.github.io/iptv/countries/az.m3u",
    "https://iptv-org.github.io/iptv/countries/ge.m3u",
    "https://iptv-org.github.io/iptv/countries/md.m3u",
    "https://iptv-org.github.io/iptv/countries/tj.m3u",
    "https://iptv-org.github.io/iptv/countries/tm.m3u",
    "https://iptv-org.github.io/iptv/countries/il.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/languages/bel.m3u",
    "https://iptv-org.github.io/iptv/languages/kaz.m3u",
    "https://iptv-org.github.io/iptv/languages/uzb.m3u",
    "https://iptv-org.github.io/iptv/languages/kir.m3u",
    "https://iptv-org.github.io/iptv/languages/tgk.m3u",
    "https://iptv-org.github.io/iptv/languages/arm.m3u",
    "https://iptv-org.github.io/iptv/languages/aze.m3u",
    "https://iptv-org.github.io/iptv/languages/tat.m3u",
    "https://iptv-org.github.io/iptv/languages/che.m3u",
    "https://iptv-org.github.io/iptv/languages/bak.m3u",
    "https://iptv-org.github.io/iptv/languages/chv.m3u",
    "https://iptv-org.github.io/iptv/languages/udm.m3u",
    "https://iptv-org.github.io/iptv/languages/sah.m3u",
    "https://iptv-org.github.io/iptv/languages/kat.m3u",
    "https://iptv-org.github.io/iptv/languages/heb.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
    "https://iptv-org.github.io/iptv/categories/family.m3u",
    "https://iptv-org.github.io/iptv/categories/culture.m3u",
    "https://iptv-org.github.io/iptv/categories/education.m3u",
    "https://iptv-org.github.io/iptv/categories/comedy.m3u",
    "https://iptv-org.github.io/iptv/categories/series.m3u",
    "https://iptv-org.github.io/iptv/categories/animation.m3u",
    "https://iptv-org.github.io/iptv/categories/religious.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/index.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlists/playlist_russia.m3u8",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/smolnp/IPTVru/main/IPTVru.m3u",
    "https://smolnp.github.io/IPTVru/IPTVru.m3u",
    "https://raw.githubusercontent.com/hmlendea/iptv-playlist-aggregator/master/output/playlist.m3u",
    "https://raw.githubusercontent.com/VladAlex1975/IPTV/main/IPTV.m3u",
    "https://raw.githubusercontent.com/EdWeber/iptv/master/iptv.m3u",
    "https://raw.githubusercontent.com/LaneSh4d0w/IPTV_Russia/master/iptv.m3u",
    "https://raw.githubusercontent.com/zhenyafedorov/iptv/main/iptv.m3u",
    "https://raw.githubusercontent.com/SamantazFox/IPTV-RU/master/iptv.m3u",
    "http://iptv-list.mart.ru/playlist.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://webarmen.com/my/iptv/auto.m3u",
    "https://new.m3u.su/rusm", "https://new.m3u.su/so", "https://new.m3u.su/runtv",
    "https://new.m3u.su/rurt", "https://new.m3u.su/rut", "https://new.m3u.su/ruz",
    "https://new.m3u.su/lgu", "https://new.m3u.su/lgn", "https://new.m3u.su/tvoe",
    "https://new.m3u.su/h", "https://new.m3u.su/mult",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
]
HTML_SOURCES = [
    "https://m3u.su/", "https://m3u.su/m3u/", "https://new.m3u.su/",
    "https://sat-portal.com/plejlisty/", "https://6x6.msk.ru/", "https://homtv.ru/",
    "https://iptv-rus.com/", "https://iptv-rus.com/playlists/",
    "https://pikniktv.info/viewforum.php?f=328", "https://webarmen.com/my/iptv/",
    "https://go2tv.top/", "https://iptv.one/", "https://iptv.best/",
    "https://iptv-channels.net/", "https://iptv-live.ru/", "https://iptv-tv.ru/",
    "https://iptv-russia.online/", "https://vse-tv.net/", "https://vse-tv.net/playlists.html",
    "https://forumtv.org/", "https://onlinetv.ru/", "https://smotret-tv.online/",
    "https://pskovline.tv/tvm3u.php", "https://github.com/iptv-org/iptv",
    "https://github.com/Free-iptv/iptv", "https://github.com/4mirror/iptv",
    "https://github.com/hmlendea/iptv-playlist-aggregator",
]
GITHUB_QUERIES = ['iptv ru', 'iptv russia', 'iptv russian', 'm3u ru', 'm3u russia',
                  'iptv playlist ru', 'topic:iptv ru', 'iptv m3u8 ru', 'iptv снг', 'iptv cis']
GH_COMMON_PATHS = ['ru.m3u', 'russia.m3u', 'iptv.m3u', 'tv.m3u', 'main.m3u', 'index.m3u',
                   'playlist.m3u', 'channels/ru.m3u', 'playlist.m3u8', 'ru.m3u8',
                   'output/playlist.m3u']
WEB_QUERIES = ['iptv m3u ru бесплатно', 'плейлист iptv m3u россия',
               'iptv playlist m3u8 russia free', 'iptv m3u8 ru бесплатно',
               'site:t.me iptv m3u', 'iptv плейлист форум бесплатно']
TG_CHANNELS = ['iptvru', 'iptv_russia', 'russian_iptv', 'iptv_m3u', 'freeiptv_ru',
               'iptv_playlist', 'm3u_playlist', 'iptvfree', 'tv_playlist', 'iptv_rf']
FALLBACK_REGIONS = [
    "ru-kgd", "ru-mow", "ru-mos", "ru-spe", "ru-len", "ru-kda", "ru-ros",
    "ru-vgg", "ru-sta", "ru-da", "ru-sam", "ru-ud", "ru-ta", "ru-ba",
]
CFG_MSG = "📚 источники вшиты"
try:
    with open(SOURCES_FILE, encoding='utf-8') as f:
        _d = json.load(f)
    STATIC_SOURCES += _d.get('static', [])
    HTML_SOURCES += _d.get('html', [])
    TG_CHANNELS += _d.get('tg_channels', [])
    CFG_MSG = f"📚 sources.json добавил: {len(_d.get('static', []))} static"
except Exception:
    pass

MAX_CHANNELS = 8000
MAX_ALIVE = 6000
MAX_EXTRA_SOURCES = 600
MAX_CHECK_POOL = 3000
SOURCE_WORKERS = 12
CHECK_WORKERS = 15
CHECK_TIMEOUT = 15.0
SEED_TIMEOUT = 5.0
SOURCE_PHASE_MAX = 600
CHECK_PHASE_MAX = 1200
UPDATE_EVERY = 86400
RETRY_IF_EMPTY = 600
FLUSH_EVERY = 5
HEARTBEAT_SEC = 20
KEEPALIVE_SEC = 60
SWEEP_EVERY = 43200
SWEEP_TIMEOUT = 10.0
SWEEP_WORKERS = 12
DEAD_LIMIT = 2
MAX_PLAYLIST_BYTES = 1000000
MAX_HTML_BYTES = 300000
NET_P_MIN = 0.60
NET_MARGIN = 0.25
HOST_REP_MIN = 0.15
HOST_REP_CNT = 10
SCORE_MODEL_P, SCORE_MODEL_REP, SCORE_MODEL_HEUR = 0.5, 0.35, 0.15
SCORE_NOMODEL_REP, SCORE_NOMODEL_HEUR, SCORE_NOMODEL_CNT = 0.55, 0.25, 0.2
RU_BONUS = 0.15

CIS_COUNTRIES = {'RU', 'BY', 'KZ', 'KG', 'UZ', 'AM', 'AZ', 'GE', 'MD', 'TJ'}
TRUSTED_HOSTS = {'iptv-org.github.io', 'raw.githubusercontent.com', 'new.m3u.su',
                 'm3u.su', 'webarmen.com', 'smolnp.github.io', 'iptv-list.mart.ru'}
OTT_HOSTS = ('wink.ru', 'okko.tv', 'ivi.ru', 'more.tv', 'kion.ru', 'start.ru',
             'premier.one', 'zabava.ru', 'rt.ru', 'rostelecom.ru')
RU_HOST_HINTS = ('.ru', '.su', '.рф', 'm3u.su', 'new.m3u.su', 'webarmen',
                 'iptv-list', 'smolnp')
CAT_ORDER = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 'Детские',
             'Музыка', 'Познавательные', 'Развлекательные', 'Региональные',
             'Радио', 'Общие']
EPG_URLS = ("https://iptv-org.github.io/epg/guides/ru.xml.gz,"
            "https://iptv-org.github.io/epg/guides/by.xml.gz,"
            "https://iptv-org.github.io/epg/guides/kz.xml.gz")
API_CAT_MAP = [
    (['radio'], 'Радио'), (['kids', 'animation'], 'Детские'),
    (['news', 'business'], 'Новости'), (['sports'], 'Спорт'),
    (['movies', 'series'], 'Кино и сериалы'), (['music'], 'Музыка'),
    (['documentary', 'science', 'culture', 'education', 'history', 'travel',
      'food', 'cooking', 'health', 'hobby', 'home', 'auto', 'outdoor',
      'weather', 'religious', 'lifestyle'], 'Познавательные'),
    (['comedy', 'entertainment', 'family', 'relax', 'general'], 'Развлекательные'),
]

SELF_URL = os.environ.get('RENDER_EXTERNAL_URL', 'http://127.0.0.1:10000')
IS_RENDER = bool(os.environ.get('RENDER_EXTERNAL_URL'))
CLEAN_MODE = os.environ.get('CLEAN', '0') == '1'
ENABLE_SELF_UPDATE = not IS_RENDER

if IS_RENDER:
    SOURCE_WORKERS = 10
    CHECK_WORKERS = 12
    SWEEP_WORKERS = 10
    MAX_CHECK_POOL = 2500
    MAX_EXTRA_SOURCES = 400
    CLEAN_MODE = False

def api_category(cats):
    if not cats: return None
    low = [str(c).lower() for c in cats]
    for keys, cat in API_CAT_MAP:
        if any(k in low for k in keys): return cat
    return None

playlist_cache = "#EXTM3U\n# IPTV Russia Pro — идёт первая проверка...\n"
alive_list = []
SWEEP_VERDICT = {}
DEAD_STRIKES = {}
LOGO_MAP = {}
RESERVE = {}
RESERVE_CAP = 4
cache_lock = threading.Lock()
is_updating = False
stats = {
    "version": VERSION, "last_update": None, "duration_sec": 0, "sources_total": 0,
    "playlists_loaded": 0, "api_streams": 0, "parsed_channels": 0,
    "alive_channels": 0, "filtered": {}, "categories": {},
    "ml_samples": 0, "ml_accuracy": 0.0, "nb_moved": 0,
    "last_sweep": None, "sweep_removed": 0, "sweep_dead": 0, "host_blacklisted": 0,
    "check_counts": {}, "clean_mode": CLEAN_MODE,
    "ott_swapped": 0, "ott_removed": 0,
}
agent_state = {
    "status": "starting",
    "self_updates": 0,
    "worker_restarts": 0,
    "oom_caught": 0,
    "last_diagnosis": "init",
    "last_check": 0,
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)],
)
logger = logging.getLogger(__name__)
logger.info(f"🤖 Агент v{VERSION} активирован | {'RENDER' if IS_RENDER else 'LOCAL'} | CLEAN={CLEAN_MODE}")

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}
GOOD_CT = ('video/', 'audio/', 'octet-stream', 'mp2t')
UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0',
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
                 'оплат', 'заблокирован', 'недоступен', 'роскомнадзор',
                 'на этой территории', 'territory']

def proxy_url(u, ua=None, ref=None, base=None):
    q = (base or SELF_URL).rstrip('/') + '/proxy?url=' + quote(u, safe='')
    if ua: q += '&ua=' + quote(ua, safe='')
    if ref: q += '&ref=' + quote(ref, safe='')
    return q

def _sig(z):
    if z >= 0: return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z); return ez / (1.0 + ez)

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
            with open(path, 'w') as f: json.dump({'w': self.w, 'b': self.b}, f)
        except Exception: pass
    def load(self, path):
        try:
            if os.path.exists(path):
                with open(path) as f: d = json.load(f)
                self.w, self.b = d['w'], d['b']; return True
        except Exception: pass
        return False

class CheckDB:
    def __init__(self):
        self.q = deque(); self.lock = threading.Lock(); self.db = None
        self._alive = True
        try:
            self.db = sqlite3.connect(DB_FILE, check_same_thread=False)
            self.db.execute('CREATE TABLE IF NOT EXISTS checks '
                            '(id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT, alive INTEGER, ts REAL)')
            self.db.commit()
        except Exception as e:
            logger.error(f"🗄 БД недоступна: {e}")
        self._writer_thread = threading.Thread(target=self._writer, daemon=True)
        self._writer_thread.start()
    def push(self, host, alive):
        with self.lock: self.q.append((host, 1 if alive else 0, time.time()))
    def history(self):
        if not self.db: return []
        try:
            return self.db.execute('SELECT host, SUM(alive), COUNT(*) FROM checks GROUP BY host').fetchall()
        except Exception: return []
    def _writer(self):
        while self._alive:
            time.sleep(5)
            if not self.db: continue
            with self.lock:
                batch = list(self.q); self.q.clear()
            if not batch: continue
            try:
                self.db.executemany('INSERT INTO checks (host, alive, ts) VALUES (?,?,?)', batch)
                self.db.execute('DELETE FROM checks WHERE id NOT IN '
                                '(SELECT id FROM checks ORDER BY ts DESC LIMIT 20000)')
                self.db.commit()
            except Exception as e:
                logger.error(f"🗄 Ошибка записи: {e}")
    def is_alive(self): return self._alive

checkdb = CheckDB()

class CategoryNet:
    def __init__(self, dim=4096):
        self.dim = dim; self.W = {}; self.b = {}
    @staticmethod
    def _h(t): return zlib.crc32(t.encode('utf-8')) & 0x7fffffff
    def feats(self, name):
        words = re.findall(r'[a-zа-яё0-9]+', name.lower())
        idx = set()
        for w in words:
            idx.add(self._h(w) % self.dim)
            if len(w) >= 4:
                for i in range(len(w) - 1): idx.add(self._h(w[i:i+2]) % self.dim)
            if len(w) >= 5:
                for i in range(len(w) - 2): idx.add(self._h(w[i:i+3]) % self.dim)
        return list(idx)
    def scores(self, x):
        s = {c: self.b.get(c, 0.0) for c in self.b}
        for c in list(s):
            Wc = self.W.get(c)
            if Wc: s[c] += sum(Wc.get(h, 0.0) for h in x)
        return s
    def predict(self, name):
        if not self.b: return None, 0.0, 0.0
        s = self.scores(self.feats(name))
        if not s: return None, 0.0, 0.0
        mx = max(s.values())
        exps = {c: math.exp(v - mx) for c, v in s.items()}
        tot = sum(exps.values())
        order = sorted(((exps[c] / tot, c) for c in s), reverse=True)
        p1 = order[0][0]
        p2 = order[1][0] if len(order) > 1 else 0.0
        return order[0][1], p1, p2
    def train(self, pairs, epochs=5, lr=0.15):
        if not pairs: return
        for _ in range(epochs):
            for name, cat in pairs:
                x = self.feats(name)
                if not x: continue
                s = self.scores(x)
                if cat not in s: s[cat] = 0.0
                mx = max(s.values())
                exps = {c: math.exp(v - mx) for c, v in s.items()}
                tot = sum(exps.values())
                for c, e in exps.items():
                    g = (e / tot) - (1.0 if c == cat else 0.0)
                    if abs(g) < 1e-6: continue
                    self.b[c] = self.b.get(c, 0.0) - lr * g
                    Wc = self.W.setdefault(c, {})
                    for h in x: Wc[h] = Wc.get(h, 0.0) - lr * g

cat_net = CategoryNet()

def apply_net(ch_list):
    moved = 0
    for ch in ch_list:
        if ch['cat'] == 'Общие':
            pred, p1, p2 = cat_net.predict(ch['name'])
            if pred and p1 >= NET_P_MIN and (p1 - p2) >= NET_MARGIN:
                ch['cat'] = pred
                ch['inf'] = ch['inf'].replace('group-title="Общие"', 'group-title="' + pred + '"')
                moved += 1
    return moved

class MLBrain:
    def __init__(self):
        self.host_alive, self.host_total = {}, {}
        self.model = TinyLR()
        self.trained_samples = 0; self.last_accuracy = 0.0
        self.lock = threading.RLock()
        for host, s, c in checkdb.history():
            self.host_alive[host] = int(s); self.host_total[host] = int(c)
        if self.model.load(MODEL_FILE):
            logger.info("🧠 ML: веса загружены")
    def host_stats(self, host):
        with self.lock:
            t = self.host_total.get(host, 0); a = self.host_alive.get(host, 0)
        if t == 0: return 0.5, 0
        return (a + 1.0) / (t + 2.0), t
    def record(self, host, alive):
        with self.lock:
            self.host_total[host] = self.host_total.get(host, 0) + 1
            self.host_alive[host] = self.host_alive.get(host, 0) + (1 if alive else 0)
        checkdb.push(host, alive)
    def score(self, feats, host):
        rep, cnt = self.host_stats(host)
        heur = 0.5 * feats[2] + 0.3 * feats[3] + 0.2 * (1.0 - feats[5])
        try: p = self.model.prob(feats)
        except Exception: p = None
        if p is None:
            return (SCORE_NOMODEL_REP * rep + SCORE_NOMODEL_HEUR * heur +
                    SCORE_NOMODEL_CNT * min(cnt / 10.0, 1.0))
        return SCORE_MODEL_P * p + SCORE_MODEL_REP * rep + SCORE_MODEL_HEUR * heur
    def train(self, samples):
        if not samples or len(samples) < 20: return
        X = [s[0] for s in samples]; y = [s[1] for s in samples]
        if len(set(y)) < 2: return
        acc = None
        try:
            preds = [1 if self.model.prob(x) > 0.5 else 0 for x in X[:300]]
            acc = sum(1 for p, t in zip(preds, y[:300]) if p == t) / max(1, len(preds))
        except Exception: acc = None
        try:
            self.model.partial_fit(X, y)
            self.trained_samples += len(samples)
            if acc is not None: self.last_accuracy = acc
            self.model.save(MODEL_FILE)
        except Exception as e: logger.error(f"🧠 ML: {e}")

brain = MLBrain()

def extract_features(ch):
    url = ch['url']; name = (ch.get('name') or '').lower(); u = url.lower()
    rep, cnt = brain.host_stats(urlparse(url).netloc)
    return [
        min(len(u)/300.0, 1.0), min(u.count('/')/8.0, 1.0),
        1.0 if u.startswith('https') else 0.0, 1.0 if '.m3u8' in u else 0.0,
        1.0 if re.search(r'\.(ts|mp4|mkv|flv)(\?|$)', u) else 0.0,
        1.0 if any(t in u for t in ['token','key=','auth','session','sig=']) else 0.0,
        1.0 if ('hd' in name or '4k' in name) else 0.0, min(len(name)/40.0, 1.0),
        rep, min(cnt/20.0, 1.0),
        1.0 if (ch.get('ua') or ch.get('ref')) else 0.0,
        1.0 if 'iptv-org' in u else 0.0,
    ]

def is_ott_host(url):
    h = urlparse(url).netloc.lower()
    return any(d in h for d in OTT_HOSTS)
def is_ru_host(url):
    h = urlparse(url).netloc.lower()
    return any(t in h for t in RU_HOST_HINTS)
def ru_host_bonus(url):
    return RU_BONUS if is_ru_host(url) else 0.0

def push_reserve(key, url, ua='', ref=''):
    if not key or is_ott_host(url): return
    lst = RESERVE.setdefault(key, [])
    if len(lst) >= RESERVE_CAP: return
    for c in lst:
        if c['url'] == url: return
    lst.append({'url': url, 'ua': ua or '', 'ref': ref or ''})

def heal_ott(alive, alive_urls):
    swapped = 0; kept = []
    for ch in alive:
        if not is_ott_host(ch['url']):
            kept.append(ch); continue
        key = norm_name(ch['name']); pick = None
        for c in RESERVE.get(key, []):
            if c['url'] not in alive_urls and not is_ott_host(c['url']):
                pick = c; break
        if pick:
            alive_urls.discard(ch['url']); old = ch['url']
            ch['url'] = pick['url']; ch['ua'] = pick['ua']; ch['ref'] = pick['ref']
            alive_urls.add(pick['url'])
            SWEEP_VERDICT.pop(old, None); DEAD_STRIKES.pop(old, None)
            swapped += 1; kept.append(ch)
    return kept, swapped

def _parse_cached(data):
    chans = []; cur_inf = ''; cur_name = ''; cur_cat = 'Общие'
    for line in data.splitlines():
        line = line.strip()
        if line.startswith('#EXTINF:'):
            cur_inf = line
            m = re.search(r'group-title="([^"]*)"', line); cur_cat = m.group(1) if m else 'Общие'
            m2 = re.search(r',\s*(.+)$', line); cur_name = m2.group(1).strip() if m2 else ''
        elif line.startswith('#'): continue
        elif line.startswith('http'):
            if cur_name:
                chans.append({'inf': cur_inf, 'url': line, 'cat': cur_cat,
                              'name': cur_name, 'ua': '', 'ref': ''})
            cur_inf = ''; cur_name = ''; cur_cat = 'Общие'
    return chans

def load_verdicts():
    try:
        if os.path.exists(VERDICT_FILE):
            with open(VERDICT_FILE) as f: SWEEP_VERDICT.update(json.load(f))
    except Exception: pass
def save_verdicts():
    try:
        with open(VERDICT_FILE, 'w') as f: json.dump(SWEEP_VERDICT, f)
    except Exception: pass

def load_disk_cache():
    global playlist_cache, alive_list
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r', encoding='utf-8') as f: data = f.read()
            n = data.count('\nhttp')
            if n > 0:
                cleaned = [ch for ch in _parse_cached(data)
                           if not reject_reason(ch['name'], ch['url'])
                           and not is_ott_host(ch['url'])]
                with cache_lock:
                    playlist_cache = data; alive_list = cleaned
                    stats['alive_channels'] = len(cleaned)
    except Exception as e: logger.error(f"Дисковый кэш: {e}")
def save_disk_cache(data):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f: f.write(data)
    except Exception: pass

_thread_local = threading.local()
def get_session():
    s = getattr(_thread_local, 'session', None)
    if s is None:
        s = requests.Session()
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=0)
        s.mount('http://', adapter); s.mount('https://', adapter)
        _thread_local.session = s
    return s

def _read_capped(resp, cap):
    chunks = []; total = 0
    for c in resp.iter_content(65536):
        chunks.append(c); total += len(c)
        if total >= cap: break
    resp.close()
    return b''.join(chunks).decode('utf-8', errors='ignore')

def fetch_dynamic():
    found = set()
    for page in HTML_SOURCES:
        try:
            time.sleep(random.uniform(0.1, 0.5))
            r = get_session().get(page, headers=polite_headers(), timeout=(5, 10), verify=False, stream=True)
            if r.status_code == 200:
                html = _read_capped(r, MAX_HTML_BYTES)
                found.update(re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', html, re.I))
                if 'new.m3u.su' in page:
                    found.update(re.findall(r'https://new\.m3u\.su/[a-z0-9]{2,8}(?![\w/])', html))
            else: r.close()
        except Exception: pass
    return list(found)

def fetch_ru_regions():
    try:
        r = get_session().get("https://iptv-org.github.io/api/regions.json", timeout=(5, 10), headers=HEADERS_WEB)
        if r.status_code != 200: return []
        urls = []
        for reg in r.json():
            code = str(reg.get('code', ''))
            if code.upper().startswith('RU-'):
                urls.append('https://iptv-org.github.io/iptv/regions/' + code.lower() + '.m3u')
        return urls
    except Exception: return []

def fetch_github():
    sess = get_session()
    gh_headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/vnd.github+json'}
    repos = []
    for q in GITHUB_QUERIES:
        try:
            r = sess.get('https://api.github.com/search/repositories',
                         params={'q': q, 'per_page': 15, 'sort': 'stars'},
                         headers=gh_headers, timeout=(5, 15))
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    full = item.get('full_name'); branch = item.get('default_branch') or 'main'
                    if full: repos.append((full, branch))
        except Exception: continue
    repos = list(dict.fromkeys(repos))[:40]
    found = set()
    def read_readme(rb):
        full, branch = rb
        try:
            r = get_session().get(f'https://raw.githubusercontent.com/{full}/{branch}/README.md',
                                  headers=polite_headers(), timeout=(5, 10), stream=True)
            if r.status_code == 200:
                return re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', _read_capped(r, MAX_HTML_BYTES), re.I)
            r.close()
        except Exception: pass
        return []
    ex = ThreadPoolExecutor(max_workers=8)
    try:
        for links in ex.map(read_readme, repos, timeout=90): found.update(links)
    except Exception: pass
    finally:
        try: ex.shutdown(wait=False, cancel_futures=True)
        except TypeError: ex.shutdown(wait=False)
    for full, branch in repos:
        base = f'https://raw.githubusercontent.com/{full}/{branch}'
        for path in GH_COMMON_PATHS: found.add(f'{base}/{path}')
    return list(found)

def fetch_web_search():
    m3u = set(); pages = []
    for q in WEB_QUERIES:
        try:
            r = get_session().get('https://html.duckduckgo.com/html/',
                                  params={'q': q}, headers=polite_headers(), timeout=(5, 15))
            if r.status_code == 200:
                m3u.update(re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', r.text, re.I))
                for enc in re.findall(r'uddg=([^&"]+)', r.text): pages.append(unquote(enc))
        except Exception: continue
    def scrape(page):
        try:
            r = get_session().get(page, headers=polite_headers(), timeout=(5, 10), verify=False, stream=True)
            if r.status_code == 200:
                return re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', _read_capped(r, MAX_HTML_BYTES), re.I)
            r.close()
        except Exception: pass
        return []
    ex = ThreadPoolExecutor(max_workers=8)
    try:
        for links in ex.map(scrape, pages[:25], timeout=90): m3u.update(links)
    except Exception: pass
    finally:
        try: ex.shutdown(wait=False, cancel_futures=True)
        except TypeError: ex.shutdown(wait=False)
    return list(m3u)

def fetch_telegram():
    found = set()
    for ch in TG_CHANNELS:
        try:
            r = get_session().get(f'https://t.me/s/{ch}', headers=polite_headers(), timeout=(5, 10), stream=True)
            if r.status_code == 200:
                found.update(re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', _read_capped(r, MAX_HTML_BYTES), re.I))
            else: r.close()
        except Exception: continue
    return list(found)

def fetch_iptv_org_api():
    try:
        sess = get_session()
        ch_r = sess.get("https://iptv-org.github.io/api/channels.json", timeout=(10, 60), headers=HEADERS_WEB)
        st_r = sess.get("https://iptv-org.github.io/api/streams.json", timeout=(10, 60), headers=HEADERS_WEB)
        if ch_r.status_code != 200 or st_r.status_code != 200: return [], [], []
        names = {}; meta = {}; train_pairs = []; geo_pairs = []
        for ch in ch_r.json():
            if ch.get('is_nsfw'): continue
            name = ch.get('name', ''); country = ch.get('country') or ''
            if name and len(name) >= 3:
                geo_pairs.append((name, 'CIS' if country in CIS_COUNTRIES else 'OTHER'))
            if ch.get('country') == 'UA': continue
            cat = api_category(ch.get('categories') or [])
            if name and cat: train_pairs.append((name, cat))
            langs = []
            for lng in (ch.get('languages') or []):
                langs.append(lng.get('code') if isinstance(lng, dict) else lng)
            if country in CIS_COUNTRIES or 'rus' in langs:
                names[ch.get('id')] = name
                meta[ch.get('id')] = {'logo': ch.get('logo') or '', 'cid': ch.get('id') or '',
                                       'cats': ch.get('categories') or []}
        result = []
        for s in st_r.json():
            cid = s.get('channel'); url = s.get('url')
            if cid in names and url and url.startswith('http'):
                m = meta.get(cid, {})
                result.append({'url': url, 'name': names[cid], 'cats': m.get('cats', []),
                               'logo': m.get('logo', ''), 'cid': m.get('cid', ''),
                               'ua': s.get('user_agent') or '', 'ref': s.get('http_referrer') or ''})
        return result, train_pairs, geo_pairs
    except Exception as e: logger.error(f"Ошибка API: {e}"); return [], [], []

def fetch_source_text(url):
    host = urlparse(url).netloc
    try:
        time.sleep(random.uniform(0.1, 0.4))
        sem = host_sem(host)
        with sem:
            r = get_session().get(url, timeout=(5, 10), headers=polite_headers(), verify=False, stream=True)
            if r.status_code != 200: r.close(); return None
            text = _read_capped(r, MAX_PLAYLIST_BYTES)
            return text if text else None
    except Exception: return None

def _clean(lst): return [w for w in lst if isinstance(w, str) and len(w.strip()) >= 2]

ADULT_WORDS = _clean(['xxx','adult','porn','sex','hentai','18+','эротика','порно','nude','playboy'])
UA_WORDS = _clean(['україн','украина','україна','kyiv','kiev','київ','львів','львов','харків','дніпро',
                   'одеса','суспільне','суспильне','прямий','тсн','1+1','2+2','інтер','inter ua','верес'])
PAYWALL_WORDS = _clean(['подписк','subscription','оплат','payment','whatsapp','telegram','t.me','promo',
                        'магазин','shop','store','premium','премиум','vip','ppv','wink','винк','тариф'])
BLACKLIST_WORDS = _clean(['fifa','world cup','чемпионат мира','плей-офф'])
RADIO_WORDS = _clean(['радио','radio','fm','дорожное','авторадио','ретро fm','europa plus','европа плюс',
                      'шансон','dfm','monte carlo','maximum','record','energy','relax fm','маяк','вести fm'])
LATIN_RU_RE = re.compile(
    r'\b(?:rtr|planeta|pervyi|pervy|channel one|match tv|zvezda|karusel|carousel|'
    r'muz-tv|muz tv|ru\.tv|rutv|tv1000|ren tv|ntv|sts|tnt|rossiya|rossia|russia|'
    r'vesti|izvestia|kultura|soyuz|spas|domashniy|pyatnitsa|subbota|mir tv|otr|'
    r'tv centr|tv center|telekanal|shanson tv|retro tv|amedia|moscow 24|moskva 24|'
    r'peterburg|petersburg|len tv|kinopoisk|illuzion|rt)\b', re.I)
BAD_URL_WORDS = _clean(['wink','okko.tv','ivi.ru','more.tv','kion.ru','start.ru','premier.one','zabava','rostelecom'])
JUNK_WORDS = _clean(['webcam','камера','camera','без названия','безымянный','test channel','проверка'])
JUNK_NAMES = {'index','index.m3u8','playlist','playlist.m3u8','live','test','stream','video','m3u',
              'channel','tv','1','hd','fhd','4k','main','default','unknown','без названия','безымянный'}

def is_radio(n): n=n.lower(); return any(w in n for w in RADIO_WORDS) or bool(re.search(r'\bfm\b', n))
def is_adult(n): return any(w in n.lower() for w in ADULT_WORDS)
def is_ukrainian(n): return any(w in n.lower() for w in UA_WORDS)
def is_paywall(n): n=n.lower(); return any(w in n for w in PAYWALL_WORDS) or any(w in n for w in BLACKLIST_WORDS)
def is_russian_like(n):
    if re.search(r'[\u0400-\u04FF]', n): return True
    return bool(LATIN_RU_RE.search(n))
def is_bad_url(u): u=u.lower(); return any(w in u for w in BAD_URL_WORDS)
def norm_name(n):
    n = n.lower().strip()
    n = re.sub(r'[\(\[].*?[\)\]]', '', n)
    n = re.sub(r'\b(hd|fhd|uhd|4k|sd|hevc|h265|h264)\b', '', n)
    return re.sub(r'\s+', ' ', n).strip(' -_|')
def is_junk(n): n=norm_name(n); return n in JUNK_NAMES or len(n)<3 or any(w in n for w in JUNK_WORDS)
def is_hd(n): n=n.lower(); return 'hd' in n or '4k' in n or 'uhd' in n or 'fhd' in n

def reject_reason(name, url=''):
    if is_junk(name): return 'junk'
    if not is_russian_like(name): return 'not_ru'
    if is_adult(name): return 'adult'
    if is_ukrainian(name): return 'ua'
    if is_paywall(name): return 'paywall'
    if url and is_bad_url(url): return 'geo'
    if url and is_ott_host(url): return 'ott'
    return None

def get_category(name):
    if is_radio(name): return 'Радио'
    n = name.lower()
    if any(w in n for w in ['дет','kids','мульт','cartoon','карусель','disney','аниме','nick','baby']): return 'Детские'
    if any(w in n for w in ['новост','вести','информ','news','24','известия','euronews','bbc','cnn','бизнес']): return 'Новости'
    if any(w in n for w in ['спорт','sport','футбол','хоккей','матч','khl','ufc','бокс','киберспорт','баскетбол','теннис']): return 'Спорт'
    if any(w in n for w in ['кино','kino','movie','film','фильм','сериал','series','tv1000','амедиа']): return 'Кино и сериалы'
    if any(w in n for w in ['музык','music','mtv','bridge','шансон','рутв','ru.tv','tnt music','муз']): return 'Музыка'
    if any(w in n for w in ['докум','doc','познав','истори','history','discovery','science','наука','природ','культур','спас','союз']): return 'Познавательные'
    if any(w in n for w in ['развлек','entertainment','юмор','comedy','камеди','квн','шоу']): return 'Развлекательные'
    if any(w in n for w in ['москва','moscow','петербург','petersburg','казань','самара','краснодар','ростов','пермь',
                            'крым','минск','беларусь','алматы','астана','ташкент','баку','ереван','регион','regional']): return 'Региональные'
    if any(w in n for w in ['первый канал','россия 1','россия к','нтв','тнт','стс','рен тв','пятый канал','тв центр','звезда','отр']): return 'Федеральные'
    return 'Общие'

def _first_media_uri(text, base):
    for l in text.splitlines():
        s = l.strip()
        if not s or s.startswith('#'): continue
        return s if s.startswith('http') else base + s
    return None

def check_one(ch, limit=None, deep=False):
    if urlparse(ch['url']).netloc in TRUSTED_HOSTS: deep = False
    lim = limit or CHECK_TIMEOUT; url = ch['url']
    headers = dict(HEADERS_PLAYER)
    if ch.get('ua'): headers['User-Agent'] = ch['ua']
    if ch.get('ref'): headers['Referer'] = ch['ref']
    session = get_session(); start = time.monotonic()
    def remaining(): return lim - (time.monotonic() - start)
    try:
        r = session.head(url, timeout=min(10, lim), headers=headers, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(g in ct for g in GOOD_CT) and 'mpegurl' not in ct: return 'alive'
    except Exception: pass
    for _ in range(2):
        if remaining() <= 1: return 'blocked'
        try:
            r = session.get(url, timeout=remaining(), headers=headers, stream=True, allow_redirects=True, verify=False)
        except Exception: continue
        if r.status_code in (401, 403, 451): return 'blocked'
        if r.status_code in (404, 410): return 'dead'
        if r.status_code >= 400: return 'blocked'
        ct = r.headers.get('content-type', '').lower()
        try: chunk = next(r.iter_content(chunk_size=2048), b'')
        except Exception: continue
        finally:
            try: r.close()
            except Exception: pass
        if not chunk: return 'dead'
        is_hls = ('mpegurl' in ct) or ('.m3u8' in url.lower()) or (chunk[:7] == b'#EXTM3U')
        if not is_hls:
            if any(g in ct for g in GOOD_CT) or chunk[:1] == b'\x47': return 'alive'
            low = chunk[:300].lower()
            if any(m in low for m in BLOCK_MARKERS): return 'blocked'
            if b'<html' in low: return 'dead'
            return 'alive'
        if not deep: return 'alive'
        try:
            r2 = session.get(url, timeout=min(remaining(), 10), headers=headers, verify=False, allow_redirects=True)
            text = r2.text[:200000]
        except Exception: return 'blocked'
        if '#EXTM3U' not in text: return 'dead'
        base = url.rsplit('/', 1)[0] + '/'
        seg = _first_media_uri(text, base)
        if not seg: return 'dead'
        if remaining() <= 1: return 'blocked'
        try:
            rs = session.get(seg, timeout=min(remaining(), 10), headers=headers, stream=True, verify=False, allow_redirects=True)
            if rs.status_code in (401, 403, 451): return 'blocked'
            if rs.status_code >= 400: return 'dead'
            head = next(rs.iter_content(chunk_size=4096), b'')
            rs.close()
        except Exception: return 'blocked'
        if not head: return 'blocked'
        if head[:1] == b'\x47' or b'ftyp' in head[:16] or b'moov' in head[:32]: return 'alive'
        low = head[:200].lower()
        if any(m in low for m in BLOCK_MARKERS): return 'blocked'
        if b'<html' in low: return 'dead'
        return 'alive'
    return 'blocked'

def is_ok(res): return res in ('alive', 'blocked')

def parse_m3u(text, entries, seen_urls, reasons):
    current_inf = ''; current_name = ''
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        if line.startswith('#EXTINF:'):
            current_inf = line
            m = re.search(r',\s*(.+)$', line); current_name = m.group(1).strip() if m else ''
        elif line.startswith('http'):
            if current_name:
                reason = reject_reason(current_name, line)
                if reason: reasons[reason] += 1
                elif line not in seen_urls:
                    seen_urls.add(line)
                    cat = get_category(current_name)
                    inf = re.sub(r'\s*group-title="[^"]*"', '', current_inf)
                    inf = re.sub(r'(#EXTINF:-?\d+)', r'\1 group-title="' + cat + '"', inf, count=1)
                    lk = LOGO_MAP.get(norm_name(current_name))
                    if lk and 'tvg-logo="' not in inf:
                        add = ''
                        if lk[0] and 'tvg-id="' not in inf: add += ' tvg-id="' + lk[0] + '"'
                        if lk[1]: add += ' tvg-logo="' + lk[1] + '"'
                        if add: inf = re.sub(r'(#EXTINF:-?\d+)', lambda m: m.group(1) + add, inf, count=1)
                    ch = {'inf': inf, 'url': line, 'cat': cat, 'name': current_name, 'ua': '', 'ref': ''}
                    key = norm_name(current_name)
                    if key in entries:
                        push_reserve(key, line)
                        if is_hd(current_name) and not is_hd(entries[key]['name']):
                            push_reserve(key, entries[key]['url'], entries[key].get('ua',''), entries[key].get('ref',''))
                            entries[key] = ch
                    else:
                        entries[key] = ch
                        if len(entries) >= MAX_CHANNELS: return True
            current_inf = ''; current_name = ''
    return False

def flush_playlist(alive, elapsed=None, replace=False):
    global playlist_cache, alive_list
    with cache_lock: current = list(alive_list)
    if elapsed is None and not replace and current:
        have = set(c['url'] for c in current)
        have_names = set(norm_name(c['name']) for c in current)
        merged = current
        for ch in alive:
            nk = norm_name(ch['name'])
            if ch['url'] not in have and nk not in have_names:
                have.add(ch['url']); have_names.add(nk); merged.append(ch)
        alive = merged
    def sort_key(ch):
        try: i = CAT_ORDER.index(ch['cat'])
        except ValueError: i = len(CAT_ORDER)
        return (i, SWEEP_VERDICT.get(ch['url'], 0), 0 if is_ru_host(ch['url']) else 1,
                0 if is_hd(ch['name']) else 1, ch['name'].lower())
    alive_sorted = sorted(alive, key=sort_key)
    if not alive_sorted: return
    if len(alive_sorted) > MAX_ALIVE:
        good = [ch for ch in alive_sorted if SWEEP_VERDICT.get(ch['url'], 0) == 0]
        if len(good) >= MAX_ALIVE: alive_sorted = good[:MAX_ALIVE]
        else:
            rest = [ch for ch in alive_sorted if SWEEP_VERDICT.get(ch['url'], 0) != 0]
            alive_sorted = good + rest[:MAX_ALIVE - len(good)]
    cat_counts = Counter(ch['cat'] for ch in alive_sorted)
    lines = ['#EXTM3U url-tvg="' + EPG_URLS + '"',
             '# IPTV Russia Pro MAX v' + VERSION + ' | ' + time.strftime('%Y-%m-%d %H:%M'),
             '# Живых: ' + str(len(alive_sorted)) + ' | без 18+/UA']
    for ch in alive_sorted:
        lines.append(ch['inf'])
        lines.append('#EXTVLCOPT:http-user-agent=VLC/3.0.20 LibVLC/3.0.20')
        if ch.get('ref'): lines.append('#EXTVLCOPT:http-referrer=' + ch['ref'])
        lines.append(ch['url'])
    data = '\n'.join(lines)
    with cache_lock:
        playlist_cache = data; alive_list = alive_sorted
        stats['alive_channels'] = len(alive_sorted); stats['categories'] = dict(cat_counts)
        if elapsed is not None:
            stats['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
            stats['duration_sec'] = round(elapsed, 1)
    save_disk_cache(data)

def quick_seed():
    logger.info("⚡ Стартовый набор...")
    seed_sources = [u for u in STATIC_SOURCES if 'iptv-org.github.io' in u][:12]
    entries = {}; seen = set(); reasons = Counter()
    ex = ThreadPoolExecutor(max_workers=8)
    try:
        for txt in ex.map(fetch_source_text, seed_sources, timeout=30):
            if txt: parse_m3u(txt, entries, seen, reasons)
    except Exception: pass
    finally:
        try: ex.shutdown(wait=False, cancel_futures=True)
        except TypeError: ex.shutdown(wait=False)
    raw = list(entries.values())[:1000]
    if not raw: return []
    alive = []; ex = ThreadPoolExecutor(max_workers=20)
    futs = {ex.submit(check_one, ch, SEED_TIMEOUT): ch for ch in raw}
    try:
        for f in as_completed(futs.keys(), timeout=90):
            ch = futs[f]
            try: res = f.result()
            except Exception: res = 'dead'
            if is_ok(res): alive.append(ch)
            brain.record(urlparse(ch['url']).netloc, is_ok(res))
    except Exception: pass
    finally:
        try: ex.shutdown(wait=False, cancel_futures=True)
        except TypeError: ex.shutdown(wait=False)
    return alive

def health_sweep():
    with cache_lock: snapshot = list(alive_list)
    if not snapshot or is_updating: return
    logger.info(f"🩺 Свип: {len(snapshot)}...")
    dead_n = 0; processed = 0; swapped = 0; dead_urls = set()
    snap_urls = set(c['url'] for c in snapshot)
    ex = ThreadPoolExecutor(max_workers=SWEEP_WORKERS)
    futs = {ex.submit(check_one, ch, SWEEP_TIMEOUT, True): ch for ch in snapshot}
    try:
        for f in as_completed(futs.keys(), timeout=600):
            ch = futs[f]
            try: res = f.result()
            except Exception: res = 'dead'
            processed += 1
            if is_ok(res):
                SWEEP_VERDICT[ch['url']] = 0; DEAD_STRIKES.pop(ch['url'], None)
            else:
                SWEEP_VERDICT[ch['url']] = 1; dead_n += 1
                n = DEAD_STRIKES.get(ch['url'], 0) + 1
                if n >= DEAD_LIMIT:
                    key = norm_name(ch['name']); pick = None
                    for c in RESERVE.get(key, []):
                        if c['url'] != ch['url'] and c['url'] not in snap_urls and not is_ott_host(c['url']):
                            pick = c; break
                    if pick:
                        ch['url'] = pick['url']; ch['ua'] = pick['ua']; ch['ref'] = pick['ref']
                        snap_urls.add(pick['url']); SWEEP_VERDICT[ch['url']] = 0; swapped += 1
                    elif CLEAN_MODE:
                        dead_urls.add(ch['url'])
                else:
                    DEAD_STRIKES[ch['url']] = n
            brain.record(ch.get('host', urlparse(ch['url']).netloc), is_ok(res))
    except TimeoutError: logger.warning("⏳ Свип таймаут")
    except Exception as e: logger.error(f"Свип: {e}")
    finally:
        try: ex.shutdown(wait=False, cancel_futures=True)
        except TypeError: ex.shutdown(wait=False)
    save_verdicts()
    with cache_lock:
        stats['last_sweep'] = time.strftime('%Y-%m-%d %H:%M:%S')
        stats['sweep_dead'] = dead_n; stats['sweep_removed'] = len(dead_urls)
        snap = list(alive_list)
    if CLEAN_MODE and dead_urls:
        survivors = [ch for ch in snap if ch['url'] not in dead_urls]
        if survivors: flush_playlist(survivors, replace=True)
    elif snap: flush_playlist(snap, replace=True)
    logger.info(f"🩺 Итог: проверено {processed}, подозрительных {dead_n}, "
                f"заменено {swapped}, удалено {len(dead_urls)}")

def update_cache():
    global playlist_cache, is_updating, LOGO_MAP, RESERVE
    global MAX_CHECK_POOL, CHECK_WORKERS, SOURCE_WORKERS
    if is_updating: return False
    is_updating = True; start = time.time()
    agent_state['status'] = 'updating'
    logger.info(f"🔄 v{VERSION} старт...")
    try:
        api_channels, train_pairs, geo_pairs = fetch_iptv_org_api()
        LOGO_MAP = {}; RESERVE = {}
        for ach in api_channels:
            k = norm_name(ach['name'])
            if k and (ach.get('logo') or ach.get('cid')):
                LOGO_MAP.setdefault(k, (ach.get('cid') or '', ach.get('logo') or ''))
        with cache_lock: alive = list(alive_list)
        alive_urls = set(ch['url'] for ch in alive)
        alive_names = set(norm_name(ch['name']) for ch in alive)
        for ch in quick_seed():
            if ch['url'] not in alive_urls:
                nk = norm_name(ch['name'])
                if nk not in alive_names:
                    alive_names.add(nk); alive_urls.add(ch['url']); alive.append(ch)
        if alive: flush_playlist(alive)
        entries = {}; seen = set(); reasons = Counter()
        for ach in api_channels:
            name = ach['name']
            if not name: continue
            reason = reject_reason(name, ach['url'])
            if reason: reasons[reason] += 1; continue
            url = ach['url']
            if url in seen: continue
            seen.add(url)
            cat = api_category(ach.get('cats')) or get_category(name)
            inf = '#EXTINF:-1'
            if ach.get('cid'): inf += ' tvg-id="' + ach['cid'] + '"'
            if ach.get('logo'): inf += ' tvg-logo="' + ach['logo'] + '"'
            inf += ' group-title="' + cat + '",' + name
            key = norm_name(name)
            new_ch = {'inf': inf, 'url': url, 'cat': cat, 'name': name, 'ua': ach['ua'], 'ref': ach['ref']}
            if key in entries:
                push_reserve(key, url, ach['ua'], ach['ref'])
                if is_hd(name) and not is_hd(entries[key]['name']):
                    push_reserve(key, entries[key]['url'], entries[key].get('ua',''), entries[key].get('ref',''))
                    entries[key] = new_ch
            else: entries[key] = new_ch
        regions = fetch_ru_regions()
        if not regions: regions = ['https://iptv-org.github.io/iptv/regions/' + r + '.m3u' for r in FALLBACK_REGIONS]
        base = list(set(STATIC_SOURCES + regions))
        extra = list(set(fetch_dynamic() + fetch_github() + fetch_web_search() + fetch_telegram()) - set(base))
        sources = base + extra[:MAX_EXTRA_SOURCES]
        loaded = 0
        ex = ThreadPoolExecutor(max_workers=SOURCE_WORKERS)
        futs = [ex.submit(fetch_source_text, u) for u in sources]
        try:
            for f in as_completed(futs, timeout=SOURCE_PHASE_MAX):
                try: txt = f.result()
                except Exception: txt = None
                if txt: loaded += 1; parse_m3u(txt, entries, seen, reasons)
        except TimeoutError: logger.warning(f"⏳ Таймаут источников, успело {loaded}")
        except Exception as e: logger.error(f"Фаза источников: {e}")
        finally:
            try: ex.shutdown(wait=False, cancel_futures=True)
            except TypeError: ex.shutdown(wait=False)
        with cache_lock: stats['filtered'] = dict(reasons)
        kw_pairs = [(ch['name'], ch['cat']) for ch in entries.values() if ch['cat'] != 'Общие']
        cat_net.train(train_pairs + kw_pairs)
        moved = apply_net(list(entries.values()))
        with cache_lock: stats['nb_moved'] = moved
        raw = list(entries.values()); entries.clear()
        kept = []
        for ch in raw:
            rep, cnt = brain.host_stats(urlparse(ch['url']).netloc)
            if cnt >= HOST_REP_CNT and rep < HOST_REP_MIN: continue
            kept.append(ch)
        raw = kept
        for ch in raw:
            ch['feats'] = extract_features(ch)
            ch['host'] = urlparse(ch['url']).netloc
            ch['ml_score'] = brain.score(ch['feats'], ch['host']) + ru_host_bonus(ch['url'])
        raw.sort(key=lambda c: -c['ml_score'])
        if len(raw) > MAX_CHECK_POOL: raw = raw[:MAX_CHECK_POOL]
        with cache_lock:
            stats['sources_total'] = len(sources); stats['playlists_loaded'] = loaded
            stats['api_streams'] = len(api_channels); stats['parsed_channels'] = len(raw)
        samples = []; check_counts = Counter()
        since_flush = 0; checked = 0; added = 0
        last_beat = time.time(); total = len(raw)
        ex = ThreadPoolExecutor(max_workers=CHECK_WORKERS)
        futs = {ex.submit(check_one, ch, None, True): ch for ch in raw}
        raw = None
        try:
            for f in as_completed(futs.keys(), timeout=CHECK_PHASE_MAX):
                checked += 1; ch = futs[f]
                try: res = f.result()
                except Exception: res = 'dead'
                check_counts[res] += 1
                ok = is_ok(res)
                if ok and ch['url'] not in alive_urls:
                    nk = norm_name(ch['name'])
                    if nk not in alive_names:
                        alive_names.add(nk); alive_urls.add(ch['url']); alive.append(ch)
                        added += 1; since_flush += 1
                        if since_flush >= FLUSH_EVERY: flush_playlist(alive); since_flush = 0
                samples.append((ch['feats'], 1 if ok else 0))
                brain.record(ch['host'], ok)
                if time.time() - last_beat > HEARTBEAT_SEC:
                    logger.info(f"Прогресс: {checked}/{total}, в плейлисте: {len(alive)} (+{added})")
                    last_beat = time.time()
        except TimeoutError: logger.warning(f"⏳ Таймаут проверки ({CHECK_PHASE_MAX}с)")
        except Exception as e: logger.error(f"Фаза проверки: {e}")
        finally:
            try: ex.shutdown(wait=False, cancel_futures=True)
            except TypeError: ex.shutdown(wait=False)
        with cache_lock: stats['check_counts'] = dict(check_counts)
        apply_net(alive)
        before = len(alive)
        alive, sw = heal_ott(alive, alive_urls)
        rm = before - len(alive)
        with cache_lock: stats['ott_swapped'] = sw; stats['ott_removed'] = rm
        brain.train(samples)
        with cache_lock:
            stats['ml_samples'] = brain.trained_samples
            stats['ml_accuracy'] = round(brain.last_accuracy, 3)
        elapsed = time.time() - start
        flush_playlist(alive, elapsed=elapsed)
        logger.info(f"✅ Готово: {len(alive)} (+{added}) за {elapsed:.0f}с")
        return True
    except MemoryError:
        logger.exception("🧯 OOM: уменьшаю пулы вдвое")
        MAX_CHECK_POOL = max(500, MAX_CHECK_POOL // 2)
        CHECK_WORKERS = max(4, CHECK_WORKERS // 2)
        SOURCE_WORKERS = max(4, SOURCE_WORKERS // 2)
        agent_state['oom_caught'] += 1
        return False
    except Exception as e:
        logger.exception(f"Критическая: {e}"); return False
    finally:
        is_updating = False
        agent_state['status'] = 'idle'

_workers = {}
_workers_lock = threading.Lock()

def _register_worker(name, target, daemon=True):
    def wrapper():
        while True:
            try:
                target()
            except Exception as e:
                logger.error(f"💥 Worker {name} упал: {e}")
                agent_state['worker_restarts'] += 1
                time.sleep(5)
    t = threading.Thread(target=wrapper, daemon=daemon, name=name)
    t.start()
    with _workers_lock: _workers[name] = t
    return t

def run_diagnosis():
    alive = stats.get('alive_channels', 0)
    last = stats.get('last_update')
    diag = []
    if alive < 50: diag.append(f"мало каналов ({alive})")
    if not last and not is_updating: diag.append("ещё не было прогонов")
    if is_updating: diag.append("идёт прогон")
    if agent_state['oom_caught'] > 0: diag.append(f"OOM ×{agent_state['oom_caught']}")
    if agent_state['worker_restarts'] > 3: diag.append(f"много рестартов ({agent_state['worker_restarts']})")
    agent_state['last_diagnosis'] = ', '.join(diag) if diag else 'ok'

def supervisor_loop():
    expected = {'background': background_worker, 'sweep': sweep_worker}
    if IS_RENDER: expected['keepalive'] = keepalive_worker
    for name, target in expected.items():
        _register_worker(name, target)
    agent_state['status'] = 'running'
    while True:
        time.sleep(30)
        agent_state['last_check'] = time.time()
        with _workers_lock:
            for name, target in expected.items():
                t = _workers.get(name)
                if t is None or not t.is_alive():
                    logger.warning(f"🔄 Агент перезапускает worker: {name}")
                    _register_worker(name, target)
                    agent_state['worker_restarts'] += 1
        run_diagnosis()

def self_update_loop():
    if not ENABLE_SELF_UPDATE:
        logger.info("🤖 Self-update отключен (Render)")
        while True: time.sleep(3600)
    logger.info("🤖 Self-update ON")
    while True:
        time.sleep(SELF_UPDATE_INTERVAL)
        try:
            r = requests.get(GITHUB_RAW, timeout=15)
            if r.status_code != 200: continue
            remote_code = r.text
            m = re.search(r"VERSION\s*=\s*'([^']+)'", remote_code)
            if not m: continue
            remote_ver = m.group(1)
            if remote_ver == VERSION: continue
            logger.info(f"🤖 Новая версия на GitHub: {remote_ver} (у меня {VERSION})")
            try: compile(remote_code, 'app.py.new', 'exec')
            except SyntaxError as e:
                logger.error(f"🤖 Новый код с ошибкой: {e} — пропускаю"); continue
            tmp = os.path.join(BASE_DIR, 'app.py.new')
            with open(tmp, 'w', encoding='utf-8') as f: f.write(remote_code)
            bak = os.path.join(BASE_DIR, f'app.py.bak.{VERSION}')
            cur = os.path.join(BASE_DIR, 'app.py')
            os.replace(cur, bak); os.replace(tmp, cur)
            logger.info(f"🤖 Обновился до {remote_ver}, перезапускаю процесс...")
            agent_state['self_updates'] += 1
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            logger.error(f"🤖 Self-update ошибка: {e}")

def sweep_worker():
    while True:
        time.sleep(SWEEP_EVERY)
        try: health_sweep()
        except Exception as e: logger.exception(f"🩺 Свип: {e}")

def background_worker():
    while True:
        ok = False
        try: ok = update_cache()
        except Exception as e: logger.exception(f"Фон: {e}")
        with cache_lock: alive_n = stats['alive_channels']
        wait = UPDATE_EVERY if (ok and alive_n > 0) else RETRY_IF_EMPTY
        logger.info(f"Следующий прогон через {wait//60} мин (успех={ok})")
        time.sleep(wait)

def keepalive_worker():
    n = 0
    while True:
        time.sleep(KEEPALIVE_SEC); n += 1
        if n % 5 == 0:
            try: requests.get(SELF_URL + '/health', timeout=10)
            except Exception: pass

HOME_TEMPLATE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>IPTV Russia Pro v7.1</title>
<style>
body{margin:0;font-family:system-ui,sans-serif;background:linear-gradient(135deg,#0f2027,#203a43,#2c5364);color:#fff;min-height:100vh;display:flex;align-items:center;justify-content:center}
.card{background:rgba(255,255,255,.08);backdrop-filter:blur(10px);border-radius:20px;padding:40px;max-width:640px;width:92%;box-shadow:0 20px 60px rgba(0,0,0,.4)}
h1{margin:0 0 8px;font-size:32px}.sub{opacity:.7;margin-bottom:24px}
.btn{display:inline-block;background:#4caf50;color:#fff;text-decoration:none;padding:14px 28px;border-radius:12px;font-size:18px;font-weight:600;margin:8px 8px 8px 0}
.btn.blue{background:#2196f3}.btn.gray{background:#607d8b}.btn.orange{background:#ff7043}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin:24px 0}
.stat{background:rgba(255,255,255,.1);border-radius:12px;padding:14px;text-align:center}
.stat b{display:block;font-size:24px}.stat span{opacity:.7;font-size:12px}
.chip{display:inline-block;background:rgba(255,255,255,.15);border-radius:20px;padding:6px 14px;margin:4px;font-size:13px}
</style></head><body><div class="card">
<h1>🤖 IPTV Russia Pro v7.1</h1>
<div class="sub">агент: self-update + supervisor + OOM-guard • мёртвые → зеркала</div>
<a class="btn" href="/playlist.m3u">📥 Плейлист</a>
<a class="btn orange" href="/playlist.m3u?proxy=1">📡 PROXY</a>
<a class="btn blue" href="/refresh">🔄 Обновить</a>
<a class="btn gray" href="/status">📊 JSON</a>
<div class="stats">
<div class="stat"><b>__ALIVE__</b><span>живых</span></div>
<div class="stat"><b>__PARSED__</b><span>проверено</span></div>
<div class="stat"><b>__MLS__</b><span>ML примеров</span></div>
<div class="stat"><b>__MLA__</b><span>ML точность</span></div>
</div>
<div class="sub">Обновлено: __UPDATED__</div>
<div>__CATS__</div>
</div></body></html>"""

def make_home_page():
    with cache_lock: s = dict(stats)
    cat_html = ''
    for k, v in sorted(s.get('categories', {}).items(), key=lambda kv: -kv[1]):
        cat_html += f'<span class="chip">{k}: {v}</span>'
    page = HOME_TEMPLATE
    for k, v in [('__ALIVE__', s.get('alive_channels',0)), ('__PARSED__', s.get('parsed_channels',0)),
                 ('__MLS__', s.get('ml_samples',0)), ('__MLA__', s.get('ml_accuracy',0)),
                 ('__UPDATED__', s.get('last_update') or 'ещё идёт первая проверка...'),
                 ('__CATS__', cat_html)]:
        page = page.replace(k, str(v))
    return page

@app.route('/')
def home(): return make_home_page()

@app.route('/health')
def health(): return jsonify({'status': 'ok', 'agent': agent_state['status']})

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
@app.route('/playlist')
@app.route('/tv.m3u')
@app.route('/iptv.m3u')
def playlist():
    proxy_mode = request.args.get('proxy') == '1'
    with cache_lock: chans = list(alive_list)
    if not chans:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')
    lines = ['#EXTM3U url-tvg="' + EPG_URLS + '"',
             f'# IPTV Russia Pro MAX v{VERSION} | ' + time.strftime('%Y-%m-%d %H:%M') +
             (' | PROXY' if proxy_mode else ' | DIRECT')]
    for ch in chans:
        lines.append(ch['inf'])
        if proxy_mode:
            ua = ch.get('ua') or 'VLC/3.0.20 LibVLC/3.0.20'
            lines.append(proxy_url(ch['url'], ua, ch.get('ref'), request.url_root))
        else:
            lines.append('#EXTVLCOPT:http-user-agent=VLC/3.0.20 LibVLC/3.0.20')
            if ch.get('ref'): lines.append('#EXTVLCOPT:http-referrer=' + ch['ref'])
            lines.append(ch['url'])
    return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl',
                    headers={'Content-Disposition': 'attachment; filename="iptv.m3u"',
                             'Cache-Control': 'no-store'})

@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    if not url: return ('', 400)
    ua = request.args.get('ua') or HEADERS_PLAYER['User-Agent']
    ref = request.args.get('ref')
    hdr = {'User-Agent': ua}
    if ref: hdr['Referer'] = ref
    try:
        r = requests.get(url, headers=hdr, stream=True, timeout=(10, 30), verify=False, allow_redirects=True)
    except Exception: return ('', 502)
    if r.status_code >= 400:
        r.close(); return ('', 502)
    ct = (r.headers.get('Content-Type') or 'application/octet-stream').lower()
    if 'mpegurl' in ct or url.lower().endswith(('.m3u8', '.m3u')):
        text = r.text; r.close()
        base = url.rsplit('/', 1)[0] + '/'
        out = []
        for line in text.splitlines():
            s = line.strip()
            if not s: continue
            if s.startswith('#'):
                if 'URI="' in s:
                    m = re.search(r'URI="([^"]+)"', s)
                    if m:
                        u2 = m.group(1); abs_u = u2 if u2.startswith('http') else base + u2
                        s = s.replace(m.group(0), 'URI="' + proxy_url(abs_u, ua, ref, request.url_root) + '"')
                out.append(s)
            else:
                abs_u = s if s.startswith('http') else base + s
                out.append(proxy_url(abs_u, ua, ref, request.url_root))
        return Response('\n'.join(out), mimetype='application/vnd.apple.mpegurl',
                        headers={'Cache-Control': 'no-store'})
    def gen():
        try:
            for chunk in r.iter_content(65536): yield chunk
        finally: r.close()
    return Response(gen(), mimetype=ct.split(';')[0],
                    headers={'Cache-Control': 'no-store', 'Access-Control-Allow-Origin': '*'})

@app.route('/status')
def status():
    with cache_lock: data = dict(stats)
    data['is_updating'] = is_updating
    data['agent'] = dict(agent_state)
    return jsonify(data)

@app.route('/refresh')
def refresh():
    if is_updating: return jsonify({'status': 'already_updating'})
    threading.Thread(target=update_cache, daemon=True).start()
    return jsonify({'status': 'refresh_started'})

@app.route('/<path:any_path>')
def fallback(any_path):
    p = any_path.lower()
    if p.endswith(('.m3u', '.m3u8')) or 'playlist' in p or 'm3u' in p:
        return playlist()
    return make_home_page()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск на порту {port}")
    load_verdicts()
    load_disk_cache()
    _register_worker('supervisor', supervisor_loop)
    _register_worker('self_update', self_update_loop)
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)