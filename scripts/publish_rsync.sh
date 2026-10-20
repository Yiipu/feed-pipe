#!/usr/bin/env bash
# publish_rsync.sh — rsync built feeds to a remote host. No-op if RSYNC_TARGET unset.
# RSYNC_TARGET=user@host:/var/www/feeds/ ./publish_rsync.sh
set -euo pipefail
cd "$(dirname "$0")"
TARGET="${RSYNC_TARGET:-}"
[ -n "$TARGET" ] || { echo "publish_rsync: RSYNC_TARGET unset, nothing to do"; exit 0; }
[ -d out ] || { echo "publish_rsync: out/ missing, run build_feeds.sh first" >&2; exit 1; }
rsync -av out/*.xml "$TARGET/"
