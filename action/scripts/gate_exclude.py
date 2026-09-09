#!/usr/bin/env python3
"""게이트 — 기본검증에 걸린 자산을 PR 에서 뺀다.

git 병합은 전부 아니면 전무다. 한 PR 에 자산 3개가 있고 하나가 걸리면 나머지 둘도 못 들어간다.
그래서 걸린 자산의 폴더와 카탈로그 항목을 지운 커밋을 PR 브랜치에 붙인다. 지운 것은 git 이력과
history 로그(pr/)에 남는다 — 사라지는 게 아니라 '이번엔 등록 안 됨'이다.

    python action/scripts/gate_exclude.py /tmp/failed.json          # 무엇을 뺄지만 출력
    python action/scripts/gate_exclude.py /tmp/failed.json --write  # 실제로 지우고 /tmp/gate-msg.txt 에 커밋 메시지
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import catalog_lib as lib


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("failed", help="run_validators --failed-out 이 쓴 JSON (자산 → 걸린 검사 목록)")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--msg-out", default="/tmp/gate-msg.txt")
    args = ap.parse_args()

    failed: dict[str, list[str]] = json.loads(Path(args.failed).read_text(encoding="utf-8"))
    if not failed:
        print("걸린 자산 없음")
        return 0

    doc = lib.load_catalog()
    keep, dropped = [], []
    for e in doc.get("plugins", []):
        d = lib.asset_dir(e.get("source"))
        key = d.as_posix() if d else ""
        if key in failed:
            dropped.append(e)
        else:
            keep.append(e)

    lines = ["[gate] 기본검증에 걸린 자산 제외", ""]
    for asset, vals in sorted(failed.items()):
        lines.append(f"- {asset}: {', '.join(vals)}")
    lines += ["", "걸린 자산은 이 PR 에서 빠진다. 고쳐서 다시 올리면 된다. 기록은 history 브랜치 pr/ 에 남는다."]
    msg = chr(10).join(lines) + chr(10)
    print(msg)

    if not args.write:
        return 0
    for asset in failed:
        p = Path(asset)
        if p.is_dir():
            shutil.rmtree(p)
    doc["plugins"] = keep
    lib.save_catalog(doc)
    Path(args.msg_out).write_text(msg, encoding="utf-8")
    print(f"제외: 폴더 {len(failed)}개 · 카탈로그 항목 {len(dropped)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())