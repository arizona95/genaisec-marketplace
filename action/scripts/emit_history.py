#!/usr/bin/env python3
"""한 번의 검사를 이력 레코드 하나로 남긴다.

marketplace-ui 가 읽는 유일한 입력이다. "언제 · 누가 · 무엇을 · 어떤 검사자가 · 어느
버전으로 · 결과가 무엇이었나" 를 한 파일에 담는다.

검사자 버전을 레코드에 박는 이유: 검사자는 계속 올라간다. 버전이 없으면 6개월 뒤에
"이 자산은 왜 통과했지?" 를 재현할 수 없다.

    python action/scripts/emit_history.py
    python action/scripts/emit_history.py --out action/history
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REGISTRY = Path("action/validators.json")
MARKS = Path("action/marks.json")
PARTIAL = Path("action/history/.partial")


def sh(*args: str, default: str = "") -> str:
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.stdout.strip() if r.returncode == 0 else default


def actor() -> str:
    """검사자(사람). CI 면 워크플로가 알려주고, 로컬이면 git 설정에서 가져온다."""
    for env in ("GITHUB_ACTOR", "GITLAB_USER_LOGIN"):
        if os.environ.get(env):
            return os.environ[env]
    email = sh("git", "config", "user.email")
    name = sh("git", "config", "user.name")
    return f"{name} <{email}>" if email else (name or "unknown")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="action/history")
    args = ap.parse_args()

    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))["validators"]
    marks = json.loads(MARKS.read_text(encoding="utf-8")) if MARKS.exists() else {}

    rebase = {}
    rp = PARTIAL / "rebase-guard.json"
    if rp.exists():
        rebase = json.loads(rp.read_text(encoding="utf-8"))

    now = datetime.now(timezone.utc)
    head_sha = sh("git", "rev-parse", "HEAD", default="0" * 40)
    run_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{head_sha[:7]}"

    # 자산별 · 검사자별 판정
    assets = []
    for target in sorted(marks):
        entry = marks[target] or {}
        checks = []
        for v in reg:
            m = entry.get(v["name"])
            ok = bool(m.get("ok")) if isinstance(m, dict) else bool(m)
            checks.append({
                "validator": v["name"],
                "title": v.get("description", "")[:80],
                "version": (m or {}).get("version", "") if isinstance(m, dict) else "",
                "tier": v["tier"],
                "ok": ok,
            })
        required = [c for c in checks if c["tier"] == "basic"]
        advanced = [c for c in checks if c["tier"] == "deep"]
        assets.append({
            "target": target,
            "checks": checks,
            "marks": f"{sum(1 for c in checks if c['ok'])}/{len(reg)}",
            "required_passed": all(c["ok"] for c in required),
            "advanced_passed": all(c["ok"] for c in advanced),
            # 등록 여부는 필수만 본다. 심화는 태그로만 드러난다.
            "registered": all(c["ok"] for c in required),
            "tags": [f"{c['validator']}@{c['version']}" for c in checks if c["ok"]],
        })

    blocked = [a["target"] for a in assets if not a["required_passed"]]
    gate_ok = bool(rebase.get("rebased", True)) and not blocked

    record = {
        "run_id": run_id,
        "at": now.isoformat(timespec="seconds"),
        "actor": actor(),
        "trigger": os.environ.get("GITHUB_EVENT_NAME", "local"),
        "run_url": (
            f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
            f"/actions/runs/{os.environ['GITHUB_RUN_ID']}"
            if os.environ.get("GITHUB_RUN_ID") else ""
        ),
        "branch": {
            "head": rebase.get("head") or sh("git", "rev-parse", "--abbrev-ref", "HEAD"),
            "head_sha": head_sha[:12],
            "head_subject": sh("git", "log", "-1", "--pretty=%s"),
            "base": rebase.get("base", ""),
            "base_sha": rebase.get("base_sha", ""),
        },
        "rebase_guard": {
            "status": rebase.get("status", "skipped"),
            "rebased": rebase.get("rebased"),
            "behind": rebase.get("behind", []),
        },
        "validators": [
            {"name": v["name"], "tier": v["tier"], "declared_version": v.get("version", ""),
             "description": v.get("description", "")}
            for v in reg
        ],
        "assets": assets,
        "summary": {
            "assets": len(assets),
            "registered": sum(1 for a in assets if a["registered"]),
            "blocked": len(blocked),
            "blocked_targets": blocked,
            "fully_verified": sum(1 for a in assets if a["marks"].split("/")[0] == str(len(reg))),
        },
        "verdict": "passed" if gate_ok else "blocked",
    }

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 최신 것을 UI 가 바로 집을 수 있게 별칭도 남긴다.
    (out_dir / "latest.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    s = record["summary"]
    print(f"[emit-history] {path}")
    print(f"  {record['verdict']} · 자산 {s['assets']}개 · 등록 {s['registered']} · "
          f"차단 {s['blocked']} · 완전검증 {s['fully_verified']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
