from flask import Flask, Response
import requests

app = Flask(__name__)

# Расширенный список источников
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/countries/ru_general.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_general.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/channels.m3u",
    "https://smarttvnews.ru/apps/iptvchannels.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://raw.githubusercontent.com/sknk/iptv/master/kvas.m3u"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

@app.route('/')
def home():
    return "IPTV Server Online. Playlist: /playlist.m3u"

@app.route('/playlist.m3u')
def get_playlist():
    merged_content = ["#EXTM3U\n"]
    seen_urls = set()
    
    for source in SOURCES:
        try:
            response = requests.get(source, timeout=10, headers=HEADERS)
            response.raise_for_status()
            
            lines = response.text.splitlines()
            current_extinf = ""
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#EXTM3U"):
                    continue
                
                if line.startswith("#EXTINF:"):
                    current_extinf = line + "\n"
                elif line.startswith("http") or line.startswith("rtmp"): 
                    if line not in seen_urls:
                        seen_urls.add(line)
                        merged_content.append(current_extinf)
                        merged_content.append(line + "\n")
        except Exception:
            continue # Молча пропускаем битые ссылки, чтобы не засирать логи
            
    return Response("".join(merged_content), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
