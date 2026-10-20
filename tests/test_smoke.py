#!/usr/bin/env python3
"""Offline smoke test for rssmw/translate_title.py (mock mode, no API key).

Run: ./test_smoke.py   (exit 0 = PASS)
Feeds sample_reddit.rss through the middleware with OPENAI_API_KEY unset,
then asserts:
  - titles translated ([MOCK] prefix), original preserved as first body line
  - the failing item (title starts with FORCE_ERROR) keeps title AND body
  - itunes:subtitle / media:thumbnail / enclosure round-trip unchanged
"""
import os
import subprocess
import sys
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "src", "feedpipe", "translate_title.py")
SAMPLE = os.path.join(HERE, "data", "sample_reddit.rss")

ORIGINAL = open(SAMPLE, "rb").read()

env = dict(os.environ)
env.pop("OPENAI_API_KEY", None)  # force mock mode
env.pop("XDG_CACHE_HOME", None)  # deterministic, default cache location

proc = subprocess.run([sys.executable, SCRIPT], input=ORIGINAL,
                      capture_output=True, env=env)
if proc.returncode != 0:
    print("FAIL: middleware exited %d\nstderr:\n%s"
          % (proc.returncode, proc.stderr.decode()), file=sys.stderr)
    sys.exit(1)

out = etree.fromstring(proc.stdout)
ATOM = "{http://www.w3.org/2005/Atom}"
ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
MEDIA = "{http://search.yahoo.com/mrss/}"
NS = {"atom": "http://www.w3.org/2005/Atom",
      "content": "http://purl.org/rss/1.0/modules/content/"}

entries = out.findall("atom:entry", NS)
src_entries = etree.fromstring(ORIGINAL).findall("atom:entry", NS)
errors = []


def check(cond, msg):
    (errors.append(msg) if not cond else None)
    print(("  ok  " if cond else "FAIL  ") + msg)


for entry in entries:
    title = entry.find(ATOM + "title").text
    body = entry.find(ATOM + "content")
    orig_title = body.text.split("\n", 1)[0]

    if title.startswith("FORCE_ERROR"):
        check(title == src_entries[entries.index(entry)].find(ATOM + "title").text,
              "failing item title unchanged: %r" % title)
        check(body.text == src_entries[entries.index(entry)].find(ATOM + "content").text,
              "failing item body byte-identical")
        continue

    check("[MOCK] " + orig_title == title,
          "translated title, original as first body line: %r" % title)
    check(body.text.split("\n", 1)[1] == src_entries[entries.index(entry)].find(ATOM + "content").text,
          "original body content preserved below first line")


# duplicate-title regression: both entries sharing a title must be updated
dups = [e for e in entries
        if e.find(ATOM + "title").text ==
        "[MOCK] Shower thoughts are just ideas that had nowhere better to go"]
check(len(dups) == 2, "both duplicate-title entries translated (found %d)" % len(dups))
for e in dups:
    check(e.find(ATOM + "content").text.startswith(
              "Shower thoughts are just ideas that had nowhere better to go\n"),
          "duplicate entry body has original title as first line")

# pass-through of extension elements, byte-for-byte on the text/attrs
for i, (e, s) in enumerate(zip(entries, src_entries)):
    for tag, sel in (("itunes:subtitle", ITUNES + "subtitle"),
                     ("media:thumbnail", MEDIA + "thumbnail"),
                     ("enclosure", "enclosure")):
        o, x = e.find(sel), s.find(sel)
        if o is None and x is None:
            continue
        check(o is not None and x is not None,
              "entry %d: %s present in both" % (i + 1, tag))
        check((o is not None and o.tag == x.tag and o.attrib == x.attrib
               and o.text == x.text),
              "entry %d: %s round-tripped unchanged" % (i + 1, tag))

print()
if errors:
    print("SMOKE FAIL: %d problem(s)" % len(errors))
    sys.exit(1)
print("SMOKE PASS: titles translated, originals preserved as first body line, "
      "extension elements round-tripped unchanged.")
