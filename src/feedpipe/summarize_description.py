#!/usr/bin/env python3
"""rssmw/summarize-description: replaces item descriptions with AI summaries.

Reads full RSS XML on stdin, writes full RSS XML on stdout. Per item, the
<body content> (content:encoded preferred, falling back to whatever exists)
is summarized and the item's <description> text is REPLACED with the summary.
content:encoded and all other elements (title, links, extensions, ...) are
left untouched. Items without a description element are skipped entirely.

Env:
  OPENAI_BASE_URL   base URL of an OpenAI-compatible API (no default)
  OPENAI_API_KEY    API key; if unset -> offline mock mode (shared-lib mock:
                    "[MOCK] " + first 80 chars of body)
  MODEL_SUMMARIZE   model name (default: cn:glm-5.3; falls back to MODEL,
                    then the default)

Cache: $XDG_CACHE_HOME/rssmw/summarize-description.json keyed by
sha256(body content). Per-item failure => original description kept, logged
to stderr, exit 0. Exit 2 only on unreadable/broken XML.
"""
import os
import sys

from feedpipe import lib

NAME = "summarize-description"
SYSTEM_PROMPT = (
    "Summarize the following article in 2-3 concise Chinese sentences. "
    "Output ONLY the summary, no quotes, no preamble.")


def pick_body(item):
    """Body to summarize: content:encoded > description text. None if empty."""
    ce = item.find("{%s}encoded" % lib.CONTENT_NS)
    if ce is not None and (ce.text or "").strip():
        return ce.text
    desc = item.find("description")
    if desc is not None and (desc.text or "").strip():
        return desc.text
    return None


def main() -> int:
    tree = lib.parse_xml(sys.stdin.buffer.read(), NAME)
    if tree is None:
        return 2

    items = lib.find_items(tree)
    pairs = []  # (item, body_text)
    for item in items:
        body = pick_body(item)
        if body is not None and item.find("description") is not None:
            pairs.append((item, body))

    def apply(body: str, summary: str) -> None:
        for item, b in pairs:
            if b == body:
                item.find("description").text = summary

    lib.run_pipeline([b for _, b in pairs], NAME, "summary",
                     lambda s: lib.chat_complete(
                         s, SYSTEM_PROMPT, NAME,
                         lib.pick_model("MODEL_SUMMARIZE", "cn:glm-5.3")),
                     apply)
    lib.write_xml(tree)
    return 0


if __name__ == "__main__":
    sys.exit(main())
