#!/usr/bin/env python3
"""악성코드 검사 (필수).

무엇을 보나: 자산이 실제로 실행하는 코드. 스킬의 scripts/, 플러그인의 hooks/, stdio MCP
서버의 소스. 문서에 뭐라고 적혀 있든 실행되는 것은 이쪽이다.

무엇이 걸리나: 네 가지다.
  dynexec   문자열을 코드로 바꿔 실행 — eval/exec/compile/__import__. 검사기가 읽은 것과
            실행되는 것이 달라지는 순간이라, 정적 검사 전체를 무력화하는 자리다.
  credpath  자격증명이 있는 경로를 연다 — ~/.ssh, id_rsa, .aws/credentials, .netrc, .env.
            "읽기만 했다"는 변명이 성립하지 않는다. 읽은 뒤 어디로 갈지는 이 검사가 모른다.
  spawn     설명에 없는 외부 프로세스 — os.system, shell=True, curl|sh.
  obfusc    난독화된 페이로드 — base64/hex 로 감싼 뒤 실행하는 형태.

주의: 정상 자산도 subprocess 를 쓴다(gmail_peek 이 pip 를 부른다). 그래서 subprocess 자체가
아니라 **셸을 경유하는 형태**만 잡는다. 오탐이 나면 개발자가 검사기를 끄고, 그게 제일 나쁜
결과다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scanlib  # noqa: E402

NAME = "code-scan"
VERSION = "1.0.0"

I = re.IGNORECASE

RULES: dict[str, re.Pattern] = {
    # -- dynexec: 문자열 → 코드. 정적 검사를 무력화하는 자리다.
    "dynexec/eval": re.compile(r"(?<![\w.])eval\s*\("),
    "dynexec/exec": re.compile(r"(?<![\w.])exec\s*\("),
    "dynexec/compile": re.compile(r"(?<![\w.])compile\s*\([^)]*['\"]exec['\"]"),
    "dynexec/import": re.compile(r"__import__\s*\(|importlib\.import_module\s*\("),
    "dynexec/js": re.compile(r"\bnew\s+Function\s*\(|\bvm\.runInNewContext\s*\("),

    # -- credpath: 자격증명이 있는 자리를 연다
    "credpath/ssh": re.compile(r"[~/\\.\w]*\.ssh[/\\]|\bid_rsa\b|\bid_ed25519\b"),
    "credpath/cloud": re.compile(r"\.aws[/\\]credentials|\.config[/\\]gcloud|\.azure[/\\]"),
    "credpath/netrc": re.compile(r"\.netrc\b|_netrc\b"),
    "credpath/dotenv": re.compile(r"open\s*\(\s*['\"][^'\"]*\.env['\"]|['\"][^'\"]*/\.env['\"]"),
    "credpath/keystore": re.compile(
        r"(credentials|token|secret|password)s?\.(json|txt|ini|yaml|yml)\b", I),
    "credpath/browser": re.compile(r"Login Data|cookies\.sqlite|key4\.db", I),

    # -- spawn: 셸을 경유하는 외부 실행. subprocess 자체는 잡지 않는다.
    "spawn/os-system": re.compile(r"os\.system\s*\(|os\.popen\s*\("),
    "spawn/shell-true": re.compile(r"shell\s*=\s*True"),
    "spawn/pipe-to-shell": re.compile(r"(curl|wget)\b[^|\n]*\|\s*(ba)?sh\b", I),
    "spawn/js": re.compile(r"child_process|\bexecSync\s*\(|\bspawnSync\s*\("),

    # -- obfusc: 감싼 뒤 실행
    "obfusc/b64-exec": re.compile(
        r"(eval|exec)\s*\([^)]*(b64decode|base64|unhexlify|fromCharCode)", I),
    "obfusc/decode-chain": re.compile(
        r"(b64decode|unhexlify)\s*\([^)]*\)\s*\.\s*decode\s*\([^)]*\)\s*\)?\s*$"),

    # -- 프로브 마커: 픽스처가 심어둔 표식. 정상 자산에는 있을 이유가 없다.
    "probe/eicar": re.compile(r"EICAR-STANDARD-ANTIVIRUS-TEST-FILE"),
    "probe/canary": re.compile(r"PROBE-CODE-CANARY"),
}


def main() -> None:
    scanlib.run(NAME, VERSION, RULES)


if __name__ == "__main__":
    main()