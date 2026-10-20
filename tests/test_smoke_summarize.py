#!/usr/bin/env python3
"""Offline smoke test for rssmw/summarize_description.py (mock mode).

Run: ./test_smoke_summarize.py   (exit 0 = PASS)
Asserts: descriptions replaced with the shared-lib [MOCK] mock summary,
content:encoded unchanged, itunes:* / media:* / enclosure round-trip
unchanged, and the FORCE_ERROR item fully unchanged (title, description,
content, extensions).
"""
import os
import subprocess
import sys
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "src", "feedpipe", "summarize_description.py")
SAMPLE = os.path.join(HERE, "data", "sample_evalsignal.rss")
ORIGINAL = open(SAMPLE, "rb").read()
env = {k: v for k, v in os.environ.items()
       if k not in ("OPENAI_API_KEY", "OPENAI_BASE_URL")}
env.pop("XDG_CACHE_HOME", None)   # deterministic cache location

proc = subprocess.run([sys.executable, SCRIPT], input=ORIGINAL,
                      capture_output=True, env=env)
if proc.returncode != 0:
    print("FAIL: middleware exited %d\nstderr:\n%s"
          % (proc.returncode, proc.stderr.decode()), file=sys.stderr)
    sys.exit(1)

NS = {"content": "http://purl.org/rss/1.0/modules/content/"}
out = etree.fromstring(proc.stdout)
src = etree.fromstring(ORIGINAL)
o_items = out.findall(".//item")
s_items = src.findall(".//item")
errors = []


def check(cond, msg):
    (errors.append(msg) if not cond else None)
    print(("  ok  " if cond else "FAIL  ") + msg)


for i, (o, s) in enumerate(zip(o_items, s_items)):
    o_desc = o.find("description").text or ""
    s_desc = s.find("description").text or ""
    o_ce = o.find("content:encoded", NS)
    s_ce = s.find("content:encoded", NS)

    if o.find("title").text.startswith("FORCE_ERROR"):
        check(o_desc == s_desc, "item %d: FORCE_ERROR description unchanged" % i)
        check(o_ce.text == s_ce.text, "item %d: FORCE_ERROR content:encoded unchanged" % i)
        check(o.find("title").text == s.find("title").text,
              "item %d: FORCE_ERROR title unchanged" % i)
    else:
        expect = "[MOCK] " + s_ce.text[:80]
        check(o_desc == expect,
              "item %d: description replaced with [MOCK] mock of content:encoded" % i)
        check(o_desc != s_desc and o_desc.strip() != "",
              "item %d: description non-empty and differs from original" % i)
    check(o_ce.text == s_ce.text, "item %d: content:encoded byte-identical" % i)
    check(o.find("title").text == s.find("title").text,
          "item %d: title unchanged" % i)
    check(o.find("pubDate").text == s.find("pubDate").text,
          "item %d: pubDate unchanged" % i)
    for tag, sel in (("itunes:subtitle",
                      "{http://www.itunes.com/dtds/podcast-1.0.dtd}subtitle"),
                     ("media:thumbnail",
                      "{http://search.yahoo.com/mrss/}thumbnail"),
                     ("enclosure", "enclosure")):
        o_e, s_e = o.find(sel), s.find(sel)
        if s_e is None:
            continue
        check(o_e is not None and o_e.tag == s_e.tag
              and o_e.attrib == s_e.attrib and o_e.text == s_e.text,
              "item %d: %s round-tripped unchanged" % (i, tag))

# duplicate-body regression: both items sharing body content must be updated
dup_summaries = [o.find("description").text for o in o_items
                 if (o.find("description").text or "").startswith("[MOCK] <p>Sub-200ms")]
check(len(dup_summaries) == 2,
      "both duplicate-body items summarized (found %d)" % len(dup_summaries))
check(len(set(dup_summaries)) == 1,
      "duplicate-body items share the same summary")

print()
if errors:
    print("SMOKE FAIL: %d problem(s)" % len(errors))
    sys.exit(1)
print("SMOKE PASS: descriptions summarized, content:encoded/titles/"
      "extensions untouched, failing item fully unchanged.")
