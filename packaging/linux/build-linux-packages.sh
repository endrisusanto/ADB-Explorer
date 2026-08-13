#!/usr/bin/env bash
set -euo pipefail

app_id="adb-file-explorer"
app_name="ADB Explorer"
version="$(tr -d '[:space:]' < VERSION)"
arch_deb="$(dpkg --print-architecture)"
root="build/deb/${app_id}_${version}_${arch_deb}"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
pyinstaller --noconfirm --onefile --windowed --name "$app_id" \
  --hidden-import PyQt6.QtWidgets --hidden-import PyQt6.QtCore --hidden-import PyQt6.QtGui \
  --hidden-import logging.handlers --add-data "assets:assets" --clean --log-level ERROR main.py

rm -rf build/deb build/rpmbuild
install -Dm755 "dist/$app_id" "$root/opt/$app_id/$app_id"
install -Dm644 README.MD "$root/usr/share/doc/$app_id/README.MD"
install -Dm644 assets/logo.svg "$root/usr/share/icons/hicolor/scalable/apps/$app_id.svg"
install -Dm644 /dev/stdin "$root/usr/share/applications/$app_id.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=$app_name
Exec=/opt/$app_id/$app_id
Icon=$app_id
Terminal=false
Categories=Utility;FileManager;
EOF
install -Dm644 /dev/stdin "$root/DEBIAN/control" <<EOF
Package: $app_id
Version: $version
Section: utils
Priority: optional
Architecture: $arch_deb
Depends: android-tools-adb
Maintainer: endrisusanto
Description: Graphical file manager for Android devices over ADB
EOF
dpkg-deb --root-owner-group --build "$root" "dist/${app_id}_${version}_${arch_deb}.deb"

top="$PWD/build/rpmbuild"
mkdir -p "$top"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
cat > "$top/SPECS/$app_id.spec" <<EOF
Name: $app_id
Version: $version
Release: 1%{?dist}
Summary: Graphical file manager for Android devices over ADB
License: MIT
Requires: android-tools

%description
Graphical file manager for Android devices over ADB.

%install
mkdir -p %{buildroot}/opt/$app_id
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/scalable/apps
cp "$PWD/dist/$app_id" %{buildroot}/opt/$app_id/$app_id
cp "$PWD/assets/logo.svg" %{buildroot}/usr/share/icons/hicolor/scalable/apps/$app_id.svg
cat > %{buildroot}/usr/share/applications/$app_id.desktop <<DESKTOP
[Desktop Entry]
Type=Application
Name=$app_name
Exec=/opt/$app_id/$app_id
Icon=$app_id
Terminal=false
Categories=Utility;FileManager;
DESKTOP

%files
/opt/$app_id/$app_id
/usr/share/applications/$app_id.desktop
/usr/share/icons/hicolor/scalable/apps/$app_id.svg
EOF
rpmbuild --define "_topdir $top" -bb "$top/SPECS/$app_id.spec"
cp "$top"/RPMS/*/*.rpm dist/
