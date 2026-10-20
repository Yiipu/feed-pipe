#!/usr/bin/env bash
# test_e2e_summarize.sh — real-network e2e for summarize_description.py:
# fetch evalsignal.xyz archive, summarize via the real OpenAI-compatible API.
# Items that fail summarization may keep their original description (design
# constraint 3) and are reported, not fatal.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
URL="https://evalsignal.xyz/archive.xml"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$ROOT/scripts/fetch_feed.sh" "$URL" > "$TMP/feed.xml" 2> "$TMP/fetch.err"
fetch_rc=$?
if [ $fetch_rc -ne 0 ]; then
  echo "E2E FAIL: fetch_feed exited $fetch_rc"; cat "$TMP/fetch.err"; exit 1
fi

uv run summarize-description < "$TMP/feed.xml" > "$TMP/out.xml" 2> "$TMP/sd.err"
sd_rc=$?
if [ $sd_rc -ne 0 ]; then
  echo "E2E FAIL: summarize_description exited $sd_rc"; exit 1
fi

python3 - "$TMP" <<'EOF'
import sys
from lxml import etree
tmp = sys.argv[1]
src = etree.parse(tmp + "/feed.xml")
out = etree.parse(tmp + "/out.xml")
s_items = list(src.iter("item"))
o_items = list(out.iter("item"))
errors = []
if len(o_items) < 1:
    errors.append("no items in output")
changed, kept = [], []
for o, s in zip(o_items, s_items):
    title = o.find("title").text or ""
    o_desc = o.find("description").text or ""
    s_desc = s.find("description").text or ""
    o_ce = o.find("{http://purl.org/rss/1.0/modules/content/}encoded")
    s_ce = s.find("{http://purl.org/rss/1.0/modules/content/}encoded")
    if not o_desc.strip() and s_desc.strip():
        errors.append("empty description where original had text: %r" % title)
    if o_ce is None or s_ce is None or o_ce.text != s_ce.text:
        errors.append("content:encoded changed: %r" % title)
    if o.find("title").text != s.find("title").text:
        errors.append("title changed: %r" % title)
    (changed if o_desc != s_desc else kept).append(title)
if errors:
    print("E2E FAIL:"); [print("  " + e) for e in errors]; sys.exit(1)
print("E2E PASS: %d items (%d summarized, %d kept original)" %
      (len(o_items), len(changed), len(kept)))
for t in changed: print("  -> %s" % t[:80])
for t in kept: print("  (kept) %s" % t[:80])
EOF
py_rc=$?
echo "--- stderr (per-item failures) ---"
cat "$TMP/sd.err"
exit $py_rc
