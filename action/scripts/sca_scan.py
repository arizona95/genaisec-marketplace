#!/usr/bin/env python3
"""SCA — 이 자산들이 실행 시점에 어떤 외부 코드를 끌어오는지 본다.

두 가지를 검사한다.

1) **부동(floating) 자동실행 스펙.** `npx <pkg>@latest`, `uvx <pkg>` 처럼 버전이 고정되지 않은
   런처는 세션 시작 시 레지스트리가 그때 주는 코드를 실행한다. 카탈로그가 커밋 SHA 를 핀해도
   이건 안 고정된다 — 핀을 뚫는 구멍이라 마켓플레이스에서 제일 중요한 검사다.
   (Anthropic 의 scan-plugins 액션이 하는 검사와 같은 종류다.)

2) **알려진 취약점.** 스킬이 설치하는 파이썬 패키지를 pip-audit(OSV)로 조회한다. 우리 스킬은
   requirements.txt 가 아니라 스크립트 안에서 pip install 을 하므로, 소스에서 설치 대상을
   뽑아낸다 — 선언만 보면 실제로 받는 걸 놓친다.

종료코드: 0 = 통과, 1 = 차단 대상 발견, 2 = 실행 오류
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
RUNNERS = ("npx", "bunx", "uvx", "pipx")

# 스크립트 안의 pip install 대상 (우리 스킬이 쓰는 방식)
PIP_INSTALL = re.compile(
    r"""pip["'\s,\]]+install|["']install["']""", re.I)
PKG_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*(?:\[[A-Za-z0-9,._-]+\])?"
                       r"(?:[=<>!~]=?[0-9][^\s\"']*)?$")


def floating(spec: str) -> bool:
    """버전이 고정되지 않았으면 True. `pkg@1.2.3` 만 고정으로 본다."""
    spec = spec.strip()
    if not spec or spec.startswith("-"):
        return False
    name, _, ver = spec.rpartition("@")
    if not name:                       # @ 가 없다 = 버전 없음
        return True
    return not re.fullmatch(r"\d+\.\d+\.\d+.*", ver or "")


def scan_mcp_launchers(root: Path) -> list[dict]:
    """.mcp.json / plugin.json 의 mcpServers 에서 부동 런처를 찾는다."""
    out = []
    for f in sorted(root.rglob("*.json")):
        if SKIP_DIRS & set(f.parts):
            continue
        if f.name not in (".mcp.json", "plugin.json", "mcp.json"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:              # noqa: BLE001 - 형식 검사는 validate 가 한다
            continue
        servers = d.get("mcpServers") or {}
        for sname, cfg in (servers.items() if isinstance(servers, dict) else []):
            cmd = str((cfg or {}).get("command", ""))
            args = [str(a) for a in (cfg or {}).get("args", [])]
            base = Path(cmd).name
            if base in RUNNERS:
                specs = [a for a in args if not a.startswith("-")]
                for s in specs[:1]:    # 런처의 첫 비옵션 인자 = 패키지 스펙
                    if floating(s):
                        out.append({"file": f.relative_to(root).as_posix(),
                                    "server": sname, "runner": base, "spec": s})
    return out


def scan_pip_targets(root: Path) -> set[str]:
    """스크립트가 런타임에 설치하는 패키지 이름을 뽑는다."""
    pkgs: set[str] = set()
    for f in sorted(root.rglob("*.py")):
        if SKIP_DIRS & set(f.parts):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        if "pip" not in text or "install" not in text:
            continue
        # PACKAGE = "imapclient" 같은 상수, 그리고 install 인자 리스트
        for m in re.finditer(r"""^\s*(?:PACKAGE|PACKAGES|REQUIREMENTS)\s*=\s*(.+)$""",
                             text, re.M):
            for t in re.findall(r"""["']([^"']+)["']""", m.group(1)):
                if PKG_TOKEN.match(t):
                    pkgs.add(t)
    for f in sorted(root.rglob("requirements*.txt")):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#")[0].strip()
            if line and PKG_TOKEN.match(line):
                pkgs.add(line)
    return pkgs


def audit(pkgs: set[str]) -> tuple[int, str]:
    """pip-audit 으로 OSV 조회. 없으면 건너뛰되 그 사실을 알린다."""
    if not pkgs:
        return 0, "설치 대상 패키지를 찾지 못했습니다."
    try:
        subprocess.run([sys.executable, "-m", "pip_audit", "--version"],
                       capture_output=True, check=True)
    except Exception:                  # noqa: BLE001
        return 0, "pip-audit 미설치 — 취약점 조회를 건너뜁니다(설치: pip install pip-audit)."
    req = "\n".join(sorted(pkgs)) + "\n"
    tmp = Path(".sca-requirements.txt")
    tmp.write_text(req, encoding="utf-8")
    try:
        r = subprocess.run([sys.executable, "-m", "pip_audit", "-r", str(tmp),
                            "--format", "json", "--progress-spinner", "off"],
                           capture_output=True, text=True, timeout=600)
        try:
            deps = json.loads(r.stdout or "{}").get("dependencies", [])
        except json.JSONDecodeError:
            return 0, f"pip-audit 출력을 읽지 못했습니다: {r.stderr.strip()[:160]}"
        vulns = [(d["name"], d.get("version", "?"), v["id"])
                 for d in deps for v in d.get("vulns", [])]
        if vulns:
            lines = "\n".join(f"    {n} {v}  {vid}" for n, v, vid in vulns)
            return len(vulns), f"알려진 취약점 {len(vulns)}건:\n{lines}"
        return 0, f"취약점 없음 (조회 {len(deps)}개)"
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    fails = 0

    print("== 부동 자동실행 스펙 ==")
    fl = scan_mcp_launchers(root)
    if fl:
        for x in fl:
            print(f"  [차단] {x['file']}  server={x['server']}  "
                  f"{x['runner']} {x['spec']}  (버전 미고정)")
        print("  핀한 커밋 SHA 로 고정되지 않는 코드입니다. 정확한 버전으로 고정하세요.")
        fails += len(fl)
    else:
        print("  없음 — 세션 시작 시 레지스트리에서 코드를 끌어오는 런처가 없습니다.")

    print("\n== 알려진 취약점 (OSV) ==")
    pkgs = scan_pip_targets(root)
    print(f"  런타임 설치 대상: {', '.join(sorted(pkgs)) or '(없음)'}")
    n, msg = audit(pkgs)
    print(f"  {msg}")
    fails += n

    print()
    if fails:
        print(f"실패 — 차단 대상 {fails}건.")
        return 1
    print("통과.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
