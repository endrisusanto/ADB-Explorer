#!/usr/bin/env bash
set -euo pipefail

bump="${1:-patch}"
version_file="VERSION"
current="$(tr -d '[:space:]' < "$version_file")"
IFS=. read -r major minor patch <<< "$current"

case "$bump" in
  major) major=$((major + 1)); minor=0; patch=0 ;;
  minor) minor=$((minor + 1)); patch=0 ;;
  patch) patch=$((patch + 1)) ;;
  v*) next="${bump#v}" ;;
  *.*.*) next="$bump" ;;
  *) echo "usage: $0 [patch|minor|major|1.2.3|v1.2.3]" >&2; exit 2 ;;
esac

next="${next:-$major.$minor.$patch}"
printf '%s\n' "$next" > "$version_file"

python -m py_compile main.py handler.py ui/*.py
git add .
git commit -m "Release v$next"
git tag -a "v$next" -m "Release v$next"
git push
git push origin "v$next"
