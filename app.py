from flask import Flask, Response
import requests

app = Flask(__name__)

# Максимально полный список источников для поиска каналов
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/countries/ru_general.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_general.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/channels.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/world.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://smarttvnews.ru/apps/iptvchannels.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/alexeyvaneev/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/yungwizz/iptv/main/ru.m3u",
    "https://raw.githubusercontent.com/mitrad/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/bes-b11/iptv/master/ru.m3u"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36'
}

@app.route('/playlist.m3u')
def get_playlist():
    # Используем словарь для автоматического исключения дублей
    final_list = {}
    
    for source in SOURCES:
        try:
            response = requests.get(source, timeout=10, headers=HEADERS)
            if response.status_code != 200:
                continue
                
            lines = response.text.splitlines()
            current_extinf = ""
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#EXTM3U"):
                    continue
                
                if line.startswith("#EXTINF:"):
                    current_extinf = line
                elif line.startswith("http"):
                    # Если ссылка новая, добавляем её
                    if line not in final_list:
                        final_list[line] = current_extinf
        except:
            continue
            
    # Собираем финальный текст плейлиста
    output = ["#EXTM3U\n"]
    for url, extinf in final_list.items():
        output.append(f"{extinf}\n{url}\n")
            
    return Response("".join(output), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
