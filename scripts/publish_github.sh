#!/usr/bin/env bash
# publish_github.sh — copy built feeds into a git repo served by a static host
# (GitHub Pages / Gitea) and push only when content actually changed.
# FEEDS_REPO=/path/to/repo ./publish_github.sh
set -euo pipefail
cd "$(dirname "$0")"
REPO="${FEEDS_REPO:?FEEDS_REPO must point to a local clone of the feeds git repo}"
[ -d "$REPO/.git" ] || { echo "publish_github: $REPO is not a git repository" >&2; exit 1; }
[ -d out ] || { echo "publish_github: out/ missing, run build_feeds.sh first" >&2; exit 1; }
mkdir -p "$REPO/feeds"
rsync -a --delete out/*.xml "$REPO/feeds/"
cd "$REPO"
git add feeds
if git diff --cached --quiet; then
  echo "publish_github: no changes, skipping commit"
else
  git commit -m "feed update $(date '+%Y-%m-%d %H:%M:%S')"
  git push
fi
