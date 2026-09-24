import os, re, time, json, hmac, hashlib, zlib, threading, logging
from collections import OrderedDict, Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, quote, urlunparse
import requests
import urllib3
from flask import Flask, Response, jsonify, request, abort
from waitress import serve

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
app = Flask(__name__)
VERSION = "9.1"
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("iptv-pro")

# -------------------- CONFIG --------------------
PORT = int(os.getenv("PORT", "10000"))
SELF_URL = (os.getenv("SELF_URL", "") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
DATA_FILE = os.getenv("PLAYLIST_FILE", "playlist_disk.m3u")
STATE_FILE = os.getenv("STATE_FILE", "agent_state.json")
MAX_CANDIDATES = int(os.getenv("MAX_CANDIDATES", "20000"))
MAX_OUTPUT = int(os.getenv("MAX_OUTPUT", "4000"))
CHECK_LIMIT = int(os.getenv("CHECK_LIMIT", "6000"))
CHECK_WORKERS = int(os.getenv("CHECK_WORKERS", "10"))
SOURCE_WORKERS = int(os.getenv("SOURCE_WORKERS", "6"))
UPDATE_EVERY = int(os.getenv("UPDATE_EVERY", "86400"))
STARTUP_UPDATE = os.getenv("STARTUP_UPDATE", "1") == "1"
DEEP_CHECK = os.getenv("DEEP_CHECK", "1") == "1"
USE_PROXY = os.getenv("USE_PROXY", "0") == "1"
UPDATE_TOKEN = os.getenv("UPDATE_TOKEN", "")
MAX_PROXY_CONNECTIONS = int(os.getenv("MAX_PROXY_CONNECTIONS", "20"))
MAX_SOURCE_BYTES = int(os.getenv("MAX_SOURCE_BYTES", str(8 * 1024 * 1024)))
SOURCE_TIMEOUT = float(os.getenv("SOURCE_TIMEOUT", "20"))
PAYWALL_FARM_MIN = 3

BLOCK_WORDS = ("paywall", "subscription", "subscribe", "premium", "paid", "payment",
               "login", "signin", "sign-in", "password", "token_required", "private")
BAD_CONTENT_WORDS = ("cloudflare", "access denied", "forbidden", "captcha",
                     "login required", "authentication required", "subscription required")
NSFW_WORDS = ("xxx", "porn", "sex", "adult", "erotic", "playboy", "hustler", "hentai", "18+")
UA_WORDS = ("україн", "украина", "україна", "kyiv", "kiev", "київ", "львів", "львов",
            "харків", "дніпро", "одеса", "суспільне", "суспильне", "прямий", "тсн",
            "1+1", "2+2", "інтер", "inter ua", "верес")
PAYWALL_WORDS = ("подписк", "оплат", "payment", "whatsapp", "t.me", "promo",
                 "магазин", "shop", "store", "wink", "винк", "тариф", "активация")
PAYWALL_RE = re.compile(
    r"\b(tviksel|liberty|ukr|ukraine|ott|ottclub|lapti|vinter|xtra|shara|iptvbox|boxtv|"
    r"smarttv|smart tv|subscription|подписка|оплат|pay|ppv|premium|премиум|vip|вип|"
    r"gold|platinum)\b", re.I)
BAD_URL_WORDS = ("wink", "okko.tv", "ivi.ru", "more.tv", "kion.ru", "start.ru",
                 "premier.one", "zabava", "rostelecom", "geoblock", "geo-block")
OTT_HOSTS = ("wink.ru", "okko.tv", "ivi.ru", "more.tv", "kion.ru", "start.ru",
             "premier.one", "zabava.ru", "rt.ru", "rostelecom.ru")
RU_HOST_HINTS = (".ru", ".su", ".рф", "m3u.su", "new.m3u.su", "webarmen", "iptv-list", "smolnp")
JUNK_WORDS = ("webcam", "камера", "camera", "без названия", "безымянный", "test channel", "проверка")
JUNK_NAMES = {"index", "index.m3u8", "playlist", "playlist.m3u8", "live", "test", "stream",
              "video", "m3u", "channel", "tv", "1", "hd", "fhd", "4k", "main", "default",
              "unknown", "без названия", "безымянный"}
BLOCK_MARKERS = ("roskomnadzor", "zablokirovan", "blocked", "restricted", "forbidden",
                 "captcha", "cloudflare", "access denied", "оплат", "заблокирован",
                 "недоступен", "роскомнадзор", "на этой территории", "territory")

CATEGORY_ORDER = ["Федеральные", "Новости", "Кино и сериалы", "Спорт", "Детские",
                  "Музыка", "Познавательные", "Развлекательные", "Региональные",
                  "Радио", "Общие"]
CATEGORY_MAP = {
    "news": "Новости", "information": "Новости", "business": "Новости",
    "новости": "Новости", "информационные": "Новости", "информация": "Новости",
    "новостные": "Новости", "info": "Новости", "политика": "Новости",
    "movies": "Кино и сериалы", "movie": "Кино и сериалы", "series": "Кино и сериалы",
    "кино": "Кино и сериалы", "фильмы": "Кино и сериалы", "фильм": "Кино и сериалы",
    "сериалы": "Кино и сериалы", "сериал": "Кино и сериалы", "cinema": "Кино и сериалы",
    "кино и сериалы": "Кино и сериалы", "художественные": "Кино и сериалы",
    "sports": "Спорт", "sport": "Спорт", "спорт": "Спорт", "спортивные": "Спорт",
    "спортивный": "Спорт", "футбол": "Спорт", "football": "Спорт", "хоккей": "Спорт",
    "kids": "Детские", "children": "Детские", "animation": "Детские",
    "детские": "Детские", "детский": "Детские", "детское": "Детские",
    "мультфильмы": "Детские", "мультфильм": "Детские", "мультики": "Детские",
    "music": "Музыка", "музыка": "Музыка", "музыкальные": "Музыка",
    "музыкальный": "Музыка", "радио": "Радио", "radio": "Радио", "radios": "Радио",
    "fm": "Радио", "фм": "Радио", "радиостанции": "Радио",
    "culture": "Познавательные", "documentary": "Познавательные",
    "education": "Познавательные", "science": "Познавательные",
    "travel": "Познавательные", "познавательные": "Познавательные",
    "познавательный": "Познавательные", "документальные": "Познавательные",
    "документальный": "Познавательные", "документальные фильмы": "Познавательные",
    "наука": "Познавательные", "образование": "Познавательные",
    "entertainment": "Развлекательные", "comedy": "Развлекательные",
    "lifestyle": "Развлекательные", "развлекательные": "Развлекательные",
    "развлекательный": "Развлекательные", "развлечения": "Развлекательные",
    "юмор": "Развлекательные", "шоу": "Развлекательные", "show": "Развлекательные",
    "general": "Общие", "public": "Общие", "religious": "Общие",
    "regional": "Региональные", "region": "Региональные", "local": "Региональные",
    "региональные": "Региональные", "региональный": "Региональные",
    "регион": "Региональные", "местные": "Региональные", "местный": "Региональные",
    "федеральные": "Федеральные", "федеральный": "Федеральные",
    "общенациональные": "Федеральные",
}
FEDERAL_NAMES = {"первый канал", "первый", "россия 1", "россия-1", "россия 2",
                 "россия 24", "россия-24", "нтв", "пятый канал", "5 канал", "рен тв",
                 "рен-тв", "тнт", "тв3", "тв-3", "стс", "домашний", "матч тв",
                 "матч! тв", "мир", "звезда", "отр", "культура", "пятница",
                 "суббота", "ю", "муз тв", "муз-тв", "спас", "царьград"}
KEYWORDS = {
    "Детские": ["детск", "kids", "child", "children", "малыш", "мульт", "мультик",
                "cartoon", "анимаци", "animation", "nickelodeon", "никелодеон",
                "disney", "дисней", "boomerang", "бумеранг", "jimjam", "tiji", "тиджи",
                "karusel", "карусель", "фиксики", "смешарики", "барбоскин",
                "три кота", "ну, погоди", "gulli", "гулли", "baby", "бэби",
                "теремок", "сказк", "радуга"],
    "Спорт": ["спорт", "sport", "match", "матч", "футбол", "football", "хоккей",
              "hockey", "баскет", "волей", "теннис", "бокс", "boxing", "mma", "ufc",
              "khl", "nhl", "nba", "fifa", "uefa", "евроспорт", "eurosport",
              "setanta", "сетанта", "автоспорт", "формула", "гонк", "racing",
              "киберспорт", "esport", "олимп", "olympic", "экстрим", "extreme",
              "фитнес", "fitness", "борьба", "wrestling", "дзюдо", "самбо",
              "шахмат", "chess", "athletic", "спортканал"],
    "Новости": ["новост", "вести", "vest", "news", "ньюс", "информ", "info",
                "политик", "эконом", "бизнес", "business", "финансы", "делов",
                "события", "euronews", "bbc", "cnn", "cnbc", "bloomberg",
                "france 24", "24"],
    "Кино и сериалы": ["кино", "kino", "cinema", "movie", "film", "фильм",
                       "сериал", "serial", "series", "боевик", "детектив",
                       "мелодрам", "ужас", "horror", "триллер", "thriller",
                       "фантаст", "приключ", "adventure", "вестерн", "western",
                       "аниме", "anime", "tv1000", "амедиа", "amedia", "иллюзион",
                       "illuzion", "дом кино", "paramount", "голливуд",
                       "hollywood", "болливуд", "bollywood", "комед", "comedy"],
    "Радио": ["радио", "radio", "fm", "фм", "авторадио", "европа плюс", "europa plus",
              "дорожное", "маяк", "вести fm", "наше радио", "rock fm", "ретро fm",
              "хит fm", "love radio", "радио дача", "коммерсант fm"],
    "Музыка": ["музык", "music", "mtv", "vh1", "viva", "bridge", "бридж", "ру.тв",
               "ru.tv", "шансон", "shanson", "ретро", "retro", "hit", "hits",
               "хит", "top", "топ", "chart", "чарт", "clip", "клип", "караоке",
               "karaoke", "концерт", "concert", "jazz", "джаз", "blues", "блюз",
               "rock", "рок", "pop", "поп", "edm", "dance", "дэнс", "techno",
               "техно", "house", "хаус", "lounge", "лаунж", "chill", "чилл"],
    "Познавательные": ["документ", "doc", "discovery", "national geographic",
                       "nat geo", "история", "history", "наука", "science",
                       "космос", "space", "косм", "природа", "nature", "животн",
                       "animal", "wildlife", "travel", "путешеств", "туризм",
                       "география", "культура", "culture", "искусств", "art",
                       "музей", "museum", "образование", "education", "школ",
                       "техника", "tech", "technology", "технолог", "компьютер",
                       "computer", "интернет", "internet", "здоровье", "health",
                       "медицин", "medical", "врач", "кулинар", "cooking",
                       "еда", "food", "кухня", "kitchen", "дача", "сад",
                       "огород", "рыбалк", "fishing", "охот", "hunting",
                       "авто", "auto", "мото", "moto", "психологи", "философи",
                       "религи", "православ", "ислам", "церковь", "храм",
                       "биограф", "война", "war", "милитари", "military",
                       "оружие", "weapon", "тайн", "mystery", "загадк"],
    "Развлекательные": ["развлек", "entertain", "юмор", "humor", "камеди", "квн",
                        "аншлаг", "шоу", "show", "телеигра", "игра", "game",
                        "лотерея", "мода", "fashion", "стиль", "style", "красот",
                        "beauty", "дом", "home", "интерьер", "дизайн", "design",
                        "ремонт", "свадьба", "wedding", "семья", "family",
                        "отношени", "reality", "реалити", "холостяк",
                        "экстрасенс", "астролог", "гороскоп", "сатир", "анекдот",
                        "прикол"],
}
TVGID_MAP = [
    ("kid", "Детские"), ("child", "Детские"), ("cartoon", "Детские"),
    ("disney", "Детские"), ("nick", "Детские"), ("boomerang", "Детские"),
    ("karusel", "Детские"), ("gulli", "Детские"),
    ("sport", "Спорт"), ("match", "Спорт"), ("football", "Спорт"),
    ("hockey", "Спорт"), ("eurosport", "Спорт"), ("setanta", "Спорт"),
    ("olympic", "Спорт"),
    ("news", "Новости"), ("novosti", "Новости"), ("vesti", "Новости"),
    ("euronews", "Новости"), ("bbc", "Новости"), ("cnn", "Новости"),
    ("bloomberg", "Новости"),
    ("radio", "Радио"), ("fm", "Радио"),
    ("music", "Музыка"), ("mtv", "Музыка"), ("vh1", "Музыка"), ("clip", "Музыка"),
    ("cinema", "Кино и сериалы"), ("movie", "Кино и сериалы"),
    ("film", "Кино и сериалы"), ("kino", "Кино и сериалы"),
    ("serial", "Кино и сериалы"), ("series", "Кино и сериалы"),
    ("action", "Кино и сериалы"), ("comedy", "Кино и сериалы"),
    ("horror", "Кино и сериалы"),
    ("doc", "Познавательные"), ("discovery", "Познавательные"),
    ("history", "Познавательные"), ("nature", "Познавательные"),
    ("science", "Познавательные"), ("travel", "Познавательные"),
    ("culture", "Познавательные"), ("education", "Познавательные"),
    ("health", "Познавательные"),
    ("entertainment", "Развлекательные"), ("show", "Развлекательные"),
    ("game", "Развлекательные"), ("fashion", "Развлекательные"),
    ("reality", "Развлекательные"),
    ("regional", "Региональные"), ("local", "Региональные"),
]
REGION_WORDS = ("област", "край", "респуб", "округ", "район", "город", "регион",
                "region", "oblast", "krai", "republic", "москва", "москв", "спб",
                "санкт-петербург", "ленинград", "татарстан", "башкортостан", "якут",
                "саха", "чечен", "дагестан", "бурят", "удмурт", "коми", "крым",
                "минск", "беларусь", "алматы", "астана", "ташкент", "баку",
                "ереван", "губерния", "столица", "поморье", "донбасс? нет")
API_CAT_MAP = [
    (["radio"], "Радио"), (["kids", "animation"], "Детские"),
    (["news", "business"], "Новости"), (["sports"], "Спорт"),
    (["movies", "series"], "Кино и сериалы"), (["music"], "Музыка"),
    (["documentary", "science", "culture", "education", "history", "travel",
      "food", "cooking", "health", "hobby", "home", "auto", "outdoor", "weather",
      "religious", "lifestyle"], "Познавательные"),
    (["comedy", "entertainment", "family", "relax", "general"], "Развлекательные"),
]
EPG_URLS = ("https://iptv-org.github.io/epg/guides/ru.xml.gz,"
            "https://iptv-org.github.io/epg/guides/by.xml.gz,"
            "https://iptv-org.github.io/epg/guides/kz.xml.gz")

SOURCE_URLS = [
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
    "https://webarmen.com/my/iptv/", "https://go2tv.top/", "https://iptv.one/",
    "https://iptv-channels.net/", "https://iptv-live.ru/", "https://vse-tv.net/",
    "https://forumtv.org/", "https://onlinetv.ru/",
]
TG_CHANNELS = ["iptvru", "iptv_russia", "russian_iptv", "iptv_m3u", "freeiptv_ru",
               "iptv_playlist", "m3u_playlist", "iptvfree", "tv_playlist", "iptv_rf"]
WEB_QUERIES = ["iptv m3u ru бесплатно", "плейлист iptv m3u россия",
               "iptv playlist m3u8 russia free", "site:t.me iptv m3u"]
GITHUB_QUERIES = ["iptv ru", "iptv russia", "m3u ru", "iptv playlist ru", "iptv m3u8 ru"]
GH_PATHS = ["ru.m3u", "russia.m3u", "iptv.m3u", "tv.m3u", "main.m3u", "index.m3u",
            "playlist.m3u", "channels/ru.m3u", "playlist.m3u8", "ru.m3u8"]

state = {
    "lock": threading.RLock(),
    "updating": False,
    "last_update": 0,
    "started": time.time(),
    "stats": {},
    "channels": OrderedDict(),
    "allowed": set(),
    "custom_categories": [],
    "logs": [],
}
PAYWALL_URLS = set()
HASH_URLS = {}
HOSTREP = {}
API_META = {}
_hash_lock = threading.Lock()
_rep_lock = threading.Lock()
proxy_sem = threading.BoundedSemaphore(MAX_PROXY_CONNECTIONS)

def logmsg(msg):
    log.info(msg)
    with state["lock"]:
        state["logs"].append(time.strftime("%H:%M:%S") + " " + msg)
        state["logs"] = state["logs"][-80:]

def load_state():
    global PAYWALL_URLS, HOSTREP
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, encoding="utf-8") as f:
                d = json.load(f)
            PAYWALL_URLS = set(d.get("paywall", []))
            HOSTREP = {k: v for k, v in d.get("hostrep", {}).items()}
            logmsg(f"Состояние: paywall={len(PAYWALL_URLS)}, хостов={len(HOSTREP)}")
    except Exception:
        pass

def save_state():
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"paywall": list(PAYWALL_URLS)[:20000],
                       "hostrep": {k: HOSTREP[k] for k in list(HOSTREP)[-5000:]}}, f)
        os.replace(tmp, STATE_FILE)
    except Exception as e:
        logmsg(f"save_state: {e}")

def clean_text(s):
    return re.sub(r"\s+", " ", (s or "").replace("\ufeff", "")).strip()

def attr(line, key):
    m = re.search(r'%s="([^"]*)"' % re.escape(key), line, re.I)
    return clean_text(m.group(1)) if m else ""

def normalize_url(url):
    url = clean_text(url)
    if not url.startswith(("http://", "https://")):
        return ""
    p = urlparse(url)
    if not p.netloc:
        return ""
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path, p.params, p.query, ""))

def normalize_group(g):
    g = clean_text(g)
    if not g:
        return ""
    if "|" in g:
        g = g.split("|")[-1].strip()
    g = re.sub(r"^[\[\(][^\]\)]{1,30}[\]\)]\s*", "", g)
    return g

def norm_name(n):
    n = (n or "").lower().strip()
    n = re.sub(r"[\(\[].*?[\)\]]", "", n)
    n = re.sub(r"\b(hd|fhd|uhd|4k|sd|hevc|h265|h264)\b", "", n)
    return re.sub(r"\s+", " ", n).strip(" -_|")

def is_bad_url(url):
    low = url.lower()
    return any(x in low for x in BLOCK_WORDS) or any(x in low for x in BAD_URL_WORDS)

def is_ott_host(url):
    h = urlparse(url).netloc.lower()
    return any(d in h for d in OTT_HOSTS)

def is_ru_host(url):
    h = urlparse(url).netloc.lower()
    return any(t in h for t in RU_HOST_HINTS)

def is_nsfw(name, group=""):
    s = (name + " " + group).lower()
    return any(w in s for w in NSFW_WORDS)

def is_ukrainian(name):
    n = name.lower()
    return any(w in n for w in UA_WORDS)

def is_paywall_name(name):
    n = name.lower()
    if any(w in n for w in PAYWALL_WORDS):
        return True
    return bool(PAYWALL_RE.search(n))

def is_junk(name):
    n = norm_name(name)
    return n in JUNK_NAMES or len(n) < 3 or any(w in n for w in JUNK_WORDS)

def is_hd(name):
    n = (name or "").lower()
    return "hd" in n or "4k" in n or "uhd" in n or "fhd" in n

def reject_reason(name, url):
    if url and url in PAYWALL_URLS:
        return "paywall"
    if is_junk(name):
        return "junk"
    if is_nsfw(name):
        return "nsfw"
    if is_ukrainian(name):
        return "ua"
    if is_paywall_name(name):
        return "paywall"
    if url and is_bad_url(url):
        return "geo"
    if url and is_ott_host(url):
        return "ott"
    return None

def host_rep(host):
    with _rep_lock:
        ok, tot = HOSTREP.get(host, (0, 0))
    if tot == 0:
        return 0.5
    return (ok + 1.0) / (tot + 2.0)

def host_record(host, ok):
    with _rep_lock:
        o, t = HOSTREP.get(host, (0, 0))
        HOSTREP[host] = (o + (1 if ok else 0), t + 1)

def category_from_group(group):
    g = clean_text(group).lower()
    if not g:
        return ""
    for c in CATEGORY_ORDER:
        if g == c.lower():
            return c
    return CATEGORY_MAP.get(g, "")

def canonical_custom_category(group, custom_categories):
    g = clean_text(group)
    if not g:
        return ""
    gl = g.lower()
    for c in custom_categories:
        if gl == c.lower():
            return c
    return ""

def guess_category(item, custom_categories):
    c = canonical_custom_category(item.get("group", ""), custom_categories)
    if c:
        return c
    g = normalize_group(item.get("group", ""))
    c = category_from_group(g)
    if c:
        return c
    name = clean_text(item.get("name", ""))
    nl = name.lower()
    tvgid = (item.get("tvg_id") or "").lower()
    for x in FEDERAL_NAMES:
        if nl == x or nl.startswith(x + " "):
            return "Федеральные"
    for token, cat in TVGID_MAP:
        if token in tvgid:
            return cat
    for category, words in KEYWORDS.items():
        if any(w in nl or w in tvgid for w in words):
            return category
    if any(x in nl for x in REGION_WORDS):
        return "Региональные"
    return "Общие"

def load_category_set(local_items):
    cats = []
    for x in local_items:
        g = clean_text(x.get("group", ""))
        if g and g not in cats and len(g) <= 80:
            cats.append(g)
    return cats or list(CATEGORY_ORDER)

def parse_m3u(text, source=""):
    result = []
    pending = None
    for line in text.replace("\r", "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            pending = {
                "name": clean_text(line.split(",", 1)[1]) if "," in line else "Channel",
                "tvg_id": attr(line, "tvg-id"),
                "logo": attr(line, "tvg-logo"),
                "group": attr(line, "group-title"),
                "ua": attr(line, "user-agent"),
                "ref": attr(line, "referrer"),
                "source": source,
            }
        elif pending and line.startswith("http"):
            u = normalize_url(line)
            if u:
                item = dict(pending)
                item["url"] = u
                result.append(item)
            pending = None
    return result

def load_local_playlist():
    items = []
    if not os.path.exists(DATA_FILE):
        return items
    try:
        with open(DATA_FILE, "r", encoding="utf-8", errors="ignore") as f:
            items = parse_m3u(f.read(), "local")
        logmsg(f"Локальный лист: {len(items)} потоков")
    except Exception as e:
        logmsg(f"Ошибка чтения локального листа: {e}")
    return items

M3U_LINK_RE = re.compile(r"https?://[^\s\"'<>]+")

def find_m3u_links(text):
    out = set()
    for u in M3U_LINK_RE.findall(text):
        u = u.rstrip(").,;]")
        if urlparse(u).path.lower().endswith((".m3u", ".m3u8")):
            out.add(u)
    return out

def fetch_source(url):
    try:
        r = requests.get(url, timeout=SOURCE_TIMEOUT, stream=True, verify=False,
                         headers={"User-Agent": "Mozilla/5.0 IPTV-Russia-Pro/9.1"})
        if r.status_code != 200:
            return []
        chunks = []
        total = 0
        for chunk in r.iter_content(65536):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_SOURCE_BYTES:
                break
            chunks.append(chunk)
        return parse_m3u(b"".join(chunks).decode("utf-8-sig", errors="ignore"), url)
    except Exception as e:
        logmsg(f"Источник ошибка: {url} -> {e}")
        return []

def fetch_html_links():
    found = set()
    def one(page):
        try:
            r = requests.get(page, timeout=(5, 10), verify=False, stream=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code != 200:
                return set()
            total = 0
            chunks = []
            for c in r.iter_content(65536):
                chunks.append(c)
                total += len(c)
                if total > 300000:
                    break
            r.close()
            return find_m3u_links(b"".join(chunks).decode("utf-8", "ignore"))
        except Exception:
            return set()
    with ThreadPoolExecutor(max_workers=6) as ex:
        for s in ex.map(one, HTML_SOURCES):
            found.update(s)
    return list(found)

def fetch_github():
    repos = []
    for q in GITHUB_QUERIES:
        try:
            r = requests.get("https://api.github.com/search/repositories",
                             params={"q": q, "per_page": 10, "sort": "stars"},
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=(5, 15))
            if r.status_code == 200:
                for it in r.json().get("items", []):
                    if it.get("full_name"):
                        repos.append((it["full_name"], it.get("default_branch") or "main"))
        except Exception:
            continue
    out = set()
    for full, branch in list(dict.fromkeys(repos))[:25]:
        base = f"https://raw.githubusercontent.com/{full}/{branch}"
        for p in GH_PATHS:
            out.add(f"{base}/{p}")
    return list(out)

def fetch_telegram():
    found = set()
    for ch in TG_CHANNELS:
        try:
            r = requests.get(f"https://t.me/s/{ch}", timeout=(5, 10), stream=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                total = 0
                chunks = []
                for c in r.iter_content(65536):
                    chunks.append(c)
                    total += len(c)
                    if total > 300000:
                        break
                r.close()
                found.update(find_m3u_links(b"".join(chunks).decode("utf-8", "ignore")))
            else:
                r.close()
        except Exception:
            continue
    return list(found)

def fetch_web():
    found = set()
    for q in WEB_QUERIES:
        try:
            r = requests.get("https://html.duckduckgo.com/html/", params={"q": q},
                             timeout=(5, 15), headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                found.update(find_m3u_links(r.text))
        except Exception:
            continue
    return list(found)

def fetch_api():
    global API_META
    try:
        sess = requests.Session()
        ch_r = sess.get("https://iptv-org.github.io/api/channels.json", timeout=(10, 60),
                        headers={"User-Agent": "Mozilla/5.0"})
        st_r = sess.get("https://iptv-org.github.io/api/streams.json", timeout=(10, 60),
                        headers={"User-Agent": "Mozilla/5.0"})
        if ch_r.status_code != 200 or st_r.status_code != 200:
            return []
        names = {}
        meta = {}
        for ch in ch_r.json():
            if ch.get("is_nsfw") or ch.get("country") == "UA":
                continue
            name = ch.get("name", "")
            langs = [l.get("code") if isinstance(l, dict) else l for l in (ch.get("languages") or [])]
            if ch.get("country") in ("RU", "BY", "KZ", "KG", "UZ", "AM", "AZ", "GE", "MD", "TJ") or "rus" in langs:
                names[ch.get("id")] = name
                cats = ch.get("categories") or []
                cat = ""
                for keys, c in API_CAT_MAP:
                    if any(k in cats for k in keys):
                        cat = c
                        break
                meta[ch.get("id")] = {"logo": ch.get("logo") or "", "cid": ch.get("id") or "", "cat": cat}
        items = []
        API_META = {}
        for s in st_r.json():
            cid = s.get("channel")
            url = s.get("url")
            if cid in names and url and url.startswith("http"):
                m = meta.get(cid, {})
                nk = norm_name(names[cid])
                API_META[nk] = {"logo": m.get("logo", ""), "tvg_id": m.get("cid", ""),
                                "ua": s.get("user_agent") or "", "ref": s.get("http_referrer") or "",
                                "cat": m.get("cat", "")}
                items.append({"name": names[cid], "url": normalize_url(url),
                              "tvg_id": m.get("cid", ""), "logo": m.get("logo", ""),
                              "group": m.get("cat", ""), "ua": s.get("user_agent") or "",
                              "ref": s.get("http_referrer") or "", "source": "api"})
        logmsg(f"API iptv-org: {len(items)} потоков РФ/СНГ")
        return items
    except Exception as e:
        logmsg(f"API ошибка: {e}")
        return []

def rank_candidate(item):
    score = 0
    if item.get("tvg_id"):
        score += 3
    if item.get("logo"):
        score += 1
    if item.get("group"):
        score += 2
    if item.get("source") == "local":
        score += 10
    if is_ru_host(item.get("url", "")):
        score += 4
    score += int(host_rep(urlparse(item.get("url", "")).netloc) * 4)
    return score

def note_hash(url, head):
    try:
        h = zlib.crc32(head[:1024])
        with _hash_lock:
            s = HASH_URLS.setdefault(h, set())
            if len(s) < 200:
                s.add(url)
    except Exception:
        pass

def harvest_paywall():
    new = 0
    with _hash_lock:
        for h, s in list(HASH_URLS.items()):
            if len(s) >= PAYWALL_FARM_MIN:
                for u in s:
                    if u not in PAYWALL_URLS:
                        PAYWALL_URLS.add(u)
                        new += 1
    if new:
        logmsg(f"🕵️ Paywall-ферма: +{new} URL с одинаковым промо-контентом")
        save_state()
    return new

def check_stream(item):
    url = item["url"]
    headers = {"User-Agent": item.get("ua") or "VLC/3.0.20 LibVLC/3.0.20",
               "Accept": "*/*", "Range": "bytes=0-4095", "Connection": "close"}
    if item.get("ref"):
        headers["Referer"] = item["ref"]
    try:
        r = requests.get(url, headers=headers, timeout=(3, 8),
                         allow_redirects=True, stream=True, verify=False)
        code = r.status_code
        ctype = (r.headers.get("content-type") or "").lower()
        final_url = normalize_url(r.url) or url
        sample = b""
        try:
            sample = next(r.iter_content(4096), b"")
        except Exception:
            pass
        r.close()
        if code in (401, 403, 451):
            return item, "blocked", "geo"
        if code in (404, 410):
            return item, "dead", "404"
        if code >= 400:
            return item, "blocked", "http"
        if not sample:
            return item, "dead", "empty"
        low = sample.decode("utf-8", errors="ignore").lower()
        if any(x in low for x in BAD_CONTENT_WORDS):
            return item, "blocked", "markers"
        if "text/html" in ctype and "m3u" not in low:
            return item, "dead", "html"
        manifest = ("mpegurl" in ctype or "m3u8" in ctype or "#extm3u" in low
                    or url.lower().split("?")[0].endswith(".m3u8"))
        if not manifest:
            note_hash(url, sample)
            out = dict(item)
            out["url"] = final_url
            return out, "alive", "direct"
        if not DEEP_CHECK:
            return item, "alive", "manifest"
        try:
            r2 = requests.get(url, timeout=8, verify=False, allow_redirects=True,
                              headers={"User-Agent": headers["User-Agent"]})
            text = r2.text[:200000]
        except Exception:
            return item, "blocked", "manifest-timeout"
        if "#EXTM3U" not in text:
            return item, "dead", "bad-manifest"
        if "#EXT-X-ENDLIST" in text:
            return item, "vod", "endlist"
        seg = None
        for l in text.splitlines():
            s = l.strip()
            if s and not s.startswith("#"):
                seg = s
                break
        if not seg:
            return item, "dead", "no-segments"
        if not seg.startswith("http"):
            seg = url.rsplit("/", 1)[0] + "/" + seg
        try:
            rs = requests.get(seg, timeout=8, stream=True, verify=False, allow_redirects=True,
                              headers={"User-Agent": headers["User-Agent"]})
            if rs.status_code in (401, 403, 451):
                rs.close()
                return item, "blocked", "seg-geo"
            if rs.status_code >= 400:
                rs.close()
                return item, "dead", "seg-404"
            head = next(rs.iter_content(4096), b"")
            rs.close()
        except Exception:
            return item, "blocked", "seg-timeout"
        if not head:
            return item, "dead", "seg-empty"
        note_hash(url, head)
        low2 = head[:200].lower()
        if b"<html" in low2:
            return item, "dead", "seg-html"
        out = dict(item)
        out["url"] = final_url
        return out, "alive", "seg-ok"
    except (requests.RequestException, TimeoutError):
        return item, "blocked", "timeout"
    except Exception:
        return item, "blocked", "error"

def build_output(items):
    unique = OrderedDict()
    for it in items:
        u = it.get("url")
        if u and u not in unique:
            unique[u] = it
    items = list(unique.values())
    custom = state.get("custom_categories") or CATEGORY_ORDER
    for it in items:
        if not it.get("category"):
            it["category"] = guess_category(it, custom)
    best = {}
    for it in items:
        nk = norm_name(it.get("name", "")) or it["url"]
        score = (0 if it.get("verdict") == "alive" else 1,
                 0 if is_ru_host(it["url"]) else 1,
                 0 if is_hd(it.get("name", "")) else 1,
                 0 if it.get("logo") else 1)
        cur = best.get(nk)
        if cur is None or score < cur[0]:
            best[nk] = (score, it)
    picked = [v[1] for v in best.values()]
    def key(x):
        cat = x.get("category", "Общие")
        try:
            ci = CATEGORY_ORDER.index(cat)
        except ValueError:
            ci = len(CATEGORY_ORDER)
        return (ci, 0 if x.get("verdict") == "alive" else 1,
                0 if is_ru_host(x["url"]) else 1,
                clean_text(x.get("name", "")).lower())
    picked.sort(key=key)
    return picked[:MAX_OUTPUT]

def sign_url(url):
    secret = os.getenv("PROXY_SECRET", "iptv-russia-pro-change-me").encode()
    return hmac.new(secret, url.encode(), hashlib.sha256).hexdigest()[:32]

def valid_signature(url, sig):
    if not url or not sig:
        return False
    return hmac.compare_digest(sign_url(url), sig)

def make_playlist(items, proxied=False):
    lines = ['#EXTM3U url-tvg="' + EPG_URLS + '"']
    allowed = set()
    for item in items:
        name = clean_text(item.get("name", "Канал")) or "Канал"
        group = clean_text(item.get("category", "Общие")) or "Общие"
        url = item.get("url", "")
        allowed.add(url)
        attrs = [f'group-title="{group}"']
        if item.get("tvg_id"):
            attrs.append(f'tvg-id="{item["tvg_id"]}"')
        if item.get("logo"):
            attrs.append(f'tvg-logo="{item["logo"]}"')
        lines.append(f'#EXTINF:-1 {" ".join(attrs)},{name}')
        if proxied and SELF_URL:
            lines.append(f"{SELF_URL}/proxy?u={quote(url, safe='')}&s={sign_url(url)}")
        else:
            if item.get("ua"):
                lines.append(f'#EXTVLCOPT:http-user-agent={item["ua"]}')
            if item.get("ref"):
                lines.append(f'#EXTVLCOPT:http-referrer={item["ref"]}')
            lines.append(url)
    return "\n".join(lines) + "\n", allowed

def save_playlist(text):
    tmp = DATA_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        logmsg(f"Не удалось сохранить playlist: {e}")

def update_playlist(force=False):
    with state["lock"]:
        if state["updating"]:
            return False
        if not force and time.time() - state["last_update"] < UPDATE_EVERY:
            return False
        state["updating"] = True
    started = time.time()
    try:
        logmsg("=== НАЧАЛО ОБНОВЛЕНИЯ ===")
        local = load_local_playlist()
        state["custom_categories"] = load_category_set(local)
        all_items = list(local)
        ok_sources = 0
        urls = list(SOURCE_URLS)
        try:
            urls += fetch_web()
        except Exception:
            pass
        with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as ex:
            futs = {ex.submit(fetch_source, u): u for u in urls}
            for fut in as_completed(futs):
                try:
                    got = fut.result()
                except Exception:
                    got = []
                if got:
                    ok_sources += 1
                    all_items.extend(got)
        for lst_fn in (fetch_html_links, fetch_github, fetch_telegram):
            try:
                extra_urls = lst_fn()
                if extra_urls:
                    with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as ex:
                        for got in ex.map(fetch_source, extra_urls[:150]):
                            if got:
                                ok_sources += 1
                                all_items.extend(got)
            except Exception:
                pass
        all_items.extend(fetch_api())
        uniq = OrderedDict()
        reasons = Counter()
        for x in all_items:
            u = x.get("url")
            if not u:
                continue
            reason = reject_reason(x.get("name", ""), u)
            if reason:
                reasons[reason] += 1
                continue
            nk = norm_name(x.get("name", ""))
            m = API_META.get(nk)
            if m:
                if not x.get("logo"):
                    x["logo"] = m.get("logo", "")
                if not x.get("tvg_id"):
                    x["tvg_id"] = m.get("tvg_id", "")
                if not x.get("ua"):
                    x["ua"] = m.get("ua", "")
                if not x.get("ref"):
                    x["ref"] = m.get("ref", "")
                if not x.get("group") and m.get("cat"):
                    x["group"] = m.get("cat", "")
            if u not in uniq:
                uniq[u] = x
        candidates = list(uniq.values())
        candidates.sort(key=rank_candidate, reverse=True)
        candidates = candidates[:MAX_CANDIDATES]
        kept = []
        for x in candidates:
            h = urlparse(x["url"]).netloc
            ok, tot = HOSTREP.get(h, (0, 0))
            if tot >= 10 and (ok + 1.0) / (tot + 2.0) < 0.15:
                continue
            kept.append(x)
        candidates = kept
        to_check = candidates[:CHECK_LIMIT]
        logmsg(f"Кандидатов: {len(candidates)}; проверяем: {len(to_check)}; фильтры: {dict(reasons)}")
        alive = []
        verdicts = Counter()
        with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as ex:
            futs = [ex.submit(check_stream, x) for x in to_check]
            for fut in as_completed(futs):
                try:
                    item, verdict, why = fut.result()
                except Exception:
                    item, verdict, why = None, "dead", "exc"
                verdicts[verdict] += 1
                if item is None:
                    continue
                host_record(urlparse(item["url"]).netloc, verdict in ("alive", "blocked"))
                if verdict in ("alive", "blocked") and item["url"] not in PAYWALL_URLS:
                    item["verdict"] = verdict
                    alive.append(item)
        harvest_paywall()
        before = len(alive)
        alive = [x for x in alive if x["url"] not in PAYWALL_URLS]
        if before - len(alive):
            logmsg(f"🕵️ Вырезано paywall-фермы: {before - len(alive)}")
        output = build_output(alive)
        playlist_text, allowed = make_playlist(output, proxied=USE_PROXY)
        save_playlist(playlist_text)
        save_state()
        cats = Counter(x.get("category", "Общие") for x in output)
        with state["lock"]:
            state["channels"] = OrderedDict((x["url"], x) for x in output)
            state["allowed"] = allowed
            state["last_update"] = time.time()
            state["stats"] = {
                "version": VERSION,
                "sources": len(urls),
                "source_ok": ok_sources,
                "candidates": len(candidates),
                "checked": len(to_check),
                "verdicts": dict(verdicts),
                "alive": len(alive),
                "output": len(output),
                "paywall_db": len(PAYWALL_URLS),
                "categories": dict(cats),
                "seconds": round(time.time() - started, 1),
            }
        logmsg(f"=== ГОТОВО: {len(output)} каналов за {time.time()-started:.1f}s ===")
        return True
    except Exception as e:
        log.exception("update failed")
        logmsg(f"КРИТИЧЕСКАЯ ОШИБКА UPDATE: {e}")
        return False
    finally:
        with state["lock"]:
            state["updating"] = False

def background_loop():
    time.sleep(4)
    if STARTUP_UPDATE:
        update_playlist(force=True)
    while True:
        time.sleep(30)
        try:
            update_playlist(force=False)
        except Exception:
            pass

def keepalive_loop():
    if not SELF_URL:
        return
    while True:
        time.sleep(300)
        try:
            requests.get(SELF_URL + "/health", timeout=10)
        except Exception:
            pass

@app.get("/")
def index():
    with state["lock"]:
        st = dict(state["stats"])
        updating = state["updating"]
        last = state["last_update"]
    html = f"""<!doctype html>
<html lang='ru'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>IPTV Russia Pro v{VERSION}</title>
<style>body{{font-family:Arial;background:#0d1117;color:#e6edf3;margin:24px}}
.box{{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:18px;margin:12px 0}}
a{{color:#58a6ff}} .ok{{color:#3fb950}} table{{width:100%;border-collapse:collapse}}
td,th{{padding:7px;border-bottom:1px solid #30363d;text-align:left}}</style>
</head><body><h1>📺 IPTV Russia Pro v{VERSION} «ПУШКА»</h1>
<div class='box'><b>Статус:</b> {'ОБНОВЛЯЕТСЯ' if updating else 'ГОТОВ'}<br>
Каналов в выдаче: <b>{st.get('output', 0)}</b><br>
Проверено: {st.get('checked', 0)} → живых/блок: <b class='ok'>{st.get('alive', 0)}</b><br>
Вердикты: {st.get('verdicts', {})}<br>
Paywall-база: {st.get('paywall_db', 0)}<br>
Источников OK: {st.get('source_ok', 0)}/{st.get('sources', 0)}<br>
Последнее обновление: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last)) if last else 'ещё не было'}</div>
<div class='box'><a href='/playlist.m3u'>▶ playlist.m3u</a> &nbsp;|&nbsp;
<a href='/playlist.m3u?proxy=1'>▶ playlist через PROXY</a> &nbsp;|&nbsp;
<a href='/api/status'>API status</a> &nbsp;|&nbsp;
<a href='/api/update'>Обновить</a></div>
<div class='box'><h3>Категории</h3><table><tr><th>Категория</th><th>Каналов</th></tr>
{''.join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in st.get('categories', {}).items())}
</table></div></body></html>"""
    return Response(html, mimetype="text/html")

@app.get("/health")
def health():
    return jsonify(ok=True, service="iptv-russia-pro", version=VERSION,
                   uptime=round(time.time() - state["started"], 1))

@app.get("/api/status")
def api_status():
    with state["lock"]:
        return jsonify({"ok": True, "updating": state["updating"],
                        "last_update": state["last_update"],
                        "stats": state["stats"], "logs": state["logs"][-30:]})

@app.get("/api/update")
def api_update():
    if UPDATE_TOKEN and request.args.get("token") != UPDATE_TOKEN:
        abort(403)
    threading.Thread(target=update_playlist, kwargs={"force": True}, daemon=True).start()
    return jsonify(ok=True, message="Обновление запущено в фоне")

@app.get("/playlist.m3u")
@app.get("/playlist.m3u8")
@app.get("/tv.m3u")
@app.get("/iptv.m3u")
def playlist():
    proxied = request.args.get("proxy") == "1"
    with state["lock"]:
        items = list(state["channels"].values())
    if not items and os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            text = "#EXTM3U\n"
    else:
        text, _ = make_playlist(items, proxied=proxied)
    return Response(text, mimetype="audio/x-mpegurl",
                    headers={"Content-Disposition": 'inline; filename="iptv-russia-pro.m3u"',
                             "Cache-Control": "no-cache"})

@app.get("/proxy")
def proxy():
    url = request.args.get("u", "")
    sig = request.args.get("s", "")
    if not valid_signature(url, sig):
        abort(403)
    with state["lock"]:
        allowed = url in state["allowed"]
    if not allowed:
        abort(403)
    if not proxy_sem.acquire(timeout=2):
        return Response("proxy busy", status=503)
    def generate():
        try:
            r = requests.get(url, stream=True, timeout=(4, 15), verify=False,
                             allow_redirects=True,
                             headers={"User-Agent": "VLC/3.0.20 LibVLC/3.0.20", "Accept": "*/*"})
            if r.status_code >= 400:
                r.close()
                return
            for chunk in r.iter_content(64 * 1024):
                if chunk:
                    yield chunk
            r.close()
        except Exception as e:
            logmsg(f"proxy error: {e}")
        finally:
            proxy_sem.release()
    return Response(generate(), status=200, mimetype="application/octet-stream",
                    headers={"Cache-Control": "no-cache", "Access-Control-Allow-Origin": "*"})

if __name__ == "__main__":
    load_state()
    logmsg(f"IPTV Russia Pro v{VERSION} стартует на 0.0.0.0:{PORT}")
    threading.Thread(target=background_loop, daemon=True).start()
    threading.Thread(target=keepalive_loop, daemon=True).start()
    serve(app, host="0.0.0.0", port=PORT, threads=8, channel_timeout=120)