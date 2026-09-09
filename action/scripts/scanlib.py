"""필수 검사자 3개(inst-scan · code-scan · leak-scan)의 공통 뼈대.

표준 라이브러리만 쓴다. 검사자가 서드파티를 끌어오면 검사자 자체가 공급망이 된다.

검사자 계약(dowhub 규약과 동일):
    python action/scripts/<name>.py <target>     결함 있으면 exit 1
    python action/scripts/<name>.py --print-version
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REGISTRY = Path("action/validators.json")
PARTIAL = Path("action/history/.partial")

TEXT_SUFFIXES = {
    ".md", ".py", ".json", ".js", ".mjs", ".ts", ".sh", ".ps1",
    ".yml", ".yaml", ".txt", ".toml", ".cfg", ".ini",
}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "example", "schemas"}


def approved_domains() -> list[str]:
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8")).get("approved_domains", [])
    except (OSError, json.JSONDecodeError):
        return []


def walk(target: str) -> list[Path]:
    root = Path(target)
    if root.is_file():
        return [root]
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if SKIP_DIRS & set(p.parts):
            continue
        out.append(p)
    return out


def lines_of(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return
    for n, line in enumerate(text.splitlines(), start=1):
        yield n, line


def scan(files: list[Path], rules: dict[str, re.Pattern]) -> list[dict]:
    found = []
    for path in files:
        for n, line in lines_of(path):
            for rule, pat in rules.items():
                m = pat.search(line)
                if m:
                    found.append({
                        "file": path.as_posix(),
                        "line": n,
                        "rule": rule,
                        "match": m.group(0)[:80],
                        "excerpt": line.strip()[:160],
                    })
    return found


def emit(name: str, version: str, target: str, files: list[Path], found: list[dict]) -> int:
    """사람이 읽는 출력 + UI 가 읽는 findings 를 같이 낸다. 반환값이 exit code."""
    print(f"[{name}@{version}] {target} · 파일 {len(files)}개 · 결함 {len(found)}건")
    for f in found:
        print(f"  {f['file']}:{f['line']}  {f['rule']}")
        print(f"      {f['excerpt']}")

    PARTIAL.mkdir(parents=True, exist_ok=True)
    with (PARTIAL / "findings.jsonl").open("a", encoding="utf-8") as fh:
        for f in found:
            fh.write(json.dumps({"validator": name, "version": version,
                                 "target": target, **f}, ensure_ascii=False) + "\n")
    return 1 if found else 0


def cli(name: str, version: str, rules: dict[str, re.Pattern], extra=None) -> int:
    """검사자 공통 main. extra(files) -> list[dict] 로 패턴 외 검사를 덧붙인다."""
    ap = argparse.ArgumentParser(prog=name)
    ap.add_argument("target", nargs="?", default=".")
    ap.add_argument("--print-version", action="store_true")
    args = ap.parse_args()

    if args.print_version:
        print(f"{name} {version} ({len(rules)} patterns)")
        return 0

    files = walk(args.target)
    found = scan(files, rules)
    if extra:
        found += extra(files)
    return emit(name, version, args.target, files, found)


def run(name: str, version: str, rules: dict[str, re.Pattern], extra=None) -> None:
    sys.exit(cli(name, version, rules, extra))
