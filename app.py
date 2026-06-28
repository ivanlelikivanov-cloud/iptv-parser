from flask import Flask, Response
import requests
import threading
import time

app = Flask(__name__)

# Самые мощные репозитории, которые обновляются роботами ежедневно
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/countries/ru_general.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/world.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/channels.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u"
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}

# Глобальный кэш
playlist_cache = "#EXTM3U\n"

def fetch_data():
    global playlist_cache
    while True:
        try:
            seen = {}
            for url in SOURCES:
                try:
                    r = requests.get(url, timeout=15, headers=HEADERS)
                    if r.status_code == 200:
                        lines = r.text.splitlines()
                        inf = ""
                        for l in lines:
                            l = l.strip()
                            if l.startswith("#EXTINF:"): inf = l
                            elif l.startswith("http"):
                                if l not in seen: seen[l] = inf
                except: continue
            
            # Собираем чисто
            lines = ["#EXTM3U"]
            for url, inf in seen.items():
                lines.append(inf)
                lines.append(url)
            playlist_cache = "\n".join(lines)
        except: pass
        time.sleep(1800) # Обновление каждые 30 минут

threading.Thread(target=fetch_data, daemon=True).start()

@app.route('/')
@app.route('/playlist.m3u')
def get_playlist():
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
