# feed-pipe

Small Unix-pipeline-style RSS middleware: each script reads full RSS/Atom XML
on stdin and writes full RSS XML on stdout. Shared plumbing (API call, cache,
mock mode, fault-tolerant loop, XML parse/serialize) lives in
`src/feedpipe/lib.py`.

## Layout

```
feed-pipe/
├── feeds.conf                  # feed registry: name|url|pipeline
├── src/feedpipe/               # middleware modules (installed via uv)
├── scripts/                    # shell helpers: fetch/build/publish
├── tests/                      # offline + e2e tests, sample data
├── deploy/server.env.example   # server env template
└── out/                        # built feeds (gitignored)
```

## Scripts

### translate-title

Translates item titles to Chinese, keeps the original title as the first
line of the item body.

### summarize-description

Replaces each item's `<description>` text with a 2-3 sentence Chinese
summary of its body (content:encoded preferred, falling back to the
description text itself). Titles, content:encoded, links, dates and
extensions are untouched; items without a description element are skipped.

### normalize-atom-ids

Makes Atom feed/entry ids absolute IRIs (base derived from the alternate or
self link, or an already-absolute feed id). Non-Atom input passes through
byte-identical.

## Design constraints (the "RSS middleware" contract)

1. **Script, not engine** — reads full RSS XML on stdin, writes full RSS XML
   on stdout. Pipeline = chaining: `a | b | c`.
2. **Pass-through** — any XML the script does not process (unknown
   namespaces, `itunes:*`, `content:encoded`, enclosures, comments, ...) is
   preserved. Nothing non-standard is invented.
3. **Per-item fault tolerance** — one failed item (e.g. translation API
   error) keeps its original title and body, logs to stderr, and the script
   still exits 0. Non-zero exit only on unreadable input / broken XML.
4. **No infrastructure** — the script only calls an external translation
   API; no server, no scheduler.

## Usage

```sh
curl -sL -A "feed-pipe/0.1" "https://www.reddit.com/r/Showerthoughts/top.rss" \
  | uv run translate-title \
  | some-other-middleware
```

Or with the retrying fetch helper (retries 3x on network errors, non-200, or
non-XML bodies — Reddit rate-limits aggressively):

```sh
scripts/fetch_feed.sh "https://www.reddit.com/r/Showerthoughts/top.rss" \
  | uv run translate-title \
  | some-other-middleware
```

Summarize an archive feed into item descriptions:

```sh
scripts/fetch_feed.sh "https://evalsignal.xyz/archive.xml" \
  | uv run summarize-description
```

## Environment variables

| Var              | Meaning                                              |
|------------------|------------------------------------------------------|
| `OPENAI_BASE_URL`| Base URL of an OpenAI-compatible chat API (required) |
| `OPENAI_API_KEY` | API key. **Unset ⇒ offline mock mode** (shared-lib mock: `[MOCK] ` + first 80 chars of the input text, no network). |
| `MODEL_TRANSLATE` / `MODEL_SUMMARIZE` | Per-script models (defaults `cn:deepseek-v4.1-flash` / `cn:glm-5.3`); plain `MODEL` is the fallback. |
| `FEED_PROXY`     | Optional HTTP proxy for `fetch_feed.sh` (curl `-x`). |
| `XDG_CACHE_HOME` | Cache root (default `~/.cache`).                     |

## Cache

Per script, under `$XDG_CACHE_HOME/rssmw/` (default `~/.cache/rssmw/`):

- `translate-title.json` — keyed by `sha256(title)`.
- `summarize-description.json` — keyed by `sha256(body content)`.

Re-runs and polling don't re-pay for the API. Purely local files.

## Fallback semantics

- An item fails (API error) → that item stays fully original, warning on
  stderr, exit 0. Partial success is success.
- Input unreadable or XML broken → exit 2 (catastrophic). A diagnostic
  with the first bytes of input is logged; HTML/JSON input gets a
  "did you forget the .rss suffix?" hint.

## Test

```sh
uv run python tests/test_smoke.py             # translate-title, offline (mock mode)
uv run python tests/test_smoke_summarize.py   # summarize-description, offline (mock mode)
tests/test_build_feeds.sh                     # build_feeds.sh, offline (mock mode)
tests/test_e2e.sh                             # translate-title, real network + real API
tests/test_e2e_summarize.sh                   # summarize-description, real network + real API
```

Smoke tests assert translation/summary behavior and that `itunes:*` /
`media:*` / `enclosure` / `content:encoded` survive round-trip; they fail on
any pass-through violation or if the simulated-failure item is modified.
E2E tests fetch the real feeds (Reddit / evalsignal.xyz) and require the
OpenAI env vars to be set.

## Serving to a reader

### 0. Build on GitHub Actions, serve from GitHub Pages

`.github/workflows/build-feeds.yml` builds all feeds every 2 hours (and on
push to `main` / manual dispatch) in a `uv`-managed job, then deploys `out/`
as the Pages site root via the official artifact flow (actions/configure-
pages + upload-pages-artifact + deploy-pages). No daemon, no `gh-pages`
branch, no committed artifacts. Enable it once with repo Settings → Pages →
Source **GitHub Actions** (or
`gh api -X POST repos/<user>/<repo>/pages -f build_type=workflow`).

Feed URLs become `https://<user>.github.io/feed-pipe/<name>.xml` (out/ is
the site root, so `out/showerthoughts.xml` →
`.../feed-pipe/showerthoughts.xml`).

Secrets (optional): set repo secrets `OPENAI_BASE_URL` + `OPENAI_API_KEY`
to a publicly reachable OpenAI-compatible gateway (plus `MODEL_TRANSLATE` /
`MODEL_SUMMARIZE` to override models) for real translation; without them
the workflow runs in offline mock mode and still publishes valid XML.
`actions/cache` keyed on `feeds.conf` persists the translation cache across
runs, so unchanged items don't re-pay the API.

The 2-hour interval keeps the free-tier actions budget comfortable
(~370 min/month at ~1 min/run vs. the 2000 min/month cap); a 30-min cron
would exceed it.

### 1. Publish to your own host (rsync)

`build_feeds.sh` locally (e.g. from cron), then:

```sh
export RSYNC_TARGET=user@host:/var/www/feeds/
scripts/publish_rsync.sh
```

(No-op if `RSYNC_TARGET` is unset.) The per-item sha256 caches in the
middleware mean unchanged items cost nothing — a rebuild where nothing
changed is effectively free.

### 2. Subscribe from the reader

Add the static URL as a feed, e.g.:

- `https://yourname.github.io/feeds/feeds/showerthoughts.xml`
- `https://yourhost.example/feeds/evalsignal.xml`

(`.xml` files live under `feeds/` in the repo, or the rsync target dir.)

For the server-side env (gateway URL, key placeholder, proxy), see
`deploy/server.env.example`.
