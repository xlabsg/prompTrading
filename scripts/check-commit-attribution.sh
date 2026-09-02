#!/usr/bin/env bash
set -euo pipefail

# Commit messages are public once the repo is; agent-session URLs and
# assistant co-author trailers must not be part of the permanent history.
# Usage: check-commit-attribution.sh [<range>]   (default: origin/main..HEAD)
range=${1:-origin/main..HEAD}

patterns=(
  'Claude-Session:'
  'claude\.ai/code/session'
  'Co-Authored-By: Claude'
  'Generated with \[Claude Code\]'
  'Co-Authored-By: Codex'
  'chatgpt\.com/codex'
)
pattern=$(IFS='|'; echo "${patterns[*]}")

violations=()
while IFS= read -r sha; do
  [[ -n $sha ]] || continue
  hits=$(git log -1 --format='%B' "$sha" | grep -inE "$pattern" || true)
  [[ -n $hits ]] || continue
  violations+=("$(git log -1 --format='%h %s' "$sha")")
  while IFS= read -r hit; do
    violations+=("    $hit")
  done <<< "$hits"
done < <(git rev-list "$range")

if (( ${#violations[@]} == 0 )); then
  echo "check-commit-attribution: no agent attribution in commit messages for $range."
  exit 0
fi

echo "check-commit-attribution: commit messages must not carry agent attribution:" >&2
printf '  %s\n' "${violations[@]}" >&2
echo 'Rewrite the offending messages (git rebase -i, or git commit --amend --only for HEAD).' >&2
exit 1
