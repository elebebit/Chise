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
        before_show.__iadd__.assert_called_once_with(desktop.enable_media_fullscreen)
        webview.start.assert_called_once()

    def test_macos_webview_enables_element_fullscreen(self):
        window = mock.MagicMock()
        preferences = window.gui.BrowserView.instances[window.uid].webview.configuration.return_value.preferences.return_value
        with mock.patch.object(desktop.sys, 'platform', 'darwin'):
            desktop.enable_media_fullscreen(window)
        preferences.setElementFullscreenEnabled_.assert_called_once_with(True)

    def test_other_platforms_keep_their_native_fullscreen_settings(self):
        window = mock.MagicMock()
        with mock.patch.object(desktop.sys, 'platform', 'win32'):
            desktop.enable_media_fullscreen(window)
        window.gui.BrowserView.instances.__getitem__.assert_not_called()

    def test_webkit_without_element_fullscreen_reports_the_limitation(self):
        window = mock.MagicMock()
        window.gui.BrowserView.instances[window.uid].webview.configuration.return_value.preferences.return_value = object()
        with mock.patch.object(desktop.sys, 'platform', 'darwin'), self.assertLogs(level='WARNING'):
            desktop.enable_media_fullscreen(window)
