#!/usr/bin/env bash
# Fail if any tracked Python needs a newer interpreter than the supported floor.
# Ubuntu 22.04 and Jetson (JetPack 6) ship Python 3.10, so that is the floor.
set -euo pipefail
cd "$(dirname "$0")/.."

venv="$(mktemp -d)"
trap 'rm -rf "$venv"' EXIT
python3 -m venv "$venv"
"$venv/bin/pip" install --quiet --disable-pip-version-check vermin==1.9.2

mapfile -t files < <(git ls-files | while read -r f; do
  case "$f" in
    *.py) echo "$f" ;;
    *) head -c 64 "$f" 2>/dev/null | grep -q '^#!.*python' && echo "$f" || true ;;
  esac
done)
"$venv/bin/vermin" --no-tips --violations -t=3.10- --eval-annotations "${files[@]}"
