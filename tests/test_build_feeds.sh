#!/usr/bin/env bash
# test_build_feeds.sh — offline smoke test for build_feeds.sh (mock mode, no network/API).
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
unset OPENAI_API_KEY   # force mock mode
pass=0; fail=0
check() { # check <desc> <cmd...>
  local desc="$1"; shift
  if "$@" >/dev/null 2>&1; then echo "PASS: $desc"; pass=$((pass+1));
  else echo "FAIL: $desc"; fail=$((fail+1)); fi
}
# file://tests/data/x.rss relative to the repo root; build_feeds.sh resolves venv entry points via PATH.
check "build_feeds.sh exits 0" env "$ROOT/scripts/build_feeds.sh" --conf "$ROOT/tests/feeds.test.conf"
check "out/showerthoughts.xml exists" test -f out/showerthoughts.xml
check "out/evalsignal.xml exists" test -f out/evalsignal.xml
check "showerthoughts.xml parses as XML" python3 -c "from lxml import etree; etree.parse('out/showerthoughts.xml')"
check "evalsignal.xml parses as XML" python3 -c "from lxml import etree; etree.parse('out/evalsignal.xml')"
check "reddit titles [MOCK]-translated" bash -c "grep -q '\[MOCK\]' out/showerthoughts.xml"
check "evalsignal descriptions [MOCK]-summarized" bash -c "grep -q '\[MOCK\]' out/evalsignal.xml"
check "reddit sample extension elements survived (itunes/media)" bash -c "grep -q 'itunes:subtitle' out/showerthoughts.xml && grep -q 'media:thumbnail' out/showerthoughts.xml"
check "evalsignal itunes:subtitle survived" bash -c "grep -q 'itunes:subtitle' out/evalsignal.xml"

# normalize_atom_ids regression: relative Atom ids become absolute IRIs
check "showerthoughts feed id now absolute" bash -c "! grep -q '<id>/r/' out/showerthoughts.xml"
check "entry ids absolute (contain ://)" python3 - <<'EOF'
from lxml import etree
ns = {"a": "http://www.w3.org/2005/Atom"}
root = etree.parse("out/showerthoughts.xml").getroot()
ids = [root.find("a:id", ns).text] + [e.find("a:id", ns).text for e in root.findall("a:entry", ns)]
assert all("://" in i for i in ids), ids
EOF
uv run normalize-atom-ids < tests/data/sample_relative_ids.rss > /tmp/nrm_atom.xml
uv run normalize-atom-ids < tests/data/sample_evalsignal.rss > /tmp/nrm_rss.xml
check "tiny Atom sample ids normalized" python3 - <<'EOF'
from lxml import etree
ns = {"a": "http://www.w3.org/2005/Atom"}
root = etree.parse("/tmp/nrm_atom.xml").getroot()
assert root.find("a:id", ns).text == "https://www.reddit.com/r/test/top.rss", root.find("a:id", ns).text
ids = [e.find("a:id", ns).text for e in root.findall("a:entry", ns)]
assert ids == ["https://www.reddit.com/r/test/comments/a1/",
               "https://www.reddit.com/r/test/t3_a2"], ids
EOF
check "non-Atom input passes through byte-identical" cmp -s tests/data/sample_evalsignal.rss /tmp/nrm_rss.xml
check "titles unchanged by normalization" bash -c "grep -q '<title>First test entry</title>' /tmp/nrm_atom.xml"
echo "----------------------------------------"
if [ $fail -eq 0 ]; then echo "RESULT: PASS ($pass checks)"; exit 0
else echo "RESULT: FAIL ($fail/$((pass+fail)) checks failed)"; exit 1; fi
