#!/usr/bin/env python3
"""검증자를 돌려 자산별 태그(마크)를 계산한다.

태그는 이 마켓플레이스의 자격증이다. 5개가 다 붙은 자산은 문법·구조·유출·위협패턴·공급망을
전부 통과했다는 뜻이고, 카탈로그 카드에 그대로 보인다.

두 등급의 성격이 다르다:
  basic — 통과해야 병합된다. 실패하면 CI 가 빨간불이다. 여기서 막히는 건 '깨진 배포물'이라
          내보내면 사용자 쪽에서 그냥 안 돌아간다.
  deep  — 실패해도 CI 는 초록불이다. 대신 그 태그가 안 붙는다. 위협패턴·공급망은 판단이
          섞이는 영역이라 배포를 막기보다 '검증 안 된 상태로 보이게' 하는 편이 정직하다.

검증자를 추가할 때 이 파일은 안 고친다 — .github/validators.json 에 항목만 넣으면 된다.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REGISTRY = Path(".github/validators.json")
MARKS = Path(".github/marks.json")


BASES = ("skills", "plugins", "mcp")


def assets() -> list[str]:
    """검증 대상 = 이 저장소가 실제로 배포하는 것들."""
    out = []
    for base in BASES:
        out += [p.as_posix() for p in sorted(Path(base).glob("*")) if p.is_dir()]
    return out


def changed_assets(base_ref: str) -> list[str] | None:
    """base_ref 이후 손댄 자산만. 판정 불가면 None(=전수로 돌린다).

    안 건드린 자산까지 매번 다시 도는 건 낭비이기도 하지만, 무관한 자산 때문에 내 PR 이
    빨개지는 게 더 나쁘다. 다만 검증자 자체(.github/)가 바뀌면 판정 기준이 바뀐 것이므로
    그때는 전수로 돌려야 한다 — 안 그러면 옛 기준으로 받은 태그가 그대로 남는다.
    """
    try:
        r = subprocess.run(["git", "diff", "--name-only", f"{base_ref}...HEAD"],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            r = subprocess.run(["git", "diff", "--name-only", base_ref, "HEAD"],
                               capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return None
    except Exception:                                   # noqa: BLE001
        return None

    files = [f for f in r.stdout.splitlines() if f.strip()]
    if any(f.startswith(".github/") for f in files):
        print("검증 기준(.github/)이 바뀌었습니다 — 전수로 돌립니다.")
        return None

    known = set(assets())
    hit = set()
    for f in files:
        parts = f.split("/")
        if len(parts) >= 2 and parts[0] in BASES:
            a = f"{parts[0]}/{parts[1]}"
            if a in known:
                hit.add(a)
    return sorted(hit)


VERSION_RE = re.compile(r"\d+\.\d+(?:\.\d+)?(?:[a-z0-9.\-+]*)?")


def tool_version(cmd: list[str] | None) -> str:
    """도구 버전. '무엇이 검사했나' 만큼 '어느 버전이' 도 태그에 남아야 한다 —
    도구가 올라가면 같은 코드에 대한 판정이 달라질 수 있기 때문이다."""
    if not cmd:
        return ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception:                                   # noqa: BLE001
        return ""
    out = (r.stdout + r.stderr).strip().splitlines()
    if not out:
        return ""
    line = out[0]
    m = VERSION_RE.search(line)
    # 버전 숫자가 없으면(패턴 개수처럼 자체 표기) 첫 줄을 그대로 쓴다.
    return m.group(0) if m else line[:40]


def run(cmd: list[str], target: str) -> tuple[bool, str]:
    argv = [a.replace("{target}", target) for a in cmd]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=900)
    except FileNotFoundError:
        # 검증자 실행파일이 없으면 '실패'가 아니라 '판정 불가'다. 없는 도구 때문에 태그를
        # 떼면, 도구를 지우는 것만으로 검증을 통과시킬 수 있다는 뜻이 되어 더 위험하다.
        return False, f"{argv[0]} 를 찾을 수 없습니다 (미설치)"
    except subprocess.TimeoutExpired:
        return False, "시간 초과"
    tail = (r.stdout + r.stderr).strip().splitlines()
    return r.returncode == 0, (tail[-1] if tail else "")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", choices=["basic", "deep", "all"], default="all")
    ap.add_argument("--write", action="store_true", help="marks.json 갱신")
    ap.add_argument("--changed-since", default="",
                    help="이 ref 이후 바뀐 자산만 검사한다 (비우면 전수)")
    args = ap.parse_args()

    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))["validators"]
    chosen = [v for v in reg if args.tier in ("all", v["tier"])]

    all_targets = assets()
    full_sweep = True
    targets = all_targets
    if args.changed_since:
        ch = changed_assets(args.changed_since)
        if ch is not None:
            targets, full_sweep = ch, False
            if not targets:
                print(f"{args.changed_since} 이후 바뀐 자산이 없습니다 — 검사할 것 없음.")
                return 0
            print(f"변경된 자산 {len(targets)}/{len(all_targets)}개만 검사합니다: "
                  f"{', '.join(targets)}")

    marks = json.loads(MARKS.read_text(encoding="utf-8")) if MARKS.exists() else {}
    failed_basic = []

    versions = {v["name"]: tool_version(v.get("version_cmd")) for v in chosen}

    known = {v["name"] for v in reg}
    for t in targets:
        entry = marks.setdefault(t, {})
        # 등록표에서 빠진 검증자의 옛 결과를 남겨두면, 지운 검사가 계속 '미통과'로 보인다.
        for stale in [k for k in entry if k not in known]:
            entry.pop(stale)
        print(f"\n{t}")
        for v in chosen:
            ok, msg = run(v["cmd"], t if v["scope"] == "target" else ".")
            # 통과 여부와 '어느 버전이 판정했는지'를 함께 남긴다.
            entry[v["name"]] = {"ok": ok, "version": versions.get(v["name"], ""),
                                "tier": v["tier"]}
            icon = "O" if ok else "X"
            ver = versions.get(v["name"], "")
            print(f"  [{icon}] {v['name']:14} {ver:22} ({v['tier']:5}) {msg[:60]}")
            if not ok and v["tier"] == "basic":
                failed_basic.append(f"{t}/{v['name']}")

    # 요약: 5개 다 붙은 자산이 '완전 검증'이다.
    total = len(reg)
    print("\n" + "=" * 60)
    def passed(t, name):
        m = (marks.get(t) or {}).get(name)
        return bool(m.get("ok")) if isinstance(m, dict) else bool(m)

    for t in all_targets:
        if t not in marks:
            continue
        got = sum(1 for v in reg if passed(t, v["name"]))
        tags = " ".join(v["name"] for v in reg if passed(t, v["name"]))
        mark = " " if t in targets else "·"          # · = 이번에 안 돌린 것(직전 결과)
        print(f" {mark}{t:30} {got}/{total}  {tags}")

    if args.write:
        if full_sweep:
            # 부분 실행에서 지우면 안 건드린 자산의 태그가 통째로 날아간다.
            for gone in [k for k in marks if k not in all_targets]:
                marks.pop(gone)
        MARKS.write_text(json.dumps(marks, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
        print(f"\nmarks 기록: {MARKS}")

    if failed_basic:
        print(f"\n기본검증 실패: {', '.join(failed_basic)}")
        return 1
    if args.tier == "deep":
        # 심화는 떨어져도 CI 를 세우지 않는다. 태그가 안 붙는 것으로 충분히 드러난다.
        print("\n심화검증 완료 (실패해도 CI 는 통과 — 태그로만 반영됩니다).")
    else:
        print("\n기본검증 통과.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
