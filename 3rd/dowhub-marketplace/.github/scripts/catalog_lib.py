#!/usr/bin/env python3
"""카탈로그를 다루는 공용 조각 — 같은 규칙을 두 번 적지 않기 위해.

카탈로그 카드에 적힌 값(버전·도구 목록)은 **어딘가에 있는 진실원의 사본**이다. 사본은
반드시 어긋난다 — 실제로 aar-plugin 이 1.0.15 로 올라간 뒤에도 카드는 1.0.14 를,
aar-mcp 카드는 **이미 없어진 도구 43개**를 계속 광고했다. 어느 쪽도 보안 검사로는 안 잡힌다.

그래서 규칙은 하나다: **카드 값은 손으로 적지 않는다. 진실원에서 끌어온다.**
이 파일은 "그 진실원이 어디냐"를 한 곳에 모은다. 두 스크립트가 각자 경로를 해석하다
한쪽만 고쳐지는 걸 막기 위해서다(실제로 `lstrip("./")` 오용이 양쪽에 복사돼 있었다).
"""

from __future__ import annotations

import json
from pathlib import Path

CATALOG = Path(".claude-plugin/marketplace.json")


def asset_dir(src) -> Path | None:
    """카드의 source 를 저장소 경로로. 문자열 source 만 로컬 자산이다.

    🚨 `lstrip("./")` 을 쓰지 마라 — 그건 접두사가 아니라 **문자 집합**을 지운다.
    `"./.hidden/x".lstrip("./")` 은 `"hidden/x"` 가 돼 폴더를 못 찾는다(양쪽 스크립트에
    같은 실수가 복사돼 있었다). 접두사를 지우려면 removeprefix 다.
    """
    if not isinstance(src, str) or not src:
        return None
    return Path(src.removeprefix("./"))


def load_catalog() -> dict:
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def save_catalog(doc: dict) -> None:
    CATALOG.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")


def _frontmatter_value(md: Path, key: str) -> str | None:
    """SKILL.md 맨 앞 YAML 블록에서 한 줄짜리 값 하나. (의존성 없이 읽으려고 최소만 판다)"""
    try:
        lines = md.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        if line.startswith(f"{key}:"):
            return line[len(key) + 1:].strip().strip("'\"") or None
    return None


def truth_version(entry: dict) -> str | None:
    """이 항목의 진짜 버전. 없으면 None(= 저장소가 확인해 줄 수 없는 값).

    · plugin → `<source>/.claude-plugin/plugin.json` 의 version (설치·업데이트를 결정하는 값)
    · skill  → `<source>/SKILL.md` frontmatter 의 version
    · mcp    → 없다. 실물은 살아있는 서버라 저장소가 버전을 알 수 없다.
    """
    hub = entry.get("hub") or {}
    d = asset_dir(entry.get("source"))
    if d is None:
        return None
    if hub.get("type") == "plugin":
        man = d / ".claude-plugin" / "plugin.json"
        if not man.is_file():
            return None
        try:
            return json.loads(man.read_text(encoding="utf-8")).get("version")
        except json.JSONDecodeError:
            return None
    if hub.get("type") == "skill":
        return _frontmatter_value(d / "SKILL.md", "version")
    return None


def tools_snapshot_path(entry: dict) -> Path | None:
    """MCP 도구 목록 스냅샷의 위치(`<source>/tools.json`)."""
    hub = entry.get("hub") or {}
    if hub.get("type") != "mcp":
        return None
    d = asset_dir(entry.get("source"))
    return None if d is None else d / "tools.json"


def truth_tools(entry: dict) -> list[str] | None:
    """카드가 광고해도 되는 도구 목록. 스냅샷이 없으면 None.

    MCP 의 진실원은 **살아있는 서버**라 이 저장소가 직접 확인할 수 없다. 그래서 서버 소스에서
    떠 온 스냅샷(`tools.json`)을 저장소 안에 두고, 카드는 **그 파일에서만** 값을 가져오게 한다.
    서버↔스냅샷 사이 시차는 남지만(그건 `sync_mcp_tools.py` 를 돌려 없앤다), 적어도
    **카드가 저장소 안 어떤 근거도 없이 도구를 광고하는 일**은 없어진다.
    """
    p = tools_snapshot_path(entry)
    if p is None or not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    tools = data.get("tools")
    return tools if isinstance(tools, list) else None


def truth_description(entry: dict) -> str | None:
    """카드 설명의 진실원. plugin 은 plugin.json 의 description 이 그것이다."""
    hub = entry.get("hub") or {}
    d = asset_dir(entry.get("source"))
    if hub.get("type") != "plugin" or d is None:
        return None
    man = d / ".claude-plugin" / "plugin.json"
    if not man.is_file():
        return None
    try:
        return json.loads(man.read_text(encoding="utf-8")).get("description")
    except json.JSONDecodeError:
        return None


def truth_skills(entry: dict) -> list[str] | None:
    """플러그인이 실제로 들고 있는 스킬 = `<source>/skills/*/SKILL.md`.

    손으로 적으면 반드시 어긋난다 — 실제로 카드는 3종, README 는 3종, 플러그인 안 옛 카탈로그는
    4종이라 적어두고 실물은 **5종**이었다. 폴더가 말하게 한다.
    """
    hub = entry.get("hub") or {}
    d = asset_dir(entry.get("source"))
    if hub.get("type") != "plugin" or d is None:
        return None
    sk = d / "skills"
    if not sk.is_dir():
        return None
    return sorted(x.name for x in sk.iterdir() if (x / "SKILL.md").is_file())
