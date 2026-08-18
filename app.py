import os
import re
import time
import math
import json
import logging
import threading
import sqlite3
import requests
from flask import Flask, Response, jsonify
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from collections import Counter
from datetime import datetime

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== КОНФИГ ====================
MAX_CHANNELS = 20000
CHECK_WORKERS = 15
CHECK_TIMEOUT = 12.0
UPDATE_EVERY = 43200  # 12 часов
DEATH_THRESHOLD_DAYS = 21  # 3 недели
DB_FILE = "channels.db"
MODEL_FILE = "model.json"

# ==================== НЕЙРОСЕТЬ С СОХРАНЕНИЕМ ====================
class TinyNeuralNetwork:
    def __init__(self):
        self.w1 = [[0.0]*12 for _ in range(8)]
        self.b1 = [0.0]*8
        self.w2 = [0.0]*8
        self.b2 = 0.0
        self.trained = False
        
    def _sigmoid(self, z): 
        if z >= 0:
            return 1.0 / (1.0 + math.exp(-z))
        ez = math.exp(z)
        return ez / (1.0 + ez)

    def _forward(self, x):
        hidden = []
        for i in range(8):
            z = self.b1[i] + sum(self.w1[i][j] * x[j] for j in range(12))
            hidden.append(self._sigmoid(z))
        z = self.b2 + sum(self.w2[i] * hidden[i] for i in range(8))
        return self._sigmoid(z), hidden

    def predict(self, x): 
        p, _ = self._forward(x)
        return p

    def train(self, X, y):
        for _ in range(3):
            for x, target in zip(X, y):
                output, hidden = self._forward(x)
                error = output - target
                d_output = error * output * (1 - output)
                for i in range(8): 
                    self.w2[i] -= 0.1 * d_output * hidden[i]
                self.b2 -= 0.1 * d_output
                for i in range(8):
                    d_hidden = d_output * self.w2[i] * hidden[i] * (1 - hidden[i])
                    for j in range(12): 
                        self.w1[i][j] -= 0.1 * d_hidden * x[j]
                    self.b1[i] -= 0.1 * d_hidden
        self.trained = True
    
    def save(self, path=MODEL_FILE):
        try:
            data = {
                'w1': self.w1, 'b1': self.b1,
                'w2': self.w2, 'b2': self.b2,
                'trained': self.trained
            }
            with open(path, 'w') as f:
                json.dump(data, f)
            return True
        except:
            return False
    
    def load(self, path=MODEL_FILE):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            self.w1 = data['w1']
            self.b1 = data['b1']
            self.w2 = data['w2']
            self.b2 = data['b2']
            self.trained = data.get('trained', False)
            return True
        except:
            return False

brain = TinyNeuralNetwork()
brain.load()

# ==================== ИСТОЧНИКИ ====================
STATIC_SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/languages/tat.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/smolnp/IPTVru/main/IPTVru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/countries/ru.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
]

# ==================== БД ИСТОРИИ ====================
class ChannelDB:
    def __init__(self, db_file=DB_FILE):
        self.conn = sqlite3.connect(db_file, check_same_thread=False, timeout=30)
        self.conn.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                url TEXT PRIMARY KEY,
                name TEXT,
                category TEXT,
                first_seen REAL,
                last_check REAL,
                last_alive REAL,
                last_dead REAL,
                checks INTEGER DEFAULT 0,
                alive_count INTEGER DEFAULT 0
            )
        ''')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_dead ON channels(last_dead)')
        self.conn.execute('CREATE INDEX IF NOT EXISTS idx_url ON channels(url)')
        self.conn.commit()
        self.lock = threading.Lock()
    
    def record(self, url, name, category, is_alive):
        with self.lock:
            now = time.time()
            cur = self.conn.cursor()
            
            cur.execute('SELECT checks, alive_count FROM channels WHERE url = ?', (url,))
            row = cur.fetchone()
            
            if row:
                checks, alive = row
                checks += 1
                if is_alive:
                    alive += 1
                    cur.execute('''
                        UPDATE channels SET last_check=?, last_alive=?, 
                        checks=?, alive_count=? WHERE url=?
                    ''', (now, now, checks, alive, url))
                else:
                    cur.execute('''
                        UPDATE channels SET last_check=?, last_dead=?, 
                        checks=?, alive_count=? WHERE url=?
                    ''', (now, now, checks, alive, url))
            else:
                cur.execute('''
                    INSERT INTO channels (url, name, category, first_seen, last_check, 
                                         last_alive, last_dead, checks, alive_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (url, name, category, now, now, 
                      now if is_alive else None, 
                      None if is_alive else now, 1, 1 if is_alive else 0))
            
            self.conn.commit()
    
    def get_dead(self, days=DEATH_THRESHOLD_DAYS):
        threshold = time.time() - (days * 86400)
        cur = self.conn.cursor()
        cur.execute('''
            SELECT url, name, category FROM channels 
            WHERE last_dead IS NOT NULL 
            AND last_dead < ?
            AND checks >= 5
            AND (alive_count * 1.0 / checks) < 0.3
        ''', (threshold,))
        return cur.fetchall()
    
    def get_stats(self):
        cur = self.conn.cursor()
        total = cur.execute('SELECT COUNT(*) FROM channels').fetchone()[0]
        dead = cur.execute('SELECT COUNT(*) FROM channels WHERE last_dead IS NOT NULL AND alive_count*1.0/checks < 0.3').fetchone()[0]
        alive = cur.execute('SELECT COUNT(*) FROM channels WHERE alive_count*1.0/checks >= 0.7').fetchone()[0]
        return {'total': total, 'dead': dead, 'alive': alive}

db = ChannelDB()

# ==================== РАСШИРЕННЫЕ КАТЕГОРИИ ====================
CATEGORIES = {
    'Новости': [
        'новост', 'news', '24', 'вести', 'известия', 'информ', 'события', 'факты',
        'репортаж', 'интервью', 'обзор', 'итоги', 'главное', 'сегодня', 'сейчас',
        'прямой эфир', 'live', 'breaking', 'экстрен', 'чп', 'происшеств'
    ],
    'Спорт': [
        'спорт', 'sport', 'футбол', 'хоккей', 'матч', 'ufc', 'бокс', 
        'киберспорт', 'esport', 'баскетбол', 'теннис', 'биатлон', 'лыжн',
        'khl', 'nhl', 'nba', 'формула', 'racing', 'волейбол', 'гандбол',
        'фигурное катание', 'гимнастика', 'плавание', 'легкая атлетика',
        'mma', 'единоборства', 'экстрим', 'скейт', 'сноуборд'
    ],
    'Кино и сериалы': [
        'кино', 'kino', 'movie', 'film', 'фильм', 'сериал', 'series', 
        'serial', 'cinema', 'tv1000', 'амедиа', 'дом кино', 'иллюзион',
        'премьера', 'боевик', 'детектив', 'мелодрама', 'комедия',
        'триллер', 'драма', 'приключение', 'вестерн', 'мюзикл',
        'фэнтези', 'фантастика', 'ужас', 'horror', 'криминал',
        'исторический', 'военный', 'киносвидание', 'киноужас'
    ],
    'Детские': [
        'дет', 'kids', 'мульт', 'cartoon', 'карусель', 'disney', 'gulli', 
        'аниме', 'nick', 'tiji', 'baby', 'малыш', 'маленький', 'дошкольн',
        'развивай', 'обучай', 'сказк', 'игруш', 'кукл', 'лего',
        'peppa', 'папа', 'мама', 'няня', 'школа', 'класс'
    ],
    'Музыка': [
        'музык', 'music', 'mtv', 'bridge', 'шансон', 'рутв', 'ru.tv', 
        'ретро', 'хит', 'жара', 'блюз', 'jazz', 'классик', 'classic',
        'поп', 'рок', 'рэп', 'хип-хоп', 'эстрада', 'фолк', 'кантри',
        'джаз', 'опера', 'симфони', 'оркестр', 'хор', 'вокал'
    ],
    'Познавательные': [
        'докум', 'doc', 'познав', 'истори', 'history', 'discovery', 
        'science', 'наука', 'природ', 'animal', 'животн', 'океан', 
        'космос', 'культур', 'искусств', 'театр', 'музей',
        'географи', 'биолог', 'астроном', 'физик', 'химия', 'экологи',
        'техник', 'техно', 'авто', 'auto', 'дача', 'сад', 'огород',
        'рыбал', 'охота', 'кулинар', 'еда', 'food', 'здоров', 'health'
    ],
    'Развлекательные': [
        'развлек', 'entertainment', 'юмор', 'comedy', 'камеди', 
        'квн', 'шоу', 'мода', 'fashion', 'стиль', 'lifestyle',
        'лайфстайл', 'дом', 'home', 'семья', 'family', 'игры', 'game',
        'лотерея', 'анекдот', 'талант', 'конкурс', 'викторина',
        'ток-шоу', 'интервью', 'звезд', 'знаменитост'
    ],
    'Региональные': [
        'москва', 'moscow', 'петербург', 'petersburg', 'лен тв', 'len tv', 
        'екатеринбург', 'новосибирск', 'казань', 'татарстан', 'уфа',
        'башкортостан', 'самара', 'нижний новгород', 'краснодар', 'кубань',
        'ростов', 'пермь', 'челябинск', 'омск', 'красноярск', 'владивосток',
        'хабаровск', 'иркутск', 'тюмень', 'томск', 'барнаул', 'алтай',
        'кемерово', 'кузбасс', 'удмуртия', 'ижевск', 'чувашия', 'чебоксары',
        'мордовия', 'осетия', 'дагестан', 'грозный', 'чечня', 'кавказ',
        'ставрополь', 'волгоград', 'саратов', 'тверь', 'тула', 'ярославль',
        'воронеж', 'липецк', 'тамбов', 'брянск', 'курск', 'белгород',
        'калуга', 'рязань', 'владимир', 'иваново', 'кострома', 'вологда',
        'архангельск', 'мурманск', 'карелия', 'коми', 'калининград',
        'псков', 'новгород', 'смоленск', 'якутск', 'якутия', 'бурятия',
        'сахалин', 'магадан', 'камчатка', 'чукотка', 'сургут', 'югра',
        'ямал', 'крым', 'севастополь', 'симферополь', 'сочи', 'минск',
        'беларусь', 'гомель', 'брест', 'алматы', 'астана', 'ташкент',
        'бишкек', 'душанбе', 'баку', 'ереван', 'кишинев'
    ],
    'Федеральные': [
        'первый канал', 'россия 1', 'россия к', 'нтв', 'тнт', 'стс', 
        'рен тв', 'пятый канал', 'тв центр', 'звезда', 'отр', 'пятница',
        'суббота', 'домашний', 'муз-тв', '2x2', 'мир', 'channel one',
        'pervyi', 'rossiya', 'russia 1', 'russia k', 'russia 24',
        'телеканал', 'федеральн', 'общероссийск'
    ]
}

# ==================== ФИЛЬТРЫ ====================
def get_category(name):
    n = name.lower()
    for cat, keywords in CATEGORIES.items():
        if any(kw in n for kw in keywords):
            return cat
    # Если есть русские буквы, но категория не найдена
    if re.search(r'[\u0400-\u04FF]', name):
        return 'Общие'
    return 'Общие'

def is_russian(name, url):
    """Проверка, что канал русский"""
    # Специальные случаи (детские, международные)
    if any(w in name.lower() for w in ['kids', 'cartoon', 'disney', 'nick', 'baby', 'gulli']):
        return True
    
    # По названию
    if re.search(r'[а-яёА-ЯЁ]', name):
        # Проверяем на украинский
        ua_words = ['україн', 'украин', 'київ', 'kyiv', 'львів', 'харків', 'суспільне']
        if any(w in name.lower() for w in ua_words):
            return False
        return True
    
    # По URL
    ru_domains = ['.ru', '.su', '.рф', 'russian', 'russia', 'ru-', '-ru']
    if any(d in url.lower() for d in ru_domains):
        return True
    
    return False

def is_paywall(name, url):
    """Платные/рекламные каналы"""
    # По названию
    paywall_names = ['подписк', 'оплат', 'купить', 'premium', 'vip', 'реклам', 'shop', 'wink']
    if any(w in name.lower() for w in paywall_names):
        return True
    
    # По URL
    paywall_domains = ['wink.ru', 'rt.ru', 'tvigle.ru', 'megogo.net', 'okko.tv', 
                       'ivi.ru', 'start.ru', 'more.tv', 'amediateka.ru', 'kion.ru']
    if any(pd in url.lower() for pd in paywall_domains):
        return True
    
    return False

def is_radio(name):
    """Радиостанции"""
    radio = ['радио', 'radio', 'fm', 'эфир', 'волна', 'sound', 'audio']
    return any(w in name.lower() for w in radio)

# ==================== ПАРСИНГ ====================
def parse_m3u(txt, entries, seen):
    current_name = ''
    current_inf = ''
    added = 0
    
    for line in txt.splitlines():
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('#EXTINF:'):
            current_inf = line
            m = re.search(r',\s*(.+)$', line)
            current_name = m.group(1).strip() if m else ''
            
        elif line.startswith('http') and current_name:
            url = line
            
            # Фильтры
            if not current_name:
                continue
            if not is_russian(current_name, url):
                continue
            if is_paywall(current_name, url):
                continue
            if is_radio(current_name):
                continue
            if url in seen:
                continue
                
            seen.add(url)
            
            cat = get_category(current_name)
            inf = re.sub(r'group-title="[^"]*"', '', current_inf)
            inf = re.sub(r'(#EXTINF:-?\d+)', r'\1 group-title="' + cat + '"', inf, count=1)
            
            key = re.sub(r'\s+', ' ', current_name.lower().strip())
            if key not in entries:
                entries[key] = {
                    'inf': inf, 
                    'url': url, 
                    'name': current_name, 
                    'cat': cat,
                    'url_clean': url.split('?')[0]
                }
                added += 1
                
            current_name = ''
            current_inf = ''
            
    return added

# ==================== ПРОВЕРКА ====================
def check_one(ch):
    url = ch['url']
    headers = {
        'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20',
        'Connection': 'close'
    }
    
    # HEAD запрос
    try:
        r = requests.head(url, headers=headers, timeout=CHECK_TIMEOUT, 
                         allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(g in ct for g in ['video/', 'audio/', 'mp2t', 'mpeg', 'octet-stream']):
                return True
    except:
        pass
    
    # GET запрос с проверкой первого байта
    try:
        r = requests.get(url, headers=headers, timeout=CHECK_TIMEOUT, 
                        stream=True, allow_redirects=True, verify=False)
        if r.status_code >= 400:
            return False
        
        ct = r.headers.get('content-type', '').lower()
        if any(g in ct for g in ['video/', 'audio/', 'mp2t', 'mpeg']):
            return True
        
        chunk = next(r.iter_content(chunk_size=1024), b'')
        if chunk:
            if chunk[:1] == b'\x47':  # TS stream
                return True
            if b'#EXTM3U' in chunk[:100] or b'#EXTINF' in chunk[:100]:
                return True
    except:
        pass
    
    return False

# ==================== ОБНОВЛЕНИЕ ====================
def update_with_ai():
    global playlist_cache, is_updating
    if is_updating:
        return
    
    is_updating = True
    start = time.time()
    logger.info("🤖 AI-обновление запущено...")
    
    try:
        # 1. Удаляем мертвые каналы
        dead = db.get_dead()
        if dead:
            logger.info(f"🧹 Найдено {len(dead)} мертвых каналов")
        
        # 2. Загружаем источники
        sources = STATIC_SOURCES
        texts = []
        
        with ThreadPoolExecutor(max_workers=10) as ex:
            futs = [ex.submit(requests.get, u, timeout=15, verify=False) for u in sources]
            for f in as_completed(futs):
                try:
                    r = f.result()
                    if r.status_code == 200 and r.text:
                        texts.append(r.text)
                except:
                    continue
        
        logger.info(f"📥 Загружено плейлистов: {len(texts)}")
        
        # 3. Парсим
        entries = {}
        seen = set()
        total_added = 0
        
        for txt in texts:
            added = parse_m3u(txt, entries, seen)
            total_added += added
            if len(entries) >= MAX_CHANNELS:
                break
        
        logger.info(f"📊 Уникальных каналов: {len(entries)}")
        
        # 4. Сортируем по ML
        raw = list(entries.values())
        for ch in raw:
            feats = extract_features(ch)
            ch['ml_score'] = brain.predict(feats) if brain.trained else 0.7
        raw.sort(key=lambda c: -c['ml_score'])
        
        # 5. Проверяем
        check_pool = raw[:8000]
        alive = []
        samples = []
        checked = 0
        
        with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as ex:
            futs = {ex.submit(check_one, ch): ch for ch in check_pool}
            for f in as_completed(futs):
                ch = futs[f]
                checked += 1
                try:
                    is_alive = f.result()
                except:
                    is_alive = False
                
                # Запись в историю
                db.record(ch['url'], ch['name'], ch.get('cat', 'Общие'), is_alive)
                
                if is_alive:
                    alive.append(ch)
                
                samples.append((extract_features(ch), 1 if is_alive else 0))
                
                if checked % 100 == 0:
                    logger.info(f"⏳ Проверено: {checked}/{len(check_pool)}, живых: {len(alive)}")
        
        # 6. Обучаем нейросеть
        if len(samples) > 100:
            X = [s[0] for s in samples]
            y = [s[1] for s in samples]
            brain.train(X, y)
            brain.save()
            logger.info(f"🧠 ML обучен на {len(samples)} примерах")
        
        # 7. Удаляем мертвые
        dead_urls = [row[0] for row in db.get_dead()]
        alive = [ch for ch in alive if ch['url'] not in dead_urls]
        
        # 8. Сохраняем плейлист
        elapsed = time.time() - start
        flush_playlist(alive, elapsed)
        
        logger.info(f"✅ Готово: {len(alive)} живых каналов за {elapsed:.0f}с")
        
    except Exception as e:
        logger.exception(f"❌ Ошибка: {e}")
    finally:
        is_updating = False

# ==================== ВСПОМОГАТЕЛЬНЫЕ ====================
def extract_features(ch):
    url = ch['url'].lower()
    name = ch['name'].lower()
    return [
        min(len(url) / 300, 1.0),
        min(url.count('/') / 8, 1.0),
        1.0 if url.startswith('https') else 0.0,
        1.0 if '.m3u8' in url else 0.0,
        1.0 if re.search(r'\.(ts|mp4|mkv)', url) else 0.0,
        1.0 if any(x in url for x in ['hd', '4k']) else 0.0,
        min(len(name) / 40, 1.0),
        1.0 if re.search(r'[\u0400-\u04FF]', name) else 0.0,
        1.0 if any(d in url for d in ['.ru', '.su']) else 0.0,
        1.0 if 'iptv-org' in url else 0.0,
        (1.0 if 'http' in url else 0.0),
        min(url.count('?') / 5, 1.0),
    ]

def flush_playlist(alive, elapsed=None):
    global playlist_cache
    
    cat_order = ['Федеральные', 'Новости', 'Кино и сериалы', 'Спорт', 
                 'Детские', 'Музыка', 'Познавательные', 'Развлекательные', 
                 'Региональные', 'Общие']
    
    def sort_key(ch):
        try:
            idx = cat_order.index(ch.get('cat', 'Общие'))
        except:
            idx = 9
        return (idx, ch['name'].lower())
    
    alive_sorted = sorted(alive, key=sort_key)
    cat_counts = Counter(ch.get('cat', 'Общие') for ch in alive_sorted)
    
    lines = [
        '#EXTM3U',
        f'# IPTV Russia AI — {datetime.now().strftime("%Y-%m-%d %H:%M")}',
        f'# Живых: {len(alive_sorted)} | ML обучен: {brain.trained}',
        f'# Категории: {", ".join(f"{k}:{v}" for k,v in cat_counts.items())}',
    ]
    
    for ch in alive_sorted:
        lines.append(ch['inf'])
        lines.append(ch['url'])
    
    playlist_cache = '\n'.join(lines)
    logger.info(f"💾 Плейлист сохранен: {len(alive_sorted)} каналов")

playlist_cache = "#EXTM3U\n# IPTV Russia AI - загрузка...\n"
is_updating = False

def background_worker():
    while True:
        try:
            update_with_ai()
        except Exception as e:
            logger.error(f"Фоновая ошибка: {e}")
        time.sleep(UPDATE_EVERY)

# ==================== ВЕБ-ИНТЕРФЕЙС ====================
@app.route('/')
def home():
    with app.app_context():
        alive = len([l for l in playlist_cache.split('\n') if l.startswith('http')])
        stats = db.get_stats()
        
        return f"""
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
                .info {{ margin: 15px 0; padding: 10px; background: rgba(0,0,0,.2); border-radius: 10px; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>🇷🇺 IPTV Russia AI</h1>
                <div class="sub">🧠 Самообучающийся плейлист • Автоочистка • ML</div>
                
                <div>
                    <a href="/playlist.m3u" class="btn btn-green">📥 Скачать плейлист</a>
                    <a href="/force-update" class="btn btn-blue">🔄 Обновить</a>
                    <a href="/status" class="btn btn-gray">📊 Статистика</a>
                </div>
                
                <div class="stats">
                    <div class="stat"><b>{alive}</b><span>Живых каналов</span></div>
                    <div class="stat"><b>{stats.get('total', 0)}</b><span>Всего в БД</span></div>
                    <div class="stat"><b>{stats.get('dead', 0)}</b><span>Мертвых</span></div>
                    <div class="stat"><b>{'✅' if brain.trained else '❌'}</b><span>ML обучен</span></div>
                </div>
                
                <div class="info">
                    <div>🗑️ Автоудаление через {DEATH_THRESHOLD_DAYS} дней</div>
                    <div>⏱️ Обновление каждые {UPDATE_EVERY//3600} часов</div>
                </div>
            </div>
        </body>
        </html>
        """

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl',
                   headers={'Content-Disposition': 'attachment; filename="iptv_russia_ai.m3u"'})

@app.route('/status')
def status():
    stats = db.get_stats()
    alive = len([l for l in playlist_cache.split('\n') if l.startswith('http')])
    return jsonify({
        'alive_channels': alive,
        'db': stats,
        'ml_trained': brain.trained,
        'is_updating': is_updating,
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/force-update')
def force_update():
    if is_updating:
        return jsonify({'status': 'already_updating'})
    threading.Thread(target=update_with_ai, daemon=True).start()
    return jsonify({'status': 'refresh_started'})

@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'alive': len([l for l in playlist_cache.split('\n') if l.startswith('http')])})

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"🚀 Запуск на порту {port}")
    logger.info(f"🧠 Модель: {'загружена' if brain.trained else 'не обучена'}")
    
    # Запускаем фоновые задачи
    threading.Thread(target=background_worker, daemon=True).start()
    
    # Запускаем сервер
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=8)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)