import os
import re
import time
import logging
import threading
import hashlib
import requests
import urllib3
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, Response
from collections import OrderedDict

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# ==================== РАСШИРЕННЫЕ ИСТОЧНИКИ ====================
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

# ==================== НАСТРОЙКИ ====================
MAX_CHANNELS_TO_PARSE = 15000
MAX_WORKERS = 100
CHECK_TIMEOUT = 5.0
UPDATE_EVERY = 1800
MAX_ALIVE_CHANNELS = 3000

playlist_cache = "#EXTM3U\n# IPTV Russia Pro Max — идёт проверка каналов...\n"
cache_lock = threading.Lock()
is_updating = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HEADERS_WEB = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
HEADERS_PLAYER = {
    'User-Agent': 'VLC/3.0.20 LibVLC/3.0.20',
    'Connection': 'close',
    'Icy-MetaData': '1',
}


# ==================== БАЗА РОССИЙСКИХ КАНАЛОВ ====================
RUSSIAN_CHANNEL_PATTERNS = [
    'первый', '1 канал', 'channel one', 'perviy', 'pervy',
    'россия', 'russia', 'rossiya', 'rtr', 'ртр',
    'нтв', 'ntv', 'тнт', 'tnt', 'стс', 'sts', 'рен тв', 'rentv', 'рен',
    'домашний', 'domashniy', 'пятница', 'pyatnitsa', 'friday',
    'тв3', 'tv3', 'tv 3', 'звезда', 'zvezda', 'мир', 'mir',
    'спас', 'spas', 'отр', 'otr', 'тв центр', 'tvc', 'твц',
    'карусель', 'karusel', 'мульт', 'mult', 'детский', 'detskiy', 'kids',
    'бобёр', 'bober', 'ю', 'u', 'суббота', 'subbota', 'чё', 'cho', 'супер', 'super',
    'сарафан', 'sarafan', 'победа', 'pobeda',
    'русский роман', 'russkiy roman', 'русский бестселлер', 'russkiy bestseller',
    'русский детектив', 'russkiy detektiv', 'комедия', 'comedy',
    'стс love', 'sts love', 'драйв', 'drive', 'охота и рыбалка', 'ohota',
    'кухня тв', 'kukhnya', 'еда', 'eda', 'поехали', 'poehali',
    'наша тема', 'nasha tema', 'живая планета', 'zhivaya planeta',
    'иллюзион', 'illyuzion', 'индийское', 'india', 'кино тв', 'kino tv',
    'киноужас', 'kino uzhas', 'кинопремьера', 'kinopremiera',
    'киносемья', 'kinosemya', 'кинохит', 'kinohit', 'киномикс', 'kinomiks',
    'tv1000', 'tv 1000', 'amedia', 'амедиа',
    'fox', 'фокс', 'fox life', 'фокс лайф', 'paramount', 'парамаунт',
    'sony', 'сони', 'sony sci-fi', 'sony turbo', 'axn', 'аксн',
    'hollywood', 'голливуд', 'eurosport', 'евроспорт',
    'матч', 'match', 'матч премьер', 'match premier', 'матч арена', 'match arena',
    'матч игра', 'match game', 'матч боец', 'match boets',
    'матч страна', 'match strana', 'матч футбол', 'match futbol',
    'матч планета', 'match planeta', 'кхл', 'khl',
    'наш футбол', 'nash futbol', 'футбол', 'futbol', 'спорт', 'sport',
    'бокс тв', 'box tv', 'extreme sports', 'экстрим',
    'red bull', 'ред булл', 'motorvision', 'мото', 'auto plus', 'авто плюс',
    'discovery', 'дискавери', 'animal planet', 'animalplanet',
    'nat geo', 'national geographic', 'нат гео', 'history', 'хистори',
    'science', 'сайенс', 'travel', 'тревел', 'adventure', 'адвенчер',
    'viasat', 'виасат', 'id', 'investigation', 'crime', 'крим',
    'tlc', 'тлс', 'food network', 'фуд', 'fashion', 'фэшн',
    'world fashion', 'ворлд фэшн', 'luxury', 'лакшери',
    'bridge', 'бридж', 'mtv', 'эмтиви', 'mtv hits', 'mtv live',
    'muz tv', 'муз тв', 'rutv', 'рутв', 'шансон', 'shanson',
    'наше', 'nashe', 'rock', 'рок', 'jazz', 'джаз', 'classica', 'классика',
    'europa plus', 'европа плюс', 'russian musicbox', 'мьюзикбокс',
    'luxe', 'люкс', 'o2tv', 'о2тв', '2x2', '2 x 2', 'che', 'че',
    'про любовь', 'pro lyubov', 'приключения', 'priklyucheniya',
    'союз', 'soyuz', 'время', 'vremya', 'москва 24', 'moskva 24',
    'москва доверие', 'moskva doverie', '78', 'санкт-петербург',
    'лен тв', 'len tv', 'экспресс', 'express',
    'самара', 'samara', 'нижний', 'nizhniy', 'новосибирск', 'novosibirsk',
    'екатеринбург', 'ekaterinburg', 'казань', 'kazan',
    'краснодар', 'krasnodar', 'ростов', 'rostov', 'воронеж', 'voronezh',
    'волгоград', 'volgograd', 'саратов', 'saratov', 'тюмень', 'tyumen',
    'томск', 'tomsk', 'омск', 'omsk', 'челябинск', 'chelyabinsk',
    'уфа', 'ufa', 'иркутск', 'irkutsk', 'барнаул', 'barnaul',
    'красноярск', 'krasnoyarsk', 'пермь', 'perm',
    'владивосток', 'vladivostok', 'хабаровск', 'khabarovsk',
    'петропавловск', 'petropavlovsk', 'югра', 'yugra',
    'тюменская', 'tyumenskaya', 'тверь', 'tver', 'ярославль', 'yaroslavl',
    'иваново', 'ivanovo', 'кострома', 'kostroma', 'владимир', 'vladimir',
    'рязань', 'ryazan', 'тула', 'tula', 'калуга', 'kaluga',
    'орёл', 'orel', 'смоленск', 'smolensk', 'брянск', 'bryansk',
    'курск', 'kursk', 'белгород', 'belgorod', 'тамбов', 'tambov',
    'липецк', 'lipetsk', 'пенза', 'penza', 'ульяновск', 'ulyanovsk',
    'курган', 'kurgan', 'сургут', 'surgut', 'нижневартовск', 'nizhnevartovsk',
    'новый уренгой', 'novyy urengoy', 'надым', 'nadym',
    'салехард', 'salekhard', 'ноябрьск', 'noyabrsk',
    'муравленко', 'muravlenko', 'лабытнанги', 'labytnangi',
    'губкинский', 'gubkinskiy', 'тарко-сале', 'tarko-sale',
    'урай', 'uray', 'когалым', 'kogalym', 'нефтеюганск', 'nefteyugansk',
    'ханты-мансийск', 'khanty-mansiysk', 'берёзово', 'berezovo',
    'белоярский', 'beloyarskiy', 'радужный', 'raduzhnyy',
    'советский', 'sovetskiy', 'покачи', 'pokachi', 'мегион', 'megion',
    'лангепас', 'langepas', 'пыть-ях', 'pyt-yakh', 'югорск', 'yugorsk',
    'кондинское', 'kondinskoe', 'октябрьское', 'oktyabrskoe',
    'саранпауль', 'saranpaul', 'приобье', 'priobye',
    'излучинск', 'izluchinsk', 'фёдоровский', 'fyodorovskiy',
    'пойковский', 'poykovskiy', 'приобский', 'priobskiy',
    'салым', 'salym', 'барсово', 'barsovo',
    'северный', 'severnyy', 'южный', 'yuzhnyy', 'западный', 'zapadnyy',
    'восточный', 'vostochnyy', 'центральный', 'centralnyy',
    'окружной', 'okruzhnoy', 'городской', 'gorodskoy',
    'региональный', 'regional', 'местный', 'mestnyy',
    'областной', 'oblastnoy', 'краевой', 'kraevoy',
    'республиканский', 'respublikanskiy', 'национальный', 'natsionalnyy',
    'государственный', 'gosudarstvennyy', 'федеральный', 'federalnyy',
    'информационный', 'informatsionnyy', 'новостной', 'novostnoy',
    'развлекательный', 'razvlekatelniy', 'музыкальный', 'muzykalnyy',
    'киноканал', 'kinokanal', 'спортивный', 'sportivnyy',
    'познавательный', 'poznavatelniy', 'религиозный', 'religioznyy',
    'культурный', 'kulturnyy', 'образовательный', 'obrazovatelniy',
    'научный', 'nauchnyy', 'бизнес', 'business',
    'финансовый', 'finansovyy', 'экономический', 'ekonomicheskiy',
    'политический', 'politicheskiy', 'международный', 'mezhdunarodnyy',
    'европейский', 'evropeyskiy', 'азиатский', 'aziatskiy',
    'американский', 'amerikanskiy', 'британский', 'britanskiy',
    'немецкий', 'nemeckiy', 'французский', 'frantsuzskiy',
    'итальянский', 'italyanskiy', 'испанский', 'ispanskiy',
    'турецкий', 'tureckiy', 'арабский', 'arabsiy',
    'индийский', 'indiyskiy', 'китайский', 'kitayskiy',
    'японский', 'yaponskiy', 'корейский', 'koreyskiy',
    'вьетнамский', 'vetnamskiy', 'тайский', 'tayskiy',
    'филиппинский', 'filippinskiy', 'индонезийский', 'indoneziyskiy',
    'малайзийский', 'malayziyskiy', 'сингапурский', 'singapurskiy',
    'австралийский', 'avstraliyskiy', 'канадский', 'kanadskiy',
    'бразильский', 'braziliyskiy', 'мексиканский', 'meksikanskiy',
    'аргентинский', 'argentiniskiy', 'чилийский', 'chiliyskiy',
    'колумбийский', 'kolumbiyskiy', 'перуанский', 'peruanskiy',
    'венесуэльский', 'venesueliskiy', 'кубинский', 'kubinskiy',
    'пуэрто-риканский', 'puerto-rikanskiy', 'доминиканский', 'dominikanskiy',
    'ямайский', 'yamayskiy', 'гватемальский', 'gvatemalskiy',
    'сальвадорский', 'salvadorskiy', 'гондурасский', 'gondurasskiy',
    'никарагуанский', 'nikaraganskiy', 'коста-риканский', 'kosta-rikanskiy',
    'панамский', 'panamskiy', 'эквадорский', 'ekvadorskiy',
    'боливийский', 'boliviyskiy', 'парагвайский', 'paragvayskiy',
    'уругвайский', 'urugvayskiy', 'суринамский', 'surinamskiy',
    'гайанский', 'guyanskiy', 'французская гвиана', 'frantsuzskaya gviana',
    'нидерландский', 'niderlandskiy', 'бельгийский', 'belgiyskiy',
    'люксембургский', 'lyuksemburgskiy', 'швейцарский', 'shveytsarskiy',
    'австрийский', 'avstriyskiy', 'чешский', 'cheshskiy',
    'словацкий', 'slovatskiy', 'польский', 'polskiy',
    'венгерский', 'vengerskiy', 'румынский', 'rumynskiy',
    'болгарский', 'bolgarskiy', 'сербский', 'serbskiy',
    'хорватский', 'horvatskiy', 'словенский', 'slovenskiy',
    'боснийский', 'bosniyskiy', 'македонский', 'makedonskiy',
    'черногорский', 'chernogorskiy', 'албанский', 'albanskiy',
    'греческий', 'grecheskiy', 'кипрский', 'kiprskiy',
    'мальтийский', 'maltsiyskiy', 'исландский', 'islandskiy',
    'норвежский', 'norvezhskiy', 'шведский', 'shvedskiy',
    'финский', 'finskiy', 'датский', 'datskiy',
    'эстонский', 'estonskiy', 'латышский', 'latyshskiy',
    'литовский', 'litovskiy', 'украинский', 'ukrainskiy',
    'белорусский', 'belorusskiy', 'молдавский', 'moldavskiy',
    'грузинский', 'gruzinskiy', 'армянский', 'armyanskiy',
    'азербайджанский', 'azerbaydzhanskiy', 'казахский', 'kazakhskiy',
    'узбекский', 'uzbekskiy', 'киргизский', 'kirgizskiy',
    'таджикский', 'tadzhikskiy', 'туркменский', 'turkmenskiy',
    'монгольский', 'mongolskiy', 'пакистанский', 'pakistanskiy',
    'бангладешский', 'bangladeshskiy', 'шри-ланкийский', 'shri-lankiyskiy',
    'непальский', 'nepalskiy', 'бутанский', 'butanskiy',
    'мальдивский', 'maldivskiy', 'афганский', 'afganskiy',
    'иранский', 'iranskiy', 'иракский', 'irakskiy',
    'сирийский', 'siriyskiy', 'ливанский', 'livanskiy',
    'иорданский', 'iordanskiy', 'израильский', 'izrailskiy',
    'палестинский', 'palestinskiy', 'саудовский', 'saudovskiy',
    'йеменский', 'yemenskiy', 'оманский', 'omanskiy',
    'катарский', 'katarskiy', 'бахрейнский', 'bakhreyskiy',
    'кувейтский', 'kuveytskiy', 'оаэ', 'oae',
    'египетский', 'egipetskiy', 'ливийский', 'liviyskiy',
    'тунисский', 'tunisskiy', 'алжирский', 'alzhirskiy',
    'марокканский', 'marokkanskiy', 'мавританский', 'mavritanskiy',
    'малийский', 'maliyskiy', 'нигерийский', 'nigeriyskiy',
    'чадский', 'chadskiy', 'суданский', 'sudanskiy',
    'эфиопский', 'efiopskiy', 'эритрейский', 'eritreyskiy',
    'сомалийский', 'somaliyskiy', 'кенийский', 'keniyskiy',
    'танзанийский', 'tanzaaniyskiy', 'угандийский', 'ugandiyskiy',
    'руандийский', 'ruandiyskiy', 'бурундийский', 'burundiyskiy',
    'малавийский', 'malaviyskiy', 'замбийский', 'zambiyskiy',
    'зимбабвийский', 'zimbabviyskiy', 'ботсванский', 'botsvanskiy',
    'намибийский', 'namibiyskiy', 'ангольский', 'angolskiy',
    'мозамбикский', 'mozambikskiy', 'малагасийский', 'malagasiyskiy',
    'южноафриканский', 'yuzhnoafrikanskiy', 'лесотский', 'lesotskiy',
    'эсватинский', 'esvatinskiy', 'коморский', 'komorskiy',
    'маскаренский', 'maskarenskiy', 'сейшельский', 'seyshelskiy',
    'маврикийский', 'mavrikiyskiy', 'реюньонский', 'reyunionskiy',
    'майоттский', 'mayottskiy', 'сенегальский', 'senegalskiy',
    'гамбийский', 'gambiyskiy', 'гвинейский', 'gvineyskiy',
    'гвинейско-бисауский', 'gvineysko-bisauskiy', 'сьерра-леонский', 'serra-leonskiy',
    'либерийский', 'liberiyskiy', 'кот-д\'ивуарский', 'kot-d\'ivuarskiy',
    'буркина-фасо', 'burkina-faso', 'ганский', 'ganskiy',
    'тоголезский', 'togolezskiy', 'бенинский', 'beninskiy',
    'нигерский', 'nigerskiy', 'камерунский', 'kamerunskiy',
    'центральноафриканский', 'centralnoafrikanskiy',
    'экваториально-гвинейский', 'ekvatorialno-gvineyskiy',
    'габонский', 'gabonskiy', 'конголезский', 'kongolexskiy',
    'заирский', 'zairskiy', 'брундийский', 'brundiyskiy',
    'руандийский', 'ruandiyskiy', 'бурундийский', 'burundiyskiy',
]

RUSSIAN_URL_PATTERNS = [
    '.ru/', '.su/', '.xn--p1ai/', '.moscow/', '.msk/',
    'peers.tv', 'zabava.tv', 'smarttvapp.ru', 'm3u.su',
    'webarmen.com', 'allfon-tv.com', 'iptv-rus.com',
    'sat-portal.com', 'pikniktv.info', '6x6.msk.ru',
    'homtv.ru', 'pl.iptv2022.com', 'iptv.edem.tv',
    'cdn.peers.tv', 'peerstv.ru', 'youtube.com',
    'vk.com', 'ok.ru', 'twitch.tv',
]

RUSSIAN_TVG_COUNTRIES = ['RU', 'RU-RU', 'Russia', 'Russian Federation', 'Россия', 'РФ']


# ==================== ФУНКЦИИ ====================
def fetch_dynamic():
    found = set()
    for page in HTML_SOURCES:
        try:
            r = requests.get(page, headers=HEADERS_WEB, timeout=10, verify=False)
            if r.status_code == 200:
                links = re.findall(r'(https?://[^\s"\'<>]+?\.m3u8?)', r.text, re.I)
                found.update(links)
        except Exception as e:
            logger.debug(f"Пропуск {page}: {e}")
    return list(found)

def get_category(name):
    n = name.lower()
    if any(x in n for x in ['новости', 'news', '24', 'вести', 'информ', 'дождь', 'мир', 'rbc', 'рбк', 'life', 'лайф', 'время', 'time']):
        return 'Новости'
    if any(x in n for x in ['кино', 'movie', 'film', 'сериал', 'hd', 'fox', 'tv1000', 'amedia', 'кинопремьера', 'кинохит', 'киномикс', 'киносемья', 'иллюзион', 'русский роман', 'русский бестселлер', 'русский детектив', 'комедия', 'боевик', 'ужас', 'фантастика', 'триллер', 'драма', 'мелодрама', 'вестерн', 'детектив']):
        return 'Кино'
    if any(x in n for x in ['музыка', 'music', 'хит', 'radio', 'mtv', 'bridge', 'ru', 'muz', 'шансон', 'наше', 'rock', 'рок', 'jazz', 'джаз', 'classica', 'классика', 'europa plus', 'европа плюс', 'musicbox', 'мьюзикбокс', 'luxe', 'люкс', 'o2tv', 'o2 тв']):
        return 'Музыка'
    if any(x in n for x in ['спорт', 'sport', 'футбол', 'хоккей', 'матч', 'khl', 'кхл', 'бокс', 'extreme', 'экстрим', 'red bull', 'ред булл', 'motorvision', 'мото', 'auto plus', 'авто плюс', 'наш футбол', 'боевой', 'борьба', 'mma', 'ufc']):
        return 'Спорт'
    if any(x in n for x in ['дет', 'kids', 'мульт', 'cartoon', 'карусель', 'gulli', 'nickelodeon', 'никелодеон', 'nick jr', 'ник', 'disney', 'дисней', 'duck', 'дак', 'jimjam', 'джимджем', 'baby', 'беби', 'tiji', 'тиджи']):
        return 'Детские'
    if any(x in n for x in ['докум', 'doc', 'познав', 'history', 'discovery', 'nat geo', 'national geographic', 'нат гео', 'science', 'сайенс', 'travel', 'тревел', 'adventure', 'адвенчер', 'viasat', 'виасат', 'id', 'investigation', 'animal planet', 'animalplanet']):
        return 'Познавательные'
    if any(x in n for x in ['кухня', 'еда', 'food', 'фуд', 'охота', 'рыбалка', 'драйв', 'drive', 'auto', 'авто', 'поехали', 'путешествие', 'тур', 'отдых', 'дача', 'сад', 'огород']):
        return 'Бытовые'
    if any(x in n for x in ['религ', 'православ', 'христиан', 'ислам', 'мусульман', 'будд', 'иуда', 'католич', 'спас', 'soyuz', 'союз', 'тбн', 'tbn', 'глас', 'glas']):
        return 'Религиозные'
    if any(x in n for x in ['образов', 'edu', 'учеб', 'школа', 'университет', 'колледж', 'наука', 'science', 'лекция', 'курс', 'телешкола', 'телеканал знаний']):
        return 'Образовательные'
    if any(x in n for x in ['бизнес', 'business', 'финанс', 'эконом', 'полит', 'право', 'закон', 'государств']):
        return 'Бизнес'
    if any(x in n for x in ['мода', 'fashion', 'style', 'стиль', 'luxury', 'лакшери', 'world fashion', 'ворлд фэшн', 'телемагазин', 'shop', 'покупки']):
        return 'Мода и шоппинг'
    if any(x in n for x in ['юмор', 'comedy', 'квн', 'stand up', 'стендап', 'смеяться', 'смешно', 'анекдот', 'шутка']):
        return 'Юмор'
    if any(x in n for x in ['эрот', 'xxx', 'adult', 'porn', 'sex', '18+', 'порно', 'playboy', 'hustler', 'barely', 'bang', 'brazzers']):
        return 'Для взрослых'
    return 'Общие'

def is_adult(name):
    n = name.lower()
    bad = ['xxx', 'adult', 'porn', 'sex', 'hentai', '18+', 'эротика', 'порно', 'nude', 'playboy', 'hustler', 'barely', 'bang', 'brazzers']
    return any(w in n for w in bad)

def is_russian_advanced(name, url, inf_line):
    n = name.lower()
    u = url.lower()
    i = inf_line.lower()

    for pattern in RUSSIAN_CHANNEL_PATTERNS:
        if pattern in n:
            return True

    for pattern in RUSSIAN_URL_PATTERNS:
        if pattern in u:
            return True

    for country in RUSSIAN_TVG_COUNTRIES:
        if f'tvg-country="{country}"' in i or f'tvg-country={country}' in i:
            return True

    if 'tvg-language="rus"' in i or 'tvg-language="ru"' in i or 'tvg-language="russian"' in i:
        return True

    if re.search(r'[\u0400-\u04FF]', name):
        return True

    ru_groups = ['россия', 'russia', 'ru ', 'ru-', 'sng', 'снг', 'cis', 'москва', 'moscow', 'петербург', 'petersburg', 'регион', 'region', 'федерал', 'federal']
    for g in ru_groups:
        if f'group-title="{g}' in i or f'group-title={g}' in i:
            return True

    return False

def check_one(url):
    valid_content_types = ['video/', 'mpegurl', 'octet-stream', 'audio/', 'application/x-mpegurl', 'application/vnd.apple.mpegurl', 'application/mpegurl']

    try:
        r = requests.head(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(valid in ct for valid in valid_content_types):
                return True
    except:
        pass

    try:
        r = requests.get(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, stream=True, allow_redirects=True, verify=False)
        if r.status_code < 400:
            ct = r.headers.get('content-type', '').lower()
            if any(valid in ct for valid in valid_content_types):
                next(r.iter_content(chunk_size=1024), None)
                return True
    except:
        pass

    try:
        r = requests.get(url, timeout=CHECK_TIMEOUT, headers=HEADERS_PLAYER, stream=True, allow_redirects=True, verify=False)
        if r.status_code < 400:
            chunk = next(r.iter_content(chunk_size=2048), b'')
            if chunk.startswith(b'#EXTM3U') or chunk.startswith(b'\x47') or chunk.startswith(b'\x00\x00\x00') or b'ftyp' in chunk[:20]:
                return True
    except:
        pass

    return False

def normalize_channel_name(name):
    name = re.sub(r'\s+', ' ', name).strip()
    base = re.sub(r'\s*(HD|SD|UHD|4K|8K|FHD|HQ|\(.*?\)|\[.*?\])\s*$', '', name, flags=re.I).strip()
    return base

def update_cache():
    global playlist_cache, is_updating
    if is_updating:
        return

    is_updating = True
    logger.info("Запуск проверки каналов...")
    start_time = time.time()

    try:
        sources = list(set(STATIC_SOURCES + fetch_dynamic()))
        logger.info(f"Источников: {len(sources)}")

        seen_urls = set()
        seen_names = {}

        for src in sources:
            try:
                r = requests.get(src, timeout=15, headers=HEADERS_WEB, verify=False)
                if r.status_code != 200:
                    continue

                current_inf = ""
                current_name = ""

                for line in r.text.splitlines():
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith('#EXTINF:'):
                        current_inf = line
                        match = re.search(r',\s*(.+)$', line)
                        current_name = match.group(1).strip() if match else ""
                    elif line.startswith('http'):
                        if current_name and not is_adult(current_name):
                            if is_russian_advanced(current_name, line, current_inf):
                                if line not in seen_urls:
                                    seen_urls.add(line)

                                    base_name = normalize_channel_name(current_name)
                                    if base_name in seen_names:
                                        if 'HD' in current_name.upper() or 'FHD' in current_name.upper() or '4K' in current_name.upper():
                                            seen_names[base_name] = {'inf': current_inf, 'url': line, 'name': current_name}
                                    else:
                                        seen_names[base_name] = {'inf': current_inf, 'url': line, 'name': current_name}

                                    if len(seen_names) >= MAX_CHANNELS_TO_PARSE:
                                        break

                        current_inf = ""
                        current_name = ""

                if len(seen_names) >= MAX_CHANNELS_TO_PARSE:
                    break
            except Exception as e:
                logger.debug(f"Ошибка {src}: {e}")
                continue

        raw = list(seen_names.values())
        logger.info(f"Собрано {len(raw)} уникальных каналов. Проверка доступности...")

        alive = []
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_data = {executor.submit(check_one, ch['url']): ch for ch in raw}

            for future in as_completed(future_to_data):
                ch = future_to_data[future]
                try:
                    if future.result():
                        alive.append(ch)
                        if len(alive) >= MAX_ALIVE_CHANNELS:
                            for f in future_to_data:
                                f.cancel()
                            break
                except:
                    pass

        alive_sorted = sorted(alive, key=lambda x: get_category(x['name']))

        lines = [
            "#EXTM3U",
            f"# IPTV Russia Pro Max — {time.strftime('%Y-%m-%d %H:%M')}",
            f"# Работает: {len(alive_sorted)} каналов",
            f"# Проверено источников: {len(sources)}",
        ]

        current_cat = ""
        for ch in alive_sorted:
            cat = get_category(ch['name'])
            if cat != current_cat:
                lines.append(f"# {cat}")
                current_cat = cat

            inf = ch['inf']
            if 'group-title=' not in inf:
                inf = re.sub(r'(#EXTINF:-?\d+\s*)', rf'\1group-title="{cat}" ', inf, count=1)
            else:
                inf = re.sub(r'group-title="[^"]*"', f'group-title="{cat}"', inf)

            if 'tvg-language=' not in inf:
                inf = inf.replace('#EXTINF:', '#EXTINF:tvg-language="ru" ')

            lines.append(inf)
            lines.append(ch['url'])

        with cache_lock:
            playlist_cache = "\n".join(lines)

        elapsed = time.time() - start_time
        logger.info(f"Готово! Каналов: {len(alive_sorted)}. Время: {elapsed:.1f} сек")

    except Exception as e:
        logger.error(f"Ошибка: {e}")
    finally:
        is_updating = False

def background_worker():
    while True:
        try:
            update_cache()
        except Exception as e:
            logger.error(f"Фоновая ошибка: {e}")
            global is_updating
            is_updating = False
        time.sleep(UPDATE_EVERY)

threading.Thread(target=background_worker, daemon=True).start()

@app.route('/')
def home():
    return """
    <h1>IPTV Russia Pro Max</h1>
    <p>Агрегатор 1500-3000 российских каналов с проверкой доступности</p>
    <p><b>Возможности:</b></p>
    <ul>
        <li>150+ источников плейлистов</li>
        <li>Умная фильтрация по названию, URL, языку, стране</li>
        <li>Дедупликация каналов (предпочтение HD-версиям)</li>
        <li>Автоматическая категоризация</li>
        <li>Проверка работоспособности каждого канала</li>
        <li>Обновление каждые 30 минут</li>
    </ul>
    <p><a href="/playlist.m3u" style="font-size:22px">Скачать плейлист</a></p>
    <p><a href="/playlist.m3u8" style="font-size:22px">Скачать плейлист (.m3u8)</a></p>
    """

@app.route('/playlist.m3u')
@app.route('/playlist.m3u8')
def playlist():
    with cache_lock:
        response = Response(playlist_cache, mimetype='application/vnd.apple.mpegurl')
        response.headers['Content-Disposition'] = 'attachment; filename="iptv_russia_pro_max.m3u"'
        response.headers['Cache-Control'] = 'public, max-age=900'
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response

@app.route('/status')
def status():
    with cache_lock:
        lines = playlist_cache.split('\n')
        channel_count = sum(1 for line in lines if line.startswith('#EXTINF:'))
        return {
            'channels': channel_count,
            'updating': is_updating,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
        }

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    logger.info(f"Запуск на порту {port}")

    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=port, threads=20)
    except ImportError:
        app.run(host='0.0.0.0', port=port, threaded=True)
