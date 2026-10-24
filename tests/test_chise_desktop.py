from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from scripts import build_chise_desktop

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('chise_desktop', ROOT / 'desktop_app.py')
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


class DesktopHealthTests(unittest.TestCase):
    def test_only_the_application_health_response_is_ready(self):
        for payload, expected in (({'ok': True, 'service': 'peach-api'}, True),
                                  ({'ok': True, 'service': 'other'}, False),
                                  ({'ok': False, 'service': 'peach-api'}, False),
                                  ([], False)):
            response = io.BytesIO(json.dumps(payload).encode())
            opener = mock.Mock()
            opener.open.return_value = response
            with self.subTest(payload=payload), mock.patch.object(
                    desktop.urllib.request, 'build_opener', return_value=opener):
                self.assertEqual(desktop.is_service_ready(), expected)
                request = opener.open.call_args.args[0]
                self.assertEqual(request.full_url, 'http://127.0.0.1:8900/healthz')

    def test_running_backend_is_reused(self):
        with mock.patch.object(desktop, 'is_service_ready', return_value=True), \
                mock.patch.object(desktop.subprocess, 'Popen') as launch:
            self.assertIsNone(desktop.ensure_backend())
            launch.assert_not_called()

    def test_failed_tray_start_reports_an_error(self):
        with mock.patch.object(desktop, 'is_service_ready', return_value=False), \
                mock.patch.object(desktop.subprocess, 'Popen') as launch:
            launch.return_value.poll.return_value = 1
            with self.assertRaisesRegex(RuntimeError, '托盘已退出'):
                desktop.ensure_backend()

    def test_waiting_for_backend_has_a_deadline(self):
        with mock.patch.object(desktop, 'is_service_ready', return_value=False), \
                mock.patch.object(desktop.subprocess, 'Popen'), \
                mock.patch.object(desktop.time, 'monotonic', side_effect=[0, 21]):
            with self.assertRaisesRegex(RuntimeError, '20 秒'):
                desktop.ensure_backend()


class DesktopBundleTests(unittest.TestCase):
    def test_launcher_resolves_source_from_bundle_location(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary).resolve() / 'with spaces'
            app = build_chise_desktop.build(destination)
            info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
            self.assertEqual(info['CFBundleDisplayName'], 'Chise')
            launcher = app / 'Contents/MacOS' / info['CFBundleExecutable']
            self.assertTrue(launcher.stat().st_mode & 0o111)
            if shutil.which('zsh'):
                result = subprocess.run(['zsh', '-n', str(launcher)], capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            with self.assertRaises(FileExistsError):
                build_chise_desktop.build(destination)


class DesktopFullscreenTests(unittest.TestCase):
    def test_window_registers_fullscreen_setup_before_start(self):
        webview = mock.MagicMock()
        window = webview.create_window.return_value
        before_show = window.events.before_show
        with mock.patch.dict('sys.modules', {'webview': webview}), \
                mock.patch.object(desktop, 'ensure_backend'), \
                mock.patch.object(desktop.Path, 'mkdir'):
            desktop.main()
        before_show.__iadd__.assert_called_once_with(desktop.configure_desktop_window)
        webview.start.assert_called_once()

    def test_macos_window_supports_native_fullscreen_and_identifies_its_pages(self):
        window = mock.MagicMock()
        window.native.collectionBehavior.return_value = 4 | 512
        appkit = mock.Mock(NSWindowCollectionBehaviorFullScreenPrimary=128,
                           NSWindowCollectionBehaviorFullScreenNone=512)
        webkit = mock.Mock(WKUserScriptInjectionTimeAtDocumentStart=0)
        with mock.patch.object(desktop.sys, 'platform', 'darwin'), \
                mock.patch.object(desktop, 'install_background_lifecycle'), \
                mock.patch.dict('sys.modules', {'AppKit': appkit, 'WebKit': webkit}):
            desktop.configure_desktop_window(window)
        window.native.setCollectionBehavior_.assert_called_once_with(4 | 128)
        construct = webkit.WKUserScript.alloc.return_value.initWithSource_injectionTime_forMainFrameOnly_
        construct.assert_called_once_with('window.chiseDesktop = true;', 0, True)
        config = window.gui.BrowserView.instances[window.uid].webview.configuration.return_value
        config.userContentController.return_value.addUserScript_.assert_called_once_with(construct.return_value)

    def test_other_platforms_keep_their_native_fullscreen_settings(self):
        window = mock.MagicMock()
        with mock.patch.object(desktop.sys, 'platform', 'win32'):
            desktop.configure_desktop_window(window)
        window.gui.BrowserView.instances.__getitem__.assert_not_called()


class DesktopBackgroundTests(unittest.TestCase):
    def setUp(self):
        class Delegate:
            @classmethod
            def alloc(cls):
                return cls()

            def init(self):
                return self

            def applicationShouldTerminate_(self, app):
                return app.approve_quit()

        class Browser:
            WindowDelegate = Delegate
            AppDelegate = Delegate
            instances = {}
            app = mock.Mock()
            _shared_app_delegate = None

        self.browser = Browser
        self.window_delegate, self.app_delegate = desktop.background_delegate_types(Browser)
        self.addCleanup(desktop.background_delegate_types.cache_clear)

    def test_close_hides_the_window_and_vetoes_destruction(self):
        window = mock.Mock()
        self.assertFalse(self.window_delegate().windowShouldClose_(window))
        window.orderOut_.assert_called_once_with(None)
        window.close.assert_not_called()

    def test_reopen_restores_hidden_and_minimized_windows(self):
        hidden = mock.Mock()
        hidden.isMiniaturized.return_value = False
        minimized = mock.Mock()
        minimized.isMiniaturized.return_value = True
        self.browser.instances = {'hidden': mock.Mock(window=hidden),
                                  'minimized': mock.Mock(window=minimized)}
        app = mock.Mock()
        self.assertFalse(self.app_delegate().applicationShouldHandleReopen_hasVisibleWindows_(app, False))
        hidden.deminiaturize_.assert_not_called()
        minimized.deminiaturize_.assert_called_once_with(None)
        for window in (hidden, minimized):
            window.makeKeyAndOrderFront_.assert_called_once_with(None)
        app.activateIgnoringOtherApps_.assert_called_once_with(True)

    def test_explicit_quit_keeps_the_host_termination_decision(self):
        app = mock.Mock()
        app.approve_quit.return_value = True
        self.assertTrue(self.app_delegate().applicationShouldTerminate_(app))
        app.approve_quit.assert_called_once_with()

    def test_installed_delegates_are_retained_by_the_host(self):
        window = mock.Mock(uid='main')
        window.gui.BrowserView = self.browser
        instance = mock.Mock()
        self.browser.instances = {'main': instance}
        desktop.install_background_lifecycle(window)
        self.assertIsInstance(instance._windowDelegate, self.window_delegate)
        window.native.setDelegate_.assert_called_once_with(instance._windowDelegate)
        shared = self.browser._shared_app_delegate
        self.assertIsInstance(shared, self.app_delegate)
        desktop.install_background_lifecycle(window)
        self.assertIs(self.browser._shared_app_delegate, shared)
        self.browser.app.setDelegate_.assert_called_with(shared)
