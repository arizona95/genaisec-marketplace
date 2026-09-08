#!/usr/bin/env python3
"""문법 검사 — JSON 이 파싱되고 파이썬이 컴파일되는지.

가장 싼 검사지만 제일 자주 걸린다. 깨진 plugin.json 은 클라이언트가 설치 자체를 못 하고,
파이썬 문법 오류는 사용자가 스킬을 실제로 부르는 순간에야 터진다 — 그때는 이미 배포된 뒤다.
"""
import ast
import json
import sys
from pathlib import Path

SKIP = {".git", "__pycache__", "node_modules", ".venv"}


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    bad = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or SKIP & set(f.parts):
            continue
        if f.suffix == ".json":
            try:
                json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:                      # noqa: BLE001
                bad.append(f"{f}: JSON 파싱 실패 — {e}")
        elif f.suffix == ".py":
            # ast.parse: py_compile 과 달리 .pyc 를 안 쓴다 — 검사가 파일을 만들면
            # CI 작업공간이 더러워지고 대상 폴더가 읽기전용이면 실패한다.
            try:
                ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except SyntaxError as e:
                bad.append(f"{f}:{e.lineno} 파이썬 문법 오류 — {e.msg}")
    for x in bad:
        print(f"  {x}")
    print(f"{'실패' if bad else '통과'} — {root}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
