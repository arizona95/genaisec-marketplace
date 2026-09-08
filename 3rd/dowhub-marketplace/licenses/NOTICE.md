# 벤더링한 서드파티 코드

`.github/scripts/` 의 패턴 테이블 두 개는 아래 오픈소스에서 그대로 가져왔다.
각 파일 헤더에도 출처가 적혀 있다.

| 파일 | 출처 | 라이선스 |
|---|---|---|
| `skillspector_patterns.py` | [NVIDIA/SkillSpector](https://github.com/NVIDIA/SkillSpector) | Apache-2.0 |
| `clawvet_patterns.py` | [MohibShaikh/clawvet](https://github.com/MohibShaikh/clawvet) | MIT |

패턴 자체는 원본 그대로다(갱신을 쉽게 하려고). 두 형태를 하나로 맞추는 변환과
심각도 판단은 `sast_scan.py` 안에서만 한다.
