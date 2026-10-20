#!/usr/bin/env python3
"""rssmwlib — shared plumbing for rssmw middleware scripts.

Only code that is genuinely duplicated across >=2 scripts lives here:
logging, XML parse/serialize with diagnostics, OpenAI-compatible chat
completion, sha256-keyed JSON cache, mock mode, and the per-item
fault-tolerant processing loop.
"""
import hashlib
import json
import os
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from lxml import etree

ATOM = "http://www.w3.org/2005/Atom"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
MAX_WORKERS = 4
FAIL_MARKER = "FORCE_ERROR"  # mock mode: input starting with this raises


def log(name: str, msg: str) -> None:
    print("%s: %s" % (name, msg), file=sys.stderr)


def parse_xml(raw: bytes, name: str):
    """Parse stdin XML; on failure log a snippet + HTML/JSON hint, return None."""
    try:
        return etree.fromstring(raw)
    except etree.XMLSyntaxError as exc:
        log(name, "input is not well-formed XML, aborting: %s" % exc)
        snippet = repr(raw[:120])
        log(name, "first bytes of input: %s%s"
            % (snippet, "..." if len(raw) > 120 else ""))
        head = raw[:120].lstrip().lower()
        if head.startswith((b"<!doctype html", b"<html", b"{", b"[")):
            log(name, "input looks like HTML/JSON, not a feed — "
                      "did you forget the .rss suffix?")
        return None

def write_xml(tree) -> None:
    encoding = (tree.docinfo.encoding if isinstance(tree, etree._ElementTree)
                else "utf-8") or "utf-8"
    sys.stdout.buffer.write(
        etree.tostring(tree, xml_declaration=True, encoding=encoding))


def find_items(tree) -> list:
    return (tree.findall(".//item")
            or tree.findall(".//{%s}entry" % ATOM))


def cache_path(name: str) -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "rssmw", name + ".json")


def load_cache(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(path: str, cache: dict, name: str) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=1, sort_keys=True)
    except OSError as exc:
        log(name, "cache write failed (non-fatal): %s" % exc)


def sha_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def pick_model(specific: str, default: str) -> str:
    """MODEL_<SPECIFIC> env, then plain MODEL, then the script default."""
    return os.environ.get(specific) or os.environ.get("MODEL") or default

def chat_complete(user_prompt: str, system_prompt: str, script_name: str,
                  model: str) -> str:
    """OpenAI-compatible chat completion; mock when OPENAI_API_KEY is unset."""
    if "OPENAI_API_KEY" not in os.environ:
        if user_prompt.lstrip("<p> ").startswith(FAIL_MARKER):
            raise RuntimeError("simulated API failure")
        return "[MOCK] " + user_prompt[:80]
    base = os.environ["OPENAI_BASE_URL"].rstrip("/")
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }).encode()
    req = urllib.request.Request(
        base + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.load(resp)
    return payload["choices"][0]["message"]["content"].strip()


def run_pipeline(inputs: list, script_name: str, verb: str,
                 call, on_success) -> int:
    """Per-item fault-tolerant loop with cache and small concurrency.

    inputs: list of source strings (titles, bodies, ...).
    call(source) -> str: performs the API/mock call (must raise on failure).
    on_success(source, result): mutates the tree for one item.
    Returns number of failures.
    """
    if not inputs:
        return 0
    cpath = cache_path(script_name)
    cache = load_cache(cpath)
    missing = [(sha_key(s), s) for s in inputs if sha_key(s) not in cache]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [(s, pool.submit(call, s)) for _, s in missing]
        for source, fut in futures:
            try:
                cache[sha_key(source)] = fut.result()
            except Exception as exc:  # noqa: BLE001 - per-item fault tolerance
                log(script_name, "%s failed, keeping original: %r: %s"
                    % (verb, source[:80], exc))
    save_cache(cpath, cache, script_name)
    failures = 0
    for source in inputs:
        result = cache.get(sha_key(source))
        if result is None:
            log(script_name, "item left unchanged (no %s): %r"
                % (verb, source[:80]))
            failures += 1
            continue
        on_success(source, result)
    return failures
