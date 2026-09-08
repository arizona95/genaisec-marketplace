#!/usr/bin/env python3
"""detect-secrets 래퍼 — 결과가 하나라도 있으면 실패로 바꾼다.

detect-secrets scan 은 찾은 것을 baseline JSON 으로 출력하고 종료코드는 0 이다(원래
baseline 을 만드는 용도라서). CI 에서는 '찾았으면 실패'여야 하므로 여기서 뒤집는다.
"""
import json
import subprocess
import sys
from pathlib import Path

target = sys.argv[1] if len(sys.argv) > 1 else "."
r = subprocess.run(["detect-secrets", "scan", target], capture_output=True, text=True, timeout=600)
try:
    results = json.loads(r.stdout or "{}").get("results", {})
except json.JSONDecodeError:
    print(f"detect-secrets 출력을 읽지 못했습니다: {r.stderr.strip()[:200]}")
    sys.exit(2)

if results:
    n = sum(len(v) for v in results.values())
    print(f"자격증명 후보 {n}건 — {target}")
    for f, hits in results.items():
        for h in hits:
            print(f"  {f}:{h.get('line_number')}  {h.get('type')}")
    sys.exit(1)
print(f"통과 — {target}: 자격증명 후보 없음")
