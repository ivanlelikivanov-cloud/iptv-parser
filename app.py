import os
import re
import time
import logging
import threading
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from flask import Flask, Response, jsonify, request, render_template_string
import requests
import psutil
from urllib.parse import urlparse, quote

# ==================== КОНФИГУРАЦИЯ ====================
SOURCES = [
    # Основные IPTV-ORG
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-northwest.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-volga.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    
    # Community источники
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/sat-iptv/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/playlist-for-free/IPTV/main/ru.m3u",
    
    # Дополнительные
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://iptv-org.github.io/iptv/countries/by.m3u",
    "https://iptv-org.github.io/iptv/countries/kz.m3u",
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
CHECK_TIMEOUT = 3
MAX_WORKERS = 50
ALIVE_LIMIT = 500
UPDATE_INTERVAL = 1800  # 30 минут

# ==================== ЛОГИРОВАНИЕ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('iptv.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ====================
app = Flask(__name__)
state_lock = threading.Lock()
global_channels = []
stats_cache = {
    "total": 0, 
    "alive": 0, 
    "categories": 0, 
    "last_update": "", 
    "memory": 0,
    "sources": len(SOURCES)
}

# ==================== ПАРСИНГ M3U ====================
def parse_m3u(content):
    """Парсинг M3U плейлиста"""
    channels = []
    current = None
    
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('#EXTINF:'):
            # Парсинг EXTINF
            match = re.search(r'#EXTINF:(?P<dur>-?\d+)(?P<attr>.*),(?P<name>.*)', line)
            if match:
                attrs_str = match.group('attr')
                # Извлечение атрибутов в кавычках
                attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', attrs_str))
                # Извлечение атрибутов без кавычек (key=value)
                attrs.update(dict(re.findall(r'([a-zA-Z0-9-]+)=(\S+)', attrs_str)))
                
                current = {
                    'name': match.group('name').strip(),
                    'attrs': attrs,
                    'url': None,
                    'is_alive': False,
                    'latency_ms': None,
                    'last_checked': None
                }
                
        elif current and line.startswith('http'):
            current['url'] = line.split()[0]  # Берем только URL без пробелов
            channels.append(current)
            current = None
            
    return channels

# ==================== АСИНХРОННАЯ ПРОВЕРКА ====================
async def check_channel_async(session, channel):
    """Асинхронная проверка одного канала"""
    url = channel.get('url')
    if not url:
        return None
        
    try:
        start = time.time()
        async with session.head(url, timeout=aiohttp.ClientTimeout(total=CHECK_TIMEOUT),
                               allow_redirects=True, headers=HEADERS) as resp:
            latency = (time.time() - start) * 1000
            
            if resp.status < 400:
                channel['is_alive'] = True
                channel['latency_ms'] = round(latency, 1)
                channel['status_code'] = resp.status
                channel['last_checked'] = datetime.now().isoformat()
                return channel
    except asyncio.TimeoutError:
        pass
    except Exception as e:
        logger.debug(f"Error checking {url[:60]}: {e}")
    
    channel['is_alive'] = False
    channel['last_checked'] = datetime.now().isoformat()
    return None

async def check_channels_batch(channels):
    """Массовая асинхронная проверка каналов"""
    alive_channels = []
    semaphore = asyncio.Semaphore(MAX_WORKERS)
    
    async def bounded_check(ch):
        async with semaphore:
            async with aiohttp.ClientSession() as session:
                return await check_channel_async(session, ch)
    
    tasks = [bounded_check(ch) for ch in channels]
    
    for coro in asyncio.as_completed(tasks):
        try:
            result = await coro
            if result and result.get('is_alive'):
                alive_channels.append(result)
        except:
            pass
    
    return alive_channels

# ==================== ОБНОВЛЕНИЕ ПЛЕЙЛИСТА ====================
def update_playlist():
    """Фоновая задача обновления плейлиста"""
    global global_channels, stats_cache
    
    while True:
        start_time = time.time()
        logger.info(f"🔄 Начало обновления плейлиста ({len(SOURCES)} источников)...")
        
        all_channels = []
        
        # Загрузка всех источников
        for url in SOURCES:
            try:
                logger.debug(f"Загрузка: {url[:60]}...")
                response = requests.get(url, timeout=20, headers=HEADERS)
                if response.status_code == 200:
                    channels = parse_m3u(response.text)
                    all_channels.extend(channels)
                    logger.debug(f"  +{len(channels)} каналов")
            except Exception as e:
                logger.error(f"❌ Ошибка загрузки {url[:50]}: {e}")
                continue
        
        logger.info(f"📊 Всего загружено: {len(all_channels)} каналов")
        
        # Дедупликация
        seen = {}
        for ch in all_channels:
            # Ключ для уникальности: tvg-id > tvg-name > URL
            key = (ch['attrs'].get('tvg-id') or 
                   ch['attrs'].get('tvg-name') or 
                   ch['url'] or 
                   ch['name'])
            
            if key not in seen:
                seen[key] = ch
            else:
                # Предпочитаем канал с логотипом
                if not seen[key].get('attrs', {}).get('tvg-logo') and ch.get('attrs', {}).get('tvg-logo'):
                    seen[key] = ch
        
        unique_channels = list(seen.values())
        logger.info(f"✅ Уникальных каналов: {len(unique_channels)}")
        
        # Проверка живости (берем первые 1000 для скорости)
        check_sample = unique_channels[:1000] if len(unique_channels) > 1000 else unique_channels
        logger.info(f"🔍 Проверка живости {len(check_sample)} каналов...")
        
        # Запуск асинхронной проверки
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            alive_channels = loop.run_until_complete(check_channels_batch(check_sample))
        finally:
            loop.close()
        
        logger.info(f"🟢 Найдено живых: {len(alive_channels)}")
        
        # Приоритизация: живые + быстрые + с логотипами
        def channel_score(ch):
            score = 0
            if ch.get('is_alive'):
                score += 1000
                latency = ch.get('latency_ms', 9999)
                if latency < 200:
                    score += 500
                elif latency < 500:
                    score += 200
                elif latency < 1000:
                    score += 100
            if ch.get('attrs', {}).get('tvg-logo'):
                score += 50
            if ch.get('attrs', {}).get('group-title'):
                score += 30
            if 'hd' in ch.get('name', '').lower() or 'hd' in str(ch.get('attrs', {}).get('group-title', '')).lower():
                score += 20
            if '4k' in ch.get('name', '').lower() or 'uhd' in ch.get('name', '').lower():
                score += 40
            return score
        
        # Сортировка и ограничение
        sorted_channels = sorted(unique_channels, key=channel_score, reverse=True)
        
        # Берем все живые + топ мертвых до 3000
        alive_sorted = [ch for ch in sorted_channels if ch.get('is_alive')][:ALIVE_LIMIT]
        others_sorted = [ch for ch in sorted_channels if not ch.get('is_alive')][:2000]
        final_channels = alive_sorted + others_sorted
        
        # Подсчет категорий
        categories = set()
        for ch in final_channels:
            group = ch.get('attrs', {}).get('group-title')
            if group:
                categories.add(group)
        
        # Обновление глобального состояния
        with state_lock:
            global_channels = final_channels
            stats_cache = {
                "total": len(unique_channels),
                "alive": len(alive_channels),
                "categories": len(categories),
                "last_update": datetime.now().strftime("%H:%M:%S"),
                "memory": round(psutil.Process(os.getpid()).memory_info().rss / 1024**2, 1),
                "sources": len(SOURCES),
                "update_duration": round(time.time() - start_time, 1)
            }
        
        logger.info(f"✨ Обновление завершено за {stats_cache['update_duration']}с | "
                   f"Каналов: {stats_cache['total']} | Живых: {stats_cache['alive']} | "
                   f"RAM: {stats_cache['memory']} MB")
        
        time.sleep(UPDATE_INTERVAL)

# Запуск фонового обновления
update_thread = threading.Thread(target=update_playlist, daemon=True)
update_thread.start()

# ==================== HTML ШАБЛОН ====================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>📺 IPTV Aggregator Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        :root { --bg: #0d1117; --card: #161b22; --text: #c9d1d9; --accent: #58a6ff; --success: #2ea043; --danger: #da3633; }
        body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
        .card { background: var(--card); border: 1px solid #30363d; }
        .stat-card { text-align: center; padding: 2rem; border-radius: 12px; transition: transform 0.2s; }
        .stat-card:hover { transform: translateY(-5px); }
        .stat-number { font-size: 3rem; font-weight: bold; color: var(--accent); }
        .channel-list { max-height: 70vh; overflow-y: auto; }
        .channel-item { padding: 1rem; border-bottom: 1px solid #30363d; cursor: pointer; transition: all 0.2s; }
        .channel-item:hover { background: #21262d; }
        .channel-item.alive { border-left: 4px solid var(--success); }
        .channel-item.dead { border-left: 4px solid var(--danger); opacity: 0.7; }
        .badge-4k { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
        .badge-hd { background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); }
        .search-box { position: sticky; top: 0; z-index: 100; background: var(--bg); padding: 1rem 0; border-bottom: 1px solid #30363d; }
        .loading { display: none; text-align: center; padding: 3rem; }
        .loading.active { display: block; }
        .btn-custom { border-radius: 8px; padding: 0.5rem 1.5rem; font-weight: 600; }
        .logo-img { width: 60px; height: 34px; object-fit: contain; background: #21262d; border-radius: 4px; }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark border-bottom border-secondary">
        <div class="container">
            <a class="navbar-brand" href="#"><i class="bi bi-tv"></i> IPTV Pro <span class="badge bg-success">v2.0</span></a>
            <div class="navbar-nav ms-auto">
                <a class="nav-link" href="/playlist.m3u"><i class="bi bi-download"></i> M3U</a>
                <a class="nav-link" href="/playlist.json"><i class="bi bi-file-earmark-json"></i> JSON</a>
                <a class="nav-link" href="#" onclick="refreshPlaylist()"><i class="bi bi-arrow-clockwise"></i> Обновить</a>
            </div>
        </div>
    </nav>

    <div class="container py-4">
        <!-- Stats -->
        <div class="row g-3 mb-4">
            <div class="col-md-2 col-6">
                <div class="card stat-card">
                    <div class="stat-number" id="totalChannels">0</div>
                    <div>Всего</div>
                </div>
            </div>
            <div class="col-md-2 col-6">
                <div class="card stat-card">
                    <div class="stat-number text-success" id="aliveChannels">0</div>
                    <div>Рабочих</div>
                </div>
            </div>
            <div class="col-md-2 col-6">
                <div class="card stat-card">
                    <div class="stat-number text-warning" id="categoriesCount">0</div>
                    <div>Категорий</div>
                </div>
            </div>
            <div class="col-md-2 col-6">
                <div class="card stat-card">
                    <div class="stat-number text-info" id="sourcesCount">0</div>
                    <div>Источников</div>
                </div>
            </div>
            <div class="col-md-2 col-6">
                <div class="card stat-card">
                    <div class="stat-number text-primary" id="memoryUsage">0</div>
                    <div>RAM MB</div>
                </div>
            </div>
            <div class="col-md-2 col-6">
                <div class="card stat-card">
                    <div class="stat-number text-light" id="lastUpdateTime">--:--</div>
                    <div>Обновлено</div>
                </div>
            </div>
        </div>

        <!-- Search & Filters -->
        <div class="card mb-4 search-box">
            <div class="card-body">
                <div class="row g-2">
                    <div class="col-md-6">
                        <input type="text" id="searchInput" class="form-control bg-dark text-light border-secondary" 
                               placeholder="🔍 Поиск канала..." oninput="filterChannels()">
                    </div>
                    <div class="col-md-3">
                        <select id="categoryFilter" class="form-select bg-dark text-light border-secondary" onchange="filterChannels()">
                            <option value="">Все категории</option>
                        </select>
                    </div>
                    <div class="col-md-3">
                        <select id="qualityFilter" class="form-select bg-dark text-light border-secondary" onchange="filterChannels()">
                            <option value="">Любое качество</option>
                            <option value="4k">4K</option>
                            <option value="hd">HD</option>
                            <option value="sd">SD</option>
                        </select>
                    </div>
                </div>
                <div class="mt-2">
                    <button class="btn btn-outline-success btn-sm btn-custom" onclick="toggleAliveOnly()">
                        <i class="bi bi-toggle-on" id="aliveToggle"></i> Только рабочие
                    </button>
                    <button class="btn btn-outline-primary btn-sm btn-custom" onclick="refreshPlaylist()">
                        <i class="bi bi-arrow-clockwise"></i> Обновить сейчас
                    </button>
                    <span class="text-muted ms-2" id="visibleCount">0 каналов</span>
                </div>
            </div>
        </div>

        <!-- Loading -->
        <div class="loading" id="loading">
            <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;"></div>
            <p class="mt-3">Загрузка каналов...</p>
        </div>

        <!-- Channel List -->
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <span><i class="bi bi-list-ul"></i> Список каналов</span>
                <span class="badge bg-secondary" id="channelCount">0</span>
            </div>
            <div class="channel-list" id="channelList"></div>
        </div>
    </div>

    <script>
        let allChannels = [], filteredChannels = [], aliveOnly = false;
        
        async function loadStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                document.getElementById('totalChannels').textContent = data.total;
                document.getElementById('aliveChannels').textContent = data.alive;
                document.getElementById('categoriesCount').textContent = data.categories;
                document.getElementById('sourcesCount').textContent = data.sources;
                document.getElementById('memoryUsage').textContent = data.memory;
                document.getElementById('lastUpdateTime').textContent = data.last_update;
            } catch(e) { console.error('Stats error:', e); }
        }
        
        async function loadChannels() {
            document.getElementById('loading').classList.add('active');
            try {
                const res = await fetch('/api/channels');
                allChannels = await res.json();
                
                // Populate categories
                const categories = [...new Set(allChannels.map(ch => ch.attrs?.['group-title'] || 'Другое').filter(Boolean))].sort();
                const catSelect = document.getElementById('categoryFilter');
                catSelect.innerHTML = '<option value="">Все категории</option>';
                categories.forEach(cat => {
                    const opt = document.createElement('option');
                    opt.value = cat.toLowerCase();
                    opt.textContent = cat;
                    catSelect.appendChild(opt);
                });
                
                filterChannels();
            } catch(e) { console.error('Load error:', e); }
            finally { document.getElementById('loading').classList.remove('active'); }
        }
        
        function filterChannels() {
            const search = document.getElementById('searchInput').value.toLowerCase();
            const category = document.getElementById('categoryFilter').value;
            const quality = document.getElementById('qualityFilter').value;
            
            filteredChannels = allChannels.filter(ch => {
                const name = (ch.name + ' ' + (ch.attrs?.['tvg-name'] || '')).toLowerCase();
                const group = (ch.attrs?.['group-title'] || '').toLowerCase();
                const isHD = name.includes('hd') || group.includes('hd');
                const is4K = name.includes('4k') || name.includes('uhd');
                
                if (search && !name.includes(search)) return false;
                if (category && !group.includes(category)) return false;
                if (quality === '4k' && !is4K) return false;
                if (quality === 'hd' && !isHD && !is4K) return false;
                if (quality === 'sd' && (isHD || is4K)) return false;
                if (aliveOnly && !ch.is_alive) return false;
                return true;
            });
            
            renderChannels(filteredChannels);
            document.getElementById('visibleCount').textContent = `${filteredChannels.length} каналов`;
            document.getElementById('channelCount').textContent = filteredChannels.length;
        }
        
        function toggleAliveOnly() {
            aliveOnly = !aliveOnly;
            document.getElementById('aliveToggle').className = aliveOnly ? 'bi bi-toggle-on' : 'bi bi-toggle-off';
            filterChannels();
        }
        
        function renderChannels(channels) {
            const list = document.getElementById('channelList');
            if (channels.length === 0) {
                list.innerHTML = '<div class="text-center p-4 text-muted">Каналы не найдены</div>';
                return;
            }
            
            list.innerHTML = channels.slice(0, 500).map(ch => {
                const logo = ch.attrs?.['tvg-logo'] || 'https://via.placeholder.com/60x34/21262d/764ba2?text=TV';
                const group = ch.attrs?.['group-title'] || 'Другое';
                const latency = ch.latency_ms ? `<span class="badge bg-secondary ms-2">${ch.latency_ms}ms</span>` : '';
                const quality = ch.name.toLowerCase().includes('4k') || ch.name.toLowerCase().includes('uhd') ? 
                               '<span class="badge badge-4k ms-1">4K</span>' : 
                               (ch.name.toLowerCase().includes('hd') ? '<span class="badge badge-hd ms-1">HD</span>' : '');
                
                return `<div class="channel-item ${ch.is_alive ? 'alive' : 'dead'}" onclick="copyUrl('${ch.url}')">
                    <div class="d-flex align-items-center">
                        <img src="${logo}" class="logo-img me-3" onerror="this.src='https://via.placeholder.com/60x34/21262d/764ba2?text=TV'">
                        <div class="flex-grow-1">
                            <strong>${ch.name}</strong>
                            <small class="text-muted d-block">${group}${quality}${latency}</small>
                        </div>
                        <i class="bi ${ch.is_alive ? 'bi-check-circle-fill text-success fs-4' : 'bi-x-circle-fill text-danger fs-4'}"></i>
                    </div>
                </div>`;
            }).join('');
        }
        
        function copyUrl(url) {
            navigator.clipboard.writeText(url);
            const toast = document.createElement('div');
            toast.className = 'position-fixed bottom-0 end-0 m-3 alert alert-success';
            toast.textContent = '✅ URL скопирован в буфер обмена!';
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 2000);
        }
        
        function refreshPlaylist() {
            fetch('/api/refresh', {method: 'POST'});
            setTimeout(() => {
                loadStats();
                loadChannels();
            }, 2000);
        }
        
        // Auto-refresh stats every 30s
        setInterval(loadStats, 30000);
        
        // Init
        loadStats();
        loadChannels();
    </script>
</body>
</html>
"""

# ==================== API ЭНДПОИНТЫ ====================
@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/stats')
def api_stats():
    with state_lock:
        return jsonify(stats_cache)

@app.route('/api/channels')
def api_channels():
    with state_lock:
        return jsonify(global_channels)

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """Принудительное обновление"""
    global update_thread
    update_thread = threading.Thread(target=update_playlist, daemon=True)
    update_thread.start()
    return jsonify({'status': 'refreshing', 'message': 'Обновление запущено'})

@app.route('/playlist.m3u')
def playlist_m3u():
    """Генерация M3U плейлиста"""
    region = request.args.get('region', '').lower()
    search = request.args.get('search', '').lower()
    category = request.args.get('category', '').lower()
    alive_only = request.args.get('alive', 'false').lower() == 'true'
    
    with state_lock:
        channels = global_channels.copy()
    
    # Фильтрация
    filtered = []
    for ch in channels:
        name = (ch.get('name') + ' ' + ch.get('attrs', {}).get('tvg-name', '')).lower()
        group = ch.get('attrs', {}).get('group-title', '').lower()
        
        if search and search not in name:
            continue
        if region and region not in group and region not in name:
            continue
        if category and category not in group:
            continue
        if alive_only and not ch.get('is_alive'):
            continue
            
        filtered.append(ch)
    
    # Генерация M3U
    lines = ['#EXTM3U', f'# IPTV Pro Playlist', f'# Updated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 
             f'# Total: {len(filtered)} channels']
    
    for ch in filtered:
        attrs = ch.get('attrs', {})
        attr_str = ' '.join([f'{k}="{v}"' for k, v in attrs.items() if v])
        lines.append(f"#EXTINF:-1 {attr_str},{ch['name']}")
        lines.append(ch['url'])
    
    return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl',
                   headers={'Content-Disposition': 'attachment; filename=iptv_pro.m3u'})

@app.route('/playlist.json')
def playlist_json():
    """Генерация JSON плейлиста"""
    with state_lock:
        return jsonify(global_channels)

@app.route('/health')
def health():
    """Health check"""
    with state_lock:
        is_fresh = stats_cache.get('last_update') and stats_cache['total'] > 0
    return jsonify({
        'status': 'healthy' if is_fresh else 'initializing',
        'channels': stats_cache.get('total', 0),
        'alive': stats_cache.get('alive', 0),
        'timestamp': datetime.now().isoformat()
    }), 200 if is_fresh else 503

# ==================== ЗАПУСК ====================
if __name__ == '__main__':
    logger.info("🚀 IPTV Aggregator Pro запускается...")
    logger.info(f"📡 Источников: {len(SOURCES)}")
    logger.info(f"⚙️ Порт: 10000")
    logger.info(f"🔄 Интервал обновления: {UPDATE_INTERVAL}s")
    
    # Ждем немного перед стартом сервера
    time.sleep(2)
    
    app.run(host='0.0.0.0', port=10000, debug=False, threaded=True)
