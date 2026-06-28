from flask import Flask, Response
import requests

app = Flask(__name__)

# Полный список, включая m3u.su и все проверенные доноры
SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/countries/ru_general.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/world.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://smarttvnews.ru/apps/iptvchannels.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
}

@app.route('/playlist.m3u')
def get_playlist():
    merged_content = ["#EXTM3U\n"]
    seen_urls = set()
    
    for source in SOURCES:
        try:
            # Установили жесткий таймаут, чтобы не ждать вечно
            response = requests.get(source, timeout=8, headers=HEADERS)
            if response.status_code != 200:
                continue
                
            lines = response.text.splitlines()
            current_extinf = ""
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#EXTM3U"):
                    continue
                
                if line.startswith("#EXTINF:"):
                    current_extinf = line + "\n"
                elif line.startswith("http"): 
                    if line not in seen_urls:
                        seen_urls.add(line)
                        merged_content.append(current_extinf)
                        merged_content.append(line + "\n")
        except:
            continue
            
    return Response("".join(merged_content), mimetype='application/vnd.apple.mpegurl')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
