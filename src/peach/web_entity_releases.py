"""人物页的 JavBus 作品目录：按需读取公开列表，身份选择留在本次查询。"""
from __future__ import annotations

import re
import time
from http.cookies import SimpleCookie
from urllib.parse import quote, urljoin, urlsplit
from urllib.request import Request

from bs4 import BeautifulSoup
import httpx

from .catalog_rules import normalise_code_key
from .entities import normalize_entity_name, resolve_entity_id
from .jav_cache import PublicSnapshots
from .jav_cover_fetch import HostLimitedTransport, NotFound, Unavailable
from .scraping_access import SourcePaused, SourceTransport, cookie_jar, values_for
from .sources import JAVBUS
from .sources.base import Session

BASE = 'https://www.javbus.com'
ACTOR_PATH = re.compile(r'^/(?:ja/)?(?:uncensored/)?star/[A-Za-z0-9]+$')


def actor_path(value):
    """只接受来源站内的演员地址。"""
    parts = urlsplit(urljoin(BASE, str(value or '')))
    if (parts.scheme != 'https' or parts.netloc != 'www.javbus.com'
            or parts.query or parts.fragment or not ACTOR_PATH.fullmatch(parts.path)):
        raise ValueError('请选择有效的 JavBus 演员')
    return parts.path


def document(html):
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    if re.search(r'Age Verification|Just a moment|Access denied|登入|登錄|登录', title, re.I):
        raise Unavailable('JavBus 需要验证，请在采集设置中配置 JavBus Cookie 后重试')
    if not soup.select_one('#waterfall'):
        raise Unavailable('未取得 JavBus 作品目录，请稍后重试')
    return soup


def parse_actors(html):
    soup = document(html)
    found = {}
    for box in soup.select('a.avatar-box'):
        try:
            path = actor_path(box.get('href'))
        except ValueError:
            continue
        image = box.select_one('img')
        name = box.select_one('.photo-info span')
        name = name.get_text(' ', strip=True) if name else (image.get('title', '') if image else '')
        if name:
            found[path] = {'path': path, 'name': name, 'url': BASE + path}
    if not found and not re.search(r'沒有|没有|無結果|无结果|No (?:results|stars|actresses)', soup.get_text(), re.I):
        raise Unavailable('未取得 JavBus 演员列表，请稍后重试')
    return list(found.values())


def parse_works(html, path, page):
    soup = document(html)
    items = {}
    for box in soup.select('a.movie-box'):
        dates = box.select('date')
        if not dates:
            continue
        code = dates[0].get_text(strip=True)
        key = normalise_code_key(code)
        href = urlsplit(urljoin(BASE, box.get('href', '')))
        if (not key or href.scheme != 'https' or href.netloc != 'www.javbus.com'
                or normalise_code_key(href.path.rsplit('/', 1)[-1]) != key):
            continue
        image = box.select_one('img')
        title = image.get('title', '') if image else ''
        released = dates[1].get_text(strip=True) if len(dates) > 1 else ''
        items[key] = {'code': code, 'title': title, 'release_date': released
                      if re.fullmatch(r'\d{4}-\d{2}-\d{2}', released) else '',
                      'url': BASE + href.path}
    if not items and not re.search(r'沒有|没有|無結果|无结果|No (?:results|videos|movies)', soup.get_text(), re.I):
        raise Unavailable('未取得 JavBus 影片列表，请稍后重试')
    next_link = soup.select_one('a#next')
    target = urlsplit(urljoin(BASE, next_link.get('href', ''))) if next_link else None
    next_path = target.path if target and target.scheme == 'https' and target.netloc == 'www.javbus.com' else ''
    return {'items': sorted(items.values(), key=lambda row: (row['release_date'], row['code']), reverse=True),
            'next_page': page + 1 if page < 20 and next_path == f'{path}/{page + 1}' else None}


def _page(contract, url):
    cache = PublicSnapshots(contract.cover_root.parent / 'javbus-directory')
    with cache.acquire(url):
        stored = cache.load(url)
        if stored and isinstance(stored.value, str) and time.time() - stored.saved < 3600:
            return stored.value
        raw = SourceTransport(contract.follow_secrets_root, max_requests=6,
                              max_bytes=6 * 1024 * 1024, max_seconds=25)
        transport = HostLimitedTransport(raw, 2.0)
        try:
            cookies = SimpleCookie()
            request = Request(url)
            cookie_jar(values_for(contract.follow_secrets_root, 'javbus'), 'javbus').add_cookie_header(request)
            cookies.load(request.get_header('Cookie', ''))
            cookies['existmag'] = 'all'
            page = Session(transport, deadline=time.monotonic() + 25).get(
                url, config=JAVBUS, headers={'Cookie': '; '.join(f'{key}={value.coded_value}' for key, value in cookies.items())})
            text = page.text
            parts = urlsplit(url)
            if '/searchstar/' in parts.path:
                parse_actors(text)
            else:
                path, _, number = parts.path.rpartition('/')
                parse_works(text, path if number.isdecimal() else parts.path,
                            int(number) if number.isdecimal() else 1)
            cache.save(url, text, None)
            return text
        finally:
            transport.close()


def q_entity_releases(contract, args):
    """查询目录并投影馆藏命中，不写入实体或馆藏。"""
    try:
        entity_id = int(args.get('id') or 0)
        page = int(args.get('page') or 1)
    except (ValueError, TypeError):
        raise ValueError('人物或页码无效') from None
    if not 0 < entity_id < 2**63 or not 1 <= page <= 20:
        raise ValueError('人物或页码无效')
    with contract.read_connection() as connection:
        identity = resolve_entity_id(connection, entity_id)
        person = connection.execute("SELECT canonical_name FROM entity WHERE id=? AND kind='performer'", (identity,)).fetchone()
        if person is None:
            raise ValueError('未找到这位女优')
        names = [person['canonical_name']] + [row[0] for row in connection.execute(
            'SELECT alias FROM entity_alias WHERE entity_id=? ORDER BY alias', (identity,))]
        refs = [row[0] for row in connection.execute(
            "SELECT external_id FROM entity_external_ref WHERE entity_id=? AND provider='javbus' AND external_kind='performer'",
            (identity,))]
    try:
        selected = args.get('actor') or ''
        actors = []
        if selected:
            selected = actor_path(selected)
        elif len(refs) == 1 and re.fullmatch(r'[A-Za-z0-9]+', refs[0]):
            selected = '/star/' + refs[0]
        else:
            actors = parse_actors(_page(contract, BASE + '/searchstar/' + quote(names[0], safe='')))
            keys = {normalize_entity_name(name) for name in names}
            exact = [row for row in actors if normalize_entity_name(row['name']) in keys]
            if len(exact) == 1:
                selected = exact[0]['path']
            else:
                return {'actors': actors, 'items': [], 'next_page': None, 'actor': '',
                        'source_url': BASE + '/searchstar/' + quote(names[0], safe='')}
        result = parse_works(_page(contract, BASE + selected + (f'/{page}' if page > 1 else '')), selected, page)
        with contract.read_connection() as connection:
            local = {}
            for row in connection.execute("SELECT id,code FROM asset WHERE medium='video' AND disposal IS NULL AND code IS NOT NULL ORDER BY id"):
                local.setdefault(normalise_code_key(row['code']), row['id'])
        for row in result['items']:
            row['asset_id'] = local.get(normalise_code_key(row['code']))
        return dict(result, actors=actors, actor=selected, source_url=BASE + selected)
    except (OSError, NotFound, Unavailable, TimeoutError, SourcePaused, httpx.HTTPError) as error:
        return {'error': str(error), 'source_url': BASE + '/searchstar/' + quote(names[0], safe='')}
