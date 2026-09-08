#!/usr/bin/env python3
"""카탈로그 카드를 진실원과 맞춘다 — 손으로 적은 값이 어긋나지 않게.

카드에 적힌 값은 전부 **어딘가의 사본**이다. 사본은 반드시 어긋난다:
  · aar-plugin 이 1.0.15 로 올라간 뒤에도 카드는 1.0.14 를 보여줬다.
  · aar-mcp 카드는 **이미 삭제된 도구 43개**를 계속 광고했다.
둘 다 보안 검사로는 안 잡힌다. 사용자는 받은 것과 다른 것을 보게 된다.

그래서 카드 값을 사람이 적지 않고 진실원에서 끌어온다. 무엇이 진실원인지는
`catalog_lib.py` 한 곳에만 적혀 있다.

  --check : 어긋나면 종료코드 1 (CI 용)
  --write : 카탈로그를 진실원에 맞춰 고친다

**저장소가 확인해 줄 수 없는 값은 조용히 넘어가지 않고 따로 보고한다** — 그게 이번 사고의
자리였다(MCP 도구 목록엔 진실원이 저장소 밖에 있었고, 아무도 안 보는 채로 유령이 남았다).
"""

from __future__ import annotations

import argparse
import sys

import catalog_lib as lib


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    doc = lib.load_catalog()
    drift: list[str] = []
    unverifiable: list[str] = []

    for e in doc.get("plugins", []):
        name = e.get("name", "이름없음")
        hub = e.setdefault("hub", {})

        # ── 버전: plugin.json / SKILL.md frontmatter 가 진실원 ──────────────
        v = lib.truth_version(e)
        if v:
            for holder, label in ((e, "version"), (hub, "hub.version")):
                if holder.get("version") != v:
                    drift.append(f"{name}: {label} {holder.get('version')!r} != 진실원 {v!r}")
                    holder["version"] = v
        elif e.get("version") or hub.get("version"):
            unverifiable.append(f"{name}: version 을 대조할 진실원이 없다"
                                f"{' (mcp 는 서버가 진실원)' if hub.get('type') == 'mcp' else ''}")

        # ── 설명·스킬 목록: plugin.json / skills 폴더가 진실원 ──────────────
        desc = lib.truth_description(e)
        if desc and e.get("description") != desc:
            drift.append(f"{name}: description 이 plugin.json 과 다르다")
            e["description"] = desc
        sk = lib.truth_skills(e)
        if sk is not None and list(hub.get("skills") or []) != sk:
            have, want = set(hub.get("skills") or []), set(sk)
            drift.append(f"{name}: hub.skills 가 실제 폴더와 다르다 — "
                         f"카드에만 {sorted(have - want) or '없음'}, "
                         f"폴더에만 {sorted(want - have) or '없음'}")
            hub["skills"] = sk

        # ── 도구 목록: mcp/<name>/tools.json 스냅샷이 진실원 ────────────────
        if hub.get("type") == "mcp":
            snap = lib.truth_tools(e)
            if snap is None:
                if hub.get("tools"):
                    drift.append(f"{name}: 도구를 광고하는데 근거 스냅샷이 없다 "
                                 f"({lib.tools_snapshot_path(e)}) — sync_mcp_tools.py 로 만들어라")
            elif list(hub.get("tools") or []) != snap:
                have, want = set(hub.get("tools") or []), set(snap)
                # 집합이 같고 순서만 다를 수 있다 — 그때 "다르다"고만 하면 무엇이 다른지
                # 아무도 못 본다(차이 목록이 양쪽 다 비어 나온다). 사유를 말로 적는다.
                if have == want:
                    why = "순서만 다르다(스냅샷 순서를 정본으로 삼는다)"
                else:
                    why = (f"카드에만 {sorted(have - want) or '없음'}, "
                           f"스냅샷에만 {sorted(want - have) or '없음'}")
                drift.append(f"{name}: hub.tools 가 스냅샷과 다르다 — {why}")
                hub["tools"] = snap

    for u in unverifiable:
        print(f"  확인 불가: {u}")

    if not drift:
        print("일치 — 카탈로그가 진실원과 같습니다.")
        return 0

    for d in drift:
        print(f"  어긋남: {d}")
    if args.write:
        lib.save_catalog(doc)
        print(f"\n{len(drift)}건을 진실원에 맞춰 고쳤습니다: {lib.CATALOG}")
        return 0
    print(f"\n실패 — {len(drift)}건 어긋났습니다."
          "\n고치려면: python .github/scripts/sync_catalog.py --write")
    return 1


if __name__ == "__main__":
    sys.exit(main())
