#!/usr/bin/env python3
"""업로드 파일(.zip / .skill / .mcpb) → 저장소 규격 자산 폴더 + 카탈로그 항목.

비개발자가 클론 없이 올리는 길의 첫 단계다. 여기서는 git 을 모른다 — 압축을 풀고, 무엇인지
판별하고, 저장소가 요구하는 모양으로 옮겨 놓고, 카탈로그에 항목을 넣는 것까지만 한다.
(브랜치·PR 은 publish_upload.py 가 한다.)

판별 규칙(한 곳에만 적는다):
  · `.claude-plugin/plugin.json` 이 있으면 구성요소 집합으로 가른다 —
      {skills} 만 → skill, {mcp} 만 → mcp, 그 외(commands/agents/hooks 포함·둘 이상) → plugin
  · plugin.json 이 없으면
      `.mcp.json` 또는 MCPB `manifest.json`(server 키) → mcp
      `SKILL.md`(루트 또는 skills/*/) → skill
      아니면 → Pass (아무것도 하지 않는다)

이름은 plugin.json → manifest.json → SKILL.md frontmatter → 파일명 순으로 잡고 kebab-case 로
정규화한다(validate_catalog 의 규칙 — claude.ai 동기화가 kebab 만 받는다).

    python action/scripts/ingest.py <파일> --repo . [--write]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog_lib as lib  # noqa: E402
from sync_mcp_tools import tools_from_source  # noqa: E402

ALLOWED_EXT = (".zip", ".skill", ".mcpb")
MAX_BYTES = 50 * 1024 * 1024
BASE_DIR = {"skill": "skills", "mcp": "mcp", "plugin": "plugins"}
_KEBAB_OK = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class Pass(Exception):
    """판별 불가·규격 위반 — 저장소에 아무 흔적도 남기지 않고 이유만 돌려준다."""


@dataclass
class Asset:
    kind: str                 # skill | mcp | plugin
    name: str                 # kebab-case
    root: Path                # 압축 해제된 자산 루트
    workdir: Path             # 임시 폴더(호출자가 정리)
    version: str = "1.0.0"
    description: str = ""
    notes: list[str] = field(default_factory=list)   # 정규화하며 한 일(사람에게 보여줄 것)

    def cleanup(self) -> None:
        shutil.rmtree(self.workdir, ignore_errors=True)


def kebab(name: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", name).lower()).strip("-")
    if not _KEBAB_OK.match(out):
        raise Pass(f"이름을 kebab-case 로 만들 수 없다: {name!r}")
    return out


def _json(p: Path) -> dict:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _frontmatter(md: Path) -> dict[str, str]:
    """SKILL.md 맨 앞 YAML 블록의 한 줄짜리 값들. catalog_lib 와 같은 최소 파서."""
    out: dict[str, str] = {}
    try:
        lines = md.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    if not lines or lines[0].strip() != "---":
        return out
    for line in lines[1:]:
        if line.strip() == "---":
            break
        k, sep, v = line.partition(":")
        if sep and k.strip() and not line.startswith(" "):
            out[k.strip()] = v.strip().strip("'\"")
    return out


# ── 1. 압축 해제 ─────────────────────────────────────────────────────────────
def extract(path: Path) -> Path:
    """zip 컨테이너를 임시 폴더에 푼다. zip-slip·크기·확장자를 여기서 막는다."""
    if path.suffix.lower() not in ALLOWED_EXT:
        raise Pass(f"허용 확장자가 아니다({', '.join(ALLOWED_EXT)}): {path.name}")
    if path.stat().st_size > MAX_BYTES:
        raise Pass(f"{MAX_BYTES // (1024 * 1024)}MB 를 넘는다: {path.name}")
    if not zipfile.is_zipfile(path):
        raise Pass(f"zip 형식이 아니다: {path.name}")
    work = Path(tempfile.mkdtemp(prefix="ingest-"))
    out = work / "x"
    out.mkdir()
    with zipfile.ZipFile(path) as z:
        total = 0
        for info in z.infolist():
            name = info.filename
            if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                shutil.rmtree(work, ignore_errors=True)
                raise Pass(f"압축 안에 바깥을 가리키는 경로가 있다: {name}")
            total += info.file_size
            if total > MAX_BYTES * 4:
                shutil.rmtree(work, ignore_errors=True)
                raise Pass("압축 해제 크기가 너무 크다")
        z.extractall(out)
    return work


def find_root(extracted: Path) -> Path:
    """자산 루트. 사람이 폴더째 압축하면 최상위 폴더 하나가 감싸고 있다 — 그걸 벗긴다."""
    def entries(d: Path) -> list[Path]:
        return [p for p in d.iterdir() if p.name not in ("__MACOSX", ".DS_Store")]
    cur = extracted
    for _ in range(3):
        es = entries(cur)
        if len(es) == 1 and es[0].is_dir() and not _looks_like_asset(cur):
            cur = es[0]
        else:
            break
    return cur


def _looks_like_asset(d: Path) -> bool:
    return any((d / f).exists() for f in (".claude-plugin/plugin.json", ".mcp.json", "manifest.json", "SKILL.md", "skills"))


# ── 2. 판별 ──────────────────────────────────────────────────────────────────
def classify(root: Path) -> str:
    man = _json(root / ".claude-plugin" / "plugin.json") if (root / ".claude-plugin" / "plugin.json").is_file() else None
    has_skills = (root / "SKILL.md").is_file() or any((root / "skills").glob("*/SKILL.md"))
    has_mcp = (root / ".mcp.json").is_file() or bool(_json(root / "manifest.json").get("server"))
    has_other = any((root / d).is_dir() and any((root / d).iterdir()) for d in ("commands", "agents", "hooks"))
    if man is not None:
        parts = {k for k, v in (("skills", has_skills), ("mcp", has_mcp), ("other", has_other)) if v}
        if parts == {"skills"}:
            return "skill"
        if parts == {"mcp"}:
            return "mcp"
        if parts:
            return "plugin"
        raise Pass("plugin.json 은 있는데 skills/·commands/·agents/·hooks/·.mcp.json 중 아무것도 없다")
    if has_mcp:
        return "mcp"
    if has_skills:
        return "skill"
    raise Pass("skill(SKILL.md)·mcp(.mcp.json/manifest.json)·plugin(.claude-plugin/plugin.json) 어느 것도 아니다")


def _identity(root: Path, kind: str, fallback: str) -> tuple[str, str, str]:
    """(이름, 버전, 설명) — 진실원 우선순위: plugin.json → manifest.json → SKILL.md → 파일명."""
    man = _json(root / ".claude-plugin" / "plugin.json")
    if man.get("name"):
        return str(man["name"]), str(man.get("version") or "1.0.0"), str(man.get("description") or "")
    mf = _json(root / "manifest.json")
    if kind == "mcp" and mf.get("name"):
        return str(mf["name"]), str(mf.get("version") or "1.0.0"), str(mf.get("description") or "")
    md = root / "SKILL.md"
    if not md.is_file():
        found = sorted((root / "skills").glob("*/SKILL.md"))
        md = found[0] if found else md
    fm = _frontmatter(md) if md.is_file() else {}
    if fm.get("name"):
        return fm["name"], fm.get("version") or "1.0.0", fm.get("description") or ""
    return fallback, "1.0.0", ""


def inspect(path: Path) -> Asset:
    """파일 하나를 열어 무엇인지 알아낸다. 실패하면 Pass(임시 폴더는 정리됨)."""
    path = Path(path)
    work = extract(path)
    try:
        root = find_root(work / "x")
        kind = classify(root)
        raw, version, desc = _identity(root, kind, Path(path.name).stem)
        return Asset(kind=kind, name=kebab(raw), root=root, workdir=work, version=version, description=desc)
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


# ── 3. 정규화 + 배치 ─────────────────────────────────────────────────────────
def _write_json(p: Path, doc: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_plugin_json(a: Asset, dest: Path) -> None:
    man = dest / ".claude-plugin" / "plugin.json"
    if man.is_file():
        return
    _write_json(man, {"name": a.name, "version": a.version, "description": a.description,
                      "author": {"name": "upload"}})
    a.notes.append("plugin.json 생성")


def _normalize_skill(a: Asset, dest: Path) -> None:
    # 루트 SKILL.md(옛 형태) → skills/<name>/SKILL.md 로. 채팅 쪽 동기화가 그 형태만 스킬로 본다.
    if (a.root / "SKILL.md").is_file() and not any((a.root / "skills").glob("*/SKILL.md")):
        inner = dest / "skills" / a.name
        inner.mkdir(parents=True)
        for p in a.root.iterdir():
            if p.name in (".claude-plugin",):
                shutil.copytree(p, dest / p.name)
            elif p.is_dir():
                shutil.copytree(p, inner / p.name)
            else:
                shutil.copy2(p, inner / p.name)
        a.notes.append(f"SKILL.md 를 skills/{a.name}/ 로 감쌈")
    else:
        shutil.copytree(a.root, dest)
    _ensure_plugin_json(a, dest)


def _normalize_mcp(a: Asset, dest: Path) -> str:
    """mcp 폴더를 만들고 카드에 적을 hub.url 을 돌려준다."""
    shutil.copytree(a.root, dest)
    _ensure_plugin_json(a, dest)
    mcp_json = dest / ".mcp.json"
    if not mcp_json.is_file():
        server = _json(dest / "manifest.json").get("server") or {}
        entry = server.get("entry_point") or ""
        cmd = {"python": "python", "node": "node", "binary": entry}.get(server.get("type"), "")
        if not cmd or (server.get("type") != "binary" and not entry):
            raise Pass("manifest.json 의 server(type/entry_point) 로 .mcp.json 을 만들 수 없다")
        spec = {"type": "stdio", "command": cmd, "args": [] if server.get("type") == "binary" else [entry]}
        _write_json(mcp_json, {"mcpServers": {a.name: spec}})
        a.notes.append(".mcp.json 을 manifest.json 에서 생성")
    # 도구 스냅샷: 있으면 그대로, 없으면 소스에서 뜬다. 못 뜨면 안 만든다(근거 없는 광고 금지).
    if not (dest / "tools.json").is_file():
        found: list[str] = []
        src_used = ""
        for py in sorted(dest.rglob("*.py")):
            try:
                t = tools_from_source(py)
            except SyntaxError:
                continue
            if t:
                found, src_used = t, py.relative_to(dest).as_posix()
                break
        if found:
            _write_json(dest / "tools.json", {"generated_from": src_used, "generated_at": "",
                                              "note": "업로드 시 서버 소스에서 뜬 스냅샷. 카드는 여기서만 값을 가져온다.",
                                              "tools": found})
            a.notes.append(f"tools.json 생성({len(found)}개, {src_used})")
    return _hub_url(mcp_json)


def _hub_url(mcp_json: Path) -> str:
    servers = _json(mcp_json).get("mcpServers") or {}
    for spec in servers.values():
        if not isinstance(spec, dict):
            continue
        if spec.get("url"):
            return str(spec["url"])
        if spec.get("command"):
            return "stdio://" + " ".join([str(spec["command"]), *map(str, spec.get("args") or [])])
    return "stdio://unknown"


def place(a: Asset, repo: Path) -> Path:
    """저장소 안 <base>/<name>/ 에 놓고 카탈로그 항목을 추가/교체한다. 같은 이름은 업데이트다."""
    repo = Path(repo)
    dest = repo / BASE_DIR[a.kind] / a.name
    if dest.exists():
        shutil.rmtree(dest)
        a.notes.append("같은 이름이 있어 교체(업데이트)")
    dest.parent.mkdir(parents=True, exist_ok=True)
    url = None
    if a.kind == "skill":
        _normalize_skill(a, dest)
    elif a.kind == "mcp":
        url = _normalize_mcp(a, dest)
    else:
        shutil.copytree(a.root, dest)

    catalog = repo / lib.CATALOG
    doc = json.loads(catalog.read_text(encoding="utf-8"))
    entries = [e for e in doc.get("plugins", []) if e.get("name") != a.name]
    entry: dict = {"name": a.name, "source": f"./{BASE_DIR[a.kind]}/{a.name}",
                   "hub": {"type": a.kind, "status": "published"}}
    if url:
        entry["hub"]["url"] = url
    entries.append(entry)
    doc["plugins"] = entries
    catalog.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--repo", default=".")
    ap.add_argument("--write", action="store_true", help="저장소에 실제로 놓는다(없으면 판별만)")
    args = ap.parse_args()
    try:
        a = inspect(Path(args.file))
    except Pass as e:
        print(json.dumps({"pass": True, "reason": str(e)}, ensure_ascii=False))
        return 3
    try:
        out = {"kind": a.kind, "name": a.name, "version": a.version, "description": a.description}
        if args.write:
            out["dest"] = str(place(a, Path(args.repo)))
            out["notes"] = a.notes
        print(json.dumps(out, ensure_ascii=False))
        return 0
    except Pass as e:
        print(json.dumps({"pass": True, "reason": str(e)}, ensure_ascii=False))
        return 3
    finally:
        a.cleanup()


if __name__ == "__main__":
    sys.exit(main())
