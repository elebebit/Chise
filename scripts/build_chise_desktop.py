"""生成依赖当前源码与 venv 的 Chise macOS 窗口入口。"""
from __future__ import annotations

import os
from pathlib import Path
import plistlib
import shlex
import shutil

ROOT = Path(__file__).resolve().parents[1]


def build(destination: Path) -> Path:
    app = destination.resolve() / 'Chise.app'
    macos = app / 'Contents/MacOS'
    resources = app / 'Contents/Resources'
    macos.mkdir(parents=True, exist_ok=False)
    resources.mkdir()
    relative_root = os.path.relpath(ROOT, macos)
    launcher = macos / 'Chise'
    launcher.write_text(
        '#!/bin/zsh\nset -eu\n'
        f'CHISE_ROOT="$(cd "$(dirname "$0")"/{shlex.quote(relative_root)} && pwd)"\n'
        'cd "$CHISE_ROOT"\n'
        'exec "$CHISE_ROOT/.venv/bin/python3" "$CHISE_ROOT/desktop_app.py"\n',
        encoding='utf-8',
    )
    launcher.chmod(0o755)
    shutil.copy2(ROOT / 'resources/peach.icns', resources / 'peach.icns')
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleName': 'Chise', 'CFBundleDisplayName': 'Chise',
        'CFBundleIdentifier': 'io.github.elebebit.chise.desktop',
        'CFBundleExecutable': 'Chise', 'CFBundleIconFile': 'peach',
        'CFBundlePackageType': 'APPL', 'NSHighResolutionCapable': True,
    }))
    return app


if __name__ == '__main__':
    print(build(ROOT / 'dist/chise-desktop'))
