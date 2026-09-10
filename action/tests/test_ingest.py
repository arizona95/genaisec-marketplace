"""ingest.py — 업로드 파일을 저장소 규격 자산으로 바꾸는 규칙을 검사한다.

픽스처는 저장소의 probe 자산을 zip 으로 묶어 만든다(별도 픽스처 파일 없음). 실행:
    python -m unittest action/tests/test_ingest.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "action" / "scripts"))

import ingest  # noqa: E402


def zip_dir(src: Path, dest: Path, wrap: str | None = None) -> Path:
    """폴더를 zip 으로. wrap 이 있으면 그 이름의 최상위 폴더로 감싼다(사람이 폴더째 압축한 모양)."""
    with zipfile.ZipFile(dest, "w") as z:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                rel = p.relative_to(src).as_posix()
                z.write(p, f"{wrap}/{rel}" if wrap else rel)
    return dest


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ingest-test-"))
        # 카탈로그·자산 폴더가 있는 가짜 저장소
        self.repo = self.tmp / "repo"
        for b in ("skills", "mcp", "plugins", ".claude-plugin"):
            (self.repo / b).mkdir(parents=True)
        (self.repo / ".claude-plugin" / "marketplace.json").write_text(json.dumps(
            {"name": "t", "owner": {"name": "t"}, "plugins": []}), encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class Classify(Fixture):
    def test_skill_plugin_form(self):
        z = zip_dir(ROOT / "skills/probe-skill-norm-1", self.tmp / "a.zip", wrap="probe-skill-norm-1")
        r = ingest.inspect(z)
        self.assertEqual((r.kind, r.name), ("skill", "probe-skill-norm-1"))

    def test_bare_skill_md(self):
        d = self.tmp / "bare"; d.mkdir()
        (d / "SKILL.md").write_text("---\nname: My_Cool Skill\ndescription: hi\nversion: 2.0.0\n---\n# x\n", encoding="utf-8")
        z = zip_dir(d, self.tmp / "bare.skill")
        r = ingest.inspect(z)
        self.assertEqual((r.kind, r.name), ("skill", "my-cool-skill"))

    def test_mcp_plugin_form(self):
        z = zip_dir(ROOT / "mcp/probe-localhost-local-norm-1", self.tmp / "m.zip")
        r = ingest.inspect(z)
        self.assertEqual((r.kind, r.name), ("mcp", "probe-localhost-local-norm-1"))

    def test_mcpb_manifest_only(self):
        d = self.tmp / "bundle"; d.mkdir()
        (d / "manifest.json").write_text(json.dumps({"manifest_version": "0.1", "name": "Bundle One",
                                                      "version": "0.3.0", "description": "d",
                                                      "server": {"type": "python", "entry_point": "server.py"}}))
        (d / "server.py").write_text("from mcp.server.fastmcp import FastMCP\nmcp = FastMCP('x')\n"
                                     "@mcp.tool()\ndef hello():\n    return 1\n")
        z = zip_dir(d, self.tmp / "b.mcpb")
        r = ingest.inspect(z)
        self.assertEqual((r.kind, r.name), ("mcp", "bundle-one"))

    def test_plugin_with_commands(self):
        z = zip_dir(ROOT / "plugins/probe-plugin-norm-1", self.tmp / "p.zip", wrap="probe-plugin-norm-1")
        r = ingest.inspect(z)
        self.assertEqual((r.kind, r.name), ("plugin", "probe-plugin-norm-1"))

    def test_unknown_is_pass(self):
        d = self.tmp / "junk"; d.mkdir()
        (d / "README.md").write_text("nothing")
        z = zip_dir(d, self.tmp / "j.zip")
        with self.assertRaises(ingest.Pass):
            ingest.inspect(z)

    def test_bad_extension(self):
        f = self.tmp / "x.tar.gz"; f.write_bytes(b"x")
        with self.assertRaises(ingest.Pass):
            ingest.inspect(f)

    def test_not_a_zip(self):
        f = self.tmp / "x.zip"; f.write_bytes(b"not a zip")
        with self.assertRaises(ingest.Pass):
            ingest.inspect(f)


class Place(Fixture):
    def test_bare_skill_normalized(self):
        d = self.tmp / "bare"; d.mkdir()
        (d / "SKILL.md").write_text("---\nname: bare-one\ndescription: 설명\nversion: 1.2.3\n---\n# x\n", encoding="utf-8")
        z = zip_dir(d, self.tmp / "bare.skill")
        r = ingest.inspect(z)
        dest = ingest.place(r, self.repo)
        self.assertEqual(dest, self.repo / "skills/bare-one")
        man = json.loads((dest / ".claude-plugin/plugin.json").read_text())
        self.assertEqual((man["name"], man["version"], man["description"]), ("bare-one", "1.2.3", "설명"))
        self.assertTrue((dest / "skills/bare-one/SKILL.md").is_file())
        cat = json.loads((self.repo / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(cat["plugins"][0]["source"], "./skills/bare-one")
        self.assertEqual(cat["plugins"][0]["hub"]["type"], "skill")

    def test_mcpb_normalized(self):
        d = self.tmp / "bundle"; d.mkdir()
        (d / "manifest.json").write_text(json.dumps({"manifest_version": "0.1", "name": "bundle-one",
                                                      "version": "0.3.0", "description": "d",
                                                      "server": {"type": "python", "entry_point": "server.py"}}))
        (d / "server.py").write_text("@mcp.tool()\ndef hello():\n    return 1\n")
        z = zip_dir(d, self.tmp / "b.mcpb")
        dest = ingest.place(ingest.inspect(z), self.repo)
        self.assertEqual(dest, self.repo / "mcp/bundle-one")
        mcp = json.loads((dest / ".mcp.json").read_text())
        self.assertEqual(mcp["mcpServers"]["bundle-one"]["args"], ["server.py"])
        self.assertEqual(json.loads((dest / "tools.json").read_text())["tools"], ["hello"])
        self.assertTrue((dest / ".claude-plugin/plugin.json").is_file())
        cat = json.loads((self.repo / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(cat["plugins"][0]["hub"]["url"], "stdio://python server.py")

    def test_replace_existing(self):
        z = zip_dir(ROOT / "skills/probe-skill-norm-1", self.tmp / "a.zip")
        ingest.place(ingest.inspect(z), self.repo)
        (self.repo / "skills/probe-skill-norm-1/stale.txt").write_text("old")
        ingest.place(ingest.inspect(z), self.repo)
        self.assertFalse((self.repo / "skills/probe-skill-norm-1/stale.txt").exists())
        cat = json.loads((self.repo / ".claude-plugin/marketplace.json").read_text())
        self.assertEqual(len(cat["plugins"]), 1)

    def test_zip_slip_rejected(self):
        z = self.tmp / "evil.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("SKILL.md", "---\nname: evil\n---\n")
            zf.writestr("../../escape.txt", "x")
        with self.assertRaises(ingest.Pass):
            ingest.inspect(z)


if __name__ == "__main__":
    unittest.main()
