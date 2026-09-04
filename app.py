import os
import re
import time
import math
import zlib
import json
import random
import logging
import threading
import sqlite3
import requests
import urllib3
from collections import Counter, deque
from urllib.parse import urlparse, unquote, quote
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify, request

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)
VERSION = '5.5'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'playlist_disk.m3u')
DB_FILE = os.path.join(BASE_DIR, 'ml_history.db')
MODEL_FILE = os.path.join(BASE_DIR, 'ml_model.json')
SOURCES_FILE = os.path.join(BASE_DIR, 'sources.json')

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
FALLBACK_REGIONS = [
    "ru-kgd", "ru-mow", "ru-mos", "ru-spe", "ru-len", "ru-kda", "ru-ros",
    "ru-vgg", "ru-sta", "ru-da", "ru-sam", "ru-ud", "ru-ta", "ru-ba",
    "ru-udm", "ru-per", "ru-sve", "ru-che", "ru-tyu", "ru-oms", "ru-nvs",
    "ru-tom", "ru-kem", "ru-alt", "ru-kya", "ru-irk", "ru-bu", "ru-sa",
    "ru-zab", "ru-pri", "ru-kha", "ru-amu", "ru-sak", "ru-mag", "ru-kam",
    "ru-chu",
]
CFG_MSG = "📚 источники вшиты в код"
try:
    with open(SOURCES_FILE, encoding='utf-8') as f:
        _d = json.load(f)
    STATIC_SOURCES += _d.get('static', [])
    HTML_SOURCES += _d.get('html', [])
    CFG_MSG = f"📚 sources.json добавил: {len(_d.get('static', []))} static"
except Exception:
    pass

MAX_CHANNELS = 20000
MAX_EXTRA_SOURCES = 600
MAX_CHECK_POOL = 12000
SOURCE_WORKERS = 20
CHECK_WORKERS = 60
CHECK_TIMEOUT = 40.0
SEED_TIMEOUT = 8.0
SOURCE_PHASE_MAX = 600
CHECK_PHASE_MAX = 1800
UPDATE_EVERY = 86400
RETRY_IF_EMPTY = 600
FLUSH_EVERY = 10
HEARTBEAT_SEC = 20
KEEPALIVE_SEC = 60
SWEEP_EVERY = 21600
SWEEP_TIMEOUT = 25.0
SWEEP_WORKERS = 30
DEAD_LIMIT = 3
MAX_PLAYLIST_BYTES = 2_000_000
MAX_HTML_BYTES = 524_288
NET_P_MIN = 0.60
NET_MARGIN = 0.25
HOST_REP_MIN = 0.15
HOST_REP_CNT = 10
SCORE_MODEL_P, SCORE_MODEL_REP, SCORE_MODEL_HEUR = 0.5, 0.35, 0.15
SCORE_NOMODEL_REP, SCORE_NOMODEL_HEUR, SCORE_NOMODEL_CNT = 0.55, 0.25, 0.2

CIS_COUNTRIES = {'RU', 'BY', 'KZ', 'KG', 'UZ', 'AM', 'AZ', 'GE', 'MD', 'TJ'}
TRUSTED_HOSTS = {'iptv-org.github.io', 'raw.githubusercontent.com', 'new.m3u.su',
                 'm3u.su', 'webarmen.com', 'smolnp.github.io', 'iptv-list.mart.ru'}
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
    "last_sweep": None, "sweep_removed": 0, "host_blacklisted": 0,
    "geo_pairs": 0, "check_counts": {},
}
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)
logger.info(CFG_MSG)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}
GOOD_CT = ('video/', 'audio/', 'octet-stream', 'mp2t')
UA_POOL = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
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
SELF_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://iptv-parser.onrender.com')

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
    def load(self, path):
        try:
            if os.path.exists(path):
                with open(path) as f:
                    d = json.load(f)
                self.w, self.b = d['w'], d['b']
                return True
        except Exception:
            pass
        return False

class CheckDB:
    def __init__(self):
        self.q = deque()
        self.lock = threading.Lock()
        self.db = None
        try:
            self.db = sqlite3.connect(DB_FILE, check_same_thread=False)
            self.db.execute('CREATE TABLE IF NOT EXISTS checks '
                            '(id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT, alive INTEGER, ts REAL)')
            self.db.commit()
        except Exception as e:
            logger.error(f"🗄 БД недоступна: {e}")
        threading.Thread(target=self._writer, daemon=True).start()
    def push(self, host, alive):
        with self.lock:
            self.q.append((host, 1 if alive else 0, time.time()))
    def history(self):
        if not self.db:
            return []
        try:
            return self.db.execute('SELECT host, SUM(alive), COUNT(*) FROM checks GROUP BY host').fetchall()
        except Exception:
            return []
    def _writer(self):
        while True:
            time.sleep(5)
            if not self.db:
                continue
            with self.lock:
                batch = list(self.q)
                self.q.clear()
            if not batch:
                continue
            try:
                self.db.executemany('INSERT INTO checks (host, alive, ts) VALUES (?,?,?)', batch)
                self.db.execute('DELETE FROM checks WHERE id NOT IN '
                                '(SELECT id FROM checks ORDER BY ts DESC LIMIT 20000)')
                self.db.commit()
            except Exception as e:
                logger.error(f"🗄 Ошибка записи: {e}")

checkdb = CheckDB()

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
            if pred and p1 >= NET_P_MIN and (p1 - p2) >= NET_MARGIN:
                ch['cat'] = pred
                ch['inf'] = ch['inf'].replace('group-title="Общие"', 'group-title="' + pred + '"')
                moved += 1
    return moved

class MLBrain:
    def __init__(self):
        self.host_alive, self.host_total = {}, {}
        self.model = TinyLR()
        self.trained_samples = 0
        self.last_accuracy = 0.0
        self.lock = threading.RLock()
        for host, s, c in checkdb.history():
            self.host_alive[host] = int(s)
            self.host_total[host] = int(c)
        logger.info(f"🧠 ML: история хостов: {len(self.host_total)}")
        if self.model.load(MODEL_FILE):
            logger.info("🧠 ML: веса Смотрителя загружены (JSON)")
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
        checkdb.push(host, alive)
    def score(self, feats, host):
        rep, cnt = self.host_stats(host)
        heur = 0.5 * feats[2] + 0.3 * feats[3] + 0.2 * (1.0 - feats[5])
        p = None
        try:
            p = self.model.prob(feats)
        except Exception:
            p = None
        if p is None:
            return (SCORE_NOMODEL_REP * rep + SCORE_NOMODEL_HEUR * heur +
                    SCORE_NOMODEL_CNT * min(cnt / 10.0, 1.0))
        return SCORE_MODEL_P * p + SCORE_MODEL_REP * rep + SCORE_MODEL_HEUR * heur
    def train(self, samples):
        if not samples or len(samples) < 20:
            return
        X = [s[0] for s in samples]
        y = [s[1] for s in samples]
        if len(set(y)) < 2:
            return
        acc = None
        try:
            preds = [1 if self.model.prob(x) > 0.5 else 0 for x in X[:300]]
            acc = sum(1 for p, t in zip(preds, y[:300]) if p == t) / max(1, len(preds))
        except Exception:
            acc = None
        try:
            self.model.partial_fit(X, y)
            self.trained_samples += len(samples)
            if acc is not None:
                self.last_accuracy = acc
            self.model.save(MODEL_FILE)
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
        min(len(u) / 300.0, 1.0), min(u.count('/') / 8.0, 1.0),
        1.0 if u.startswith('https') else 0.0, 1.0 if '.m3u8' in u else 0.0,
        1.0 if re.search(r'\.(ts|mp4|mkv|flv)(\?|$)', u) else 0.0,
        1.0 if any(t in u for t in ['token', 'key=', 'auth', 'session', 'sig=']) else 0.0,
        1.0 if ('hd' in name or '4k' in name) else 0.0, min(len(name) / 40.0, 1.0),
        rep, min(cnt / 20.0, 1.0),
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
                cleaned = [ch for ch in _parse_cached(data)
                           if not reject_reason(ch['name'], ch['url'])]
                with cache_lock:
                    playlist_cache = data
                    alive_list = cleaned
                    stats['alive_channels'] = len(cleaned)
                logger.info(f"💾 Восстановлен плейлист: {len(cleaned)} каналов "
                            f"(вычищено {n - len(cleaned)})")
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
            time.sleep(random.uniform(0.1, 0.5))
            r = get_session().get(page, headers=polite_headers(), timeout=(5, 10), verify=False, stream=True)
            if r.status_code == 200:
                html = _read_capped(r, MAX_HTML_BYTES)
                found.update(re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', html, re.I))
                if 'new.m3u.su' in page:
                    found.update(re.findall(r'https://new\.m3u\.su/[a-z0-9]{2,8}(?![\w/])', html))
            else:
                r.close()
        except Exception:
            pass
    return list(found)

def fetch_ru_regions():
    try:
        r = get_session().get("https://iptv-org.github.io/api/regions.json", timeout=(5, 10), headers=HEADERS_WEB)
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
            time.sleep(random.uniform(0.1, 0.4))
            r = get_session().get('https://raw.githubusercontent.com/' + full + '/' + branch + '/README.md',
                                  headers=polite_headers(), timeout=(5, 10), stream=True)
            if r.status_code == 200:
                return re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', _read_capped(r, MAX_HTML_BYTES), re.I)
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

def fetch_iptv_org_api():
    try:
        sess = get_session()
        ch_r = sess.get("https://iptv-org.github.io/api/channels.json", timeout=(10, 60), headers=HEADERS_WEB)
        st_r = sess.get("https://iptv-org.github.io/api/streams.json", timeout=(10, 60), headers=HEADERS_WEB)
        if ch_r.status_code != 200 or st_r.status_code != 200:
            return [], [], []
        names = {}
        meta = {}
        train_pairs = []
        geo_pairs = []
        for ch in ch_r.json():
            if ch.get('is_nsfw'):
                continue
            name = ch.get('name', '')
            country = ch.get('country') or ''
            if name and len(name) >= 3:
                geo_pairs.append((name, 'CIS' if country in CIS_COUNTRIES else 'OTHER'))
            if ch.get('country') == 'UA':
                continue
            cat = api_category(ch.get('categories') or [])
            if name and cat:
                train_pairs.append((name, cat))
            langs = []
            for lng in (ch.get('languages') or []):
                langs.append(lng.get('code') if isinstance(lng, dict) else lng)
            if country in CIS_COUNTRIES or 'rus' in langs:
                names[ch.get('id')] = name
                meta[ch.get('id')] = {
                    'logo': ch.get('logo') or '', 'cid': ch.get('id') or '',
                    'cats': ch.get('categories') or [],
                }
        result = []
        for s in st_r.json():
            cid = s.get('channel')
            url = s.get('url')
            if cid in names and url and url.startswith('http'):
                m = meta.get(cid, {})
                result.append({
                    'url': url, 'name': names[cid], 'cats': m.get('cats', []),
                    'logo': m.get('logo', ''), 'cid': m.get('cid', ''),
                    'ua': s.get('user_agent') or '', 'ref': s.get('http_referrer') or '',
                })
        return result, train_pairs, geo_pairs
    except Exception as e:
        logger.error(f"Ошибка API iptv-org: {e}")
        return [], [], []

def fetch_source_text(url):
    host = urlparse(url).netloc
    try:
        time.sleep(random.uniform(0.1, 0.4))
        sem = host_sem(host)
        with sem:
            r = get_session().get(url, timeout=(5, 10), headers=polite_headers(), verify=False, stream=True)
            if r.status_code != 200:
                r.close()
                return None
            text = _read_capped(r, MAX_PLAYLIST_BYTES)
            return text if text else None
    except Exception:
        return None

def _clean(lst):
    return [w for w in lst if isinstance(w, str) and len(w.strip()) >= 2]

ADULT_WORDS = _clean(['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'эротика', 'порно', 'nude', 'playboy'])
UA_WORDS = _clean(['україн', 'украина', 'україна', 'kyiv', 'kiev', 'київ', 'львів', 'львов',
                   'харків', 'дніпро', 'одеса', 'суспільне', 'суспильне', 'прямий', 'тсн',
                   '1+1', '2+2', 'інтер', 'inter ua', 'верес', 'тоніс', 'тонис', 'ua: ',
                   'ua |', '| ua', ' ukraine', 'украинск', '5 kanal', 'надія', 'новий',
                   'перший', 'ранок', 'мова', 'тб', 'нація', 'світ тв', 'люд', 'країна'])
PAYWALL_WORDS = _clean(['подписк', 'subscription', 'оплат', 'payment', 'купить', 'продаж',
                        'whatsapp', 'telegram', 't.me', 'promo', 'реклам', 'advert',
                        'магазин', 'shop', 'store', 'premium', 'премиум', 'vip', 'вип',
                        'ppv', 'pay per view', 'активация', 'fifa', 'wink', 'винк',
                        'world cup', 'чемпионат мира', 'плей-офф', 'тариф', 'абонент'])
BLACKLIST_WORDS = _clean(['fifa', 'world cup', 'чемпионат мира', 'плей-офф'])
RADIO_WORDS = _clean(['радио', 'radio', 'fm', 'ржд', 'дорожное', 'авторадио', 'ретро fm',
                      'europa plus', 'европа плюс', 'шансон', 'dfm', 'monte carlo', 'maximum',
                      'record', 'energy', 'relax fm', 'детское радио', 'юмор fm', 'azadliq',
                      'radiola', 'dorognoe', 'nashe radio', 'наше радио', 'kommersant fm',
                      'маяк', 'вести fm', 'радио дача', 'хит fm', 'love radio', 'радио мир'])
LATIN_RU_RE = re.compile(
    r'\b(?:rtr|planeta|pervyi|pervy|channel one|match tv|zvezda|karusel|carousel|'
    r'muz-tv|muz tv|ru\.tv|rutv|tv1000|ren tv|ntv|sts|tnt|rossiya|rossia|russia|'
    r'vesti|izvestia|kultura|soyuz|spas|domashniy|pyatnitsa|subbota|mir tv|otr|'
    r'tv centr|tv center|telekanal|shanson tv|retro tv|amedia|moscow 24|moskva 24|'
    r'peterburg|petersburg|len tv|kinopoisk|illuzion|rt)\b', re.I)
BAD_URL_WORDS = _clean(['wink', 'okko.tv', 'ivi.ru', 'more.tv', 'kion.ru',
                        'start.ru', 'premier.one', 'geoblock', 'geo-block'])
JUNK_WORDS = _clean(['webcam', 'камера', 'camera', 'без названия', 'безымянный', 'test channel', 'проверка'])
JUNK_NAMES = {'index', 'index.m3u8', 'playlist', 'playlist.m3u8', 'live', 'test', 'stream',
              'video', 'm3u', 'channel', 'tv', '1', 'hd', 'fhd', '4k', 'main', 'default',
              'unknown', 'без названия', 'безымянный'}

def is_radio(name):
    n = name.lower()
    return any(w in n for w in RADIO_WORDS) or bool(re.search(r'\bfm\b', n)) or 'радиостанция' in n
def is_adult(name):
    return any(w in name.lower() for w in ADULT_WORDS)
def is_ukrainian(name):
    return any(w in name.lower() for w in UA_WORDS)
def is_paywall(name):
    n = name.lower()
    return any(w in n for w in PAYWALL_WORDS) or any(w.lower() in n for w in BLACKLIST_WORDS)
def is_russian_like(name):
    if re.search(r'[\u0400-\u04FF]', name):
        return True
    return bool(LATIN_RU_RE.search(name))
def is_bad_url(url):
    u = url.lower()
    return any(w in u for w in BAD_URL_WORDS)
def norm_name(name):
    n = name.lower().strip()
    n = re.sub(r'[\(\[].*?[\)\]]', '', n)
    n = re.sub(r'\b(hd|fhd|uhd|4k|sd|hevc|h265|h264)\b', '', n)
    return re.sub(r'\s+', ' ', n).strip(' -_|')
def is_junk(name):
    n = norm_name(name)
    if n in JUNK_NAMES or len(n) < 3:
        return True
    return any(w in n for w in JUNK_WORDS)
def is_hd(name):
    n = name.lower()
    return 'hd' in n or '4k' in n or 'uhd' in n or 'fhd' in n
def reject_reason(name, url=''):
    if is_junk(name):
        return 'junk'
    if not is_russian_like(name):
        return 'not_ru'
    if is_adult(name):
        return 'adult'
    if is_ukrainian(name):
        return 'ua'
    if is_paywall(name):
        return 'paywall'
    if url and is_bad_url(url):
        return 'geo'
    return None

def get_category(name):
    if is_radio(name):
        return 'Радио'
    n = name.lower()
    if any(w in n for w in ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney', 'gulli', 'аниме', 'anime', 'nick', 'tiji', 'baby', 'погоди', 'обезьянк', 'незнайк', 'смешар', 'простокваш', 'чебураш', 'карлсон', 'винни', 'попугай', 'богатыр', 'алёша', 'трёшка', 'мультимани', 'тоша']):
        return 'Детские'
    if any(w in n for w in ['новост', 'вести', 'информ', 'news', '24', 'известия', 'ртд', 'euronews', 'bbc', 'cnn', 'политик', 'эконом', 'бизнес', 'business']):
        return 'Новости'
    if any(w in n for w in ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'khl', 'ufc', 'бокс', 'киберспорт', 'esport', 'автоспорт', 'баскетбол', 'теннис', 'биатлон', 'лыжн']):
        return 'Спорт'
    if any(w in n for w in ['кино', 'kino', 'movie', 'film', 'фильм', 'сериал', 'series', 'serial', 'cinema', 'tv1000', 'амедиа', 'дом кино', 'иллюзион', 'премьер', 'боевик', 'детектив', 'мелодрам', 'комедия', 'ужас', 'фантаст', 'триллер', 'киномикс', 'киносемья', 'кинокомедия', 'киносвидание', 'киноужас', 'кинопоказ']):
        return 'Кино и сериалы'
    if any(w in n for w in ['музык', 'music', 'mtv', 'bridge', 'шансон', 'рутв', 'ru.tv', 'ретро', 'хит', 'жара', 'блюз', 'jazz', 'классик', 'classic', 'муз', 'tnt music', 'о2тв', 'o2tv', 'first music', 'музсоюз', 'клип']):
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

def _first_media_uri(text, base):
    for l in text.splitlines():
        s = l.strip()
        if not s or s.startswith('#'):
            continue
        return s if s.startswith('http') else base + s
    return None

def check_fast(ch):
    url = ch['url']
    headers = dict(HEADERS_PLAYER)
    if ch.get('ua'):
        headers['User-Agent'] = ch['ua']
    if ch.get('ref'):
        headers['Referer'] = ch['ref']
    session = get_session()
    try:
        r = session.head(url, timeout=8, headers=headers, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(g in ct for g in GOOD_CT) and 'mpegurl' not in ct:
                return 'alive'
    except Exception:
        pass
    try:
        r = session.get(url, timeout=8, headers=headers, stream=True, allow_redirects=True, verify=False)
        if r.status_code in (401, 403, 451):
            return 'blocked'
        if r.status_code >= 400:
            return 'dead'
        ct = r.headers.get('content-type', '').lower()
        chunk = next(r.iter_content(chunk_size=2048), b'')
        r.close()
        if not chunk:
            return 'dead'
        if any(g in ct for g in GOOD_CT) or chunk[:1] == b'\x47' or chunk[:7] == b'#EXTM3U':
            return 'alive'
        low = chunk[:300].lower()
        if any(m in low for m in BLOCK_MARKERS):
            return 'blocked'
        if b'<html' in low or b'<!doctype' in low:
            return 'dead'
        return 'alive'
    except Exception:
        return 'blocked'

# deep=False (набор): мягко — объём. deep=True (свип): рентген сегмента — чистка зомби.
def check_one(ch, limit=None, deep=False):
    if urlparse(ch['url']).netloc in TRUSTED_HOSTS:
        return check_fast(ch)
    lim = limit or CHECK_TIMEOUT
    url = ch['url']
    headers = dict(HEADERS_PLAYER)
    if ch.get('ua'):
        headers['User-Agent'] = ch['ua']
    if ch.get('ref'):
        headers['Referer'] = ch['ref']
    session = get_session()
    start = time.monotonic()
    def remaining():
        return lim - (time.monotonic() - start)
    try:
        r = session.head(url, timeout=min(10, lim), headers=headers, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(g in ct for g in GOOD_CT) and 'mpegurl' not in ct:
                return 'alive'
    except Exception:
        pass
    for _ in range(2):
        if remaining() <= 1:
            return 'blocked'
        try:
            r = session.get(url, timeout=remaining(), headers=headers, stream=True, allow_redirects=True, verify=False)
        except Exception:
            continue
        if r.status_code in (401, 403, 451):
            return 'blocked'
        if r.status_code in (404, 410):
            return 'dead'
        if r.status_code >= 400:
            return 'blocked'
        ct = r.headers.get('content-type', '').lower()
        try:
            chunk = next(r.iter_content(chunk_size=2048), b'')
        except Exception:
            continue
        finally:
            r.close()
        if not chunk:
            return 'dead'
        is_hls = ('mpegurl' in ct) or ('.m3u8' in url.lower()) or (chunk[:7] == b'#EXTM3U')
        if not is_hls:
            if any(g in ct for g in GOOD_CT):
                return 'alive'
            if chunk[:1] == b'\x47':
                return 'alive'
            low = chunk[:300].lower()
            if any(m in low for m in BLOCK_MARKERS):
                return 'blocked'
            if b'<html' in low or b'<!doctype' in low or b'<script' in low:
                return 'dead'
            return 'alive'
        if not deep:
            return 'alive'
        # 🔬 рентген: читаем плейлист и щупаем первый сегмент
        try:
            r2 = session.get(url, timeout=min(remaining(), 10), headers=headers, verify=False, allow_redirects=True)
            text = r2.text[:200000]
        except Exception:
            return 'blocked'
        if '#EXTM3U' not in text:
            return 'dead'
        base = url.rsplit('/', 1)[0] + '/'
        seg = _first_media_uri(text, base)
        if not seg:
            return 'dead'
        if remaining() <= 1:
            return 'blocked'
        try:
            rs = session.get(seg, timeout=min(remaining(), 10), headers=headers, stream=True, verify=False, allow_redirects=True)
            if rs.status_code in (401, 403, 451):
                return 'blocked'
            if rs.status_code >= 400:
                return 'dead'
            head = next(rs.iter_content(chunk_size=4096), b'')
            rs.close()
        except Exception:
            return 'blocked'
        if not head:
            return 'blocked'
        if head[:1] == b'\x47' or b'ftyp' in head[:16] or b'moov' in head[:32] or b'styp' in head[:16] or head[:7] == b'#EXTM3U':
            return 'alive'
        low = head[:200].lower()
        if any(m in low for m in BLOCK_MARKERS):
            return 'blocked'
        if b'<html' in low or b'<!doctype' in low:
            return 'dead'
        return 'alive'
    return 'blocked'

def is_ok(res):
    return res in ('alive', 'blocked')

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
                reason = reject_reason(current_name, line)
                if reason:
                    reasons[reason] += 1
                elif line not in seen_urls:
                    seen_urls.add(line)
                    cat = get_category(current_name)
                    inf = re.sub(r'\s*group-title="[^"]*"', '', current_inf)
                    inf = re.sub(r'(#EXTINF:-?\d+)', r'\1 group-title="' + cat + '"', inf, count=1)
                    ch = {'inf': inf, 'url': line, 'cat': cat, 'name': current_name, 'ua': '', 'ref': ''}
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

def flush_playlist(alive, elapsed=None, replace=False):
    global playlist_cache, alive_list
    with cache_lock:
        current = list(alive_list)
    if elapsed is None and not replace and current:
        have = set(c['url'] for c in current)
        have_names = set(norm_name(c['name']) for c in current)
        merged = current
        for ch in alive:
            nk = norm_name(ch['name'])
            if ch['url'] not in have and nk not in have_names:
                have.add(ch['url'])
                have_names.add(nk)
                merged.append(ch)
        alive = merged
    def sort_key(ch):
        try:
            i = CAT_ORDER.index(ch['cat'])
        except ValueError:
            i = len(CAT_ORDER)
        return (i, ch['name'].lower())
    alive_sorted = sorted(alive, key=sort_key)
    if not alive_sorted:
        return
    cat_counts = Counter(ch['cat'] for ch in alive_sorted)
    lines = [
        '#EXTM3U url-tvg="' + EPG_URLS + '"',
        '# IPTV Russia Pro MAX v' + VERSION + ' | ' + time.strftime('%Y-%m-%d %H:%M'),
        '# Живых каналов: ' + str(len(alive_sorted)) + ' | без 18+ | без UA | радио — отдельный раздел',
    ]
    for ch in alive_sorted:
        lines.append(ch['inf'])
        lines.append('#EXTVLCOPT:http-user-agent=VLC/3.0.20 LibVLC/3.0.20')
        if ch.get('ref'):
            lines.append('#EXTVLCOPT:http-referrer=' + ch['ref'])
        lines.append(ch['url'])
    data = '\n'.join(lines)
    with cache_lock:
        playlist_cache = data
        alive_list = alive_sorted
        stats['alive_channels'] = len(alive_sorted)
        stats['categories'] = dict(cat_counts)
        if elapsed is not None:
            stats['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
            stats['duration_sec'] = round(elapsed, 1)
    save_disk_cache(data)

def build_playlist(chans, proxied):
    lines = [
        '#EXTM3U url-tvg="' + EPG_URLS + '"',
        '# IPTV Russia Pro MAX v' + VERSION + ' | ' + time.strftime('%Y-%m-%d %H:%M') +
        (' | PROXY' if proxied else ' | DIRECT'),
    ]
    for ch in chans:
        lines.append(ch['inf'])
        if proxied:
            ua = ch.get('ua') or 'VLC/3.0.20 LibVLC/3.0.20'
            lines.append(proxy_url(ch['url'], ua, ch.get('ref')))
        else:
            lines.append('#EXTVLCOPT:http-user-agent=VLC/3.0.20 LibVLC/3.0.20')
            if ch.get('ref'):
                lines.append('#EXTVLCOPT:http-referrer=' + ch['ref'])
            lines.append(ch['url'])
    return '\n'.join(lines)

@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    if not url:
        return ('', 400)
    ua = request.args.get('ua') or HEADERS_PLAYER['User-Agent']
    ref = request.args.get('ref')
    hdr = {'User-Agent': ua}
    if ref:
        hdr['Referer'] = ref
    try:
        r = requests.get(url, headers=hdr, stream=True, timeout=(10, 30), verify=False, allow_redirects=True)
    except Exception:
        return ('', 502)
    if r.status_code >= 400:
        r.close()
        return ('', 502)
    ct = (r.headers.get('Content-Type') or 'application/octet-stream').lower()
    if 'mpegurl' in ct or url.lower().endswith(('.m3u8', '.m3u')):
        text = r.text
        r.close()
        base = url.rsplit('/', 1)[0] + '/'
        out = []
        for line in text.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith('#'):
                if 'URI="' in s:
                    m = re.search(r'URI="([^"]+)"', s)
                    if m:
                        u2 = m.group(1)
                        abs_u = u2 if u2.startswith('http') else base + u2
                        s = s.replace(m.group(0), 'URI="' + proxy_url(abs_u, ua, ref) + '"')
                out.append(s)
            else:
                abs_u = s if s.startswith('http') else base + s
                out.append(proxy_url(abs_u, ua, ref))
        resp = Response('\n'.join(out), mimetype='application/vnd.apple.mpegurl')
        resp.headers['Cache-Control'] = 'no-store'
        return resp
    def gen():
        try:
            for chunk in r.iter_content(65536):
                yield chunk
        finally:
            r.close()
    resp = Response(gen(), mimetype=ct.split(';')[0])
    resp.headers['Cache-Control'] = 'no-store'
    resp.headers['Access-Control-Allow-Origin'] = '*'
    return resp

def make_playlist_response():
    proxy_mode = request.args.get('proxy') == '1'
    with cache_lock:
        chans = list(alive_list)
    data = build_playlist(chans, proxy_mode) if chans else playlist_cache
    resp = Response(data, mimetype='application/vnd.apple.mpegurl')
    resp.headers['Content-Disposition'] = 'attachment; filename="iptv_russia_max.m3u"'
    resp.headers['Cache-Control'] = 'no-store'
    return resp

def quick_seed():
    logger.info("⚡ Быстрый стартовый набор: надёжные источники iptv-org...")
    seed_sources = [u for u in STATIC_SOURCES if 'iptv-org.github.io' in u][:12]
    entries = {}
    seen = set()
    reasons = Counter()
    ex = ThreadPoolExecutor(max_workers=12)
    try:
        for txt in ex.map(fetch_source_text, seed_sources, timeout=30):
            if txt:
                parse_m3u(txt, entries, seen, reasons)
    except Exception:
        pass
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            ex.shutdown(wait=False)
    raw = list(entries.values())[:1000]
    if not raw:
        logger.warning("⚡ Стартовый набор пуст, ждём большой прогон")
        return []
    alive = []
    ex = ThreadPoolExecutor(max_workers=40)
    futs = {ex.submit(check_one, ch, SEED_TIMEOUT): ch for ch in raw}
    try:
        for f in as_completed(futs.keys(), timeout=90):
            ch = futs[f]
            try:
                res = f.result()
            except Exception:
                res = 'dead'
            if is_ok(res):
                alive.append(ch)
            brain.record(urlparse(ch['url']).netloc, is_ok(res))
    except Exception:
        pass
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            ex.shutdown(wait=False)
    return alive

def health_sweep():
    with cache_lock:
        snapshot = list(alive_list)
    if not snapshot or is_updating:
        return
    logger.info(f"🩺 Проверка здоровья (рентген): {len(snapshot)} каналов...")
    dead_urls = set()
    processed = 0
    ex = ThreadPoolExecutor(max_workers=SWEEP_WORKERS)
    futs = {ex.submit(check_one, ch, SWEEP_TIMEOUT, True): ch for ch in snapshot}
    try:
        for f in as_completed(futs.keys(), timeout=600):
            ch = futs[f]
            try:
                res = f.result()
            except Exception:
                res = 'dead'
            processed += 1
            if is_ok(res):
                DEAD_STRIKES.pop(ch['url'], None)
            else:
                n = DEAD_STRIKES.get(ch['url'], 0) + 1
                if n >= DEAD_LIMIT:
                    dead_urls.add(ch['url'])
                else:
                    DEAD_STRIKES[ch['url']] = n
            brain.record(ch.get('host', urlparse(ch['url']).netloc), is_ok(res))
    except TimeoutError:
        logger.warning("⏳ Таймаут свипа: часть не успела — они остаются как есть")
    except Exception as e:
        logger.error(f"Ошибка проверки здоровья: {e}")
    finally:
        try:
            ex.shutdown(wait=False, cancel_futures=True)
        except TypeError:
            ex.shutdown(wait=False)
    survivors = [ch for ch in snapshot if ch['url'] not in dead_urls]
    dead = len(dead_urls)
    if dead and survivors:
        flush_playlist(survivors, replace=True)
    with cache_lock:
        stats['last_sweep'] = time.strftime('%Y-%m-%d %H:%M:%S')
        stats['sweep_removed'] = dead
    logger.info(f"🩺 Итог: проверено {processed}/{len(snapshot)}, удалено {dead}, осталось {len(survivors)}")

def sweep_worker():
    while True:
        time.sleep(SWEEP_EVERY)
        try:
            health_sweep()
        except Exception as e:
            logger.exception(f"🩺 Ошибка свипа: {e}")

def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    start = time.time()
    logger.info("🔄 v" + VERSION + " Старт: комитет нейросетей + разведка...")
    try:
        api_channels, train_pairs, geo_pairs = fetch_iptv_org_api()
        geo_net.train(geo_pairs, epochs=3, lr=0.1)
        with cache_lock:
            stats['geo_pairs'] = len(geo_pairs)
        logger.info(f"🌍 Дипломат обучен на {len(geo_pairs)} примерах")
        with cache_lock:
            alive = list(alive_list)
        alive_urls = set(ch['url'] for ch in alive)
        alive_names = set(norm_name(ch['name']) for ch in alive)
        for ch in quick_seed():
            if ch['url'] not in alive_urls:
                nk = norm_name(ch['name'])
                if nk in alive_names:
                    continue
                alive_names.add(nk)
                alive_urls.add(ch['url'])
                alive.append(ch)
        if alive:
            flush_playlist(alive)
        entries = {}
        seen = set()
        reasons = Counter()
        logger.info(f"API iptv-org: потоков РФ/СНГ: {len(api_channels)}, меток: {len(train_pairs)}")
        for ach in api_channels:
            name = ach['name']
            if not name:
                continue
            reason = reject_reason(name, ach['url'])
            if reason:
                reasons[reason] += 1
                continue
            url = ach['url']
            if url in seen:
                continue
            seen.add(url)
            cat = api_category(ach.get('cats')) or get_category(name)
            inf = '#EXTINF:-1'
            if ach.get('cid'):
                inf += ' tvg-id="' + ach['cid'] + '"'
            if ach.get('logo'):
                inf += ' tvg-logo="' + ach['logo'] + '"'
            inf += ' group-title="' + cat + '",' + name
            key = norm_name(name)
            new_ch = {'inf': inf, 'url': url, 'cat': cat, 'name': name, 'ua': ach['ua'], 'ref': ach['ref']}
            if key in entries:
                if is_hd(name) and not is_hd(entries[key]['name']):
                    entries[key] = new_ch
            else:
                entries[key] = new_ch
        regions = fetch_ru_regions()
        if not regions:
            regions = ['https://iptv-org.github.io/iptv/regions/' + r + '.m3u' for r in FALLBACK_REGIONS]
        base = list(set(STATIC_SOURCES + regions))
        extra = list(set(fetch_dynamic() + fetch_github()) - set(base))
        sources = base + extra[:MAX_EXTRA_SOURCES]
        logger.info(f"ВСЕГО источников: {len(sources)}")
        loaded = 0
        ex = ThreadPoolExecutor(max_workers=SOURCE_WORKERS)
        futs = [ex.submit(fetch_source_text, u) for u in sources]
        try:
            for f in as_completed(futs, timeout=SOURCE_PHASE_MAX):
                try:
                    txt = f.result()
                except Exception:
                    txt = None
                if txt:
                    loaded += 1
                    parse_m3u(txt, entries, seen, reasons)
        except TimeoutError:
            logger.warning(f"⏳ Таймаут источников ({SOURCE_PHASE_MAX}с), успело: {loaded}")
        except Exception as e:
            logger.error(f"Ошибка фазы источников: {e}")
        finally:
            try:
                ex.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                ex.shutdown(wait=False)
        logger.info(f"Распарсено плейлистов: {loaded}")
        logger.info(f"Фильтры вырезали: {dict(reasons)}")
        with cache_lock:
            stats['filtered'] = dict(reasons)
        kw_pairs = [(ch['name'], ch['cat']) for ch in entries.values() if ch['cat'] != 'Общие']
        cat_net.train(train_pairs + kw_pairs)
        moved = apply_net(list(entries.values()))
        with cache_lock:
            stats['nb_moved'] = moved
        logger.info(f"🧠 Ирочка распределила из «Общих»: {moved} каналов")
        raw = list(entries.values())
        skipped = 0
        kept = []
        for ch in raw:
            rep, cnt = brain.host_stats(urlparse(ch['url']).netloc)
            if cnt >= HOST_REP_CNT and rep < HOST_REP_MIN:
                skipped += 1
                continue
            kept.append(ch)
        raw = kept
        with cache_lock:
            stats['host_blacklisted'] = skipped
        if skipped:
            logger.info(f"🚫 Смотритель отсёк {skipped} каналов с мёртвых хостов")
        for ch in raw:
            ch['feats'] = extract_features(ch)
            ch['host'] = urlparse(ch['url']).netloc
            ch['ml_score'] = brain.score(ch['feats'], ch['host'])
        raw.sort(key=lambda c: -c['ml_score'])
        if len(raw) > MAX_CHECK_POOL:
            logger.info(f"Кандидатов {len(raw)}, ML выбрал топ-{MAX_CHECK_POOL}")
            raw = raw[:MAX_CHECK_POOL]
        if not raw:
            logger.error("⚠️ ВСЕ каналы отфильтрованы!")
        with cache_lock:
            stats['sources_total'] = len(sources)
            stats['playlists_loaded'] = loaded
            stats['api_streams'] = len(api_channels)
            stats['parsed_channels'] = len(raw)
        logger.info(f"Кандидатов: {len(raw)}. Мягкая проверка (объём)...")
        samples = []
        check_counts = Counter()
        since_flush = 0
        checked = 0
        added = 0
        last_beat = time.time()
        ex = ThreadPoolExecutor(max_workers=CHECK_WORKERS)
        futs = {ex.submit(check_one, ch): ch for ch in raw}
        try:
            for f in as_completed(futs.keys(), timeout=CHECK_PHASE_MAX):
                checked += 1
                ch = futs[f]
                try:
                    res = f.result()
                except Exception:
                    res = 'dead'
                check_counts[res] += 1
                ok = is_ok(res)
                if ok and ch['url'] not in alive_urls:
                    nk = norm_name(ch['name'])
                    if nk not in alive_names:
                        alive_names.add(nk)
                        alive_urls.add(ch['url'])
                        alive.append(ch)
                        added += 1
                        since_flush += 1
                        if since_flush >= FLUSH_EVERY:
                            flush_playlist(alive)
                            since_flush = 0
                samples.append((ch['feats'], 1 if ok else 0))
                brain.record(ch['host'], ok)
                if time.time() - last_beat > HEARTBEAT_SEC:
                    logger.info(f"Прогресс: {checked}/{len(raw)}, в плейлисте: {len(alive)} (+{added})")
                    last_beat = time.time()
        except TimeoutError:
            logger.warning(f"⏳ Таймаут проверки ({CHECK_PHASE_MAX}с)")
        except Exception as e:
            logger.error(f"Ошибка фазы проверки: {e}")
        finally:
            try:
                ex.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                ex.shutdown(wait=False)
        with cache_lock:
            stats['check_counts'] = dict(check_counts)
        logger.info(f"🔬 Проверка: {dict(check_counts)}")
        apply_net(alive)
        brain.train(samples)
        with cache_lock:
            stats['ml_samples'] = brain.trained_samples
            stats['ml_accuracy'] = round(brain.last_accuracy, 3)
        elapsed = time.time() - start
        flush_playlist(alive, elapsed=elapsed)
        logger.info(f"✅ Готово: в плейлисте {len(alive)} (добавлено {added}) за {elapsed:.0f} сек")
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

HOME_TEMPLATE = """<!DOCTYPE html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IPTV Russia Pro MAX v5.5</title>
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
<h1>🇷 IPTV Russia Pro MAX 🧠 v5.5</h1>
<div class="sub">📈 мягкий набор = объём • 🩺 рентген-свип = чистка</div>
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
    with cache_lock:
        s = dict(stats)
    cat_html = ''
    for k, v in sorted(s.get('categories', {}).items(), key=lambda kv: -kv[1]):
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

@app.route('/memory')
def memory():
    try:
        with open('/proc/self/status') as f:
            for line in f:
                if line.startswith('VmRSS'):
                    return jsonify({'rss_kb': int(line.split()[1])})
    except Exception:
        pass
    return jsonify({'rss_kb': -1})

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
    load_disk_cache()
    threading.Thread(target=background_worker, daemon=True).start()
    threading.Thread(target=keepalive_worker, daemon=True).start()
    threading.Thread(target=sweep_worker, daemon=True).start()
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)