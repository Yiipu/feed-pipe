#!/usr/bin/env python3
"""rssmw/translate-title: RSS middleware that translates item titles to Chinese.

Reads full RSS/Atom XML on stdin, writes full RSS XML on stdout.
All unprocessed XML (namespaces, extensions, enclosures, ...) is preserved.

Env:
  OPENAI_BASE_URL   base URL of an OpenAI-compatible API (no default)
  OPENAI_API_KEY    API key; if unset -> offline mock mode ("[MOCK] " prefix)
  MODEL_TRANSLATE   model name (default: cn:deepseek-v4.1-flash;
                    falls back to MODEL, then the default)

Cache: $XDG_CACHE_HOME/rssmw/translate-title.json (or ~/.cache/...) keyed by
sha256 of the source title. Per-item failure => item kept unchanged, logged
to stderr, exit stays 0. Non-zero exit only on unreadable/broken XML.
"""
import os
import sys

from lxml import etree

from feedpipe import lib

NAME = "translate-title"
SYSTEM_PROMPT = ("Translate the given RSS item title to Chinese. "
                 "Output ONLY the translation, no quotes, no explanations.")
ATOM = lib.ATOM
CONTENT_NS = lib.CONTENT_NS


def body_elements(item) -> list:
    """Body-bearing elements of an item/entry, in priority order."""
    bodies = []
    content = item.find("{%s}encoded" % CONTENT_NS)
    if content is not None:
        bodies.append(content)
    for tag in ("content", "summary" if item.tag == "{%s}entry" % ATOM
                else "description"):
        el = (item.find("{%s}%s" % (ATOM, tag)) if item.tag == "{%s}entry" % ATOM
              else item.find(tag))
        if el is not None:
            bodies.append(el)
    return bodies


def prepend_first_line(el, line: str) -> None:
    """Put `line\\n` before whatever the element's text content starts with."""
    old = el.text or ""
    el.text = line + "\n" + old if old.strip() else line + "\n"


def main() -> int:
    tree = lib.parse_xml(sys.stdin.buffer.read(), NAME)
    if tree is None:
        return 2

    items = lib.find_items(tree)
    titles = []
    for item in items:
        t = item.find("title") or item.find("{%s}title" % ATOM)
        if t is not None and (t.text or "").strip():
            titles.append(t.text)

    def apply(original: str, translated: str) -> None:
        for item in items:
            t = item.find("title") or item.find("{%s}title" % ATOM)
            if t is not None and t.text == original:
                t.text = translated
                bodies = body_elements(item)
                if bodies:
                    prepend_first_line(bodies[0], original)

    lib.run_pipeline(titles, NAME, "translation",
                     lambda s: lib.chat_complete(
                         s, SYSTEM_PROMPT, NAME,
                         lib.pick_model("MODEL_TRANSLATE", "cn:deepseek-v4.1-flash")),
                     apply)
    lib.write_xml(tree)
    return 0


if __name__ == "__main__":
    sys.exit(main())
