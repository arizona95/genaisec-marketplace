#!/usr/bin/env python3
"""정보유출 검사 (필수).

두 가지를 본다. 성격이 달라서 한 검사기에 같이 둔다 — 둘 다 "이 저장소 밖으로 뭔가 나간다"는
같은 사고의 두 방향이기 때문이다.

  exfil   승인 도메인 밖으로 **보내는** 코드. URL 이 문서에 적혀 있는 것만으로는 잡지 않는다 —
          .mcp.json 은 원래 남의 엔드포인트를 적는 파일이고, README 는 링크를 단다. 전송
          동사(post/put/urlopen/fetch/curl -d ...)와 같은 줄에 있을 때만 결함이다.
  secret  하드코딩된 자격증명. 이 저장소는 public 이라 한 번 push 된 비밀은 지워도 GitHub
          이벤트 API·포크·미러에 남는다. "나중에 지우면 된다"가 성립하지 않으므로 예외 한도를
          두지 않는다.

승인 도메인은 action/validators.json 의 approved_domains 하나뿐이다. 여기와 검사기에 각각
적으면 한쪽만 고쳐졌을 때 조용히 갈라진다.

값이 아니라 모양(shape)으로 잡는다. 특정 값을 하드코딩하면 그 값을 바꾼 순간 무력해지고,
하드코딩한 비밀이 이 파일에 남는 자기모순이 된다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scanlib  # noqa: E402

NAME = "leak-scan"
VERSION = "1.0.0"

I = re.IGNORECASE

# -- secret: 자격증명의 모양 -------------------------------------------------
RULES: dict[str, re.Pattern] = {
    "secret/aws-key": re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b"),
    "secret/github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "secret/slack-token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "secret/openai-key": re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
    "secret/google-key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "secret/private-key": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
    "secret/jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\."),
    "secret/bearer-literal": re.compile(
        r"(authorization|bearer)\s*[:=]\s*['\"][A-Za-z0-9._-]{20,}['\"]", I),
    # 변수명이 비밀인데 값이 리터럴인 형태. 환경변수에서 읽는 건 걸리지 않는다.
    "secret/assigned-literal": re.compile(
        r"\b(api_?key|secret|token|passwd|password|passphrase)\s*[:=]\s*"
        r"['\"](?!.*(\$\{|os\.environ|process\.env|<|xxx|your|example|dummy|placeholder))"
        r"[^'\"]{12,}['\"]", I),

    # -- 프로브 마커: 픽스처가 심어둔 표식. 정상 자산에는 있을 이유가 없다.
    "probe/canary": re.compile(r"PROBE-EXFIL-CANARY"),
}

# 전송 동사가 같은 줄에 있어야 exfil 로 본다. 링크·엔드포인트 기재는 결함이 아니다.
SEND = re.compile(
    r"\b(requests\.(post|put|patch|get)|urlopen|urlretrieve|Request\s*\(|http\.client|"
    r"fetch\s*\(|axios\.(post|put|get)|XMLHttpRequest|\.send\s*\(|sendBeacon|"
    r"curl\b[^\n]*\s-(d|F|T|-data)\b|wget\b[^\n]*--post)", I)

URL = re.compile(r"https?://([A-Za-z0-9.\-]+)(?::\d+)?", I)


def _approved(host: str, approved: list[str]) -> bool:
    h = host.lower()
    return any(h == a or h.endswith("." + a) for a in (x.lower() for x in approved))


def exfil(files: list[Path]) -> list[dict]:
    """승인 도메인 밖으로 보내는 줄만. URL 이 있다는 사실만으로는 잡지 않는다."""
    approved = scanlib.approved_domains()
    found = []
    for path in files:
        for n, line in scanlib.lines_of(path):
            if not SEND.search(line):
                continue
            for host in URL.findall(line):
                if _approved(host, approved):
                    continue
                found.append({
                    "file": path.as_posix(),
                    "line": n,
                    "rule": "exfil/unapproved-host",
                    "match": host[:80],
                    "excerpt": line.strip()[:160],
                })
    return found


def main() -> None:
    scanlib.run(NAME, VERSION, RULES, extra=exfil)


if __name__ == "__main__":
    main()