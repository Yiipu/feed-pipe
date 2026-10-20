#!/usr/bin/env python3
"""rssmw/normalize-atom-ids: make Atom feed/entry ids absolute IRIs.

Reads XML on stdin, writes XML on stdout. Non-Atom input passes through
byte-identical. For an Atom feed, a base IRI is derived from
<link rel="alternate"> (path stripped), else <link rel="self">, else an
already-absolute feed <id>; relative feed/entry ids are then rewritten:
feed id := base + relative id; entry id := its <link rel="alternate"> href
if present, else base + "/" + id. Nothing else is touched. If no base can
be determined, input passes through unchanged.
"""
import sys

from feedpipe import lib

ATOM = lib.ATOM


def is_relative(iri: str) -> bool:
    return "://" not in iri


def find_link(el, rel: str):
    for link in el.findall("{%s}link" % ATOM):
        if link.get("rel") == rel and link.get("href"):
            return link.get("href")
    return None


def main() -> int:
    data = sys.stdin.buffer.read()
    tree = lib.parse_xml(data, "normalize-atom-ids")
    if tree is None:
        return 2
    root = tree if not hasattr(tree, "getroot") else tree.getroot()
    if root.tag != "{%s}feed" % ATOM:
        sys.stdout.buffer.write(data)
        return 0

    feed_id = root.find("{%s}id" % ATOM)
    base = None
    alt = find_link(root, "alternate")
    if alt and not is_relative(alt):
        host = "/".join(alt.split("/")[:3])          # scheme://host
        base = alt.rsplit("/", 1)[0]                 # .../path minus last segment
    elif find_link(root, "self"):
        sl = find_link(root, "self")
        host = "/".join(sl.split("/")[:3])
        base = sl.rsplit("/", 1)[0]
    elif feed_id is not None and not is_relative(feed_id.text or ""):
        host = "/".join(feed_id.text.split("/")[:3])
        base = feed_id.text.rsplit("/", 1)[0]
    if base is None:
        sys.stdout.buffer.write(data)
        return 0
    base = base.rstrip("/")

    if feed_id is not None and is_relative(feed_id.text or ""):
        fid = feed_id.text
        feed_id.text = (host + fid if fid.startswith("/")
                        else base + "/" + fid.lstrip("/"))

    for entry in root.findall("{%s}entry" % ATOM):
        eid = entry.find("{%s}id" % ATOM)
        if eid is None or not is_relative(eid.text or ""):
            continue
        permalink = find_link(entry, "alternate")
        eid.text = permalink if permalink else base + "/" + eid.text
    lib.write_xml(tree)
    return 0


if __name__ == "__main__":
    sys.exit(main())
