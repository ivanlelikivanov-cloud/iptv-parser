from flask import Flask, Response
import requests
import threading
import time

app = Flask(__name__)

SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
]

playlist_cache = "#EXTM3U\n# IPTV Russia - Loading...\n"

def update():
    global playlist_cache
    lines = ["#EXTM3U", "# IPTV Russia Pro"]
    seen = set()
    for url in SOURCES:
        try:
            r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                for line in r.text.splitlines():
                    line = line.strip()
                    if line.startswith('#EXTINF:'):
                        inf = line
                    elif line.startswith('http') and line not in seen:
                        seen.add(line)
                        lines.append(inf)
                        lines.append(line)
        except:
            pass
    playlist_cache = "\n".join(lines)
    print(f"✅ Загружено {len(seen)} каналов")

threading.Thread(target=update, daemon=True).start()
time.sleep(12)  # первая загрузка

@app.route('/playlist.m3u')
def playlist():
    return Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')

@app.route('/')
def home():
    return "<h1>IPTV Russia</h1><a href='/playlist.m3u'>Скачать плейлист</a>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
