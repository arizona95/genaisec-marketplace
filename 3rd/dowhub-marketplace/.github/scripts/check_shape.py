#!/usr/bin/env python3
"""구조 검사 — 클라이언트가 읽을 수 있는 모양인지.

스킬은 SKILL.md 의 frontmatter(name/description)로 언제 쓸지 판단되고, 플러그인은
.claude-plugin/plugin.json 의 name/version 으로 설치·업데이트가 결정된다. 둘 중 하나라도
없거나 비어 있으면 파일이 아무리 멀쩡해도 배포물로서는 동작하지 않는다.
"""
import json
import re
import sys
from pathlib import Path


def check_skill(d: Path) -> list[str]:
    f = d / "SKILL.md"
    if not f.is_file():
        return [f"{f} 없음"]
    text = f.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return [f"{f}: frontmatter(--- 블록)가 없습니다"]
    fm = m.group(1)
    return [f"{f}: frontmatter 에 {k} 가 없습니다"
            for k in ("name", "description") if not re.search(rf"^{k}\s*:", fm, re.M)]


def check_plugin(d: Path) -> list[str]:
    f = d / ".claude-plugin" / "plugin.json"
    if not f.is_file():
        return [f"{f} 없음"]
    try:
        j = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:                              # noqa: BLE001
        return [f"{f}: 파싱 실패 — {e}"]
    return [f"{f}: {k} 가 비어 있습니다" for k in ("name", "version") if not j.get(k)]


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    if (root / ".claude-plugin").is_dir():
        errs = check_plugin(root)
        kind = "plugin"
    elif (root / "SKILL.md").is_file() or root.parent.name == "skills":
        errs = check_skill(root)
        kind = "skill"
    else:
        print(f"통과 — {root} (스킬도 플러그인도 아님, 검사 대상 없음)")
        return 0
    for e in errs:
        print(f"  {e}")
    print(f"{'실패' if errs else '통과'} — {root} ({kind})")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
