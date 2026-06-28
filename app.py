from flask import Flask, Response
import requests
import threading
import time

app = Flask(__name__)

SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/world.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://smarttvnews.ru/apps/iptvchannels.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u"
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}

cache = "#EXTM3U\n"

def refresh_loop():
    global cache
    while True:
        temp_list = {}
        for url in SOURCES:
            try:
                r = requests.get(url, timeout=10, headers=HEADERS)
                if r.status_code == 200:
                    lines = r.text.splitlines()
                    info = ""
                    for line in lines:
                        if line.startswith("#EXTINF:"): info = line
                        elif line.startswith("http"):
                            if line not in temp_list: temp_list[line] = info
            except: continue
        
        out = ["#EXTM3U\n"]
        for u, i in temp_list.items():
            out.append(f"{i}\n{u}\n")
        cache = "".join(out)
        time.sleep(3600) # Обновление раз в час

threading.Thread(target=refresh_loop, daemon=True).start()

@app.route('/')
def root(): return Response(cache, mimetype='application/vnd.apple.mpegurl')

@app.route('/playlist.m3u')
def playlist(): return Response(cache, mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
