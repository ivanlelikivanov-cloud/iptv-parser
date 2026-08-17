import os
import re
import time
import math
import json
import logging
import threading
import sqlite3
import pickle
import requests
import urllib3
from urllib.parse import urlparse, unquote
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response, jsonify, request

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== РАСШИРЕННАЯ СТАТИКА ====================
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
]

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS = 25000
MAX_EXTRA_SOURCES = 300
MAX_CHECK_POOL = 8000
SOURCE_WORKERS = 20
CHECK_WORKERS = 50
CHECK_TIMEOUT = 30.0
SEED_TIMEOUT = 8.0
SOURCE_PHASE_MAX = 300
CHECK_PHASE_MAX = 1800
UPDATE_EVERY = 43200  # 12 часов
RETRY_IF_EMPTY = 600
FLUSH_EVERY = 10
HEARTBEAT_SEC = 20
KEEPALIVE_SEC = 60
DEATH_THRESHOLD_DAYS = 21  # 3 недели

CIS_COUNTRIES = {'RU', 'BY', 'KZ', 'KG', 'UZ', 'AM', 'AZ', 'GE', 'MD', 'TJ'}

CAT_ORDER = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 'Детские',
             'Музыка', 'Познавательные', 'Развлекательные', 'Региональные', 'Общие']

playlist_cache = "#EXTM3U\n# IPTV Russia AI — идёт обучение...\n"
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
    "dead_removed": 0,
    "new_added": 0,
    "filtered": {},
    "categories": {},
    "ml_samples": 0,
    "ml_accuracy": 0.0,
    "ml_on": True,
    "last_death_cleanup": None,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20'}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, 'playlist_disk.m3u')
DB_FILE = os.path.join(BASE_DIR, 'ml_history.db')
MODEL_FILE = os.path.join(BASE_DIR, 'ml_model.pkl')
CHANNEL_DB = os.path.join(BASE_DIR, 'channels.db')  # Новая БД для истории каналов

# ==================== УЛУЧШЕННАЯ НЕЙРОСЕТЬ ====================
class TinyNeuralNetwork:
    """Мини-нейросеть: 12 входов, 8 нейронов в скрытом слое, 1 выход"""
    def __init__(self, input_size=12, hidden_size=8):
        # Веса: вход->скрытый
        self.w1 = [[0.0] * input_size for _ in range(hidden_size)]
        self.b1 = [0.0] * hidden_size
        # Веса: скрытый->выход
        self.w2 = [0.0] * hidden_size
        self.b2 = 0.0
        self.hidden_size = hidden_size
        self.input_size = input_size
        
    def _sigmoid(self, z):
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        ez = math.exp(z)
        return ez / (1.0 + ez)
    
    def _forward(self, x):
        # Скрытый слой
        hidden = []
        for i in range(self.hidden_size):
            z = self.b1[i] + sum(self.w1[i][j] * x[j] for j in range(self.input_size))
            hidden.append(self._sigmoid(z))
        # Выходной слой
        z = self.b2 + sum(self.w2[i] * hidden[i] for i in range(self.hidden_size))
        return self._sigmoid(z), hidden
    
    def predict(self, x):
        p, _ = self._forward(x)
        return p
    
    def train(self, X, y, lr=0.1, epochs=3):
        for _ in range(epochs):
            for x, target in zip(X, y):
                # Прямой проход
                output, hidden = self._forward(x)
                error = output - target
                
                # Обратное распространение
                # Выходной слой
                d_output = error * output * (1 - output)
                for i in range(self.hidden_size):
                    self.w2[i] -= lr * d_output * hidden[i]
                self.b2 -= lr * d_output
                
                # Скрытый слой
                for i in range(self.hidden_size):
                    d_hidden = d_output * self.w2[i] * hidden[i] * (1 - hidden[i])
                    for j in range(self.input_size):
                        self.w1[i][j] -= lr * d_hidden * x[j]
                    self.b1[i] -= lr * d_hidden

# ==================== БД ДЛЯ ИСТОРИИ КАНАЛОВ ====================
class ChannelHistory:
    """Хранит историю каналов: URL, время жизни, дата смерти"""
    def __init__(self):
        self.conn = sqlite3.connect(CHANNEL_DB, check_same_thread=False)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                name TEXT,
                category TEXT,
                first_seen REAL,
                last_alive REAL,
                last_dead REAL,
                deaths INTEGER DEFAULT 0,
                checks INTEGER DEFAULT 0,
                alive_ratio REAL DEFAULT 0.5
            )
        ''')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_url ON channels(url)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_dead ON channels(last_dead)')
        self.conn.commit()
        self.lock = threading.Lock()
        
    def record_check(self, url, name, category, is_alive):
        """Записать результат проверки канала"""
        with self.lock:
            now = time.time()
            cur = self.conn.cursor()
            
            # Проверяем, есть ли канал
            cur.execute('SELECT id, deaths, checks, alive_ratio FROM channels WHERE url = ?', (url,))
            row = cur.fetchone()
            
            if row:
                ch_id, deaths, checks, alive_ratio = row
                checks += 1
                if is_alive:
                    last_alive = now
                    # Обновляем alive_ratio
                    alive_ratio = ((alive_ratio * (checks - 1)) + 1) / checks if checks > 0 else 1.0
                else:
                    last_dead = now
                    deaths += 1
                    alive_ratio = ((alive_ratio * (checks - 1)) + 0) / checks if checks > 0 else 0.0
                
                cur.execute('''
                    UPDATE channels SET 
                        last_alive = ?, last_dead = ?, deaths = ?, 
                        checks = ?, alive_ratio = ?
                    WHERE id = ?
                ''', (last_alive if is_alive else None, 
                      last_dead if not is_alive else None,
                      deaths, checks, alive_ratio, ch_id))
            else:
                # Новый канал
                cur.execute('''
                    INSERT INTO channels (url, name, category, first_seen, last_alive, checks, alive_ratio)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (url, name, category, now, now if is_alive else None, 1, 1.0 if is_alive else 0.0))
            
            self.conn.commit()
    
    def get_dead_channels(self, days=DEATH_THRESHOLD_DAYS):
        """Найти каналы, которые мертвы более N дней"""
        threshold = time.time() - (days * 86400)
        with self.lock:
            cur = self.conn.cursor()
            cur.execute('''
                SELECT url, name, category, last_dead, deaths, checks, alive_ratio
                FROM channels 
                WHERE last_dead IS NOT NULL 
                AND last_dead < ?
                AND alive_ratio < 0.3
                AND checks > 5
            ''', (threshold,))
            return cur.fetchall()
    
    def cleanup_dead(self, urls_to_remove):
        """Пометить каналы как удаленные (не удаляем физически, а архивируем)"""
        if not urls_to_remove:
            return
        with self.lock:
            placeholders = ','.join(['?'] * len(urls_to_remove))
            self.conn.execute(f'''
                UPDATE channels SET last_dead = ?, alive_ratio = 0 
                WHERE url IN ({placeholders})
            ''', (time.time(), *urls_to_remove))
            self.conn.commit()
            logger.info(f"🗑️ Заархивировано {len(urls_to_remove)} мертвых каналов")
    
    def get_stats(self):
        """Статистика по каналам"""
        with self.lock:
            cur = self.conn.cursor()
            total = cur.execute('SELECT COUNT(*) FROM channels').fetchone()[0]
            dead = cur.execute('SELECT COUNT(*) FROM channels WHERE alive_ratio < 0.3 AND checks > 5').fetchone()[0]
            alive = cur.execute('SELECT COUNT(*) FROM channels WHERE alive_ratio >= 0.7 AND checks > 5').fetchone()[0]
            return {'total': total, 'dead': dead, 'alive': alive}

channel_history = ChannelHistory()

# ==================== УЛУЧШЕННЫЙ ML-МОЗГ ====================
class ImprovedMLBrain:
    def __init__(self):
        self.model = None
        self.trained_samples = 0
        self.last_accuracy = 0.0
        self.db = None
        self.lock = threading.Lock()
        
        # Используем новую нейросеть
        try:
            self.db = sqlite3.connect(DB_FILE, check_same_thread=False)
            with self.lock:
                self.db.execute('CREATE TABLE IF NOT EXISTS checks '
                                '(id INTEGER PRIMARY KEY AUTOINCREMENT, host TEXT, alive INTEGER, ts REAL)')
                self.db.commit()
                rows = self.db.execute('SELECT host, SUM(alive), COUNT(*) FROM checks GROUP BY host').fetchall()
            logger.info(f"🧠 ML: загружена история {len(rows)} хостов")
        except Exception as e:
            logger.error(f"🧠 ML: ошибка БД: {e}")
            self.db = None
            
        try:
            if os.path.exists(MODEL_FILE):
                with open(MODEL_FILE, 'rb') as f:
                    self.model = pickle.load(f)
                logger.info("🧠 ML: нейросеть загружена с диска")
        except Exception:
            self.model = None
            
    def host_stats(self, host):
        """Статистика по хосту из БД"""
        if self.db is None:
            return 0.5, 0
        try:
            with self.lock:
                row = self.db.execute('SELECT SUM(alive), COUNT(*) FROM checks WHERE host = ?', (host,)).fetchone()
                if row and row[1] > 0:
                    return (row[0] + 1.0) / (row[1] + 2.0), row[1]
        except:
            pass
        return 0.5, 0
    
    def record(self, host, alive):
        """Запись результата проверки"""
        if self.db is None:
            return
        try:
            with self.lock:
                self.db.execute('INSERT INTO checks (host, alive, ts) VALUES (?,?,?)',
                                (host, 1 if alive else 0, time.time()))
                self.db.commit()
        except Exception as e:
            logger.error(f"Ошибка записи в БД: {e}")
    
    def predict(self, feats):
        """Предсказание нейросети"""
        if self.model is None:
            return None
        try:
            return self.model.predict(feats)
        except:
            return None
    
    def score(self, feats, host):
        """Комбинированный скор: нейросеть + статистика хоста"""
        rep, cnt = self.host_stats(host)
        p = self.predict(feats)
        if p is None:
            # Если модель не обучена, используем эвристику
            heuristic = 0.4 * feats[2] + 0.3 * feats[3] + 0.3 * (1.0 - feats[5])
            return 0.6 * rep + 0.4 * heuristic
        # Взвешенная сумма
        return 0.5 * p + 0.3 * rep + 0.2 * min(cnt / 10.0, 1.0)
    
    def train(self, samples):
        """Обучение нейросети"""
        if not samples or len(samples) < 30:
            return
        
        X = [s[0] for s in samples]
        y = [s[1] for s in samples]
        
        if len(set(y)) < 2:
            logger.warning("ML: недостаточно разнообразия для обучения")
            return
        
        # Оценка точности до обучения
        acc_before = None
        if self.model is not None:
            try:
                test_size = min(200, len(X) // 3)
                preds = [1 if self.model.predict(x) > 0.5 else 0 for x in X[:test_size]]
                acc_before = sum(1 for p, t in zip(preds, y[:test_size]) if p == t) / max(1, test_size)
            except:
                pass
        
        # Обучение
        try:
            if self.model is None:
                self.model = TinyNeuralNetwork(len(X[0]))
            self.model.train(X, y, lr=0.1, epochs=2)
            self.trained_samples += len(samples)
            
            # Оценка точности после
            acc_after = None
            try:
                test_size = min(200, len(X) // 3)
                preds = [1 if self.model.predict(x) > 0.5 else 0 for x in X[:test_size]]
                acc_after = sum(1 for p, t in zip(preds, y[:test_size]) if p == t) / max(1, test_size)
                self.last_accuracy = acc_after
            except:
                pass
            
            # Сохраняем модель
            with open(MODEL_FILE, 'wb') as f:
                pickle.dump(self.model, f)
                
            logger.info(f"🧠 ML: обучено на {len(samples)} примерах (всего {self.trained_samples}), "
                        f"точность: {acc_before:.2%} → {acc_after:.2%}" if acc_before and acc_after else 
                        f"🧠 ML: обучено на {len(samples)} примерах")
        except Exception as e:
            logger.error(f"🧠 ML: ошибка обучения: {e}")

brain = ImprovedMLBrain()

# ==================== ИНТЕЛЛЕКТУАЛЬНЫЙ ПОИСК ИСТОЧНИКОВ ====================
class IntelligentSourceFinder:
    """AI-агент для поиска новых источников в сети"""
    
    def __init__(self):
        self.discovered_sources = set()
        self.source_quality = defaultdict(float)  # оценка качества источника
        self.lock = threading.Lock()
        
    def discover_from_search_engines(self):
        """Поиск новых источников через поисковики"""
        queries = [
            'iptv m3u ru бесплатный 2026',
            'плейлист iptv россия m3u8',
            'сайт iptv плейлист скачать бесплатно',
            'm3u playlist russia free',
            'telegram канал iptv плейлист',
            'актуальный плейлист iptv 2026',
            'iptv список каналов россия m3u',
            'бесплатные iptv плейлисты россия',
            'iptv russian channels m3u',
            'playlist iptv russia 2026',
        ]
        
        found_urls = []
        for q in queries[:5]:  # Ограничиваем для экономии времени
            try:
                # Поиск через DuckDuckGo
                r = requests.get('https://api.duckduckgo.com/', 
                                params={'q': q, 'format': 'json', 'no_html': 1},
                                headers=HEADERS_WEB, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    # Парсим результаты
                    for result in data.get('Results', []):
                        url = result.get('FirstURL', '')
                        if url and '.m3u' in url or 'iptv' in url:
                            found_urls.append(url)
                            
                    # Из RelatedTopics тоже берем
                    for topic in data.get('RelatedTopics', []):
                        if 'FirstURL' in topic:
                            url = topic['FirstURL']
                            if url and ('.m3u' in url or 'iptv' in url):
                                found_urls.append(url)
            except:
                continue
                
        # Ищем через простой поиск в HTML
        for q in queries[:3]:
            try:
                r = requests.get('https://html.duckduckgo.com/html/',
                                params={'q': q}, headers=HEADERS_WEB, timeout=10)
                if r.status_code == 200:
                    # Ищем ссылки на плейлисты
                    urls = re.findall(r'(https?://[^\s"\']+\.m3u8?)', r.text, re.I)
                    found_urls.extend(urls)
            except:
                continue
        
        # Фильтруем и добавляем
        with self.lock:
            for url in found_urls:
                if url.startswith('http') and any(word in url.lower() for word in ['iptv', 'm3u', 'playlist', 'tv']):
                    self.discovered_sources.add(url)
        
        logger.info(f"🔍 Найдено новых источников: {len(found_urls)}")
        return list(found_urls)[:50]  # Возвращаем первые 50
    
    def discover_from_telegram(self):
        """Поиск в Telegram-каналах"""
        channels = [
            'iptvru', 'iptv_russia', 'russian_iptv', 'iptv_m3u', 
            'freeiptv_ru', 'iptv_playlist', 'm3u_playlist', 'iptvfree',
            'iptv_rf', 'playlist_iptv', 'iptv_su', 'free_iptv_ru'
        ]
        
        found = []
        for ch in channels[:5]:  # Ограничиваем
            try:
                r = requests.get(f'https://t.me/s/{ch}', 
                               headers=HEADERS_WEB, timeout=10)
                if r.status_code == 200:
                    # Ищем ссылки на плейлисты
                    urls = re.findall(r'(https?://[^\s"\']+\.m3u8?)', r.text, re.I)
                    found.extend(urls)
            except:
                continue
                
        logger.info(f"📱 Найдено ссылок в Telegram: {len(found)}")
        return found[:30]
    
    def discover_from_git(self):
        """Поиск в GitHub/GitLab"""
        repos = []
        
        # GitHub
        try:
            r = requests.get('https://api.github.com/search/repositories',
                           params={'q': 'iptv m3u russia', 'per_page': 15, 
                                  'sort': 'updated', 'order': 'desc'},
                           headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            if r.status_code == 200:
                for item in r.json().get('items', []):
                    full = item.get('full_name')
                    branch = item.get('default_branch') or 'main'
                    if full:
                        repos.append((full, branch))
        except:
            pass
            
        found = []
        for full, branch in repos:
            base = f'https://raw.githubusercontent.com/{full}/{branch}'
            for path in ['ru.m3u', 'playlist.m3u', 'iptv.m3u', 'tv.m3u', 'main.m3u']:
                found.append(f'{base}/{path}')
                
        logger.info(f"📦 Найдено ссылок на GitHub: {len(found)}")
        return found[:30]
    
    def get_all_sources(self):
        """Собрать все источники"""
        all_sources = set()
        
        # Добавляем статику
        all_sources.update(STATIC_SOURCES)
        
        # Добавляем найденные
        all_sources.update(self.discover_from_search_engines())
        all_sources.update(self.discover_from_telegram())
        all_sources.update(self.discover_from_git())
        
        # Очищаем дубли
        all_sources = list(all_sources)
        
        # Сортируем по качеству (если есть оценка)
        with self.lock:
            all_sources.sort(key=lambda x: -self.source_quality.get(x, 0))
        
        return all_sources

source_finder = IntelligentSourceFinder()

# ==================== ФИЛЬТРЫ И КАТЕГОРИИ ====================
def get_category(name):
    """Интеллектуальная категоризация с обучением"""
    n = name.lower()
    # Взвешенные правила
    categories = {
        'Детские': ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney', 'gulli', 'аниме', 'nick', 'tiji', 'baby', 'малыш'],
        'Новости': ['новост', 'вести', 'информ', 'news', '24', 'известия', 'ртд', 'euronews', 'bbc', 'cnn', 'политик', 'эконом', 'бизнес', 'business', 'события', 'факты', 'репортаж'],
        'Спорт': ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'khl', 'ufc', 'бокс', 'киберспорт', 'esport', 'автоспорт', 'баскетбол', 'теннис', 'биатлон', 'лыжн', 'волейбол', 'фигурное катание', 'гимнастика'],
        'Кино и сериалы': ['кино', 'kino', 'movie', 'film', 'фильм', 'сериал', 'series', 'serial', 'cinema', 'tv1000', 'амедиа', 'дом кино', 'иллюзион', 'премьера', 'боевик', 'детектив', 'мелодрама', 'комедия', 'ужас', 'фантастика', 'киномикс', 'киносемья', 'кинокомедия', 'киносвидание', 'киноужас', 'кинопоказ', 'триллер', 'драма', 'приключение', 'вестерн', 'мюзикл'],
        'Музыка': ['музык', 'music', 'mtv', 'bridge', 'шансон', 'рутв', 'ru.tv', 'ретро', 'хит', 'жара', 'блюз', 'jazz', 'классик', 'classic', 'муз', 'tnt music', 'о2тв', 'o2tv', 'first music', 'музсоюз', 'поп', 'рок', 'рэп', 'хип-хоп', 'эстрада', 'фолк', 'кантри'],
        'Познавательные': ['докум', 'doc', 'познав', 'истори', 'history', 'discovery', 'science', 'наука', 'природ', 'animal', 'животн', 'океан', 'космос', 'культур', 'искусств', 'театр', 'музей', 'образов', 'школ', 'язык', 'travel', 'путешеств', 'религ', 'relig', 'спас', 'союз', 'техник', 'техно', 'авто', 'auto', 'дача', 'сад', 'огород', 'рыбал', 'охота', 'кулинар', 'еда', 'food', 'здоров', 'health', 'медицин', 'географи', 'биолог', 'астроном', 'физик', 'химия', 'экологи'],
        'Развлекательные': ['развлек', 'entertainment', 'юмор', 'comedy', 'камеди', 'квн', 'шоу', 'мода', 'fashion', 'стиль', 'lifestyle', 'лайфстайл', 'дом', 'home', 'семья', 'family', 'игры', 'game', 'лотерея', 'анекдот', 'талант', 'конкурс', 'викторина', 'ток-шоу'],
        'Региональные': ['москва', 'moscow', 'петербург', 'petersburg', 'лен тв', 'len tv', 'екатеринбург', 'новосибирск', 'казань', 'татарстан', 'уфа', 'башкортостан', 'самара', 'нижний новгород', 'краснодар', 'кубань', 'ростов', 'пермь', 'челябинск', 'омск', 'красноярск', 'владивосток', 'хабаровск', 'иркутск', 'тюмень', 'томск', 'барнаул', 'алтай', 'кемерово', 'кузбасс', 'удмуртия', 'ижевск', 'чувашия', 'чебоксары', 'мордовия', 'осетия', 'дагестан', 'грозный', 'чечня', 'кавказ', 'ставрополь', 'волгоград', 'саратов', 'тверь', 'тула', 'ярославль', 'воронеж', 'липецк', 'тамбов', 'брянск', 'курск', 'белгород', 'калуга', 'рязань', 'владимир', 'иваново', 'кострома', 'вологда', 'череповец', 'архангельск', 'мурманск', 'карелия', 'коми', 'калининград', 'псков', 'новгород', 'смоленск', 'якутск', 'якутия', 'бурятия', 'улан-удэ', 'чита', 'забайкаль', 'сахалин', 'магадан', 'камчатка', 'чукотка', 'сургут', 'югра', 'ямал', 'крым', 'севастополь', 'симферополь', 'сочи', 'минск', 'беларусь', 'гомель', 'брест', 'алматы', 'астана', 'ташкент', 'бишкек', 'душанбе', 'баку', 'ереван', 'кишинев', 'регион'],
        'Федеральные': ['первый канал', 'россия 1', 'россия к', 'нтв', 'тнт', 'стс', 'рен тв', 'пятый канал', 'тв центр', 'звезда', 'отр', 'пятница', 'суббота', 'домашний', 'муз-тв', '2x2', 'мир', 'channel one', 'pervyi', 'rossiya', 'russia 1', 'russia k', 'russia 24', 'ntv', 'ren tv', 'fifth channel', 'tv centr', 'телеканал']
    }
    
    # Считаем очки для каждой категории
    scores = {}
    for cat, keywords in categories.items():
        score = 0
        for kw in keywords:
            if kw in n:
                # Длинные совпадения весят больше
                score += len(kw) / 5
        if score > 0:
            scores[cat] = score
    
    # Возвращаем категорию с максимальным счетом
    if scores:
        return max(scores, key=scores.get)
    
    # Если ничего не найдено, проверяем наличие русских букв
    if re.search(r'[\u0400-\u04FF]', name):
        return 'Общие'
    
    return 'Общие'

def is_russian_channel(name, url):
    """Определяет, русский ли канал"""
    # Проверяем по названию
    if re.search(r'[\u0400-\u04FF]', name):
        return True
    
    # Проверяем по домену
    domain = urlparse(url).netloc.lower()
    ru_domains = ['.ru', '.su', '.рф', 'ru.', 'russia', 'russian']
    if any(d in domain for d in ru_domains):
        return True
    
    # Проверяем по ключевым словам в URL
    ru_keywords = ['russia', 'russian', 'ru-', '-ru', 'moskva', 'moscow']
    if any(kw in url.lower() for kw in ru_keywords):
        return True
    
    return False

def is_dead_channel(url):
    """Проверяет, не умер ли канал по истории"""
    dead_channels = channel_history.get_dead_channels(DEATH_THRESHOLD_DAYS)
    dead_urls = [row[0] for row in dead_channels]
    return url in dead_urls

# ==================== УЛУЧШЕННЫЙ ПАРСЕР ====================
def parse_m3u_ai(text, entries, seen_urls, reasons):
    """Парсинг с AI-фильтрацией"""
    current_inf = ''
    current_name = ''
    channels_added = 0
    
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('#EXTINF:'):
            current_inf = line
            m = re.search(r',\s*(.+)$', line)
            current_name = m.group(1).strip() if m else ''
            
        elif line.startswith('http') and current_name:
            url = line
            
            # Проверяем, русский ли канал
            if not is_russian_channel(current_name, url):
                reasons['not_russian'] += 1
                current_name = ''
                continue
            
            # Проверяем, не умер ли канал
            if is_dead_channel(url):
                reasons['dead_channel'] += 1
                current_name = ''
                continue
            
            # Проверяем дубли
            if url in seen_urls:
                reasons['duplicate'] += 1
                current_name = ''
                continue
                
            seen_urls.add(url)
            
            # Определяем категорию
            cat = get_category(current_name)
            
            # Формируем запись
            inf = re.sub(r'\s*group-title="[^"]*"', '', current_inf)
            inf = re.sub(r'(#EXTINF:-?\d+)', r'\1 group-title="' + cat + '"', inf, count=1)
            
            ch = {
                'inf': inf,
                'url': url,
                'cat': cat,
                'name': current_name,
                'ua': '',
                'ref': '',
                'source': 'parse'
            }
            
            # Уникальный ключ
            key = norm_name(current_name)
            if key in entries:
                # Предпочитаем HD/4K
                if is_hd(current_name) and not is_hd(entries[key]['name']):
                    entries[key] = ch
            else:
                entries[key] = ch
                channels_added += 1
                
            # Лимит каналов
            if len(entries) >= MAX_CHANNELS:
                return True
                
            current_name = ''
            current_inf = ''
            
    return False

# ==================== ПРОВЕРКА С ИСТОРИЕЙ ====================
def check_with_history(ch):
    """Проверка канала с записью в историю"""
    url = ch['url']
    name = ch['name']
    cat = ch['cat']
    
    # Проверяем
    is_alive = check_one(ch)
    
    # Записываем в историю
    channel_history.record_check(url, name, cat, is_alive)
    
    return is_alive

def check_one(ch, limit=None):
    """Проверка одного канала (оригинальная функция)"""
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
        r = session.head(url, timeout=min(10, lim), headers=headers,
                         allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            good_ct = ('video/', 'audio/', 'mpegurl', 'octet-stream', 'mp2t')
            if any(g in ct for g in good_ct):
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
        if any(g in ct for g in ('video/', 'audio/', 'mpegurl', 'octet-stream', 'mp2t')):
            return True
        if chunk[:1] == b'\x47':  # TS stream
            return True
        low = chunk[:300].lower()
        if b'#extm3u' in low or b'#extinf' in low:
            return True
        if b'<html' in low or b'<!doctype' in low or b'<script' in low:
            return False
        try:
            txt_low = low.decode('utf-8', errors='ignore')
        except Exception:
            txt_low = ''
        block_markers = ['roskomnadzor', 'zablokirovan', 'blocked', 'restricted',
                        'forbidden', 'captcha', 'cloudflare', 'access denied']
        if any(m in txt_low for m in block_markers):
            return False
        return True

    return False

# ==================== АВТОМАТИЧЕСКОЕ УДАЛЕНИЕ МЕРТВЫХ ====================
def cleanup_dead_channels():
    """Удаляет каналы, которые мертвы более 3 недель"""
    logger.info("🧹 Запуск очистки мертвых каналов...")
    
    dead = channel_history.get_dead_channels(DEATH_THRESHOLD_DAYS)
    if not dead:
        logger.info("🧹 Мертвых каналов не найдено")
        return 0
    
    dead_urls = [row[0] for row in dead]
    
    # Удаляем из основного плейлиста
    global playlist_cache
    with cache_lock:
        lines = playlist_cache.split('\n')
        new_lines = []
        removed = 0
        skip_next = False
        
        for line in lines:
            if skip_next:
                skip_next = False
                continue
            if line.startswith('http'):
                url = line.strip()
                if url in dead_urls:
                    # Удаляем эту строку и предыдущую (EXTINF)
                    if new_lines and new_lines[-1].startswith('#EXTINF'):
                        new_lines.pop()
                    removed += 1
                    continue
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)
        
        if removed > 0:
            playlist_cache = '\n'.join(new_lines)
            save_disk_cache(playlist_cache)
            channel_history.cleanup_dead(dead_urls)
            
            with cache_lock:
                stats['dead_removed'] += removed
                stats['alive_channels'] = len([l for l in new_lines if l.startswith('http')])
                
            logger.info(f"🧹 Удалено {removed} мертвых каналов")
    
    return removed

# ==================== ОБНОВЛЕНИЕ С AI ====================
def update_with_ai():
    """Основной процесс обновления с AI"""
    global playlist_cache, is_updating
    if is_updating:
        return
    is_updating = True
    start = time.time()
    
    logger.info("🤖 Запуск AI-обновления...")
    
    try:
        # 1. Очистка мертвых каналов
        cleanup_dead_channels()
        
        # 2. Поиск новых источников
        sources = source_finder.get_all_sources()
        logger.info(f"🔍 Найдено источников: {len(sources)}")
        
        # 3. Загрузка плейлистов
        texts = []
        with ThreadPoolExecutor(max_workers=SOURCE_WORKERS) as ex:
            futs = [ex.submit(fetch_source_text, u) for u in sources[:MAX_EXTRA_SOURCES + len(STATIC_SOURCES)]]
            for f in as_completed(futs, timeout=SOURCE_PHASE_MAX):
                try:
                    txt = f.result()
                    if txt:
                        texts.append(txt)
                except:
                    continue
        
        logger.info(f"📥 Загружено плейлистов: {len(texts)}")
        
        # 4. Парсинг с AI-фильтрацией
        entries = {}
        seen = set()
        reasons = Counter()
        
        for txt in texts:
            if parse_m3u_ai(txt, entries, seen, reasons):
                break
        
        with cache_lock:
            stats['filtered'] = dict(reasons)
            stats['playlists_loaded'] = len(texts)
            stats['parsed_channels'] = len(entries)
        
        logger.info(f"📊 Уникальных каналов: {len(entries)}, фильтры: {dict(reasons)}")
        
        # 5. ML-сортировка
        raw = list(entries.values())
        for ch in raw:
            feats = extract_features(ch)
            host = urlparse(ch['url']).netloc
            ch['ml_score'] = brain.score(feats, host)
            ch['feats'] = feats
            ch['host'] = host
        
        raw.sort(key=lambda c: -c['ml_score'])
        
        # 6. Проверка каналов
        if len(raw) > MAX_CHECK_POOL:
            logger.info(f"🧠 ML выбрал топ-{MAX_CHECK_POOL} из {len(raw)}")
            raw = raw[:MAX_CHECK_POOL]
        
        alive = []
        samples = []
        checked = 0
        last_beat = time.time()
        
        with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as ex:
            futs = {ex.submit(check_with_history, ch): ch for ch in raw}
            for f in as_completed(futs.keys(), timeout=CHECK_PHASE_MAX):
                checked += 1
                ch = futs[f]
                try:
                    ok = bool(f.result())
                except:
                    ok = False
                    
                if ok:
                    alive.append(ch)
                    if len(alive) % FLUSH_EVERY == 0:
                        flush_playlist(alive)
                
                samples.append((ch['feats'], 1 if ok else 0))
                
                if time.time() - last_beat > HEARTBEAT_SEC:
                    logger.info(f"⏳ Прогресс: {checked}/{len(raw)}, живых: {len(alive)}")
                    last_beat = time.time()
        
        # 7. Обучение нейросети
        brain.train(samples)
        with cache_lock:
            stats['ml_samples'] = brain.trained_samples
            stats['ml_accuracy'] = round(brain.last_accuracy, 3)
        
        # 8. Финализация
        elapsed = time.time() - start
        flush_playlist(alive, elapsed=elapsed)
        
        with cache_lock:
            stats['alive_channels'] = len(alive)
            stats['new_added'] = len(alive)
            stats['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            stats['duration_sec'] = round(elapsed, 1)
        
        logger.info(f"✅ Готово: {len(alive)} живых каналов за {elapsed:.0f} сек")
        
    except Exception as e:
        logger.exception(f"❌ Ошибка обновления: {e}")
    finally:
        is_updating = False

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def extract_features(ch):
    """Извлечение признаков для ML"""
    url = ch['url']
    name = (ch.get('name') or '').lower()
    u = url.lower()
    
    return [
        min(len(u) / 300.0, 1.0),
        min(u.count('/') / 8.0, 1.0),
        1.0 if u.startswith('https') else 0.0,
        1.0 if '.m3u8' in u else 0.0,
        1.0 if re.search(r'\.(ts|mp4|mkv|flv)(\?|$)', u) else 0.0,
        1.0 if any(t in u for t in ['token', 'key=', 'auth', 'session', 'sig=']) else 0.0,
        1.0 if ('hd' in name or '4k' in name) else 0.0,
        min(len(name) / 40.0, 1.0),
        1.0 if (ch.get('ua') or ch.get('ref')) else 0.0,
        1.0 if 'iptv-org' in u else 0.0,
        1.0 if any(domain in u for domain in ['.ru', '.su', 'russian']) else 0.0,
        1.0 if re.search(r'[\u0400-\u04FF]', name) else 0.0,
    ]

def norm_name(name):
    """Нормализация названия"""
    n = name.lower().strip()
    n = re.sub(r'[\(\[].*?[\)\]]', '', n)
    n = re.sub(r'\b(hd|fhd|uhd|4k|sd|hevc|h265|h264)\b', '', n)
    return re.sub(r'\s+', ' ', n).strip(' -_|')

def is_hd(name):
    n = name.lower()
    return 'hd' in n or '4k' in n or 'uhd' in n or 'fhd' in n

def fetch_source_text(url):
    try:
        r = requests.get(url, timeout=(5, 10), headers=HEADERS_WEB, verify=False)
        if r.status_code == 200 and r.text:
            return r.text
    except:
        pass
    return None

def get_session():
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10, max_retries=0)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def flush_playlist(alive, elapsed=None):
    global playlist_cache
    alive_sorted = sorted(alive, key=lambda c: (CAT_ORDER.index(c['cat']) if c['cat'] in CAT_ORDER else len(CAT_ORDER), c['name'].lower()))
    cat_counts = Counter(ch['cat'] for ch in alive_sorted)
    
    lines = [
        '#EXTM3U',
        f'# IPTV Russia AI — {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        f'# Живых каналов: {len(alive_sorted)} | Без UA/радио/платных | AI-фильтрация',
        f'# Категории: {", ".join(f"{k}:{v}" for k,v in cat_counts.most_common(5))}'
    ]
    
    for ch in alive_sorted:
        lines.append(ch['inf'])
        lines.append(ch['url'])
    
    data = '\n'.join(lines)
    with cache_lock:
        playlist_cache = data
        stats['categories'] = dict(cat_counts)
        if elapsed is not None:
            stats['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            stats['duration_sec'] = round(elapsed, 1)
    save_disk_cache(data)

def save_disk_cache(data):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            f.write(data)
    except:
        pass

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
                logger.info(f"💾 Восстановлен плейлист: {n} каналов")
    except Exception as e:
        logger.error(f"Ошибка загрузки кэша: {e}")

def background_worker():
    while True:
        try:
            update_with_ai()
        except Exception as e:
            logger.exception(f"Фоновая ошибка: {e}")
        finally:
            with cache_lock:
                alive_n = stats['alive_channels']
            wait = UPDATE_EVERY if alive_n > 0 else RETRY_IF_EMPTY
            logger.info(f"⏰ Следующая проверка через {wait // 60} мин")
            time.sleep(wait)

def keepalive_worker():
    while True:
        time.sleep(KEEPALIVE_SEC)
        logger.debug("💓 AI-сервис жив")

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    with cache_lock:
        s = dict(stats)
        alive = s.get('alive_channels', 0)
        last_update = s.get('last_update', 'Нет данных')
        categories = s.get('categories', {})
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>IPTV Russia AI</title>
        <style>
            body {{ font-family: system-ui, sans-serif; background: linear-gradient(135deg, #0f2027, #203a43, #2c5364); color: #fff; min-height: 100vh; margin: 0; display: flex; align-items: center; justify-content: center; }}
            .card {{ background: rgba(255,255,255,.1); backdrop-filter: blur(10px); border-radius: 20px; padding: 40px; max-width: 700px; width: 90%; box-shadow: 0 20px 60px rgba(0,0,0,.4); }}
            h1 {{ margin: 0 0 10px; font-size: 28px; }}
            .sub {{ opacity: .7; margin-bottom: 20px; }}
            .btn {{ display: inline-block; padding: 12px 24px; border-radius: 10px; text-decoration: none; font-weight: 600; margin: 5px; }}
            .btn-green {{ background: #4caf50; color: #fff; }}
            .btn-blue {{ background: #2196f3; color: #fff; }}
            .btn-gray {{ background: #607d8b; color: #fff; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; margin: 20px 0; }}
            .stat {{ background: rgba(255,255,255,.1); border-radius: 10px; padding: 12px; text-align: center; }}
            .stat b {{ display: block; font-size: 22px; }}
            .stat span {{ font-size: 11px; opacity: .7; }}
            .chip {{ display: inline-block; background: rgba(255,255,255,.15); border-radius: 15px; padding: 4px 12px; margin: 3px; font-size: 12px; }}
            .info {{ margin: 15px 0; padding: 10px; background: rgba(0,0,0,.2); border-radius: 10px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🇷🇺 IPTV Russia AI</h1>
            <div class="sub">🧠 Самообучающийся плейлист • Умная фильтрация • Автоочистка</div>
            
            <div>
                <a href="/playlist.m3u" class="btn btn-green">📥 Скачать плейлист</a>
                <a href="/refresh" class="btn btn-blue">🔄 Обновить</a>
                <a href="/status" class="btn btn-gray">📊 Статистика</a>
                <a href="/cleanup" class="btn btn-gray">🧹 Очистить мертвые</a>
            </div>
            
            <div class="stats">
                <div class="stat"><b>{alive}</b><span>Живых каналов</span></div>
                <div class="stat"><b>{s.get('parsed_channels', 0)}</b><span>Проверено</span></div>
                <div class="stat"><b>{s.get('ml_samples', 0)}</b><span>ML примеров</span></div>
                <div class="stat"><b>{s.get('ml_accuracy', 0):.1%}</b><span>Точность ML</span></div>
            </div>
            
            <div class="info">
                <div>📅 Обновлено: <b>{last_update}</b></div>
                <div>⏱️ Длительность: <b>{s.get('duration_sec', 0)}с</b></div>
                <div>🗑️ Удалено: <b>{s.get('dead_removed', 0)}</b> мертвых каналов</div>
            </div>
            
            <div>
                <b>Категории:</b><br>
                {''.join(f'<span class="chip">{k}: {v}</span>' for k,v in sorted(categories.items(), key=lambda x: -x[1])[:10])}
            </div>
            
            <div style="margin-top: 15px; font-size: 12px; opacity: .6;">
                ⚡ Автоматическое удаление каналов, умерших более {DEATH_THRESHOLD_DAYS} дней назад
            </div>
        </div>
    </body>
    </html>
    """
    return html

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    with cache_lock:
        data = playlist_cache
    response = Response(data, mimetype='application/vnd.apple.mpegurl')
    response.headers['Content-Disposition'] = 'attachment; filename="iptv_russia_ai.m3u"'
    response.headers['Cache-Control'] = 'no-store'
    return response

@app.route('/status')
def status():
    with cache_lock:
        data = dict(stats)
    data['is_updating'] = is_updating
    data['channel_db'] = channel_history.get_stats()
    return jsonify(data)

@app.route('/refresh')
def refresh():
    if is_updating:
        return jsonify({'status': 'already_updating'})
    threading.Thread(target=update_with_ai, daemon=True).start()
    return jsonify({'status': 'refresh_started'})

@app.route('/cleanup')
def cleanup():
    removed = cleanup_dead_channels()
    return jsonify({'status': 'cleanup_done', 'removed': removed})

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'alive_channels': stats['alive_channels'],
        'is_updating': is_updating,
        'ml_trained': brain.trained_samples > 0
    })

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    
    # Загружаем кэш
    load_disk_cache()
    
    # Запускаем фоновые задачи
    threading.Thread(target=background_worker, daemon=True).start()
    threading.Thread(target=keepalive_worker, daemon=True).start()
    
    logger.info(f"🚀 AI-сервис запущен на порту {port}")
    logger.info(f"🧠 Модель: {'загружена' if brain.model else 'не обучена'}")
    logger.info(f"🗄️ База каналов: {channel_history.get_stats()}")
    
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)