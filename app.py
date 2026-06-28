from flask import Flask, Response
import requests
import threading
import time

app = Flask(__name__)

SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/countries/ru_general.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/world.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://smarttvnews.ru/apps/iptvchannels.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u"
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'}

# Переменная для хранения готового списка
cached_playlist = "#EXTM3U\n"

def update_playlist():
    global cached_playlist
    while True:
        final_list = {}
        for source in SOURCES:
            try:
                r = requests.get(source, timeout=10, headers=HEADERS)
                if r.status_code == 200:
                    lines = r.text.splitlines()
                    current_extinf = ""
                    for line in lines:
                        line = line.strip()
                        if line.startswith("#EXTINF:"): current_extinf = line
                        elif line.startswith("http"):
                            if line not in final_list: final_list[line] = current_extinf
            except: continue
        
        output = ["#EXTM3U\n"]
        for url, extinf in final_list.items():
            output.append(f"{extinf}\n{url}\n")
        cached_playlist = "".join(output)
        time.sleep(7200) # Обновление каждые 2 часа

# Запуск фонового потока
threading.Thread(target=update_playlist, daemon=True).start()

@app.route('/playlist.m3u')
def get_playlist():
    return Response(cached_playlist, mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
