#!/usr/bin/env python3
"""Chise 的 macOS 原生窗口，连接本机开发服务。"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

PROJECT_DIR = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8900/"


def is_service_ready(url: str = URL, timeout: float = 1.0) -> bool:
    request = urllib.request.Request(url.rstrip('/') + '/healthz')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            payload = json.load(response)
            return payload.get('ok') is True and payload.get('service') == 'peach-api'
    except (OSError, ValueError, AttributeError):
        return False


def ensure_backend() -> subprocess.Popen | None:
    """连接现有服务，或通过托盘启动服务并等待健康检查。"""
    if is_service_ready():
        return None
    process = subprocess.Popen(
        [str(PROJECT_DIR / '.venv/bin/peach-tray'), '--silent'],
        cwd=PROJECT_DIR,
        start_new_session=True,
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if is_service_ready():
            return process
        if process.poll() is not None:
            raise RuntimeError('Chise 托盘已退出，请查看数据目录中的托盘日志。')
        time.sleep(0.4)
    raise RuntimeError('Chise 服务未能在 20 秒内启动，请检查托盘与 8900 端口。')


def configure_desktop_window(window) -> None:
    """在 Cocoa 主线程配置窗口全屏与网页宿主身份。"""
    if sys.platform != 'darwin':
        return
    import AppKit
    import WebKit

    behavior = window.native.collectionBehavior()
    window.native.setCollectionBehavior_(
        (behavior & ~AppKit.NSWindowCollectionBehaviorFullScreenNone)
        | AppKit.NSWindowCollectionBehaviorFullScreenPrimary
    )
    # pywebview 6.2.1 此时尚未将 WKWebView 设为 NSWindow 的内容视图。
    native_view = window.gui.BrowserView.instances[window.uid].webview
    script = WebKit.WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
        'window.chiseDesktop = true;', WebKit.WKUserScriptInjectionTimeAtDocumentStart, True,
    )
    native_view.configuration().userContentController().addUserScript_(script)


def main() -> None:
    import webview

    ensure_backend()
    # 沿用本机窗口存储目录，保留登录状态和偏好。
    storage = Path.home() / 'Library/Application Support/Peach/webview'
    storage.mkdir(parents=True, exist_ok=True)
    webview.settings['ALLOW_DOWNLOADS'] = True
    window = webview.create_window(
        title='Chise', url=URL, width=1320, height=880,
        min_size=(960, 600), resizable=True, text_select=True,
        zoomable=True, background_color='#121214',
    )
    window.events.before_show += configure_desktop_window
    icon = PROJECT_DIR / 'resources/peach.icns'
    webview.start(private_mode=False, storage_path=str(storage),
                  icon=str(icon) if icon.is_file() else None)


if __name__ == '__main__':
    main()
