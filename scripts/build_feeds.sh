#!/usr/bin/env bash
# build_feeds.sh [--conf <file>] — build all feeds listed in feeds.conf.
# Per feed: fetch | pipeline > out/<name>.xml. One failing feed doesn't stop the rest.
# Exit 0 if at least one feed built, 1 only if all fail.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONF="$ROOT/feeds.conf"
if [ "${1:-}" = "--conf" ]; then CONF="${2:?usage: build_feeds.sh [--conf <file>]}"; shift 2; fi
CONF_DIR="$(cd "$(dirname "$CONF")" && pwd)"; CONF="$CONF_DIR/$(basename "$CONF")"
mkdir -p "$ROOT/out"
[ -d "$ROOT/.venv/bin" ] && PATH="$ROOT/.venv/bin:$PATH"
cd "$ROOT"
built=0; failed=0
while IFS='|' read -r name url pipeline; do
  case "$name" in ''|'#'*) continue;; esac
  src_ok=0
  if [ "${url%%://*}" = "file" ]; then
    cat "$ROOT/${url#file://}" > "$name.xml.tmp" && src_ok=1
  elif "$ROOT/scripts/fetch_feed.sh" "$url" > "$name.xml.tmp"; then src_ok=1; fi
  if [ $src_ok -eq 0 ] || ! sh -c "$pipeline" < "$name.xml.tmp" 2>>build.log | tee "$name.xml.tmp.pipe" > /dev/null; then
    echo "build_feeds: $name: fetch/pipeline failed, keeping previous output" >&2; rm -f "$name.xml.tmp" "$name.xml.tmp.pipe"; failed=$((failed+1)); continue
  fi
  if ! python3 -c "from lxml import etree; import sys; etree.parse(sys.argv[1])" "$name.xml.tmp.pipe" 2>/dev/null; then
    echo "build_feeds: $name: output is not valid XML, discarding" >&2; rm -f "$name.xml.tmp" "$name.xml.tmp.pipe"; failed=$((failed+1)); continue
  fi
  mkdir -p out && mv "$name.xml.tmp.pipe" "out/$name.xml"; rm -f "$name.xml.tmp"; built=$((built+1))
  echo "build_feeds: $name OK"
done < "$CONF"
echo "build_feeds: summary: $built built, $failed failed"
[ $built -gt 0 ] && exit 0 || exit 1
