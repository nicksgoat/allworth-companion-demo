#!/usr/bin/env bash
# Re-capture the API contract into a temp dir and byte-diff it against goldens/.
# Exits nonzero naming the first mismatched file.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
GOLD="$HERE/goldens"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

"$HERE/capture_goldens.sh" "$TMP" >/dev/null

fail=0
for f in "$GOLD"/*; do
  name="$(basename "$f")"
  if ! cmp -s "$f" "$TMP/$name"; then
    echo "MISMATCH: $name"
    diff <(head -c 2000 "$f") <(head -c 2000 "$TMP/$name") | head -10 || true
    fail=1
  fi
done
[ "$fail" = 0 ] && echo "All $(ls "$GOLD" | wc -l | tr -d ' ') goldens byte-identical." || exit 1
