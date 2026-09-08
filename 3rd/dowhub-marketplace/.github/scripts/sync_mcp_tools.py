#!/usr/bin/env python3
"""MCP 도구 목록 스냅샷을 서버 소스에서 뜬다 — 카드를 손으로 적지 않기 위해.

MCP 의 진실원은 **살아있는 서버**다. 이 저장소는 그 서버가 아니라서 도구 목록을 직접
확인할 수 없고, 그래서 카드에 손으로 적힌 목록이 아무 저항 없이 낡아갔다
(aar-mcp 카드가 **없어진 도구 43개**를 계속 광고한 게 그렇게 살아남았다).

그 구멍을 이렇게 막는다:
  ① 서버 소스에서 도구 이름을 뽑아 `mcp/<이름>/tools.json` 에 **출처와 함께** 박는다.
  ② 카드는 그 파일에서만 값을 가져온다(`sync_catalog.py` 가 강제).
  ③ CI 는 카드↔스냅샷을 대조한다.
서버↔스냅샷 시차는 남는다 — 그건 배포 전에 이 스크립트를 다시 돌려 없앤다. 대신
**저장소 안 아무 근거도 없이 도구를 광고하는 일**은 사라진다.

쓰기:
    python .github/scripts/sync_mcp_tools.py --mcp aar-mcp \
        --source ~/…/agentreview_mcp.py --write
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


def tools_from_source(path: Path) -> list[str]:
    """`@mcp.tool` 이 붙은 최상위 함수 이름. 소스를 **import 하지 않고** AST 로 읽는다 —
    import 하면 그 프로세스가 실제 백엔드에 붙어 부작용이 난다(전시용으론 정적 파싱이 맞다)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(getattr(d, "attr", None) == "tool" for d in node.decorator_list):
            names.append(node.name)
    return sorted(names)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mcp", required=True, help="mcp/<이름>")
    ap.add_argument("--source", required=True, help="서버 소스 .py (이 저장소 밖이어도 된다)")
    ap.add_argument("--stamp", default="", help="생성 시각(YYYY-MM-DD). 비우면 기존 값 유지")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    src = Path(args.source).expanduser()
    if not src.is_file():
        print(f"소스가 없습니다: {src}")
        return 2
    out = Path("mcp") / args.mcp / "tools.json"
    if not out.parent.is_dir():
        print(f"그런 MCP 가 없습니다: {out.parent}")
        return 2

    tools = tools_from_source(src)
    old = {}
    if out.is_file():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = {}

    doc = {
        # 이 목록이 **어디서** 왔는지 남긴다 — 출처 없는 목록은 다음 사람이 검증할 수 없다.
        "generated_from": str(src),
        "generated_at": args.stamp or old.get("generated_at", ""),
        "note": "진실원은 살아있는 서버다. 이 파일은 그 서버 소스에서 뜬 스냅샷이고, "
                "카탈로그 카드는 여기서만 값을 가져온다.",
        "tools": tools,
    }
    same = old.get("tools") == tools
    print(f"{args.mcp}: 도구 {len(tools)}개"
          + ("" if same else f" (이전 {len(old.get('tools') or [])}개 → 바뀜)"))
    if not same and old.get("tools") is not None:
        a, b = set(old["tools"]), set(tools)
        print(f"  없어진 것: {sorted(a - b) or '-'}")
        print(f"  새로 생긴 것: {sorted(b - a) or '-'}")
    if args.write:
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  기록: {out}  — 이어서 `sync_catalog.py --write` 로 카드를 맞춰라.")
        return 0
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
