#!/usr/bin/env python3
"""SAST — 스킬·플러그인 소스를 정적 패턴으로 훑는다.

패턴은 두 오픈소스에서 그대로 가져왔다(출처·라이선스는 licenses/ 참조):
  skillspector_patterns.py : NVIDIA/SkillSpector (Apache-2.0), 504개 / 13 카테고리
  clawvet_patterns.py      : MohibShaikh/clawvet (MIT), 57개 / 13 카테고리

이 스캐너의 목적은 "위험한 걸 찾는 것"이 아니라 **"선언되지 않은 위험이 늘었는지"** 를 보는 것이다.
스킬은 원래 코드를 실행하고 밖으로 나간다 — gmail_peek 만 해도 credential_theft·data_exfiltration 이
정직하게 잡힌다. 그래서 매 실행의 절대 건수로 막으면 아무것도 배포 못 한다. 대신 각 자산이
baseline.json 에 자기 몫을 선언하게 하고, **그 선을 넘는 것만** 실패로 만든다. 선을 올리는 행위는
곧 baseline 을 고치는 커밋이고, 그건 PR 에서 사람 눈에 보인다.

종료코드: 0 = 통과, 1 = baseline 초과(승인 필요), 2 = 실행 오류
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from clawvet_patterns import CLAWVET_PATTERNS          # noqa: E402
from skillspector_patterns import SKILLSPECTOR_PATTERNS  # noqa: E402

# 본문을 읽을 확장자. 나머지(이미지·아카이브)는 건너뛴다.
TEXT_SUFFIXES = {".py", ".js", ".ts", ".sh", ".md", ".json", ".yml", ".yaml", ".toml", ".txt"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "licenses"}
BLOCKING = {"high", "critical"}
ALLOWLIST = Path(".github/sast-allowlist.json")


def load_allowlist() -> tuple[dict, list[str]]:
    """오탐 예외. baseline 과 목적이 다르다 — baseline 은 '위험하지만 승인', 여기는 '위험 아님'."""
    if not ALLOWLIST.exists():
        return {}, []
    d = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    return d.get("rules", {}), d.get("first_party_hosts", [])


URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+")


def suppressed(rule_id: str, line: str, rules: dict, hosts: list[str]) -> bool:
    r = rules.get(rule_id)
    if not r:
        return False
    if r.get("ignore_always"):
        return True
    if r.get("ignore_only_first_party") or r.get("ignore_if_only_first_party"):
        urls = URL_RE.findall(line)
        # URL 이 하나라도 있고 전부 우리 것이면 오탐이다.
        return bool(urls) and all(any(h in u for h in hosts) for u in urls)
    return False


def compiled():
    """두 출처의 패턴을 (rule_id, category, severity, title, 정규식, 코드전용) 으로 통일한다.

    형태가 다르다 — skillspector 는 5-튜플, clawvet 은 dict. 원본을 verbatim 으로 유지하는 게
    갱신할 때 유리하므로 변환은 여기서만 한다. clawvet 의 code_only 는 지켜야 한다:
    `curl | sh` 같은 규칙은 코드에서 위험하지만 문서에 적힌 예시까지 잡으면 오탐이 된다."""
    raw = []
    for p in SKILLSPECTOR_PATTERNS:
        rule_id, cat, sev, title, rx = p
        raw.append((rule_id, cat, sev, title, rx, False))
    for p in CLAWVET_PATTERNS:
        raw.append((p["name"], p["category"], p["severity"], p["title"],
                    p["regex"], bool(p.get("code_only"))))

    out = []
    for rule_id, cat, sev, title, rx, code_only in raw:
        try:
            out.append((rule_id, cat, sev, title, re.compile(rx, re.I), code_only))
        except re.error:
            continue          # 한 패턴이 깨졌다고 전체 스캔을 못 돌리면 안 된다
    return out


def scan_target(root: Path, patterns) -> list[dict]:
    rules, hosts = load_allowlist()
    findings = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.suffix not in TEXT_SUFFIXES:
            continue
        if SKIP_DIRS & set(f.parts):
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = f.relative_to(root).as_posix()
        is_code = f.suffix not in (".md", ".txt")
        for n, line in enumerate(lines, 1):
            if len(line) > 4000:      # 압축된 한 줄짜리 번들: 정규식이 폭주한다
                continue
            for rule_id, cat, sev, title, rx, code_only in patterns:
                if code_only and not is_code:
                    continue          # 문서에 적힌 예시까지 잡으면 오탐이다
                if rx.search(line):
                    if suppressed(rule_id, line, rules, hosts):
                        continue
                    findings.append({"file": rel, "line": n, "category": cat,
                                     "severity": sev, "rule": rule_id, "title": title,
                                     "excerpt": line.strip()[:120]})
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("targets", nargs="*", help="검사할 폴더 (없으면 skills/ + plugins/ 전부)")
    ap.add_argument("--baseline", default=".github/sast-baseline.json")
    ap.add_argument("--update-baseline", action="store_true",
                    help="현재 결과를 baseline 으로 기록한다(사람이 검토한 뒤에만 쓸 것)")
    ap.add_argument("--json-out", default="")
    ap.add_argument("--print-version", action="store_true",
                    help="패턴 개수를 버전으로 출력한다 — 규칙이 늘면 판정도 달라지므로 태그에 박는다")
    args = ap.parse_args()

    if args.print_version:
        print(f"skillspector {len(SKILLSPECTOR_PATTERNS)}+clawvet {len(CLAWVET_PATTERNS)}")
        return 0

    repo = Path.cwd()
    targets = [Path(t) for t in args.targets] or \
        [p for base in ("skills", "plugins") for p in sorted(Path(base).glob("*")) if p.is_dir()]
    if not targets:
        print("검사할 대상이 없습니다.")
        return 0

    patterns = compiled()
    print(f"패턴 {len(patterns)}개 로드 (skillspector {len(SKILLSPECTOR_PATTERNS)} + "
          f"clawvet {len(CLAWVET_PATTERNS)})\n")

    baseline_path = repo / args.baseline
    baseline = {}
    if baseline_path.exists():
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    report, failed, new_baseline = {}, [], {}
    for t in targets:
        if not t.is_dir():
            continue
        key = t.as_posix()
        f = scan_target(t, patterns)
        report[key] = f
        blocking = [x for x in f if x["severity"] in BLOCKING]
        by_cat = Counter(x["category"] for x in blocking)
        new_baseline[key] = dict(sorted(by_cat.items()))

        allowed = baseline.get(key, {})
        over = {c: n for c, n in by_cat.items() if n > allowed.get(c, 0)}
        mark = "FAIL" if over else "ok"
        print(f"[{mark:4}] {key}: 전체 {len(f)}건 / 차단대상(high+) {len(blocking)}건")
        for c, n in sorted(by_cat.items()):
            lim = allowed.get(c, 0)
            flag = "  <== 승인된 한도 초과" if n > lim else ""
            print(f"         {c:22} {n:3} (승인됨 {lim}){flag}")
        if over:
            failed.append(key)
            for c in over:
                for x in [y for y in blocking if y["category"] == c][:3]:
                    print(f"           {x['file']}:{x['line']}  {x['rule']}  {x['excerpt'][:70]}")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                       encoding="utf-8")
    if args.update_baseline:
        # 🚨 스캔한 대상만 갱신하고 나머지는 **보존**한다. 전에는 new_baseline 으로 파일을
        #    통째로 덮어써서, 한 자산만 지정해 돌리면 다른 자산의 승인 한도가 조용히 사라졌다
        #    (그 자산들이 그 뒤 무한 허용이 아니라 '한도 0' 이 돼 다음 PR 에서 엉뚱하게 실패한다).
        merged = dict(baseline)
        merged.update(new_baseline)
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(dict(sorted(merged.items())),
                                            ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        changed = [k for k in new_baseline if baseline.get(k) != new_baseline[k]]
        print(f"\nbaseline 갱신: {baseline_path}"
              f" (바뀐 자산 {len(changed)}개: {', '.join(changed) or '없음'}, 나머지 {len(merged)-len(new_baseline)}개 보존)")
        return 0

    if failed:
        print(f"\n실패: {', '.join(failed)}")
        print("승인된 한도를 넘었습니다. 의도한 변경이면 baseline 을 같은 PR 에서 함께 고치세요"
              " (그 diff 가 리뷰어에게 '위험이 늘었다'는 신호가 됩니다).")
        return 1
    print("\n통과 — 승인된 한도 안입니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
