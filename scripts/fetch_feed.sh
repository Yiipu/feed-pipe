#!/usr/bin/env bash
# fetch_feed.sh [URL] [UA] — fetch a feed, retrying 3x on failure.
# Failure = curl error, non-200, or body not starting with '<' (HTML/error page).
set -u
URL="${1:?usage: fetch_feed.sh <url> [user-agent]}"
UA="${2:-rssmw/0.1}"
PROXY=()
[ -n "${FEED_PROXY:-}" ] && PROXY=(-x "$FEED_PROXY")
for i in 1 2 3; do
  tmp="$(mktemp)"
  code="$(curl -sL "${PROXY[@]}" -A "$UA" -o "$tmp" -w '%{http_code}' "$URL")"
  rc=$?
  body="$(LC_ALL=C tr -d ' \t\r\n' < "$tmp" | head -c 1)"
  if [ $rc -eq 0 ] && [ "$code" = "200" ] && [ "$body" = "<" ]; then
    cat "$tmp"; rm -f "$tmp"; exit 0
  fi
  echo "fetch_feed: attempt $i/3 failed (curl rc=$rc http=$code body_start=${body:-none})" >&2
  rm -f "$tmp"
  [ $i -lt 3 ] && sleep 5
done
echo "fetch_feed: giving up after 3 attempts: $URL" >&2
exit 1
