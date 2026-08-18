#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
bump="${1:-patch}"
version_file="VERSION"
current="$(git tag --list 'v[0-9]*.[0-9]*.[0-9]*' | sed 's/^v//' | sort -V | tail -n1)"
current="${current:-$(tr -d '[:space:]' < "$version_file")}"
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
if git rev-parse -q --verify "refs/tags/v$next" >/dev/null; then
  echo "tag v$next already exists" >&2
  exit 1
fi
printf '%s\n' "$next" > "$version_file"

python -m py_compile main.py handler.py ui/*.py
git add .
git commit -m "Release v$next"
git tag -a "v$next" -m "Release v$next"
git push origin "v$next"
git push origin HEAD:main || echo "warning: main push failed; v$next tag was pushed and should trigger release" >&2
