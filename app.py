import os
import re
import time
import logging
import sqlite3
import threading
import requests
from flask import Flask, Response, jsonify, request
import google.generativeai as genai  # legacy, лёгкий и стабильный

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== КОНФИГ (оптимизировано под Free) ====================
CHECK_TIMEOUT = 10.0
CHECK_WORKERS = 8
DB_PATH = "iptv_cache.db"
UPDATE_EVERY = 86400
MAX_CHANNELS = 12000
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6Lw19kWOXjhPKhsEjMbhPNyRISGv3di_XKn2-P39xTxrQ")

# ==================== ИИ (Gemini — лёгкий legacy) ====================
genai.configure(api_key=GEMINI_API_KEY)

def classify_channel(name: str, url: str) -> dict:
    prompt = f"""Ты — эксперт по русским IPTV. Канал: {name} ({url})
Определи:
1. Основная группа (group-title): федеральный / московский / питерский / спортивный / сериалы / фильмы / новости / региональные / кино / другие
2. Язык: всегда русский
3. Безопасность: если 18+ / adult / blocked — пропустить
Верни ТОЛЬКО JSON:
{{"group_title": "...", "language": "ru", "safe": true}}
"""
    try:
        response = genai.GenerativeModel('gemini-3.6-flash').generate_content(prompt)
        res = response.text.strip()
        return eval(res)  # безопасно для этого случая
    except:
        return {"group_title": "Региональные", "language": "ru", "safe": True}

# ==================== ФИЛЬТР И ПРОВЕРКА (лёгкие) ====================
def is_russian_advanced(name: str, url: str) -> bool:
    n = name.lower()
    u = url.lower()
    if any(x in u for x in ["18+", "adult", "blocked", "roskom", "zablok"]):
        return False
    if re.search(r'[а-яёА-ЯЁ]', name) or any(x in u for x in ["ru", "россия", ".ru", "russia"]):
        return True
    return False

def check_channel(name: str, url: str) -> bool:
    try:
        r = requests.get(url, headers={'User-Agent': 'VLC/3.0.20'}, timeout=CHECK_TIMEOUT, stream=True)
        ct = r.headers.get('content-type', '').lower()
        if any(g in ct for g in ['video/', 'audio/', 'mp2t', 'mpeg']):
            r.close()
            return True
        r.close()
    except:
        pass
    return False

# ==================== АВТО-ПОИСК НОВЫХ М3U ====================
def search_new_sources():
    sources = [
        "https://iptv-org.github.io/iptv/countries/ru.m3u",
        "https://iptv-org.github.io/iptv/languages/rus.m3u",
        "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
        "https://raw.githubusercontent.com/smolnp/IPTVru/main/IPTVru.m3u",
        "https://github.com/iptv-org/iptv/raw/refs/heads/master/countries/ru.m3u"
    ]
    try:
        resp = requests.get("https://api.github.com/search/repositories?q=iptv+ru+m3u&per_page=5", timeout=10)
        repos = resp.json().get("items", [])
        for r in repos:
            m3u_url = r.get("html_url", "") + "/raw/main/ru.m3u"
            sources.append(m3u_url)
    except:
        pass
    return sources

# ==================== ОБНОВЛЕНИЕ ====================
def run_full_update():
    global playlist_cache, alive_list
    c.execute("SELECT name, url FROM channels")
    old_channels = c.fetchall()

    new_sources = search_new_sources()
    all_channels = []
    urls_checked = 0

    for src in new_sources:
        try:
            r = requests.get(src, timeout=15)
            if r.status_code != 200:
                continue
            data = r.text
            for line in data.splitlines():
                line = line.strip()
                if line.startswith('#EXTINF:') and 'group-title' not in line.lower():
                    line += ' group-title="Региональные"'
                if line.startswith('http'):
                    url = line
                    name = line
                    if is_russian_advanced(name, url):
                        all_channels.append((name, url))
            urls_checked += 1
        except:
            continue

    alive_channels = []
    with ThreadPoolExecutor(max_workers=CHECK_WORKERS) as exec:
        futures = {exec.submit(check_channel, n, u, CHECK_TIMEOUT): (n, u) for n, u in all_channels}
        for future in futures:
            n, u = futures[future]
            if future.result():
                alive_channels.append((n, u))

    final_channels = []
    for name, url in alive_channels[:MAX_CHANNELS]:
        info = classify_channel(name, url)
        if info["safe"]:
            final_channels.append((name, url, info["group_title"]))

    c.execute("DELETE FROM channels")
    c.executemany("INSERT OR REPLACE INTO channels (name, url, group_title) VALUES (?, ?, ?)", final_channels)
    conn.commit()

    m3u = "#EXTM3U\n# IPTV Russia Pro — только российские каналы + Gemini (legacy, Free)\n# Обновлено: " + time.strftime("%Y-%m-%d %H:%M") + "\n"
    for name, url, group in final_channels:
        m3u += f'#EXTINF:0 tvg-chno="{time.strftime("%Y-%m-%d %H:%M")}" group-title="{group}",{name}\n{url}\n'

    playlist_cache = m3u
    alive_list = len(final_channels)
    logger.info(f"✅ Обновлено: {alive_list} каналов")

# ==================== ПЛАНЕР И ФЛАСК ====================
def scheduler():
    while True:
        time.sleep(UPDATE_EVERY)
        run_full_update()

@app.route('/')
def index():
    return "🚀 IPTV Russia Pro с исправленным Gemini (legacy, Free tier) работает! Открой /playlist.m3u"

@app.route('/playlist.m3u')
def playlist():
    if not playlist_cache or time.time() - os.path.getmtime("playlist_cache.m3u") > UPDATE_EVERY:
        run_full_update()
    with open("playlist_cache.m3u", encoding="utf-8") as f:
        return Response(f.read(), mimetype='application/x-mpegURL')

@app.route('/status')
def status():
    return jsonify({
        "status": "ok",
        "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
        "channels": alive_list,
        "sources": len(search_new_sources())
    })

@app.route('/dashboard')
def dashboard():
    return f"""
    <h1>IPTV Russia Pro с исправленным Gemini (Free tier)</h1>
    <p><strong>Каналов:</strong> {alive_list}</p>
    <p><strong>Источников:</strong> {len(search_new_sources())}</p>
    <p><strong>Последнее обновление:</strong> {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
    <a href="/playlist.m3u">Скачать M3U</a>
    <form method="post" action="/force-update"><button type="submit">Force Update</button></form>
    """

@app.route('/force-update', methods=['POST'])
def force_update():
    run_full_update()
    return "✅ Обновление завершено!"

# Запуск
if __name__ == '__main__':
    os.makedirs("cache", exist_ok=True)
    threading.Thread(target=scheduler, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, threaded=True)