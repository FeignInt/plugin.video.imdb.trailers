# -*- coding: utf-8 -*-
"""
    IMDB Trailers Kodi Addon
    Copyright (C) 2018 gujal

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

# Imports
import re
import sys
import datetime
import json
from kodi_six import xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs
import base64
from bs4 import BeautifulSoup, SoupStrainer
import requests
import requests_cache
import six
from six.moves import urllib

# HTMLParser() depreciated in Python 3.4 and removed in Python 3.9
if sys.version_info >= (3,4,0):
    import html
    _html_parser = html
else:
    from six.moves import html_parser
    _html_parser = html_parser.HTMLParser()

# DEBUG
DEBUG = False

_addon = xbmcaddon.Addon()
_addonID = _addon.getAddonInfo('id')
_plugin = _addon.getAddonInfo('name')
_version = _addon.getAddonInfo('version')
_icon = _addon.getAddonInfo('icon')
_fanart = _addon.getAddonInfo('fanart')
_language = _addon.getLocalizedString
_settings = _addon.getSetting
_addonpath = 'special://profile/addon_data/{}/'.format(_addonID)

force_mode = _settings("forceViewMode") == "true"
if force_mode:
    menu_mode = int(_settings('MenuMode'))
    view_mode = int(_settings('VideoMode'))

if not xbmcvfs.exists(_addonpath):
    xbmcvfs.mkdir(_addonpath)

CACHE_FILE = xbmc.translatePath(_addonpath + 'requests_cache')
requests_cache.install_cache(CACHE_FILE, backend='sqlite', expire_after=int(_settings('timeout')) * 3600)

CONTENT_URL = 'https://www.imdb.com/trailers/'
SHOWING_URL = 'https://www.imdb.com/movies-in-theaters/'
COMING_URL = 'https://www.imdb.com/movies-coming-soon/{}-{:02}'
ID_URL = 'https://www.imdb.com/_json/video/{}'
DETAILS_PAGE = "https://m.imdb.com/videoplayer/{}"
USER_AGENT = 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.17 (KHTML, like Gecko) Chrome/24.0.1312.57 Safari/537.17'
quality = int(_settings("video_quality")[:-1])
LOGINFO = xbmc.LOGINFO if six.PY3 else xbmc.LOGNOTICE

if not xbmcvfs.exists(_addonpath + 'settings.xml'):
    _addon.openSettings()


class Main(object):
    def __init__(self):
        if ('action=list3' in sys.argv[2]):
            self.list_contents3()
        elif ('action=list2' in sys.argv[2]):
            self.list_contents2()
        elif ('action=play_id' in sys.argv[2]):
            self.play_id()
        elif ('action=play' in sys.argv[2]):
            self.play()
        elif ('action=search' in sys.argv[2]):
            self.search()
        elif ('action=clear' in sys.argv[2]):
            self.clear_cache()
        else:
            self.main_menu()

    def main_menu(self):
        if DEBUG:
            self.log('main_menu()')
        category = [{'title': _language(30201), 'key': 'showing'},
                    {'title': _language(30202), 'key': 'coming'},
                    {'title': _language(30208), 'key': 'trending'},
                    {'title': _language(30209), 'key': 'anticipated'},
                    {'title': _language(30210), 'key': 'popular'},
                    {'title': _language(30211), 'key': 'recent'},
                    {'title': _language(30206), 'key': 'search'},
                    {'title': _language(30207), 'key': 'cache'}]
        for i in category:
            listitem = xbmcgui.ListItem(i['title'])
            listitem.setArt({'thumb': _icon,
                             'fanart': _fanart,
                             'icon': _icon})

            if i['key'] == 'cache':
                url = sys.argv[0] + '?' + urllib.parse.urlencode({'action': 'clear'})
            elif i['key'] == 'search':
                url = sys.argv[0] + '?' + urllib.parse.urlencode({'action': 'search'})
            elif i['key'] == 'showing' or i['key'] == 'coming':
                url = sys.argv[0] + '?' + urllib.parse.urlencode({'action': 'list2',
                                                                  'key': i['key']})
            else:
                url = sys.argv[0] + '?' + urllib.parse.urlencode({'action': 'list3',
                                                                  'key': i['key']})

            xbmcplugin.addDirectoryItems(int(sys.argv[1]), [(url, listitem, True)])

        # Sort methods and content type...
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.setContent(int(sys.argv[1]), 'addons')
        if force_mode:
            xbmc.executebuiltin('Container.SetViewMode({})'.format(menu_mode))
        # End of directory...
        xbmcplugin.endOfDirectory(int(sys.argv[1]), True)

    def clear_cache(self):
        """
        Clear the cache database.
        """
        msg = 'Cached Data has been cleared'
        requests_cache.get_cache().clear()
        xbmcgui.Dialog().notification(_plugin, msg, _icon, 3000, False)

    def search(self):
        keyboard = xbmc.Keyboard()
        keyboard.setHeading('Search IMDb by Title')
        keyboard.doModal()
        if keyboard.isConfirmed():
            search_text = urllib.parse.quote(keyboard.getText())
        else:
            search_text = ''
        if len(search_text) > 2:
            url = 'https://www.imdb.com/find?q={}&s=tt'.format(search_text)
            page_data = fetch(url).text
            tlink = SoupStrainer('table', {'class': 'findList'})
            soup = BeautifulSoup(page_data, "html.parser", parse_only=tlink)
            items = soup.find_all('tr')
            for item in items:
                imdb_id = item.find('a').get('href').split('/')[2]
                title = item.text.strip()
                icon = item.find('img')['src']
                poster = icon.split('_')[0] + 'jpg'
                listitem = xbmcgui.ListItem(title)
                listitem.setArt({'thumb': poster,
                                 'icon': icon,
                                 'poster': poster,
                                 'fanart': _fanart})

                listitem.setInfo(type='video',
                                 infoLabels={'title': title,
                                             'imdbnumber': imdb_id})

                listitem.setProperty('IsPlayable', 'true')
                url = sys.argv[0] + '?' + urllib.parse.urlencode({'action': 'play_id',
                                                                  'imdb': imdb_id})
                xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, listitem, False)

            # Sort methods and content type...
            xbmcplugin.setContent(int(sys.argv[1]), 'movies')
            xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_UNSORTED)
            xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_VIDEO_TITLE)
            if force_mode:
                xbmc.executebuiltin('Container.SetViewMode({})'.format(view_mode))
            # End of directory...
            xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=True)
        else:
            msg = 'Need atleast 3 characters'
            xbmcgui.Dialog().notification(_plugin, msg, _icon, 3000, False)
            return

    def list_contents2(self):
        if DEBUG:
            self.log('content_list2()')
        if self.parameters('key') == 'showing':
            page_data = fetch(SHOWING_URL).text
            tlink = SoupStrainer('div', {'id': 'main'})
        else:
            year, month, _ = datetime.date.today().isoformat().split('-')
            page_data = ''
            nyear = int(year)
            for i in range(4):
                nmonth = int(month) + i
                if nmonth > 12:
                    nmonth = nmonth - 12
                    nyear = int(year) + 1
                url = COMING_URL.format(nyear, nmonth)
                page_data += fetch(url).text
            tlink = SoupStrainer('div', {'class': 'list detail'})

        mdiv = BeautifulSoup(page_data, "html.parser", parse_only=tlink)
        videos = mdiv.find_all('table')
        h = _html_parser

        for video in videos:
            vdiv = video.find('a', {'itemprop': 'trailer'})
            if vdiv:
                videoId = vdiv.get('href').split('?')[0].split('/')[-1]
                plot = h.unescape(video.find(class_='outline').text).strip()
                tdiv = video.find(class_='image')
                icon = tdiv.find('img')['src']
                title = tdiv.find('img')['title']
                # imdb = tdiv.find('a')['href'].split('/')[-2]
                poster = icon.split('_')[0] + 'jpg'
                infos = video.find_all(class_='txt-block')
                director = []
                directors = infos[0].find_all('a')
                for name in directors:
                    director.append(name.text)
                cast = []
                stars = infos[1].find_all('a')
                for name in stars:
                    cast.append(name.text)
                labels = {'title': title,
                          'plot': plot,
                          # 'imdbnumber': imdb,
                          'director': director,
                          'cast': cast}
                try:
                    year = int(re.findall(r'\((\d{4})', title)[0])
                    title = re.sub(r'\s\(\d{4}\)', '', title)
                    labels.update({'title': title, 'year': year})
                except IndexError:
                    pass

                listitem = xbmcgui.ListItem(title)
                listitem.setArt({'thumb': poster,
                                 'icon': icon,
                                 'poster': poster,
                                 'fanart': _fanart})

                listitem.setInfo(type='video', infoLabels=labels)

                listitem.setProperty('IsPlayable', 'true')
                url = sys.argv[0] + '?' + urllib.parse.urlencode({'action': 'play',
                                                                  'videoid': videoId})
                xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, listitem, False)

        # Sort methods and content type...
        xbmcplugin.setContent(int(sys.argv[1]), 'movies')
        xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_VIDEO_TITLE)
        if force_mode:
            xbmc.executebuiltin('Container.SetViewMode({})'.format(view_mode))
        # End of directory...
        xbmcplugin.endOfDirectory(int(sys.argv[1]), True)

    def list_contents3(self):
        if DEBUG:
            self.log('content_list3()')

        key = self.parameters('key')
        videos = fetchdata3(key)
        for video in videos:
            if DEBUG:
                self.log(repr(video))
            if key == 'trending' or key == 'anticipated' or key == 'popular':
                title = video.get('titleText').get('text')
                imdb = video.get('id')
                videoId = video.get('latestTrailer').get('id')
                duration = video.get('latestTrailer').get('runtime').get('value')
                name = video.get('latestTrailer').get('name').get('value')
                plot = video.get('latestTrailer').get('description').get('value') if video.get('latestTrailer').get('description') else ''
                if plot == name or len(plot) == 0:
                    try:
                        plot = video.get('plot').get('plotText').get('plainText')
                    except AttributeError:
                        pass
                fanart = video.get('latestTrailer').get('thumbnail').get('url', '')
                try:
                    poster = video.get('primaryImage').get('url', '')
                except AttributeError:
                    poster = fanart
                try:
                    year = video.get('releaseDate').get('year')
                except AttributeError:
                    year = ''
            elif key == 'recent':
                try:
                    title = video.get('primaryTitle').get('titleText').get('text')
                except AttributeError:
                    title = ''
                try:
                    imdb = video.get('primaryTitle').get('id')
                except AttributeError:
                    imdb = ''
                videoId = video.get('id')
                duration = video.get('runtime').get('value')
                name = video.get('name').get('value')
                plot = video.get('description').get('value') if video.get('description') else ''
                if plot == name or len(plot) == 0:
                    try:
                        plot = video.get('primaryTitle').get('plot').get('plotText').get('plainText')
                    except AttributeError:
                        pass
                fanart = video.get('thumbnail').get('url', '')
                try:
                    poster = video.get('primaryTitle').get('primaryImage').get('url', '')
                except AttributeError:
                    poster = fanart
                try:
                    year = video.get('primaryTitle').get('releaseDate').get('year')
                except AttributeError:
                    year = ''

            if title in name:
                name = name.replace(title, '').strip()
            if len(name) > 0:
                if six.PY2:
                    name = name.encode('utf8')
                    title = title.encode('utf8')
                title = '{0} [COLOR cyan][I]{1}[/I][/COLOR]'.format(title, name)
            labels = {'title': title,
                      'plot': plot,
                      'duration': duration,
                      'imdbnumber': imdb}
            if year:
                labels.update({'year': year})

            listitem = xbmcgui.ListItem(title)
            listitem.setArt({'thumb': poster,
                             'icon': poster,
                             'poster': poster,
                             'fanart': fanart})

            listitem.setInfo(type='video', infoLabels=labels)

            listitem.setProperty('IsPlayable', 'true')
            url = sys.argv[0] + '?' + urllib.parse.urlencode({'action': 'play',
                                                              'videoid': videoId})
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), url, listitem, False)

        # Sort methods and content type...
        xbmcplugin.setContent(int(sys.argv[1]), 'movies')
        xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(int(sys.argv[1]), xbmcplugin.SORT_METHOD_VIDEO_TITLE)
        if force_mode:
            xbmc.executebuiltin('Container.SetViewMode({})'.format(view_mode))
        # End of directory...
        xbmcplugin.endOfDirectory(int(sys.argv[1]), True)

    def get_video_url(self, video_id):
        if DEBUG:
            self.log('get_video_url()')
        data = {"type": "VIDEO_PLAYER",
                "subType": "FORCE_LEGACY",
                "id": video_id}
        if six.PY3:
            data = base64.b64encode(json.dumps(data).encode())
            vidurl = 'https://m.imdb.com/ve/data/VIDEO_PLAYBACK_DATA?key={}'.format(data.decode())
        else:
            data = base64.b64encode(json.dumps(data))
            vidurl = 'https://m.imdb.com/ve/data/VIDEO_PLAYBACK_DATA?key={}'.format(data)
        details = fetch(vidurl).text
        if quality == 480 or '"definition":"auto"' not in details.lower():
            vids = re.findall(r'definition":"(\d+)p".+?url":"([^"]+)', details, re.IGNORECASE)
            vids.sort(key=lambda x: int(x[0]), reverse=True)
            if DEBUG:
                self.log('Found %s videos' % len(vids))
            for qual, vid in vids:
                if int(qual) <= quality:
                    if DEBUG:
                        self.log('videoURL: %s' % vid)
                    videoUrl = vid.replace('\\u002F', '/').replace('\\/', '/')
                    if DEBUG:
                        self.log('cleaned videoURL: %s' % videoUrl)
                    return videoUrl
        else:
            vid = re.findall(r'definition":"auto".+?url":"([^"]+)', details, re.IGNORECASE)[0]
            hls = fetch(vid).text
            hlspath = re.findall(r'(http.+/)', vid)[0]
            quals = re.findall(r'BANDWIDTH=([^,]+)[^x]+x(\d+).+\n([^\n]+)', hls)
            if DEBUG:
                self.log('Found %s qualities' % len(quals))
            quals = sorted(quals, key=lambda x: int(x[0]), reverse=True)
            if DEBUG:
                self.log('Found %s qualities after sort' % len(quals))
            for _, qual, svid in quals:
                if int(qual) <= quality:
                    videoUrl = hlspath + svid
                    if DEBUG:
                        self.log('videoURL: %s' % videoUrl)
                    return videoUrl

    def play(self):
        if DEBUG:
            self.log('play()')
        title = xbmc.getInfoLabel("ListItem.Title")
        thumbnail = xbmc.getInfoImage("ListItem.Thumb")
        plot = xbmc.getInfoLabel("ListItem.Plot")
        # only need to add label, icon and thumbnail, setInfo() and addSortMethod() takes care of label2
        listitem = xbmcgui.ListItem(title)
        listitem.setArt({'thumb': thumbnail})

        # set the key information
        listitem.setInfo('video', {'title': title,
                                   'plot': plot,
                                   'plotOutline': plot})

        listitem.setPath(self.get_video_url(self.parameters('videoid')))
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, listitem=listitem)

    def play_id(self):
        if DEBUG:
            self.log('play_id()')
        iurl = ID_URL.format(self.parameters('imdb'))
        if DEBUG:
            self.log('IMDBURL: %s' % iurl)
        try:
            details = fetch(iurl).json()
        except ValueError:
            msg = 'No Trailers available'
            xbmcgui.Dialog().notification(_plugin, msg, _icon, 3000, False)
        video_list = details['playlists'][self.parameters('imdb')]['listItems']
        if len(video_list) > 0:
            videoid = video_list[0]['videoId']
            if DEBUG:
                self.log('VideoID: %s' % videoid)
            title = xbmc.getInfoLabel("ListItem.Title")
            thumbnail = xbmc.getInfoImage("ListItem.Thumb")
            listitem = xbmcgui.ListItem(title)
            listitem.setArt({'thumb': thumbnail})
            # set the key information
            listitem.setInfo('video', {'title': title})

            encodings = details['videoMetadata'][videoid]['encodings']
            vids = []
            for item in encodings:
                if item['mimeType'] == 'video/mp4':
                    qual = "360p" if item["definition"] == "SD" else item["definition"]
                    vids.append((qual[:-1], item["videoUrl"]))
            vids.sort(key=lambda elem: int(elem[0]), reverse=True)
            for qual, vid in vids:
                if int(qual) <= quality:
                    if DEBUG:
                        self.log('videoURL: %s' % vid)
                    videoUrl = vid
                    break

            listitem.setPath(videoUrl)
            xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, listitem=listitem)
        else:
            msg = 'No Trailers available'
            xbmcgui.Dialog().notification(_plugin, msg, _icon, 3000, False)

    def parameters(self, arg):
        _parameters = urllib.parse.parse_qs(urllib.parse.urlparse(sys.argv[2]).query)
        return _parameters[arg][0]

    def log(self, description):
        xbmc.log("[ADD-ON] '{} v{}': {}".format(_plugin, _version, description), LOGINFO)


def fetch(url):
    headers = {'User-Agent': USER_AGENT,
               'Referer': 'https://www.imdb.com/',
               'Origin': 'https://www.imdb.com'}
    if 'graphql' in url:
        headers.update({'content-type': 'application/json'})
    data = requests.get(url, headers=headers)
    return data


def fetchdata3(key):
    api_url = 'https://graphql.prod.api.imdb.a2z.com/'
    vpar = {'limit': 100}
    if key == 'trending':
        query_pt1 = ("query TrendingTitles($limit: Int!, $paginationToken: String) {"
                     "  trendingTitles(limit: $limit, paginationToken: $paginationToken) {"
                     "    titles {"
                     "      latestTrailer {"
                     "        ...TrailerVideoMeta"
                     "      }"
                     "      ...TrailerTitleMeta"
                     "    }"
                     "    paginationToken"
                     "  }"
                     "}")
        ptoken = "60"
        opname = "TrendingTitles"
    elif key == 'recent':
        query_pt1 = ("query RecentVideos($limit: Int!, $paginationToken: String, $queryFilter: RecentVideosQueryFilter!) {"
                     "  recentVideos(limit: $limit, paginationToken: $paginationToken, queryFilter: $queryFilter) {"
                     "    videos {"
                     "      ...TrailerVideoMeta"
                     "      primaryTitle {"
                     "        ...TrailerTitleMeta"
                     "      }"
                     "    }"
                     "    paginationToken"
                     "  }"
                     "}")
        ptoken = "blank"
        opname = "RecentVideos"
        vpar.update({'queryFilter': {"contentTypes": ["TRAILER"]}})
    elif key == 'anticipated' or key == 'popular':
        query_pt1 = ("query PopularTitles($limit: Int!, $paginationToken: String, $queryFilter: PopularTitlesQueryFilter!) {"
                     "  popularTitles(limit: $limit, paginationToken: $paginationToken, queryFilter: $queryFilter) {"
                     "    titles {"
                     "      latestTrailer {"
                     "        ...TrailerVideoMeta"
                     "      }"
                     "      ...TrailerTitleMeta"
                     "    }"
                     "    paginationToken"
                     "  }"
                     "}")
        ptoken = "blank"
        opname = "PopularTitles"
        d1 = datetime.date.today().isoformat()
        if key == 'anticipated':
            vpar.update({'queryFilter': {"releaseDateRange": {"start": d1}}})
        else:
            vpar.update({'queryFilter': {"releaseDateRange": {"end": d1}}})

    query_pt2 = ("fragment TrailerTitleMeta on Title {"
                 "  id"
                 "  titleText {"
                 "    text"
                 "  }"
                 "  plot {"
                 "    plotText {"
                 "      plainText"
                 "    }"
                 "  }"
                 "  primaryImage {"
                 "    url"
                 "  }"
                 "  releaseDate {"
                 "    year"
                 "  }"
                 "}"
                 "fragment TrailerVideoMeta on Video {"
                 "  id"
                 "  name {"
                 "    value"
                 "  }"
                 "  runtime {"
                 "    value"
                 "  }"
                 "  description {"
                 "    value"
                 "  }"
                 "  thumbnail {"
                 "    url"
                 "  }"
                 "}")

    qstr = urllib.parse.quote(query_pt1 + query_pt2, "(")
    items = []

    while len(items) < 200 and ptoken:
        if ptoken != "blank":
            vpar.update({"paginationToken": ptoken})

        vtxt = urllib.parse.quote(json.dumps(vpar).replace(" ", ""))
        r = fetch("{0}?operationName={1}&query={2}&variables={3}".format(api_url, opname, qstr, vtxt))
        data = r.json().get('data')

        if key == 'trending' or key == 'anticipated' or key == 'popular':
            if key == 'trending':
                data = data.get('trendingTitles')
            elif key == 'anticipated' or key == 'popular':
                data = data.get('popularTitles')
            titles = data.get('titles')
            for title in titles:
                if title.get('latestTrailer'):
                    items.append(title)
        elif key == 'recent':
            data = data.get('recentVideos')
            titles = data.get('videos')
            items.extend(titles)

        if len(titles) < 1:
            ptoken = None
        else:
            ptoken = data.get('paginationToken')

    return items
