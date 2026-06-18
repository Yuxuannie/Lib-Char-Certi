#!/usr/bin/env bash
# Build the delivery ZIP for Lib-Char-Certi.
#
# Uses `git archive`, so it ships ONLY committed files and honours the
# `export-ignore` rules in .gitattributes (legacy trees, tests, internal docs,
# etc. are excluded). Commit your work before running.
#
# Usage:  scripts/make_delivery.sh  [output-dir]
set -euo pipefail

cd "$(dirname "$0")/.."

version="$(grep -m1 '^version' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/')"
out_dir="${1:-dist}"
mkdir -p "$out_dir"
zip_path="${out_dir}/Lib-Char-Certi-v${version}.zip"

if [ -n "$(git status --porcelain)" ]; then
  echo "WARNING: working tree has uncommitted changes; git archive ships HEAD only." >&2
fi

git archive --format=zip --prefix="Lib-Char-Certi/" -o "$zip_path" HEAD

echo "Wrote $zip_path"
echo "--- contents (top level) ---"
unzip -l "$zip_path" | awk '{print $4}' | sed -n 's#^Lib-Char-Certi/\([^/]*\).*#\1#p' | sort -u
