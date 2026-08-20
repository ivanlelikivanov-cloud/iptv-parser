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
VERSION = '3.3'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'playlist_disk.m3u')
DB_FILE = os.path.join(BASE_DIR, 'ml_history.db')
MODEL_FILE = os.path.join(BASE_DIR, 'ml_model.json')
SOURCES_FILE = os.path.join(BASE_DIR, 'sources.json')

def _load_sources():
    d = {
        "static": ["https://iptv-org.github.io/iptv/countries/ru.m3u",
                   "https://iptv-org.github.io/iptv/languages/rus.m3u",
                   "https://iptv-org.github.io/iptv/index.m3u"],
        "html": ["https://m3u.su/", "https://new.m3u.su/"],
        "regions_fallback": [], "github_queries": [], "gh_paths": [],
        "probe_paths": [], "web_queries": [], "tg_channels": [],
    }
    try:
        with open(SOURCES_FILE, encoding='utf-8') as f:
            d.update(json.load(f))
        msg = f"📚 sources.json: {len(d['static'])} источников"
    except Exception:
        msg = "⚠️ sources.json не найден — встроенный минимум"
    return d, msg

CFG, CFG_MSG = _load_sources()
STATIC_SOURCES = CFG['static']
HTML_SOURCES = CFG['html']
FALLBACK_REGIONS = CFG['regions_fallback']
GITHUB_QUERIES = CFG['github_queries']
GH_COMMON_PATHS = CFG['gh_paths']
PROBE_PATHS = CFG['probe_paths']
WEB_QUERIES = CFG['web_queries']
TG_CHANNELS = CFG['tg_channels']

MAX_CHANNELS = 20000
MAX_EXTRA_SOURCES = 200
MAX_CHECK_POOL = 9000
SOURCE_WORKERS = 12
CHECK_WORKERS = 40
CHECK_TIMEOUT = 40.0
SEED_TIMEOUT = 8.0
SOURCE_PHASE_MAX = 300
CHECK_PHASE_MAX = 1500
UPDATE_EVERY = 86400
RETRY_IF_EMPTY = 600
FLUSH_EVERY = 10
HEARTBEAT_SEC = 20
KEEPALIVE_SEC = 60
SWEEP_EVERY = 21600
SWEEP_TIMEOUT = 15.0
SWEEP_WORKERS = 30
DEAD_LIMIT = 3
MAX_PLAYLIST_BYTES = 2_000_000
MAX_HTML_BYTES = 524_288
NET_P_MIN = 0.45
NET_MARGIN = 0.12
GEO_P_MIN = 0.6
GEO_MARGIN = 0.2
HOST_REP_MIN = 0.15
HOST_REP_CNT = 10

SCORE_MODEL_P, SCORE_MODEL_REP, SCORE_MODEL_HEUR = 0.5, 0.35, 0.15
SCORE_NOMODEL_REP, SCORE_NOMODEL_HEUR, SCORE_NOMODEL_CNT = 0.55, 0.25, 0.2

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
logger.info(CFG_MSG)

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
    def model_prob(self, feats):
        try:
            return self.model.prob(feats)
        except Exception:
            return None
    def score(self, feats, host):
        rep, cnt = self.host_stats(host)
        heur = 0.5 * feats[2] + 0.3 * feats[3] + 0.2 * (1.0 - feats[5])
        p = self.model_prob(feats)
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
            time.sleep(random.uniform(0.3, 0.9))
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
            time.sleep(random.uniform(0.2, 0.7))
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

def fetch_gitlab():
    found = set()
    try:
        r = get_session().get('https://gitlab.com/api/v4/projects',
                              params={'search': 'iptv', 'per_page': 15}, headers=HEADERS_WEB, timeout=(5, 15))
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
                              params={'q': 'name ~ "iptv"', 'pagelen': 15}, headers=HEADERS_WEB, timeout=(5, 15))
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
        ('https://codeberg.org/api/v1/repos/search?q=iptv&limit=10', 'https://codeberg.org/', '/raw/branch/'),
        ('https://gitea.com/api/v1/repos/search?q=iptv&limit=10', 'https://gitea.com/', '/raw/'),
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
            time.sleep(random.uniform(0.5, 1.2))
            r = get_session().get('https://html.duckduckgo.com/html/',
                                  params={'q': q}, headers=polite_headers(), timeout=(5, 15))
            if r.status_code != 200:
                continue
            m3u.update(re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', r.text, re.I))
            for enc in re.findall(r'uddg=([^&"]+)', r.text):
                pages.append(unquote(enc))
        except Exception:
            continue
    def scrape(page):
        try:
            time.sleep(random.uniform(0.3, 0.9))
            r = get_session().get(page, headers=polite_headers(), timeout=(5, 10), verify=False, stream=True)
            if r.status_code == 200:
                return re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', _read_capped(r, MAX_HTML_BYTES), re.I)
            r.close()
        except Exception:
            pass
        return []
    ex = ThreadPoolExecutor(max_workers=8)
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
            time.sleep(random.uniform(0.4, 1.0))
            r = get_session().get('https://t.me/s/' + ch, headers=polite_headers(), timeout=(5, 10), stream=True)
            if r.status_code == 200:
                found.update(re.findall(r'(https?://[^\s"\'<>()]+?\.m3u8?)', _read_capped(r, MAX_HTML_BYTES), re.I))
            else:
                r.close()
        except Exception:
            continue
    logger.info(f"Telegram: ссылок: {len(found)}")
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
                    'logo': ch.get('logo') or '',
                    'cid': ch.get('id') or '',
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
        time.sleep(random.uniform(0.3, 1.0))
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

def _first_media_uri(text, base):
    for l in text.splitlines():
        s = l.strip()
        if not s or s.startswith('#'):
            continue
        return s if s.startswith('http') else base + s
    return None

def check_one(ch, limit=None):
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
                return True
    except Exception:
        pass
    for _ in range(2):
        if remaining() <= 1:
            return False
        try:
            r = session.get(url, timeout=remaining(), headers=headers, stream=True, allow_redirects=True, verify=False)
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
        is_hls = ('mpegurl' in ct) or ('.m3u8' in url.lower()) or (chunk[:7] == b'#EXTM3U')
        if not is_hls:
            if any(g in ct for g in GOOD_CT):
                return True
            if chunk[:1] == b'\x47':
                return True
            low = chunk[:300].lower()
            if b'<html' in low or b'<!doctype' in low or b'<script' in low:
                return False
            try:
                txt_low = low.decode('utf-8', errors='ignore')
            except Exception:
                txt_low = ''
            if any(m in txt_low for m in BLOCK_MARKERS):
                return False
            return True
        try:
            r2 = session.get(url, timeout=min(remaining(), 10), headers=headers,
                             verify=False, allow_redirects=True)
            text = r2.text[:200000]
        except Exception:
            return True
        if '#EXTM3U' not in text:
            return False
        base = url.rsplit('/', 1)[0] + '/'
        seg = _first_media_uri(text, base)
        if not seg:
            return False
        if remaining() <= 1:
            return True
        try:
            rs = session.get(seg, timeout=min(remaining(), 10), headers=headers,
                             stream=True, verify=False, allow_redirects=True)
            if rs.status_code >= 400:
                return False
            head = next(rs.iter_content(chunk_size=4096), b'')
            rs.close()
        except Exception:
            return True
        if not head:
            return True
        if head[:1] == b'\x47' or b'ftyp' in head[:16] or b'moov' in head[:32] \
                or b'styp' in head[:16] or head[:7] == b'#EXTM3U':
            return True
        low = head[:200].lower()
        if b'<html' in low or b'<!doctype' in low or any(m in low for m in BLOCK_MARKERS):
            return False
        return True
    return False

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