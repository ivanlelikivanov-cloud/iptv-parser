from flask import Flask, Response
import requests

app = Flask(__name__)

# Наши доноры
SOURCES = [
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u",
    "https://smarttvnews.ru/apps/iptvchannels.m3u",
    "https://denmsu.github.io/tv/tv.m3u"
]

@app.route('/')
def home():
    return "Сервер IPTV работает! Твоя ссылка на плейлист: /playlist.m3u"

@app.route('/playlist.m3u')
def get_playlist():
    merged_content = ["#EXTM3U\n"]
    seen_urls = set()
    
    for source in SOURCES:
        try:
            response = requests.get(source, timeout=10)
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
                elif line.startswith("http"):
                    # Фильтруем дубликаты ссылок
                    if line not in seen_urls:
                        seen_urls.add(line)
                        merged_content.append(current_extinf)
                        merged_content.append(line + "\n")
        except Exception as e:
            print(f"Ошибка источника {source}: {e}")
            
    # Отдаем собранный текст с правильным заголовком, чтобы плееры поняли, что это плейлист
    return Response("".join(merged_content), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    # Порт 10000 часто используется по умолчанию на облачных платформах
    app.run(host='0.0.0.0', port=10000)