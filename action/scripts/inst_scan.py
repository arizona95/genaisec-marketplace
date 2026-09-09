#!/usr/bin/env python3
"""악성지시문 검사 (필수).

무엇을 보나: 자산이 모델에게 건네는 텍스트 전부. SKILL.md 본문, 커맨드/에이전트 정의,
그리고 MCP 도구 설명(tools.json). 도구 설명은 사용자 눈에 거의 안 보이는데 모델은
반드시 읽으므로, 주입하기에 가장 좋은 자리다.

무엇이 걸리나: 세 가지 구조다.
  override  이전 지시를 무효화하려는 문장
  secrecy   사용자에게 알리지 말라는 요구
  spoof     시스템/개발자 권한을 흉내내는 표식
  exfil     특정 URL 로 보내라는 지시

주의: 단어 하나로는 안 잡는다. "ignore" 나 "system" 은 정상 문서에도 흔하다.
잡는 것은 '무효화 대상 + 무효화 동사'가 같이 있는 형태다. 그래야 norm 픽스처가
안 걸린다 — 오탐이 나면 개발자가 검사자를 끄게 되고, 그게 제일 나쁜 결과다.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scanlib  # noqa: E402

NAME = "inst-scan"
VERSION = "1.0.0"

I = re.IGNORECASE

RULES: dict[str, re.Pattern] = {
    # -- override: 앞선 지시를 무효화하려는 시도
    "override/system": re.compile(r"system\s*[-_ ]?override|override\s*:\s*system", I),
    "override/ignore-prev": re.compile(
        r"(ignore|disregard|forget|discard)\b[^.\n]{0,30}"
        r"(previous|prior|above|earlier|preceding|all)\b[^.\n]{0,20}"
        r"(instruction|prompt|rule|guideline|direction)", I),
    "override/ko-ignore-prev": re.compile(
        r"(이전|위|앞|기존|상위)[^.\n]{0,12}"
        r"(지시|지침|규칙|명령|프롬프트)[^.\n]{0,12}"
        r"(무효|무시|폐기|잊)"),
    "override/new-rule": re.compile(
        r"(from\s+now\s+on|starting\s+now)\b[^.\n]{0,30}(must|always|never)\b", I),
    "override/ko-new-rule": re.compile(r"(이제부터|지금부터)[^.\n]{0,20}반드시"),

    # -- secrecy: 사용자에게 감추라는 요구
    "secrecy/dont-tell": re.compile(
        r"(do\s*not|don'?t|never|without)\s+"
        r"(tell|telling|inform|informing|notify|notifying|reveal|revealing|"
        r"mention|mentioning|disclose|disclosing|show|showing)\b[^.\n]{0,40}"
        r"(user|human|operator|사용자)", I),
    "secrecy/ko-dont-tell": re.compile(
        r"사용자에게[^.\n]{0,20}(알리지|말하지|밝히지|보여주지|노출하지)[^.\n]{0,8}(말|않|마)"),
    "secrecy/silent": re.compile(
        r"(silently|covertly|secretly)\b[^.\n]{0,30}"
        r"(send|post|upload|read|collect|execute|run)", I),
    "secrecy/pretend": re.compile(
        r"(pretend|claim|say)\b[^.\n]{0,30}(that\s+)?(it\s+is|you\s+are|this\s+is)\b"
        r"[^.\n]{0,30}(normal|ordinary|plain|harmless|simple)", I),
    "secrecy/ko-pretend": re.compile(r"(평범한|일반적인|무해한)[^.\n]{0,20}(라고만|이라고만)\s*(답|말)"),

    # -- spoof: 권한 표식 위장
    "spoof/tag": re.compile(r"<\s*/?\s*(system|assistant|developer)\s*>", I),
    "spoof/header": re.compile(
        r"^\s*[\[\(#*\-]*\s*(system|developer|admin|root)\s*"
        r"(prompt|message|instruction|override|mode)\b", I),
    "spoof/you-are-now": re.compile(
        r"you\s+are\s+now\b[^.\n]{0,30}(developer|admin|root|unrestricted|dan)\b", I),

    # -- exfil 지시: 어디로 보내라는 명령형
    "exfil/send-to-url": re.compile(
        r"(send|post|upload|forward|transmit|exfiltrate)\b[^.\n]{0,40}"
        r"(to|→|->)\s*[\"'`]?https?://", I),
    "exfil/ko-send-to-url": re.compile(r"https?://[^\s\"'`]+[^.\n]{0,20}(으로|로)\s*(전송|전달|업로드|보내)"),

    # -- 프로브 카나리: 픽스처가 심어둔 표식. 정상 자산에는 있을 이유가 없다.
    "probe/canary": re.compile(r"PROBE-INJ-CANARY"),
}


def main() -> None:
    scanlib.run(NAME, VERSION, RULES)


if __name__ == "__main__":
    main()
