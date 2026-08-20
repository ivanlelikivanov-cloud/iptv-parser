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
import pickle
import requests
import urllib3
from urllib.parse import urlparse, unquote, quote
from collections import Counter
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify, request

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

VERSION = '3.2'

# ==================== ИНИЦИАЛИЗАЦИЯ LOGGER ДО ВСЕГО ====================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# ==================== ЗАГРУЗКА КОНФИГА ИЗ JSON ====================
def load_config():
    """Загружает конфигурацию из sources.json"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sources.json')
    default_config = {
        "static": [],
        "html": [],
        "regions_fallback": ["ru-kgd", "ru-mow", "ru-mos", "ru-spe", "ru-len"],
        "github_queries": ["iptv ru", "iptv russia", "m3u ru"],
        "gh_paths": ["ru.m3u", "playlist.m3u", "iptv.m3u", "tv.m3u", "main.m3u"],
        "probe_paths": ["ru.m3u", "playlist.m3u", "iptv.m3u", "tv.m3u"],
        "web_queries": ["iptv m3u ru", "плейлист iptv россия"],
        "tg_channels": ["iptvru", "iptv_russia", "russian_iptv"],
        "max_channels": 20000,
        "max_extra_sources": 200,
        "max_check_pool": 9000,
        "source_workers": 12,
        "check_workers": 40,
        "check_timeout": 40.0,
        "update_every": 86400,
        "sweep_every": 21600,
        "dead_limit": 3,
        "net_p_min": 0.45,
        "net_margin": 0.12,
        "geo_p_min": 0.6,
        "geo_margin": 0.2,
        "host_rep_min": 0.15,
        "host_rep_cnt": 10
    }
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                # Объединяем с дефолтами (чтобы новые поля не ломали)
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                logger.info(f"✅ Загружена конфигурация из {config_path}")
                return config
    except Exception as e:
        logger.warning(f"⚠️ Не удалось загрузить config: {e}, использую дефолты")
    
    return default_config

# ==================== ЗАГРУЖАЕМ КОНФИГ ====================
CONFIG = load_config()

# ==================== ИСТОЧНИКИ ИЗ КОНФИГА ====================
STATIC_SOURCES = CONFIG.get('static', [])
HTML_SOURCES = CONFIG.get('html', [])
FALLBACK_REGIONS = CONFIG.get('regions_fallback', [])
GITHUB_QUERIES = CONFIG.get('github_queries', [])
GH_COMMON_PATHS = CONFIG.get('gh_paths', [])
PROBE_PATHS = CONFIG.get('probe_paths', [])
WEB_QUERIES = CONFIG.get('web_queries', [])
TG_CHANNELS = CONFIG.get('tg_channels', [])

MAX_CHANNELS = CONFIG.get('max_channels', 20000)
MAX_EXTRA_SOURCES = CONFIG.get('max_extra_sources', 200)
MAX_CHECK_POOL = CONFIG.get('max_check_pool', 9000)
SOURCE_WORKERS = CONFIG.get('source_workers', 12)
CHECK_WORKERS = CONFIG.get('check_workers', 40)
CHECK_TIMEOUT = CONFIG.get('check_timeout', 40.0)
UPDATE_EVERY = CONFIG.get('update_every', 86400)
SWEEP_EVERY = CONFIG.get('sweep_every', 21600)
DEAD_LIMIT = CONFIG.get('dead_limit', 3)
NET_P_MIN = CONFIG.get('net_p_min', 0.45)
NET_MARGIN = CONFIG.get('net_margin', 0.12)
GEO_P_MIN = CONFIG.get('geo_p_min', 0.6)
GEO_MARGIN = CONFIG.get('geo_margin', 0.2)
HOST_REP_MIN = CONFIG.get('host_rep_min', 0.15)
HOST_REP_CNT = CONFIG.get('host_rep_cnt', 10)

# ==================== ОСТАЛЬНЫЕ НАСТРОЙКИ ====================
CIS_COUNTRIES = {'RU', 'BY', 'KZ', 'KG', 'UZ', 'AM', 'AZ', 'GE', 'MD', 'TJ'}

CAT_ORDER = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 'Детские',
             'Музыка', 'Познавательные', 'Развлекательные', 'Региональные', 'Общие']

EPG_URLS = ("https://iptv-org.github.io/epg/guides/ru.xml.gz,"
            "https://iptv-org.github.io/epg/guides/by.xml.gz,"
            "https://iptv-org.github.io/epg/guides/kz.xml.gz")

API_CAT_MAP = [
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
    "geo_pairs": 0, "geo_rejected": 0,
}

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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'playlist_disk.m3u')
DB_FILE = os.path.join(BASE_DIR, 'ml_history.db')
MODEL_FILE = os.path.join(BASE_DIR, 'ml_model.pkl')

SELF_URL = os.environ.get('RENDER_EXTERNAL_URL', 'https://iptv-parser.onrender.com')

# ==================== УТИЛИТЫ ====================
def host_sem(host):
    with _host_sems_lock:
        s = _host_sems.get(host)
        if s is None:
            s = threading.BoundedSemaphore(2)
            _host_sems[host] = s
        return s

def polite_headers():
    return {'User-Agent': random.choice(UA_POOL), 'Accept': '*/*'}

def _sig(z):
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)

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

def proxy_url(u, ua=None, ref=None):
    q = SELF_URL + '/proxy?url=' + quote(u, safe='')
    if ua:
        q += '&ua=' + quote(ua, safe='')
    if ref:
        q += '&ref=' + quote(ref, safe='')
    return q

# ==================== НЕЙРОСЕТИ ====================
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

brain = MLBrain()

# ==================== ФИЛЬТРЫ ====================
def _clean(lst):
    return [w for w in lst if isinstance(w, str) and len(w.strip()) >= 2]

ADULT_WORDS = _clean(['xxx', 'adult', 'porn', 'sex', 'hentai', '18+',
                      'эротика', 'порно', 'nude', 'playboy'])
UA_WORDS = _clean(['україн', 'украина', 'україна', 'kyiv', 'kiev', 'київ',
                   'львів', 'львов', 'харків', 'дніпро', 'одеса', 'суспільне'])
PAYWALL_WORDS = _clean(['подписк', 'subscription', 'оплат', 'payment', 'купить',
                        'premium', 'vip', 'wink', 'ivi', 'okko', 'megogo'])
RADIO_WORDS = _clean(['радио', 'radio', 'fm'])
LATIN_RU_WORDS = _clean(['rt ', 'rtr', 'pervyi', 'match tv', 'zvezda', 'karusel',
                         'ntv', 'sts', 'tnt', 'rossiya', 'russia', 'vesti'])
BAD_URL_WORDS = _clean(['wink.ru', 'okko.tv', 'ivi.ru', 'more.tv', 'kion.ru'])
JUNK_WORDS = _clean(['webcam', 'камера', 'без названия', 'test channel'])
JUNK_NAMES = {'index', 'playlist', 'live', 'test', 'stream', 'video', 'm3u', 'channel'}

def get_category(name):
    n = name.lower()
    if any(w in n for w in ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney']):
        return 'Детские'
    if any(w in n for w in ['новост', 'news', '24', 'вести', 'известия']):
        return 'Новости'
    if any(w in n for w in ['спорт', 'sport', 'футбол', 'хоккей', 'матч']):
        return 'Спорт'
    if any(w in n for w in ['кино', 'kino', 'movie', 'film', 'фильм', 'сериал', 'series']):
        return 'Кино и сериалы'
    if any(w in n for w in ['музык', 'music', 'mtv', 'шансон']):
        return 'Музыка'
    if any(w in n for w in ['докум', 'discovery', 'наука', 'истори']):
        return 'Познавательные'
    if any(w in n for w in ['развлек', 'юмор', 'comedy', 'шоу']):
        return 'Развлекательные'
    if any(w in n for w in ['москва', 'петербург', 'казань', 'екатеринбург']):
        return 'Региональные'
    if any(w in n for w in ['первый канал', 'россия 1', 'нтв', 'тнт', 'стс']):
        return 'Федеральные'
    
    pred, p1, p2 = cat_net.predict(name)
    if pred and p1 >= NET_P_MIN and (p1 - p2) >= NET_MARGIN:
        return pred
    
    if re.search(r'[\u0400-\u04FF]', name):
        return 'Общие'
    return 'Общие'

def is_russian_like(name):
    if re.search(r'[\u0400-\u04FF]', name):
        pred, p1, p2 = geo_net.predict(name)
        if pred == 'OTHER' and p1 >= GEO_P_MIN and (p1 - p2) >= GEO_MARGIN:
            return False
        return True
    n = name.lower()
    return any(w in n for w in LATIN_RU_WORDS)

def is_adult(name):
    return any(w in name.lower() for w in ADULT_WORDS)

def is_ukrainian(name):
    return any(w in name.lower() for w in UA_WORDS)

def is_paywall(name):
    n = name.lower()
    return any(w in n for w in PAYWALL_WORDS)

def is_radio(name):
    n = name.lower()
    return any(w in n for w in RADIO_WORDS) or bool(re.search(r'\bfm\b', n))

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
    if is_radio(name):
        return 'radio'
    if url and is_bad_url(url):
        return 'geo'
    return None

# ==================== ЗАГРУЗКА И ПАРСИНГ ====================
def _first_media_uri(text, base):
    for l in text.splitlines():
        s = l.strip()
        if not s or s.startswith('#'):
            continue
        return s if s.startswith('http') else base + s
    return None

def get_session():
    s = requests.Session()
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=0)
    s.mount('http://', adapter)
    s.mount('https://', adapter)
    return s

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
            text = _read_capped(r, 2_000_000)
            return text if text else None
    except Exception:
        return None

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
            BLOCK_MARKERS = ['roskomnadzor', 'zablokirovan', 'blocked', 'restricted',
                             'forbidden', 'captcha', 'cloudflare', 'access denied',
                             'оплат', 'заблокирован', 'недоступен']
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
        if head[:1] == b'\x47' or b'ftyp' in head[:16] or b'moov' in head[:32]:
            return True
        low = head[:200].lower()
        if b'<html' in low or b'<!doctype' in low:
            return False
        return True
    return False

# ==================== ОСНОВНОЕ ОБНОВЛЕНИЕ ====================
def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    start = time.time()
    logger.info("🔄 v" + VERSION + " Старт: комитет нейросетей + разведка...")
    
    try:
        entries = {}
        seen = set()
        reasons = Counter()
        
        loaded = 0
        with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as ex:
            futures = {ex.submit(fetch_source_text, url): url for url in STATIC_SOURCES}
            for future in as_completed(futures):
                try:
                    txt = future.result()
                    if txt:
                        loaded += 1
                        parse_m3u(txt, entries, seen, reasons)
                except Exception:
                    pass
        
        logger.info(f"📊 Загружено {loaded} источников, найдено {len(entries)} каналов")
        
        if not entries:
            playlist_cache = "#EXTM3U\n# Нет каналов\n"
            stats['alive_channels'] = 0
            return
        
        raw = list(entries.values())
        alive = []
        
        with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as ex:
            futures = {ex.submit(check_one, ch): ch for ch in raw[:MAX_CHECK_POOL]}
            for future in as_completed(futures):
                ch = futures[future]
                try:
                    if future.result():
                        alive.append(ch)
                except Exception:
                    pass
        
        def sort_key(ch):
            try:
                idx = CAT_ORDER.index(ch['cat'])
            except ValueError:
                idx = 9
            return (idx, ch['name'].lower())
        
        alive_sorted = sorted(alive, key=sort_key)
        
        lines = [
            '#EXTM3U url-tvg="' + EPG_URLS + '"',
            '# IPTV Russia Pro MAX v' + VERSION + ' | ' + time.strftime('%Y-%m-%d %H:%M'),
            '# Живых каналов: ' + str(len(alive_sorted))
        ]
        
        for ch in alive_sorted:
            lines.append(ch['inf'])
            lines.append('#EXTVLCOPT:http-user-agent=VLC/3.0.20 LibVLC/3.0.20')
            if ch.get('ref'):
                lines.append('#EXTVLCOPT:http-referrer=' + ch['ref'])
            lines.append(ch['url'])
        
        playlist_cache = '\n'.join(lines)
        stats['alive_channels'] = len(alive_sorted)
        stats['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S')
        stats['duration_sec'] = round(time.time() - start, 1)
        
        logger.info(f"✅ Готово: {len(alive_sorted)} живых каналов за {stats['duration_sec']}с")
        
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
    finally:
        is_updating = False

def background_worker():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Фоновая ошибка: {e}")
        time.sleep(UPDATE_EVERY)

# ==================== ВЕБ ====================
@app.route('/')
def home():
    count = stats.get('alive_channels', 0)
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>IPTV Russia Pro MAX v{VERSION}</title>
        <style>
            body {{ font-family: system-ui; background: #0f2027; color: #fff; min-height: 100vh; display: flex; align-items: center; justify-content: center; }}
            .card {{ background: rgba(255,255,255,.1); border-radius: 20px; padding: 40px; max-width: 500px; width: 90%; }}
            h1 {{ margin: 0; }}
            .stat {{ font-size: 72px; font-weight: bold; margin: 10px 0; background: rgba(255,255,255,.05); border-radius: 15px; padding: 20px; }}
            .btn {{ display: inline-block; padding: 12px 24px; border-radius: 10px; text-decoration: none; font-weight: 600; margin: 5px; }}
            .green {{ background: #4caf50; color: #fff; }}
            .blue {{ background: #2196f3; color: #fff; }}
            .gray {{ background: #607d8b; color: #fff; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🇷🇺 IPTV Russia Pro MAX</h1>
            <div class="stat">{count}</div>
            <p>каналов</p>
            <div>
                <a href="/playlist.m3u" class="btn green">📥 Скачать</a>
                <a href="/refresh" class="btn blue">🔄 Обновить</a>
                <a href="/status" class="btn gray">📊 Статус</a>
            </div>
            <p style="font-size:12px;opacity:.7;">v{VERSION} • 3 нейросети</p>
        </div>
    </body>
    </html>
    """

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                   headers={'Content-Disposition': 'attachment; filename="iptv_russia_pro.m3u"'})

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

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск IPTV Russia Pro MAX v{VERSION} на порту {port}")
    logger.info(f"📡 Источников: {len(STATIC_SOURCES)}")
    
    threading.Thread(target=background_worker, daemon=True).start()
    
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)