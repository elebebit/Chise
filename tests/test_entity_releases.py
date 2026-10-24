"""人物最新影片的来源身份、分页、失败和馆藏投影。"""
from __future__ import annotations

import sqlite3
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from peach import web_entity_releases as releases
from peach import settings_file
from peach.jav_cover_fetch import Unavailable
from support.ledger import fresh_ledger
import test_web_e2e as browser_fixture


def actor(name='测试女优', path='/star/abc'):
    return f'<a class="avatar-box" href="{path}"><div class="photo-info"><span>{name}</span></div></a>'


def movie(code='ABW-358', date='2026-10-23', title='测试影片', host='https://www.javbus.com'):
    return (f'<a class="movie-box" href="{host}/{code}"><img title="{title}">'
            f'<div class="photo-info"><date>{code}</date><date>{date}</date></div></a>')


def page(body):
    return f'<html><title>JavBus</title><div id="waterfall">{body}</div></html>'


class JavbusDirectoryTests(unittest.TestCase):
    def test_actor_identity_keeps_ambiguous_names_separate(self):
        rows = releases.parse_actors(page(actor(path='/star/a') + actor(path='/star/b') + actor(path='https://evil.example/star/c')))
        self.assertEqual([row['path'] for row in rows], ['/star/a', '/star/b'])

    def test_movie_page_deduplicates_and_sorts_release_dates(self):
        rows = releases.parse_works(page(movie(date='2026-01-01') + movie('ABW-359') + movie()
                                        + movie('ABW-360', host='https://evil.example')
                                        + '<a id="next" href="/star/a/2">下一页</a>'), '/star/a', 1)
        self.assertEqual([row['code'] for row in rows['items']], ['ABW-359', 'ABW-358'])
        self.assertEqual(rows['next_page'], 2)

    def test_next_page_stays_in_the_selected_actor_and_is_bounded(self):
        for link in ('/star/b/2', '/star/a/1', '/star/a/999'):
            self.assertIsNone(releases.parse_works(page(movie() + f'<a id="next" href="{link}">下一页</a>'), '/star/a', 1)['next_page'])
        self.assertIsNone(releases.parse_works(page(movie() + '<a id="next" href="/star/a/21">下一页</a>'), '/star/a', 20)['next_page'])

    def test_verification_and_unknown_layout_are_failures(self):
        for html in ('<title>Age Verification JavBus</title>', '<title>Just a moment</title>', page('未知页面')):
            with self.subTest(html=html), self.assertRaises(Unavailable):
                releases.parse_works(html, '/star/a', 1)
        self.assertEqual(releases.parse_works(page('沒有影片'), '/star/a', 1)['items'], [])

    def test_actor_addresses_cannot_change_origin_or_add_queries(self):
        for value in ('https://evil.example/star/a', '/star/a?q=x', '/star/a#x', '/star/../a', '//www.javbus.com:443/star/a'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                releases.actor_path(value)


class EntityReleasesTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        root = Path(holder.name).resolve()
        self.connection = sqlite3.connect(fresh_ledger(root))
        self.connection.row_factory = sqlite3.Row
        self.addCleanup(self.connection.close)
        self.connection.execute("INSERT INTO entity(id,kind,canonical_name,normalized_name,created_at,updated_at) VALUES(1,'performer','测试女优','测试女优','t','t')")
        self.connection.execute("INSERT INTO asset(id,location,path,name,medium,code) VALUES(1,'local','R:\\Media\\1.mp4','1.mp4','video','ABW-358')")
        self.connection.commit()
        self.contract = SimpleNamespace(read_connection=lambda: self.connection, cover_root=root / 'covers', follow_secrets_root=root / 'secrets')

    def test_exact_identity_reads_only_the_selected_actor_and_marks_local_works(self):
        before = self.connection.total_changes
        with patch.object(releases, '_page', side_effect=[page(actor()), page(movie())]) as fetch:
            result = releases.q_entity_releases(self.contract, {'id': '1'})
        self.assertEqual(result['actor'], '/star/abc')
        self.assertEqual(result['items'][0]['asset_id'], 1)
        self.assertEqual(fetch.call_args.args[1], releases.BASE + '/star/abc')
        self.assertEqual(self.connection.total_changes, before)

    def test_ambiguous_names_require_selection(self):
        with patch.object(releases, '_page', return_value=page(actor(path='/star/a') + actor(path='/star/b'))) as fetch:
            result = releases.q_entity_releases(self.contract, {'id': '1'})
        self.assertEqual(len(result['actors']), 2)
        self.assertEqual(result['actor'], '')
        self.assertEqual(fetch.call_count, 1)

    def test_selected_actor_pagination_skips_name_search(self):
        with patch.object(releases, '_page', return_value=page(movie())) as fetch:
            result = releases.q_entity_releases(self.contract, {'id': '1', 'actor': '/star/abc', 'page': '2'})
        self.assertEqual(result['items'][0]['code'], 'ABW-358')
        fetch.assert_called_once_with(self.contract, releases.BASE + '/star/abc/2')

    def test_source_failure_is_not_an_empty_success(self):
        with patch.object(releases, '_page', side_effect=Unavailable('需要验证')):
            result = releases.q_entity_releases(self.contract, {'id': '1'})
        self.assertEqual(result['error'], '需要验证')
        self.assertNotIn('items', result)

    def test_invalid_entity_and_page_do_not_request_the_source(self):
        with patch.object(releases, '_page') as fetch:
            for args in ({'id': '1', 'page': '21'}, {'id': '-1'}, {'id': '999'}, {'id': str(2**63)}):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    releases.q_entity_releases(self.contract, args)
            fetch.assert_not_called()

    def test_directory_cache_preserves_session_cookie_and_avoids_repeat_requests(self):
        transport = Mock()
        session = Mock()
        session.get.return_value.text = page(actor())
        url = releases.BASE + '/searchstar/name'
        with patch.object(releases, 'SourceTransport'), \
                patch.object(releases, 'HostLimitedTransport', return_value=transport), \
                patch.object(releases, 'values_for', return_value={'cookie': 'age=verified; existmag=mag'}), \
                patch.object(releases, 'Session', return_value=session):
            first = releases._page(self.contract, url)
            second = releases._page(self.contract, url)
        self.assertEqual(first, second)
        session.get.assert_called_once()
        cookie = session.get.call_args.kwargs['headers']['Cookie']
        self.assertIn('age=verified', cookie)
        self.assertIn('existmag=all', cookie)
        self.assertNotIn('existmag=mag', cookie)
        transport.close.assert_called_once()

    def test_imported_cookie_file_participates_in_directory_requests(self):
        session = Mock()
        session.get.return_value.text = page(actor())
        values = {'cookies_text': '# Netscape HTTP Cookie File\n.javbus.com\tTRUE\t/\tTRUE\t4102444800\tage\tverified\n'}
        with patch.object(releases, 'SourceTransport'), \
                patch.object(releases, 'HostLimitedTransport'), \
                patch.object(releases, 'values_for', return_value=values), \
                patch.object(releases, 'Session', return_value=session):
            releases._page(self.contract, releases.BASE + '/searchstar/name')
        self.assertIn('age=verified', session.get.call_args.kwargs['headers']['Cookie'])

    def test_unrecognized_pages_are_not_cached(self):
        transport = Mock()
        session = Mock()
        session.get.return_value.text = page('未知页面')
        url = releases.BASE + '/searchstar/name'
        with patch.object(releases, 'SourceTransport'), \
                patch.object(releases, 'HostLimitedTransport', return_value=transport), \
                patch.object(releases, 'values_for', return_value={}), \
                patch.object(releases, 'Session', return_value=session):
            for _ in range(2):
                with self.assertRaises(Unavailable):
                    releases._page(self.contract, url)
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(transport.close.call_count, 2)


class EntityReleasesBrowserTests(unittest.TestCase):
    """只用空账本与模拟目录的浏览器夹具，不读取媒体路径。"""

    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which('node')
        cls.chrome = browser_fixture.chrome_executable()
        if not cls.node or not cls.chrome:
            browser_fixture.missing_prerequisite('最新影片浏览器验证需要 Node 与 Chrome')
        root = Path(__file__).resolve().parents[1]
        if not (root / 'frontend/node_modules/playwright-core').is_dir():
            browser_fixture.missing_prerequisite('最新影片浏览器验证需要 frontend 依赖')
        cls.root = Path(tempfile.mkdtemp(prefix='peach-releases-browser-')).resolve()
        cls.data = cls.root / 'data'
        (cls.data / 'database').mkdir(parents=True)
        cls.db = fresh_ledger(cls.data / 'database')
        cls.port = browser_fixture.free_port()
        cls.server = None
        cls.addClassCleanup(lambda: browser_fixture.WebE2ESmokeTests.tearDownClass.__func__(cls))
        config = settings_file.PeachConfig(
            cls.data, cls.data / settings_file.SETTINGS_FILENAME,
            present=True, data_root_found=True, locations={'local': ('R:\\media',)},
            mounts={'local': (str(cls.root / 'media'),)},
            server=settings_file.ServerSettings(port=cls.port))
        settings_file.write(config)
        browser_fixture.WebE2ESmokeTests._start_server.__func__(cls)

    @classmethod
    def _server_log(cls):
        cls.log.flush()
        return (cls.root / 'serve.log').read_text(encoding='utf-8', errors='replace')[-4000:]

    def test_expansion_and_layout_in_desktop_and_mobile_browsers(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, PEACH_E2E_ORIGIN=self.origin, PEACH_E2E_CHROME=self.chrome)
        result = subprocess.run(
            [self.node, '--test', '--test-reporter=tap', '--test-concurrency=1', 'e2e/entity-releases.test.ts'],
            cwd=root / 'frontend', env=env, capture_output=True, text=True, encoding='utf-8', timeout=150)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r'# pass 2\b')
