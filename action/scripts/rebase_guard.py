#!/usr/bin/env python3
"""dev 가 main 최신 커밋 위에 rebase 되어 있는지 본다.

검증자가 아니다. 검증자는 "내용이 안전한가"를 묻고, 이건 "그 판정이 병합 후에도 유효한가"를
묻는다. base(main) 의 tip 이 head 의 조상이 아니면, main 에 head 가 모르는 커밋이 있다는
뜻이다. 그 상태로 받은 초록불은 병합될 코드에 대한 판정이 아니라 낡은 스냅샷에 대한
판정이므로, 검증자를 다 통과해도 의미가 없다.

merge 로 따라잡는 것도 가능하지만 rebase 를 요구한다 — 이력이 선형이면 "어느 커밋이
어느 검증을 통과했나"가 1:1 로 남고, merge 커밋이 끼면 그 대응이 깨진다.

    python action/scripts/rebase_guard.py                    # base=origin/main
    python action/scripts/rebase_guard.py --base origin/main
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

OUT = Path("action/history/.partial/rebase-guard.json")


def sh(*args: str) -> tuple[int, str]:
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    default_base = os.environ.get("GITHUB_BASE_REF") or "main"
    if not default_base.startswith("origin/"):
        default_base = f"origin/{default_base}"
    ap.add_argument("--base", default=default_base)
    args = ap.parse_args()

    code, base_sha = sh("git", "rev-parse", args.base)
    if code != 0:
        print(f"[rebase-guard] base ref 를 못 찾았습니다: {args.base}")
        print("  CI 라면 actions/checkout 에 fetch-depth: 0 이 있는지 보세요.")
        return 2
    _, head_sha = sh("git", "rev-parse", "HEAD")
    _, head_branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD")

    # base 의 tip 이 HEAD 의 조상인가 = HEAD 가 base 최신 위에 있는가
    code, _ = sh("git", "merge-base", "--is-ancestor", base_sha, "HEAD")
    rebased = code == 0

    _, behind_raw = sh("git", "log", "--oneline", f"HEAD..{base_sha}")
    behind = [l for l in behind_raw.splitlines() if l.strip()]
    _, ahead_raw = sh("git", "log", "--oneline", f"{base_sha}..HEAD")
    ahead = [l for l in ahead_raw.splitlines() if l.strip()]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "gate": "rebase-guard",
        "base": args.base,
        "base_sha": base_sha[:12],
        "head": head_branch,
        "head_sha": head_sha[:12],
        "rebased": rebased,
        "behind": behind,
        "ahead": ahead,
        "status": "pass" if rebased else "fail",
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[rebase-guard] {head_branch}@{head_sha[:8]} vs {args.base}@{base_sha[:8]}")
    print(f"  내 커밋 {len(ahead)}개 · main 에만 있는 커밋 {len(behind)}개")

    if rebased:
        print("  통과 — main 최신 위에 있습니다.")
        return 0

    print(f"\n  차단 — main 에 이 브랜치가 모르는 커밋이 {len(behind)}개 있습니다.")
    for line in behind[:10]:
        print(f"    {line}")
    if len(behind) > 10:
        print(f"    ... 외 {len(behind) - 10}개")
    print("\n  이렇게 따라잡으세요.")
    print("    git fetch origin")
    print(f"    git rebase origin/{args.base.removeprefix('origin/')}")
    print("    git push --force-with-lease")
    return 1


if __name__ == "__main__":
    sys.exit(main())
