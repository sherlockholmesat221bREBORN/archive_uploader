#!/usr/bin/env bash
# Zero-effort code versioning: bumps a counter, commits everything with
# no message required, tags it. Run this yourself before/after an
# editing session, or wire it to a file watcher (entr/watchexec) — either
# way you never type a commit message.
#
#   ./tools/snap.sh              # snapshot now
#   git diff snap-00041 snap-00042   # see exactly what an edit changed
#   git checkout snap-00041 -- archive_uploader/some_file.py   # revert one file
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT"

if [ ! -d .git ]; then
    git init -q
fi

COUNTER_FILE=".snapcount"
[ -f "$COUNTER_FILE" ] || echo 0 > "$COUNTER_FILE"

# Counter is only persisted AFTER a successful commit below — if commit
# fails for any reason (no git identity set, a hook rejects it, disk
# full, etc.) the number is retried next time instead of leaving a
# permanent gap.
n=$(( $(cat "$COUNTER_FILE") + 1 ))
TAG=$(printf "snap-%05d" "$n")

git add -A

if git diff --cached --quiet; then
    echo "Nothing changed since last snapshot (no $TAG created)."
    exit 0
fi

git commit -q -m "$TAG"
git tag "$TAG"
echo "$n" > "$COUNTER_FILE"
echo "Created $TAG"
