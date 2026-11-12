#!/bin/bash
# The engine files every style shares live ONCE in shared/. Edit them there, then run this to copy them into each style's
# example (only where the example already has that file, so a style can leave one out). new_video.sh also copies them
# into every new project, so a fix reaches new videos even if you forget to sync.
#   bash scripts/sync_shared.sh            copy shared/ into styles/*/example/
#   bash scripts/sync_shared.sh --check    only report examples that differ from shared/ (exit 1 if any)
set -eu
SKILL="$(cd "$(dirname "$0")/.." && pwd)"; cd "$SKILL/shared"; diffs=0
for f in $(find . -type f | sed 's|^\./||'); do
  for ex in "$SKILL"/styles/*/example; do
    [ -f "$ex/$f" ] || continue
    if ! cmp -s "$f" "$ex/$f"; then
      if [ "${1:-}" = "--check" ]; then echo "differs: ${ex#$SKILL/}/$f"; diffs=1; else cp "$f" "$ex/$f"; echo "updated: ${ex#$SKILL/}/$f"; fi
    fi
  done
done
[ "${1:-}" = "--check" ] && { [ $diffs = 0 ] && echo "all examples match shared/"; exit $diffs; }
echo "shared files in sync"
