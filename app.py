import os
import re
import time
import logging
import threading
import requests
from flask import Flask, Response, jsonify

app = Flask(__name__)

# ==================== КАЧЕСТВЕННЫЕ ИСТОЧНИКИ ====================
SOURCES = [
    # IPTV-ORG — лучший проект
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-far-east.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-volga.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-south.m3u",

    # Free-TV + GitHub
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/sat-iptv/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/playlist-for-free/IPTV/main/ru.m3u",

    # M3U.SU + другие
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru_hd.m3u",
    "https://m3u.su/m3u/ru_4k.m3u",
    "https://m3u.su/m3u/ru_sport.m3u",
    "https://m3u.su/m3u/ru_kino.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
]

EPG_URL = "https://iptv-org.github.io/epg/guides/ru/index.xml"

playlist_cache = "#EXTM3U\n"
cache_lock = threading.Lock()
stats = {"total": 0, "sources_ok": 0, "epg": EPG_URL}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def is_russian_channel(name, attrs, url):
    name_lower = name.lower()
    lang = attrs.get('tvg-language', '').lower()
    if lang in ['rus', 'ru', 'russian']:
        return True
    if re.search(r'[\u0400-\u04FF]', name):
        return True
    return False

def get_category(name):
    n = name.lower()
    if any(k in n for k in ['новости', 'news', '24', 'vesti']):
        return 'Новости'
    elif any(k in n for k in ['кино', 'movie', 'film', 'сериал']):
        return 'Кино'
    elif any(k in n for k in ['музыка', 'music', 'хит', 'radio']):
        return 'Музыка'
    elif any(k in n for k in ['спорт', 'sport', 'футбол']):
        return 'Спорт'
    elif any(k in n for k in ['дет', 'kids', 'мульт']):
        return 'Детские'
    return 'Общие'

def update_cache():
    global playlist_cache, stats
    logger.info("🔄 Сборка плейлиста...")
   
    lines = [
        "#EXTM3U",
        f"# 🇷🇺 IPTV Russia Pro — {time.strftime('%Y-%m-%d %H:%M')}",
        f"# EPG: {EPG_URL}",
        "# Часовые пояса настраиваются в плеере"
    ]
    seen_urls = set()
    seen_keys = set()
    count = 0
    ok_sources = 0

    for url in SOURCES:
        try:
            r = requests.get(url, timeout=12, headers={'User-Agent': 'Mozilla/5.0'})
            if r.ok:
                ok_sources += 1
                current_inf = None
                current_attrs = {}
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        match = re.search(r'#EXTINF:-?\d+\s*(.*),(.+)', line)
                        if match:
                            attrs = dict(re.findall(r'([a-zA-Z0-9-]+)="([^"]*)"', match.group(1)))
                            name = match.group(2).strip()
                            if is_russian_channel(name, attrs, url):
                                if 'group-title' not in attrs:
                                    attrs['group-title'] = get_category(name)
                                current_attrs = attrs
                                current_inf = f"#EXTINF:-1 {' '.join(f'{k}=\"{v}\"' for k,v in attrs.items())},{name}"
                    elif current_inf and line.startswith('http'):
                        ch_url = line.split()[0]
                        key = current_attrs.get('tvg-id') or current_attrs.get('tvg-name') or ch_url
                        if ch_url not in seen_urls and key not in seen_keys:
                            seen_urls.add(ch_url)
                            seen_keys.add(key)
                            lines.append(current_inf)
                            lines.append(ch_url)
                            count += 1
                        current_inf = None
        except Exception as e:
            logger.debug(f"❌ {url[:40]}: {e}")

    with cache_lock:
        playlist_cache = "\n".join(lines)
        stats = {"total": count, "sources_ok": ok_sources, "epg": EPG_URL}

    logger.info(f"✅ {count} RU каналов из {ok_sources} источников")


def background_update():
    while True:
        update_cache()
        time.sleep(1800)


threading.Thread(target=background_update, daemon=True).start()
time.sleep(15)


@app.route('/')
def home():
    with cache_lock:
        s = stats.copy()
    return f"""
    <h1>🇷🇺 IPTV Russia Pro</h1>
    <p>Каналов: <b>{s['total']}</b></p>
    <p>Источников: <b>{s['sources_ok']}</b></p>
    <p>EPG: <a href="{s['epg']}">Скачать</a></p>
    <p><a href="/playlist.m3u">📥 Скачать M3U</a></p>
    """


@app.route('/playlist.m3u')
def playlist():
    with cache_lock:
        return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')


if __name__ == '__main__':
    logger.info(f"🚀 Запуск... {len(SOURCES)} источников")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
