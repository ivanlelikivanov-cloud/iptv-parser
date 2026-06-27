from flask import Flask, Response
import requests

app = Flask(__name__)

SOURCES = [
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://smarttvnews.ru/apps/iptvchannels.m3u",
    "https://denmsu.github.io/tv/tv.m3u"
]

# Маскируемся под обычный браузер
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

@app.route('/')
def home():
    return "Сервер IPTV работает! Твоя ссылка на плейлист: /playlist.m3u"

@app.route('/playlist.m3u')
def get_playlist():
    merged_content = ["#EXTM3U\n"]
    seen_urls = set()
    
    for source in SOURCES:
        try:
            # Добавили заголовки (headers) и увеличили таймаут
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
                # Некоторые трансляции могут начинаться с rtmp, добавим и их
                elif line.startswith("http") or line.startswith("rtmp"): 
                    if line not in seen_urls:
                        seen_urls.add(line)
                        merged_content.append(current_extinf)
                        merged_content.append(line + "\n")
        except Exception as e:
            # В логах Render теперь будет видно, если источник отвалился
            print(f"Ошибка источника {source}: {e}", flush=True)
            
    return Response("".join(merged_content), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
