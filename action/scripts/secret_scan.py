#!/usr/bin/env python3
"""정보유출 검사 — 자격증명이 이 저장소에 들어오는 것을 막는다.

이 repo 는 public 이다. 한 번 push 된 비밀은 삭제해도 GitHub 이벤트 API·포크·미러에 남으므로
"나중에 지우면 된다"가 성립하지 않는다. 그래서 이 검사만은 baseline 도, 예외 한도도 없다 —
하나라도 걸리면 실패다.

형태(shape)로 잡는다. 특정 값을 하드코딩하면 그 값을 바꾼 순간 무력해지고, 하드코딩한 비밀이
이 파일에 남는 자기모순이 된다.

종료코드: 0 = 깨끗, 1 = 발견(차단), 2 = 실행 오류
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# (이름, 정규식, 설명). 값이 아니라 모양을 본다.
RULES = [
    ("google_app_password",
     r"\b(?:[a-z]{4}\s){3}[a-z]{4}\b",
     "Google 앱 비밀번호 (4자×4 묶음)"),
    ("github_token",
     r"\bgh[pousr]_[A-Za-z0-9]{16,}\b",
     "GitHub 토큰"),
    ("anthropic_key",
     r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b",
     "Anthropic API 키"),
    ("openai_key",
     r"\bsk-(?!ant-)[A-Za-z0-9]{32,}\b",
     "OpenAI 계열 API 키"),
    ("aws_access_key",
     r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b",
     "AWS 액세스 키 ID"),
    ("slack_token",
     r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b",
     "Slack 토큰"),
    ("private_key_block",
     r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----",
     "개인키 블록"),
    ("bearer_literal",
     r"(?i)\b(?:authorization|bearer)\b\s*[:=]\s*[\"']?[A-Za-z0-9_\-\.]{24,}",
     "코드에 박힌 Bearer 토큰"),
    ("password_assignment",
     r"(?i)\b(?:password|passwd|app_password|secret|api_key|token)\s*[:=]\s*[\"'][^\"'\s${}]{8,}[\"']",
     "비밀번호/키 리터럴 대입"),
]

TEXT_SUFFIXES = {".py", ".js", ".ts", ".sh", ".md", ".json", ".yml", ".yaml", ".toml", ".txt", ".env"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv"}
# 이 파일 자체는 규칙(=비밀처럼 생긴 정규식)을 담고 있으므로 건너뛴다.
SKIP_FILES = {"secret_scan.py"}

# 값이 아니라 자리표시자인 줄. 문서에서 사용법을 설명할 때 필요하다.
PLACEHOLDER = re.compile(
    r"(?i)(x{4,}|\.\.\.|<[a-z_ ]+>|\byour[-_ ]|\bexample\b|여기에|앱 비밀번호 16자|"
    r"\$\{|%\(|\bREDACTED\b|\bdummy\b|\bfake\b|\bplaceholder\b)")


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    compiled = [(n, re.compile(rx), d) for n, rx, d in RULES]
    hits = []
    for f in sorted(root.rglob("*")):
        if not f.is_file() or SKIP_DIRS & set(f.parts) or f.name in SKIP_FILES:
            continue
        if f.suffix not in TEXT_SUFFIXES and f.name != ".env":
            continue
        try:
            lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        rel = f.relative_to(root).as_posix()
        for n, line in enumerate(lines, 1):
            if PLACEHOLDER.search(line):
                continue
            for name, rx, desc in compiled:
                m = rx.search(line)
                if m:
                    shown = m.group(0)
                    masked = shown[:4] + "*" * max(0, len(shown) - 8) + shown[-4:]
                    hits.append((rel, n, name, desc, masked))

    if hits:
        print(f"자격증명으로 보이는 것 {len(hits)}건 — 이 저장소는 public 입니다.\n")
        for rel, n, name, desc, masked in hits:
            print(f"  {rel}:{n}  [{name}] {desc}")
            print(f"      {masked}")
        print("\n실패. 값을 지우고 환경변수/시크릿으로 옮기세요. 이미 커밋했다면 "
              "**그 자격증명을 폐기**해야 합니다 — 되돌려도 이력에서 회수됩니다.")
        return 1
    print(f"통과 — {root}: 자격증명 형태 없음.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
