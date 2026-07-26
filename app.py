import os
import re
import time
import json
import logging
import threading
import sqlite3
import hashlib
import random
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import urllib3
from flask import Flask, Response, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== КОНФИГУРАЦИЯ ====================
DB_PATH = os.environ.get('DB_PATH', 'iptv_cache.db')
MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '30'))
CHECK_TIMEOUT = float(os.environ.get('CHECK_TIMEOUT', '8.0'))
FULL_UPDATE_INTERVAL = int(os.environ.get('FULL_UPDATE_INTERVAL', '86400'))
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', '200'))
MAX_CHANNELS = int(os.environ.get('MAX_CHANNELS', '8000'))
TARGET_ALIVE = int(os.environ.get('TARGET_ALIVE', '3000'))

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
    'VLC/3.0.20 LibVLC/3.0.20',
    'Kodi/20.2 (Windows NT 10.0; Win64; x64) App_Bitness/64 Version/20.2',
    'Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 Chrome/126.0.0.0 Mobile Safari/537.36',
    'IPTV Smarters/1.0.0 (Linux; Android 12)',
]

HEADERS_WEB = {'User-Agent': USER_AGENTS[0]}
HEADERS_PLAYER = {
    'User-Agent': USER_AGENTS[1],
    'Connection': 'close',
    'Icy-MetaData': '1',
}

STATIC_SOURCES = [
    "https://iptv-org.github.io/iptv/countries/ru.m3u",
    "https://iptv-org.github.io/iptv/languages/rus.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-spb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ural.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sib.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-nw.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-vlg.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-cen.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sou.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kav.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-far.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-cr.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ba.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ta.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-da.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kb.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kc.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-se.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ud.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ki.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-me.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mo.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sa.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ka.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-le.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ore.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-pnz.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ros.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-rya.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sam.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sar.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-tve.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-tul.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-vla.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-vgg.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-yar.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-alt.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-amu.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ark.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ast.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-bel.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-bry.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-bu.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-che.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-chu.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-irk.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-iva.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kam.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kha.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-khm.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kir.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kko.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-klu.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kra.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-krm.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-kya.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-len.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-lip.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mag.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mos.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mow.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-mur.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-nen.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ngr.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-niz.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-nov.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-oms.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ore.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-orl.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-per.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-pri.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-psk.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sta.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-sve.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-tam.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-tom.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-tu.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ty.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-tyu.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ud.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-ul.m3u",
    "https://iptv-org.github.io/iptv/regions/ru-zab.m3u",
    "https://iptv-org.github.io/iptv/categories/news.m3u",
    "https://iptv-org.github.io/iptv/categories/movies.m3u",
    "https://iptv-org.github.io/iptv/categories/sports.m3u",
    "https://iptv-org.github.io/iptv/categories/kids.m3u",
    "https://iptv-org.github.io/iptv/categories/music.m3u",
    "https://iptv-org.github.io/iptv/categories/documentary.m3u",
    "https://iptv-org.github.io/iptv/categories/entertainment.m3u",
    "https://iptv-org.github.io/iptv/categories/education.m3u",
    "https://iptv-org.github.io/iptv/categories/lifestyle.m3u",
    "https://iptv-org.github.io/iptv/categories/shop.m3u",
    "https://iptv-org.github.io/iptv/categories/religious.m3u",
    "https://iptv-org.github.io/iptv/categories/series.m3u",
    "https://iptv-org.github.io/iptv/categories/science.m3u",
    "https://iptv-org.github.io/iptv/categories/travel.m3u",
    "https://iptv-org.github.io/iptv/categories/weather.m3u",
    "https://iptv-org.github.io/iptv/categories/animation.m3u",
    "https://iptv-org.github.io/iptv/categories/auto.m3u",
    "https://iptv-org.github.io/iptv/categories/business.m3u",
    "https://iptv-org.github.io/iptv/categories/classic.m3u",
    "https://iptv-org.github.io/iptv/categories/comedy.m3u",
    "https://iptv-org.github.io/iptv/categories/culture.m3u",
    "https://iptv-org.github.io/iptv/categories/family.m3u",
    "https://iptv-org.github.io/iptv/categories/general.m3u",
    "https://iptv-org.github.io/iptv/categories/history.m3u",
    "https://iptv-org.github.io/iptv/categories/legislative.m3u",
    "https://iptv-org.github.io/iptv/categories/outdoor.m3u",
    "https://raw.githubusercontent.com/Free-iptv/iptv/master/channels/ru.m3u",
    "https://raw.githubusercontent.com/4mirror/iptv/master/ru.m3u",
    "https://raw.githubusercontent.com/DenMSU/tv/main/tv.m3u",
    "https://raw.githubusercontent.com/Free-TV/IPTV/master/playlist.m3u8",
    "https://raw.githubusercontent.com/benmoose39/YouTube_to_m3u/main/youtube.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_sibir.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_mo.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kavkaz.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_ural.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_povolzhye.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_sev-zapad.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_dalny-vostok.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_centr.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_yug.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_krym.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_bashkortostan.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_tatarstan.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_dagestan.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_chechnya.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_ingushetia.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kabardino-balkaria.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_karachay-cherkessia.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_north-ossetia.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_adygea.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kalmykia.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_mari-el.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_mordovia.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_chuvashia.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_tuva.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_khakassia.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_altai.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_buryatia.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_sakha.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kamchatka.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_primorye.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_khabarovsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_amur.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_sakhalin.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_jewish-autonomous.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_chukotka.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_magadan.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_nenets.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_khanty-mansi.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_yamalo-nenets.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_komi.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_karelia.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_arhangelsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_murmansk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_novgorod.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_pskov.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_vologda.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kaliningrad.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_leningrad.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_st-petersburg.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kostroma.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_ivanovo.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_vladimir.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_ryazan.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_tula.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kaluga.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_bryansk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_smolensk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_orlov.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kursk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_belgorod.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_voronezh.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_tambov.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_lipetsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_penza.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_saratov.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_ulyanovsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_samara.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_orenburg.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kurgan.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_chelyabinsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_sverdlovsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_tumen.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_omsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_novosibirsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_tomsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kemerovo.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_altai-krai.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_krasnoyarsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_irkutsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_buryatia.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_zabaykalsky.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_sakha.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_amur.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_yevreyskaya.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_khabarovsk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_primorsky.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_sakhalin.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_kamchatka.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_magadan.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ru_chukotka.m3u",
    "https://m3u.su/m3u/sng.m3u",
    "https://m3u.su/m3u/ru.m3u",
    "https://m3u.su/m3u/ru-mos.m3u",
    "https://m3u.su/m3u/ru-spb.m3u",
    "https://m3u.su/m3u/ru-reg.m3u",
    "https://m3u.su/m3u/ru-kids.m3u",
    "https://m3u.su/m3u/ru-music.m3u",
    "https://m3u.su/m3u/ru-news.m3u",
    "https://m3u.su/m3u/ru-sport.m3u",
    "https://m3u.su/m3u/ru-movie.m3u",
    "https://m3u.su/m3u/ru-edu.m3u",
    "https://m3u.su/m3u/ru-religious.m3u",
    "https://webarmen.com/my/iptv/auto.nogeo.m3u",
    "https://webarmen.com/my/iptv/ru.m3u",
    "https://webarmen.com/my/iptv/sng.m3u",
    "https://webarmen.com/my/iptv/cis.m3u",
    "https://smarttvapp.ru/app/iptvlist.m3u",
    "https://smarttvapp.ru/app/ru.m3u",
    "https://smarttvapp.ru/app/sng.m3u",
    "https://smarttvapp.ru/app/europe.m3u",
    "https://smarttvapp.ru/app/usa.m3u",
    "https://smarttvapp.ru/app/asia.m3u",
    "https://smarttvapp.ru/app/sport.m3u",
    "https://smarttvapp.ru/app/movie.m3u",
    "https://smarttvapp.ru/app/kids.m3u",
    "https://smarttvapp.ru/app/music.m3u",
    "https://smarttvapp.ru/app/news.m3u",
    "https://smarttvapp.ru/app/edu.m3u",
    "https://smarttvapp.ru/app/religious.m3u",
    "https://allfon-tv.com/iptv/playlist.m3u",
    "https://allfon-tv.com/ru/playlist.m3u",
    "https://zabava.tv/playlist.m3u",
    "https://zabava.tv/ru/playlist.m3u",
    "https://zabava.tv/sng/playlist.m3u",
    "https://zabava.tv/all/playlist.m3u",
    "https://peerstv.ru/playlist.m3u",
    "https://peerstv.ru/ru/playlist.m3u",
    "https://peerstv.ru/sng/playlist.m3u",
    "https://cdn.peers.tv/playlist.m3u",
    "https://cdn.peers.tv/ru/playlist.m3u",
    "https://cdn.peers.tv/sng/playlist.m3u",
    "https://iptv-rus.com/playlist.m3u",
    "https://iptv-rus.com/ru/playlist.m3u",
    "https://iptv-rus.com/sng/playlist.m3u",
    "https://6x6.msk.ru/playlist.m3u",
    "https://6x6.msk.ru/ru/playlist.m3u",
    "https://homtv.ru/playlist.m3u",
    "https://homtv.ru/ru/playlist.m3u",
    "https://sat-portal.com/plejlisty/playlist.m3u",
    "https://sat-portal.com/plejlisty/ru/playlist.m3u",
    "https://pikniktv.info/playlist.m3u",
    "https://pikniktv.info/ru/playlist.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/youtube.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/youtube_ru.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/twitch.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/vk.m3u",
    "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/ok.ru.m3u",
]

HTML_SOURCES = [
    "https://sat-portal.com/plejlisty/4036-samoobnovlyaemye-plejlisty-2026",
    "https://6x6.msk.ru/",
    "https://homtv.ru/",
    "https://iptv-rus.com/",
    "https://pikniktv.info/viewtopic.php?t=6737",
    "https://m3u.su/",
    "https://webarmen.com/my/iptv/",
    "https://allfon-tv.com/",
    "https://zabava.tv/",
    "https://peerstv.ru/",
    "https://smarttvapp.ru/",
    "https://pl.iptv2022.com/",
    "https://iptv.edem.tv/",
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# ==================== БАЗА ДАННЫХ ====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            inf_line TEXT,
            category TEXT,
            source TEXT,
            is_alive INTEGER DEFAULT 0,
            last_check REAL DEFAULT 0,
            check_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            response_time REAL DEFAULT 0,
            content_type TEXT,
            added_at REAL DEFAULT 0,
            priority INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

def db_insert_or_update_channel(url, name, inf_line, category, source):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = time.time()
    c.execute("""
        INSERT INTO channels (url, name, inf_line, category, source, added_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(url) DO UPDATE SET
            name=excluded.name,
            inf_line=excluded.inf_line,
            category=excluded.category,
            source=excluded.source
    """, (url, name, inf_line, category, source, now))
    conn.commit()
    conn.close()

def db_update_check(url, is_alive, response_time, content_type):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE channels SET
            is_alive = ?,
            last_check = ?,
            check_count = check_count + 1,
            fail_count = CASE WHEN ? = 0 THEN fail_count + 1 ELSE 0 END,
            response_time = ?,
            content_type = ?
        WHERE url = ?
    """, (1 if is_alive else 0, time.time(), 1 if is_alive else 0, response_time, content_type, url))
    conn.commit()
    conn.close()

def db_get_alive_channels():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, inf_line, url, category FROM channels WHERE is_alive = 1 ORDER BY category, name")
    rows = c.fetchall()
    conn.close()
    return rows

def db_get_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), SUM(is_alive) FROM channels")
    total, alive = c.fetchone()
    c.execute("SELECT value FROM meta WHERE key = ?", ("last_full_update",))
    last_update = c.fetchone()
    conn.close()
    return {
        "total": total or 0,
        "alive": alive or 0,
        "last_full_update": last_update[0] if last_update else None
    }

def db_set_meta(key, value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


# ==================== ФИЛЬТРАЦИЯ И КАТЕГОРИИ ====================
RU_PATTERNS = [
    "первый","россия","нтв","тнт","стс","рен","домашний","пятница","тв3","звезда",
    "мир","спас","отр","твц","карусель","мульт","детский","бобёр","ю ","суббота",
    "чё","супер","сарафан","победа","русский","комедия","стс love","драйв","охота",
    "кухня","еда","поехали","иллюзион","кино","tv1000","amedia","fox","paramount",
    "sony","axn","hollywood","eurosport","матч","кхл","наш футбол","футбол","спорт",
    "бокс","extreme","red bull","motorvision","auto plus","discovery","animal planet",
    "nat geo","history","science","travel","adventure","viasat","id ","crime","tlc",
    "food network","fashion","world fashion","luxury","bridge","mtv","muz tv","rutv",
    "шансон","наше","rock","рок","jazz","джаз","classica","классика","europa plus","европа плюс",
    "musicbox","мьюзикбокс","luxe","люкс","o2tv","o2 тв","2x2","che","про любовь",
    "приключения","союз","время","москва 24","москва доверие","78","лен тв","экспресс",
    "самара","нижний","новосибирск","екатеринбург","казань","краснодар","ростов","воронеж",
    "волгоград","саратов","тюмень","томск","омск","челябинск","уфа","иркутск","барнаул",
    "красноярск","пермь","владивосток","хабаровск","петропавловск","югра","тверь","ярославль",
    "иваново","кострома","владимир","рязань","тула","калуга","орёл","смоленск","брянск",
    "курск","белгород","тамбов","липецк","пенза","ульяновск","курган","сургут",
    "нижневартовск","новый уренгой","надым","салехард","ноябрьск","муравленко",
    "лабытнанги","губкинский","тарко-сале","урай","когалым","нефтеюганск",
    "ханты-мансийск","берёзово","белоярский","радужный","советский","покачи",
    "мегион","лангепас","пыть-ях","югорск","кондинское","октябрьское","саранпауль",
    "приобье","излучинск","фёдоровский","пойковский","приобский","салым","барсово",
    "северный","южный","западный","восточный","центральный","окружной","городской",
    "региональный","местный","областной","краевой","республиканский","национальный",
    "государственный","федеральный","информационный","новостной","развлекательный",
    "музыкальный","киноканал","спортивный","познавательный","религиозный","культурный",
    "образовательный","научный","бизнес","финансовый","экономический","политический",
    "международный","европейский","азиатский","американский","британский","немецкий",
    "французский","итальянский","испанский","турецкий","арабский","индийский",
    "китайский","японский","корейский","вьетнамский","тайский","филиппинский",
    "индонезийский","малайзийский","сингапурский","австралийский","канадский",
    "бразильский","мексиканский","аргентинский","чилийский","колумбийский",
    "перуанский","венесуэльский","кубинский","пуэрто-риканский","доминиканский",
    "ямайский","гватемальский","сальвадорский","гондурасский","никарагуанский",
    "коста-риканский","панамский","эквадорский","боливийский","парагвайский",
    "уругвайский","суринамский","гайанский","нидерландский","бельгийский",
    "люксембургский","швейцарский","австрийский","чешский","словацкий","польский",
    "венгерский","румынский","болгарский","сербский","хорватский","словенский",
    "боснийский","македонский","черногорский","албанский","греческий","кипрский",
    "мальтийский","исландский","норвежский","шведский","финский","датский",
    "эстонский","латышский","литовский","украинский","белорусский","молдавский",
    "грузинский","армянский","азербайджанский","казахский","узбекский","киргизский",
    "таджикский","туркменский","монгольский","пакистанский","бангладешский",
    "шри-ланкийский","непальский","бутанский","мальдивский","афганский","иранский",
    "иракский","сирийский","ливанский","иорданский","израильский","палестинский",
    "саудовский","йеменский","оманский","катарский","бахрейнский","кувейтский",
    "оаэ","египетский","ливийский","тунисский","алжирский","марокканский",
    "мавританский","малийский","нигерийский","чадский","суданский","эфиопский",
    "эритрейский","сомалийский","кенийский","танзанийский","угандийский",
    "руандийский","бурундийский","малавийский","замбийский","зимбабвийский",
    "ботсванский","намибийский","ангольский","мозамбикский","малагасийский",
    "южноафриканский","лесотский","эсватинский","коморский","маскаренский",
    "сейшельский","маврикийский","реюньонский","майоттский","сенегальский",
    "гамбийский","гвинейский","гвинейско-бисауский","сьерра-леонский",
    "либерийский","кот-д'ивуарский","буркина-фасо","ганский","тоголезский",
    "бенинский","нигерский","камерунский","центральноафриканский",
    "экваториально-гвинейский","габонский","конголезский","заирский","брундийский",
]

RU_URL_PATTERNS = [
    ".ru/",".su/",".xn--p1ai/",".moscow/",".msk/",
    "peers.tv","zabava.tv","smarttvapp.ru","m3u.su",
    "webarmen.com","allfon-tv.com","iptv-rus.com",
    "sat-portal.com","pikniktv.info","6x6.msk.ru",
    "homtv.ru","pl.iptv2022.com","iptv.edem.tv",
    "cdn.peers.tv","peerstv.ru","youtube.com",
    "vk.com","ok.ru","twitch.tv",
]

def is_russian(name, url, inf):
    n = name.lower()
    u = url.lower()
    i = inf.lower()
    for p in RU_PATTERNS:
        if p in n:
            return True
    for p in RU_URL_PATTERNS:
        if p in u:
            return True
    if re.search(r"[\u0400-\u04FF]", name):
        return True
    if 'tvg-language="ru"' in i or 'tvg-language="rus"' in i:
        return True
    for c in ["ru","russia","россия","снг","sng"]:
        if f'group-title="{c}' in i or f"group-title={c}" in i:
            return True
    return False

def is_adult(name):
    n = name.lower()
    return any(w in n for w in ["xxx","adult","porn","sex","hentai","18+","эротика","порно","nude","playboy","hustler"])

def get_category(name):
    n = name.lower()
    cats = [
        (["новости","news","24","вести","информ","дождь","мир ","rbc","рбк","life","лайф","время","time"],"Новости"),
        (["кино","movie","film","сериал","fox","tv1000","amedia","кинопремьера","кинохит","киномикс","киносемья","иллюзион","русский роман","русский бестселлер","русский детектив","комедия","боевик","ужас","фантастика","триллер","драма","мелодрама","вестерн","детектив"],"Кино"),
        (["музыка","music","хит","radio","mtv","bridge","ru ","muz ","шансон","наше","rock","рок","jazz","джаз","classica","классика","europa plus","европа плюс","musicbox","мьюзикбокс","luxe","люкс","o2tv","o2 тв"],"Музыка"),
        (["спорт","sport","футбол","хоккей","матч","khl","кхл","бокс","extreme","экстрим","red bull","ред булл","motorvision","мото","auto plus","авто плюс","наш футбол","боевой","борьба","mma","ufc"],"Спорт"),
        (["дет","kids","мульт","cartoon","карусель","gulli","nickelodeon","никелодеон","nick jr","ник ","disney","дисней","duck","дак","jimjam","джимджем","baby","беби","tiji","тиджи"],"Детские"),
        (["докум","doc","познав","history","discovery","nat geo","national geographic","нат гео","science","сайенс","travel","тревел","adventure","адвенчер","viasat","виасат","id ","investigation","animal planet","animalplanet"],"Познавательные"),
        (["кухня","еда","food","фуд","охота","рыбалка","драйв","drive","auto","авто","поехали","путешествие","тур","отдых","дача","сад","огород"],"Бытовые"),
        (["религ","православ","христиан","ислам","мусульман","будд","иуда","католич","спас","soyuz","союз","тбн","tbn","глас","glas"],"Религиозные"),
        (["образов","edu","учеб","школа","университет","колледж","наука","science","лекция","курс","телешкола","телеканал знаний"],"Образовательные"),
        (["бизнес","business","финанс","эконом","полит","право","закон","государств"],"Бизнес"),
        (["мода","fashion","style","стиль","luxury","лакшери","world fashion","ворлд фэшн","телемагазин","shop","покупки"],"Мода и шоппинг"),
        (["юмор","comedy","квн","stand up","стендап","смеяться","смешно","анекдот","шутка"],"Юмор"),
        (["эрот","xxx","adult","porn","sex","18+","порно","playboy","hustler","barely","bang","brazzers"],"Для взрослых"),
    ]
    for keywords, cat in cats:
        if any(k in n for k in keywords):
            return cat
    return "Общие"


# ==================== ПРОВЕРКА КАНАЛОВ ====================
def check_channel(url):
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Connection": "close",
        "Icy-MetaData": "1",
    }
    valid_ct = ["video/","mpegurl","octet-stream","audio/","application/x-mpegurl","application/vnd.apple.mpegurl"]
    
    start = time.time()
    
    # Попытка 1: HEAD
    try:
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers=headers, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get("content-type","").lower()
            if any(v in ct for v in valid_ct):
                return True, time.time()-start, ct
    except:
        pass
    
    # Попытка 2: GET stream
    try:
        r = requests.get(url, timeout=CHECK_TIMEOUT, headers=headers, stream=True, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get("content-type","").lower()
            if any(v in ct for v in valid_ct):
                chunk = next(r.iter_content(chunk_size=1024), None)
                return True, time.time()-start, ct
    except:
        pass
    
    # Попытка 3: Анализ первых байт
    try:
        r = requests.get(url, timeout=CHECK_TIMEOUT, headers=headers, stream=True, allow_redirects=True, verify=False)
        if r.status_code < 400:
            chunk = next(r.iter_content(chunk_size=2048), b"")
            if chunk.startswith(b"#EXTM3U") or chunk.startswith(b"\x47") or chunk.startswith(b"\x00\x00\x00") or b"ftyp" in chunk[:20]:
                return True, time.time()-start, "binary/stream"
    except:
        pass
    
    return False, time.time()-start, ""


# ==================== ПАРСИНГ ИСТОЧНИКОВ ====================
def fetch_source(url):
    try:
        r = requests.get(url, timeout=20, headers=HEADERS_WEB, verify=False)
        if r.status_code == 200:
            return r.text
    except Exception as e:
        logger.debug(f"Ошибка загрузки {url}: {e}")
    return None

def parse_m3u(text, source_name):
    channels = []
    current_inf = ""
    current_name = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            current_inf = line
            m = re.search(r",\s*(.+)$", line)
            current_name = m.group(1).strip() if m else ""
        elif line.startswith("http"):
            if current_name and not is_adult(current_name):
                if is_russian(current_name, line, current_inf):
                    cat = get_category(current_name)
                    channels.append({
                        "url": line,
                        "name": current_name,
                        "inf": current_inf,
                        "category": cat,
                        "source": source_name
                    })
            current_inf = ""
            current_name = ""
    return channels

def fetch_dynamic():
    found = set()
    for page in HTML_SOURCES:
        try:
            r = requests.get(page, headers=HEADERS_WEB, timeout=10, verify=False)
            if r.status_code == 200:
                links = re.findall(r"(https?://[^\s\"\'<>]+?\.m3u8?)", r.text, re.I)
                found.update(links)
        except:
            pass
    return list(found)


# ==================== ОСНОВНОЙ ЦИКЛ ОБНОВЛЕНИЯ ====================
def normalize_name(name):
    name = re.sub(r"\s+", " ", name).strip()
    return re.sub(r"\s*(HD|SD|UHD|4K|8K|FHD|HQ|\(.*?$$|\[.*?$$)\s*$", "", name, flags=re.I).strip()

def run_full_update():
    global is_updating
    if is_updating:
        logger.info("Обновление уже идёт, пропускаем")
        return
    is_updating = True
    logger.info("=" * 50)
    logger.info("ZAPUSK POLNOGO OBNOVLENIYA")
    logger.info("=" * 50)
    start = time.time()
    
    try:
        # 1. Собираем все источники
        sources = list(set(STATIC_SOURCES + fetch_dynamic()))
        logger.info(f"Istochnikov dlya proverki: {len(sources)}")
        
        # 2. Парсим все источники
        all_channels = []
        seen_urls = set()
        for src in sources:
            text = fetch_source(src)
            if text:
                chs = parse_m3u(text, src)
                for ch in chs:
                    if ch["url"] not in seen_urls:
                        seen_urls.add(ch["url"])
                        all_channels.append(ch)
            if len(all_channels) >= MAX_CHANNELS:
                break
        
        logger.info(f"Sobrano unikalnyh kanalov: {len(all_channels)}")
        
        # 3. Дедупликация по имени (предпочитаем HD)
        dedup = {}
        for ch in all_channels:
            base = normalize_name(ch["name"])
            if base in dedup:
                if any(x in ch["name"].upper() for x in ["HD","FHD","4K"]):
                    dedup[base] = ch
            else:
                dedup[base] = ch
        
        unique_channels = list(dedup.values())
        logger.info(f"Posle deduplikacii: {len(unique_channels)}")
        
        # 4. Сохраняем в БД
        for ch in unique_channels:
            db_insert_or_update_channel(ch["url"], ch["name"], ch["inf"], ch["category"], ch["source"])
        
        # 5. Проверяем каналы пачками
        total_to_check = len(unique_channels)
        checked = 0
        alive_count = 0
        
        for batch_start in range(0, total_to_check, BATCH_SIZE):
            batch = unique_channels[batch_start:batch_start + BATCH_SIZE]
            logger.info(f"Proverka pachki {batch_start+1}-{min(batch_start+BATCH_SIZE, total_to_check)} / {total_to_check}")
            
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                future_to_ch = {executor.submit(check_channel, ch["url"]): ch for ch in batch}
                for future in as_completed(future_to_ch):
                    ch = future_to_ch[future]
                    try:
                        is_alive, resp_time, ct = future.result()
                        db_update_check(ch["url"], is_alive, resp_time, ct)
                        checked += 1
                        if is_alive:
                            alive_count += 1
                    except Exception as e:
                        logger.debug(f"Ошибка проверки {ch['url']}: {e}")
                        db_update_check(ch["url"], False, 0, "")
                        checked += 1
            
            logger.info(f"   Provereno: {checked}, Zhivyh: {alive_count}")
        
        # 6. Сохраняем метаданные
        db_set_meta("last_full_update", str(time.time()))
        db_set_meta("last_update_str", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        elapsed = time.time() - start
        logger.info("=" * 50)
        logger.info(f"OBNOVLENIE ZAVERSHENO")
        logger.info(f"   Provereno: {checked}")
        logger.info(f"   Zhivyh: {alive_count}")
        logger.info(f"   Vremya: {elapsed:.1f} sek")
        logger.info("=" * 50)
        
    except Exception as e:
        logger.error(f"Kriticheskaya oshibka obnovleniya: {e}")
    finally:
        is_updating = False

def rebuild_playlist():
    """Пересобирает M3U из alive каналов в БД"""
    channels = db_get_alive_channels()
    lines = [
        "#EXTM3U",
        f"# IPTV Russia Pro Max — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"# Rabotaet: {len(channels)} kanalov",
        f"# Avtoobnovlenie: kazhdye {FULL_UPDATE_INTERVAL // 3600} chasov",
    ]
    
    current_cat = ""
    for name, inf, url, category in channels:
        if category != current_cat:
            lines.append(f"# {category}")
            current_cat = category
        
        # Обновляем group-title
        if "group-title=" not in inf:
            inf = re.sub(r"(#EXTINF:-?\d+\s*)", rf'\1group-title="{category}" ', inf, count=1)
        else:
            inf = re.sub(r'group-title="[^"]*"', f'group-title="{category}"', inf)
        
        # Добавляем tvg-language
        if "tvg-language=" not in inf:
            inf = inf.replace("#EXTINF:", '#EXTINF:tvg-language="ru" ')
        
        lines.append(inf)
        lines.append(url)
    
    return "\n".join(lines)


# ==================== ФОНОВЫЕ ПРОЦЕССЫ ====================
is_updating = False

def scheduler():
    """Главный планировщик: полное обновление каждые N секунд"""
    # Первый запуск сразу
    run_full_update()
    
    while True:
        time.sleep(FULL_UPDATE_INTERVAL)
        run_full_update()

def keep_alive_pinger():
    """Пингует сам себя, чтобы Render не усыпал сервис во время работы"""
    while True:
        time.sleep(60 * 10)  # каждые 10 минут
        try:
            port = os.environ.get("PORT", "10000")
            requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
        except:
            pass


# ==================== FLASK ROUTES ====================
playlist_cache = ""
cache_lock = threading.Lock()
last_cache_update = 0

def get_cached_playlist():
    global playlist_cache, last_cache_update
    with cache_lock:
        # Кэш устарел через 5 минут или пустой
        if time.time() - last_cache_update > 300 or not playlist_cache:
            playlist_cache = rebuild_playlist()
            last_cache_update = time.time()
        return playlist_cache

@app.route("/")
def home():
    stats = db_get_stats()
    last_str = stats["last_full_update"]
    if last_str:
        try:
            last_dt = datetime.fromtimestamp(float(last_str)).strftime("%Y-%m-%d %H:%M:%S")
        except:
            last_dt = last_str
    else:
        last_dt = "Nikogda"
    return f"""
    <h1>IPTV Russia Pro Max</h1>
    <p><b>Status:</b> {"Obnovlyaetsya..." if is_updating else "Aktiven"}</p>
    <p><b>Vsego kanalov v baze:</b> {stats["total"]}</p>
    <p><b>Rabochih kanalov:</b> {stats["alive"]}</p>
    <p><b>Poslednee obnovlenie:</b> {last_dt}</p>
    <p><b>Interval obnovleniya:</b> {FULL_UPDATE_INTERVAL // 3600} chasov</p>
    <hr>
    <p><a href="/playlist.m3u" style="font-size:20px">Skachat plejlist</a></p>
    <p><a href="/playlist.m3u8" style="font-size:20px">Skachat plejlist (.m3u8)</a></p>
    <p><a href="/status" style="font-size:16px">JSON status</a></p>
    <p><a href="/force-update" style="font-size:16px">Prinuditelnoe obnovlenie</a></p>
    """

@app.route("/playlist.m3u")
@app.route("/playlist.m3u8")
def playlist():
    pl = get_cached_playlist()
    resp = Response(pl, mimetype="application/vnd.apple.mpegurl")
    resp.headers["Content-Disposition"] = 'attachment; filename="iptv_russia_pro_max.m3u"'
    resp.headers["Cache-Control"] = "public, max-age=300"
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp

@app.route("/status")
def status():
    stats = db_get_stats()
    return jsonify({
        "total_channels": stats["total"],
        "alive_channels": stats["alive"],
        "is_updating": is_updating,
        "last_full_update": stats["last_full_update"],
        "update_interval_hours": FULL_UPDATE_INTERVAL // 3600,
        "db_path": DB_PATH,
        "timestamp": datetime.now().isoformat()
    })

@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route("/force-update")
def force_update():
    if is_updating:
        return jsonify({"status": "already_running"}), 429
    threading.Thread(target=run_full_update, daemon=True).start()
    return jsonify({"status": "started"})


# ==================== ZAPUSK ====================
if __name__ == "__main__":
    logger.info("Inicializaciya bazy dannyh...")
    init_db()
    
    logger.info("Zapusk fonovyh processov...")
    threading.Thread(target=scheduler, daemon=True).start()
    threading.Thread(target=keep_alive_pinger, daemon=True).start()
    
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"Zapusk veb-servera na portu {port}")
    
    try:
        from waitress import serve
        serve(app, host="0.0.0.0", port=port, threads=16)
    except ImportError:
        app.run(host="0.0.0.0", port=port, threaded=True)
