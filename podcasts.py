"""Public podcast notes and, for 股癌, public forum posts.

Feeds were checked against the Apple Podcasts lookup on 2026-11-15.
Forum reads use one short request per source and stop when a site blocks them.
"""

import html
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import requests
import streamlit as st

from data_access import stock_choices

CACHE_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT = (5, 8)
EPISODE_LIMIT = 3
USER_AGENT = 'TaiwanStockRadar/0.11 (public RSS and forum reader)'

# Add a show by appending a name, host, and a feed URL checked against
# the Apple Podcasts lookup (collectionId is the Apple id).
SHOWS = [
    {
        'name': 'Gooaye 股癌',
        'host': '謝孟恭',
        'feed': 'https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml',
        'apple_id': '1500839292',
        'forum': True,
    },
    {
        'name': '兆華與股惑仔',
        'host': '李兆華',
        'feed': 'https://feeds.soundon.fm/podcasts/91be014b-9f55-4bf3-a910-b232eda82d11.xml',
        'apple_id': '1590806478',
    },
    {
        'name': '韭菜之聲',
        'host': '奎叔',
        'feed': 'https://feed.firstory.me/rss/user/cmmlxzdca1gpj01y9fau407u4',
        'apple_id': '1884511201',
    },
]

FORUM_TERMS = ('股癌', 'gooaye', '謝孟恭')
PTT_SEARCH = 'https://www.ptt.cc/bbs/Stock/search?q=股癌'
MOBILE01_SEARCH = 'https://www.mobile01.com/googlesearch.php?keyword=股癌'
DCARD_SEARCH = 'https://www.dcard.tw/service/api/v2/search/posts?query=股癌&limit=5'


def _session():
    http = requests.Session()
    http.headers['User-Agent'] = USER_AGENT
    return http


def _blocked(response):
    if response.status_code in {401, 403, 429, 503}:
        return True
    sample = response.text[:800].lower()
    return 'just a moment' in sample or 'access denied' in sample or 'cf-browser-verification' in sample


def _lines(raw):
    text = raw or ''
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</(p|div|h\d|tr|li)>', '\n', text)
    text = re.sub(r'(?i)<li[^>]*>', '\n• ', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = html.unescape(text).replace('\xa0', ' ')
    lines = []
    for line in text.splitlines():
        line = re.sub(r'\s+', ' ', line).strip()
        if not line or line.startswith('Hosting provided by'):
            continue
        if line.startswith(('節目內容純屬', '—— 以上為', '以上為 Firstory', '以上為 Podcast 廣告', '我能賺錢，相信你們也能')):
            continue
        if re.fullmatch(r'https?://\S+', line):
            continue
        if re.fullmatch(r'(Apple|Spotify|YouTube|Youtube|Instagram|Facebook|Telegram)(\s*\|\s*(Apple|Spotify|YouTube|Youtube|Instagram|Facebook|Telegram))*', line):
            continue
        lines.append(line)
    return lines


def _same_text(left, right):
    def compact(value):
        return re.sub(r'\W+', '', value or '')
    return compact(left) == compact(right) and compact(left) != ''


def _bullet_text(line):
    if line.startswith(('•', '・', '- ', '* ')):
        return line[1:].strip() if line[0] in '•・' else line[2:].strip()
    return ''


def key_points(title, raw, limit=4):
    lines = _lines(raw)
    if lines and (_same_text(lines[0], title) or lines[0] in title):
        lines = lines[1:]
    bullets = [text for text in (_bullet_text(line) for line in lines) if len(text) >= 4]
    plain = [line for line in lines if not _bullet_text(line)]
    chosen = bullets or plain
    limit = limit if bullets else min(limit, 2)
    points = []
    for line in chosen:
        line = line.strip()
        if len(line) < 4:
            continue
        if len(line) > 140:
            line = line[:139] + '…'
        points.append(line)
        if len(points) >= limit:
            break
    return points, '\n'.join(lines)[:2000]


def _published(value):
    if not value:
        return None, ''
    try:
        moment = parsedate_to_datetime(value)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        local = moment.astimezone(ZoneInfo('Asia/Taipei'))
        return local, local.strftime('%Y-%m-%d')
    except (TypeError, ValueError, OverflowError):
        return None, value.strip()[:32]


def parse_feed(payload):
    import xml.etree.ElementTree as ET

    root = ET.fromstring(payload)
    channel = root.find('channel')
    if channel is None:
        return []
    episodes = []
    for item in channel.findall('item'):
        title = (item.findtext('title') or '').strip()
        if not title:
            continue
        link = (item.findtext('link') or '').strip()
        if not link.startswith('http'):
            guid = (item.findtext('guid') or '').strip()
            link = guid if guid.startswith('http') else link
        moment, label = _published(item.findtext('pubDate'))
        description = item.findtext('description') or ''
        if not description.strip():
            description = item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or ''
        points, notes = key_points(title, description)
        episodes.append({
            'title': title,
            'link': link,
            'date': label,
            'points': points,
            'notes': notes,
            '_moment': moment or datetime.min.replace(tzinfo=timezone.utc),
        })
    episodes.sort(key=lambda episode: episode['_moment'], reverse=True)
    for episode in episodes:
        episode.pop('_moment', None)
    return episodes[:EPISODE_LIMIT]


def fetch_feed(url):
    try:
        response = _session().get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        episodes = parse_feed(response.content)
        if not episodes:
            return {'ok': False, 'note': '節目表是空的。', 'episodes': []}
        return {'ok': True, 'note': '', 'episodes': episodes}
    except Exception:
        return {'ok': False, 'note': '暫時無法取得節目表。', 'episodes': []}


class _PTTListParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.posts = []
        self._classes = []
        self._in_title = False
        self._in_link = False
        self._in_date = False
        self._href = ''
        self._title = []
        self._date = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'div':
            css = attributes.get('class', '')
            self._classes.append(css)
            if 'title' in css.split():
                self._in_title = True
                self._href = ''
                self._title = []
            elif css == 'date':
                self._in_date = True
                self._date = []
        elif tag == 'a' and self._in_title:
            self._in_link = True
            self._href = attributes.get('href', '')

    def handle_endtag(self, tag):
        if tag == 'a':
            self._in_link = False
        elif tag == 'div' and self._classes:
            css = self._classes.pop()
            if 'title' in css.split():
                title = ''.join(self._title).strip()
                if title and self._href and '刪除' not in title:
                    self.posts.append({'title': title, 'href': self._href, 'date': ''})
                self._in_title = False
                self._in_link = False
            elif css == 'date' and self.posts and self._in_date:
                self.posts[-1]['date'] = ''.join(self._date).strip()
                self._in_date = False

    def handle_data(self, data):
        if self._in_link:
            self._title.append(data)
        elif self._in_date:
            self._date.append(data)


def parse_ptt_list(page):
    parser = _PTTListParser()
    parser.feed(page)
    return parser.posts


def _relevant(title):
    folded = title.lower()
    return any(term.lower() in folded for term in FORUM_TERMS)


def _excerpt_from_article(page):
    match = re.search(r'id="main-content"[^>]*>(.*)', page, flags=re.S | re.I)
    if not match:
        return ''
    body = match.group(1)
    body = re.split(r'\n--\n|※ 發信站', html.unescape(re.sub(r'<[^>]+>', '\n', body)))[0]
    kept = []
    for line in body.splitlines():
        line = re.sub(r'\s+', ' ', line).strip()
        if not line or line.startswith(('作者', '標題', '時間', '看板')):
            continue
        kept.append(line)
        if len(kept) >= 2:
            break
    excerpt = ' '.join(kept)
    return excerpt[:160] + ('…' if len(excerpt) > 160 else '')


def fetch_ptt():
    source = 'PTT 股票板'
    try:
        response = _session().get(PTT_SEARCH, cookies={'over18': '1'}, timeout=REQUEST_TIMEOUT)
    except requests.Timeout:
        return {'source': source, 'ok': False, 'note': '連線逾時。', 'posts': []}
    except requests.RequestException:
        return {'source': source, 'ok': False, 'note': '連線失敗。', 'posts': []}
    if _blocked(response):
        return {'source': source, 'ok': False, 'note': '網站要求瀏覽器驗證，沒有取到文章。', 'posts': []}
    if response.status_code != 200:
        return {'source': source, 'ok': False, 'note': '暫時無法取得。', 'posts': []}
    matches = [post for post in parse_ptt_list(response.text) if _relevant(post['title'])][:3]
    posts = []
    http = _session()
    for post in matches:
        href = post['href']
        link = href if href.startswith('http') else 'https://www.ptt.cc' + href
        excerpt = ''
        try:
            article = http.get(link, cookies={'over18': '1'}, timeout=REQUEST_TIMEOUT)
            if article.status_code == 200 and not _blocked(article):
                excerpt = _excerpt_from_article(article.text)
        except requests.RequestException:
            excerpt = ''
        posts.append({
            'title': post['title'],
            'date': post['date'],
            'link': link,
            'excerpt': excerpt,
            'source': source,
        })
    note = '' if posts else '沒有最近的相關文章。'
    return {'source': source, 'ok': True, 'note': note, 'posts': posts}


def fetch_mobile01():
    source = 'Mobile01'
    try:
        response = _session().get(MOBILE01_SEARCH, timeout=REQUEST_TIMEOUT)
    except requests.Timeout:
        return {'source': source, 'ok': False, 'note': '連線逾時。', 'posts': []}
    except requests.RequestException:
        return {'source': source, 'ok': False, 'note': '連線失敗。', 'posts': []}
    if _blocked(response) or response.status_code != 200:
        return {'source': source, 'ok': False, 'note': '拒絕連線。', 'posts': []}
    posts = []
    for href, title in re.findall(r'href="([^"]*topicdetail\.php[^"]*)"[^>]*>([^<]+)', response.text):
        title = html.unescape(re.sub(r'\s+', ' ', title)).strip()
        if not _relevant(title):
            continue
        link = href if href.startswith('http') else 'https://www.mobile01.com/' + href.lstrip('/')
        posts.append({'title': title, 'date': '', 'link': link, 'excerpt': '', 'source': source})
        if len(posts) >= 3:
            break
    if not posts:
        return {'source': source, 'ok': False, 'note': '公開搜尋頁沒有附上文章列表。', 'posts': []}
    return {'source': source, 'ok': True, 'note': '', 'posts': posts}


def fetch_dcard():
    source = 'Dcard'
    try:
        response = _session().get(
            DCARD_SEARCH,
            headers={'Accept': 'application/json'},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        return {'source': source, 'ok': False, 'note': '連線逾時。', 'posts': []}
    except requests.RequestException:
        return {'source': source, 'ok': False, 'note': '連線失敗。', 'posts': []}
    if _blocked(response) or response.status_code != 200:
        return {'source': source, 'ok': False, 'note': '拒絕連線。', 'posts': []}
    try:
        payload = response.json()
    except ValueError:
        return {'source': source, 'ok': False, 'note': '回應不是文章列表。', 'posts': []}
    rows = payload if isinstance(payload, list) else payload.get('posts') or payload.get('items') or []
    posts = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get('title') or '').strip()
        if not title or not _relevant(title + ' ' + str(row.get('excerpt') or '')):
            continue
        forum = row.get('forumAlias') or row.get('forumId') or 'stock'
        link = f"https://www.dcard.tw/f/{forum}/p/{row.get('id')}"
        _, date = _published(str(row.get('createdAt') or ''))
        excerpt = re.sub(r'\s+', ' ', str(row.get('excerpt') or '')).strip()
        posts.append({
            'title': title,
            'date': date,
            'link': link,
            'excerpt': excerpt[:160],
            'source': source,
        })
        if len(posts) >= 3:
            break
    note = '' if posts else '沒有最近的相關文章。'
    return {'source': source, 'ok': True, 'note': note, 'posts': posts}


def fetch_forums():
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda fn: fn(), (fetch_ptt, fetch_mobile01, fetch_dcard)))
    return results


def find_mentions(text, choices):
    if not text or not choices:
        return []
    found = []
    seen = set()
    for match in re.finditer(r'(?<![A-Za-z\d])(\d{4})(?!\d)', text):
        code = match.group(1)
        if code not in choices or code in seen:
            continue
        before = text[max(0, match.start() - 12):match.start()]
        after = text[match.end():match.end() + 3].lstrip()
        if '://' in before or before.endswith('/') or after.startswith(('年', '/')):
            continue
        if before.endswith(('$', '＄')):
            continue
        if code.startswith(('19', '20')):
            company = choices[code]
            window = text[max(0, match.start() - len(company) - 2):match.end() + len(company) + 2]
            if company not in window:
                continue
        seen.add(code)
        found.append(f'{choices[code]} {code}')
    names = sorted(
        ((name, code) for code, name in choices.items() if name and len(name) >= 2),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    matched = []
    for name, code in names:
        if len(found) >= 6 or code in seen:
            continue
        start = text.find(name)
        if start < 0:
            continue
        if any(name != longer and name in longer for longer in matched):
            continue
        if len(name) < 3:
            window = text[max(0, start - 8):start + len(name) + 8]
            if code not in window:
                continue
        seen.add(code)
        matched.append(name)
        found.append(f'{name} {code}')
    return found[:6]


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def cached_feed(url):
    return fetch_feed(url)


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def cached_forums():
    return fetch_forums()


def _mentions_for(text):
    try:
        choices = stock_choices()
    except Exception:
        return []
    return find_mentions(text, choices)


def _show_episode(episode, point_limit):
    date = f' · {episode["date"]}' if episode['date'] else ''
    if episode['link']:
        st.markdown(f'[{episode["title"]}]({episode["link"]}){date}')
    else:
        st.markdown(f'{episode["title"]}{date}')
    for point in episode['points'][:point_limit]:
        st.markdown(f'- {point}')
    mentions = _mentions_for(episode['title'] + '\n' + episode['notes'])
    if mentions:
        st.caption('提到 ' + '、'.join(mentions))


def render_podcast_card():
    with st.container(border=True):
        st.subheader('財經 Podcast 重點')
        st.caption('最新一集的標題與簡介。股癌另附公開論壇。不是投資建議。')
        for show in SHOWS:
            result = cached_feed(show['feed'])
            st.markdown(f'**{show["name"]}**')
            if not result['ok']:
                st.caption(result['note'])
                continue
            episode = result['episodes'][0]
            _show_episode(episode, 1)
        st.markdown('**股癌論壇討論**')
        for source in cached_forums():
            if not source['ok']:
                st.caption(f'{source["source"]}：{source["note"]}')
                continue
            if not source['posts']:
                st.caption(f'{source["source"]}：{source["note"]}')
                continue
            post = source['posts'][0]
            date = f' · {post["date"]}' if post['date'] else ''
            st.markdown(f'[{post["title"]}]({post["link"]}) · {post["source"]}{date}')
            if post['excerpt']:
                st.caption(post['excerpt'])


def render_podcasts():
    st.header('財經 Podcast 重點')
    st.caption('三個節目的公開 RSS。重點取自簡介的條列或前幾句，不是逐字稿，也不是投資建議。')
    for show in SHOWS:
        st.subheader(show['name'])
        st.caption(show['host'])
        result = cached_feed(show['feed'])
        if not result['ok']:
            st.warning(show['name'] + '：' + result['note'])
            continue
        for episode in result['episodes']:
            _show_episode(episode, 4)
    st.subheader('股癌論壇討論')
    st.caption('PTT 股票板（公開頁，附成年確認）、Mobile01 與 Dcard 各查一次。不登入，也不繞過網站驗證。')
    for source in cached_forums():
        if not source['ok'] or not source['posts']:
            st.caption(f'{source["source"]}：{source["note"]}')
            continue
        for post in source['posts']:
            date = f' · {post["date"]}' if post['date'] else ''
            st.markdown(f'[{post["title"]}]({post["link"]}) · {post["source"]}{date}')
            if post['excerpt']:
                st.caption(post['excerpt'])
            mentions = _mentions_for(post['title'] + '\n' + post['excerpt'])
            if mentions:
                st.caption('提到 ' + '、'.join(mentions))
