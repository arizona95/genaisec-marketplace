#!/usr/bin/env bash
# history 브랜치 워크트리(/tmp/hist)의 변경을 커밋해 push 한다. 다른 실행이 먼저 밀었으면 한 번 따라잡고 다시.
#   bash action/scripts/push_history.sh <브랜치> "<라벨>"
set -e
BRANCH="$1"; LABEL="${2:-}"
cd /tmp/hist
git add -A
git commit -qm "history: $BRANCH ${GITHUB_SHA::7} $LABEL ($(date -u +%Y-%m-%dT%H:%MZ))" || { echo "변경 없음"; exit 0; }
git push -q origin HEAD:history \
  || { git fetch -q origin history && git rebase -q origin/history && git push -q origin HEAD:history; }
echo "history/$BRANCH $LABEL: https://github.com/$GITHUB_REPOSITORY/tree/history/$BRANCH" >> "$GITHUB_STEP_SUMMARY"