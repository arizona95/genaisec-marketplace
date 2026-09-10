#!/usr/bin/env python3
"""승인 도메인으로만 나가는 무해한 조회. 상태코드만 읽는다."""
import urllib.request

URL = 'https://github.com/arizona95/genaisec-marketplace'
def head():
    with urllib.request.urlopen(URL, timeout=10) as r:
        return r.status

if __name__ == '__main__':
    print('probe_skill_norm_3-OK', head())
