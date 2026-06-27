from flask import Flask, Response
import requests

app = Flask(__name__)

# Максимально стабильные источники на сегодня
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/countries/ru_general.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u"
]

# Маскировка под обычный браузер
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

@app.route('/')
def home():
    return "Сервер IPTV работает! Ссылка на плейлист: /playlist.m3u"

@app.route('/playlist.m3u')
def get_playlist():
    merged_content = ["#EXTM3U\n"]
    seen_urls = set()
    
    for source in SOURCES:
        try:
            response = requests.get(source, timeout=15, headers=HEADERS)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            lines = response.text.splitlines()
            current_extinf = ""
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                if line.startswith("#EXTINF:"):
                    current_extinf = line + "\n"
                elif line.startswith("http") or line.startswith("rtmp"): 
                    if line not in seen_urls:
                        seen_urls.add(line)
                        merged_content.append(current_extinf)
                        merged_content.append(line + "\n")
        except Exception as e:
            print(f"Ошибка источника {source}: {e}", flush=True)
            
    return Response("".join(merged_content), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
