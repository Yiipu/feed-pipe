#!/usr/bin/env bash
# test_e2e.sh — real-network end-to-end test: fetch Reddit feed, translate via
# the real OpenAI-compatible API (env: OPENAI_BASE_URL/OPENAI_API_KEY/MODEL).
# Items that fail translation may stay original (design constraint 3) and are
# reported, not fatal.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
URL="https://www.reddit.com/r/Showerthoughts/top.rss"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$ROOT/scripts/fetch_feed.sh" "$URL" > "$TMP/feed.xml" 2> "$TMP/fetch.err"
fetch_rc=$?
if [ $fetch_rc -ne 0 ]; then
  echo "E2E FAIL: fetch_feed exited $fetch_rc"; cat "$TMP/fetch.err"; exit 1
fi

uv run translate-title < "$TMP/feed.xml" > "$TMP/out.xml" 2> "$TMP/tt.err"
tt_rc=$?
if [ $tt_rc -ne 0 ]; then
  echo "E2E FAIL: translate_title exited $tt_rc"; exit 1
fi

python3 - "$TMP" <<'EOF'
import sys
from lxml import etree
ATOM = "{http://www.w3.org/2005/Atom}"
tmp = sys.argv[1]
src = etree.parse(tmp + "/feed.xml")
out = etree.parse(tmp + "/out.xml")
o_entries = list(out.iter(ATOM + "entry"))
s_entries = list(src.iter(ATOM + "entry"))
errors = []
if len(o_entries) < 1:
    errors.append("no entries in output")
translated, kept = [], []
for o, s in zip(o_entries, s_entries):
    title = o.find(ATOM + "title").text or ""
    body = o.find(ATOM + "content")
    first = (body.text or "").split("\n", 1)[0]
    if not title.strip(): errors.append("empty title: %r" % first)
    if not first.strip(): errors.append("empty first body line")
    if title == first: kept.append(title)
    else: translated.append(title)
if errors:
    print("E2E FAIL:"); [print("  " + e) for e in errors]; sys.exit(1)
print("E2E PASS: %d items (%d translated, %d kept original)" %
      (len(o_entries), len(translated), len(kept)))
for t in translated: print("  -> " + t)
for t in kept: print("  (kept) " + t)
EOF
py_rc=$?
echo "--- stderr (cache hits/misses, per-item failures) ---"
cat "$TMP/tt.err"
exit $py_rc
