#!/usr/bin/env bash
set -euo pipefail

APP_ID="adb-file-explorer"
APP_NAME="ADB Explorer"
VERSION="1.0.0"
ARCH="$(dpkg --print-architecture)"
ROOT="build/deb/${APP_ID}_${VERSION}_${ARCH}"

python3 - <<'PY'
from pathlib import Path
from shutil import rmtree

for path in ("build", "dist", ".venv-build"):
    p = Path(path)
    if p.exists():
        rmtree(p)
PY

if command -v uv >/dev/null 2>&1; then
  uv venv .venv-build
else
  python3 -m venv .venv-build
fi
. .venv-build/bin/activate
if python -m pip --version >/dev/null 2>&1; then
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
else
  uv pip install --python "$PWD/.venv-build/bin/python" -r requirements.txt
fi

pyinstaller \
  --noconfirm \
  --onefile \
  --windowed \
  --name "$APP_ID" \
  --hidden-import PyQt6.QtWidgets \
  --hidden-import PyQt6.QtCore \
  --hidden-import PyQt6.QtGui \
  --hidden-import logging.handlers \
  --add-data "assets:assets" \
  --clean \
  --log-level ERROR \
  main.py

install -Dm755 "dist/$APP_ID" "$ROOT/opt/$APP_ID/$APP_ID"
install -Dm644 README.MD "$ROOT/usr/share/doc/$APP_ID/README.MD"
install -Dm644 assets/logo.svg "$ROOT/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
install -Dm644 /dev/stdin "$ROOT/usr/share/applications/$APP_ID.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Exec=/opt/$APP_ID/$APP_ID
Icon=$APP_ID
Terminal=false
Categories=Utility;FileManager;
EOF
install -Dm644 /dev/stdin "$ROOT/DEBIAN/control" <<EOF
Package: $APP_ID
Version: $VERSION
Section: utils
Priority: optional
Architecture: $ARCH
Depends: android-tools-adb
Maintainer: Local Build <local@example.com>
Description: Graphical file manager for Android devices over ADB
EOF

dpkg-deb --root-owner-group --build "$ROOT" "dist/${APP_ID}_${VERSION}_${ARCH}.deb"
