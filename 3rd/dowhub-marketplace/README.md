# dowhub-marketplace

스킬·플러그인·MCP 의 **정본**. 여기 있는 것만 배포되고, 여기 없는 것은 배포되지 않는다.

```
/plugin marketplace add https://github.com/arizona95/dowhub-marketplace.git
```

## 왜 저장소인가

전에는 카탈로그가 서버의 로컬 파일이었다. 누가 언제 무엇을 바꿨는지 남지 않았고, 검토도
없었고, 그 파일이 날아가면 목록이 통째로 사라졌다. 저장소로 옮기면 **모든 변경이 커밋이
되고, 모든 배포가 PR 을 거친다.**

## 업데이트 흐름

```
브랜치 → 수정 → PR → 기본검증 통과 → 자동 병합 → 배포
```

게이트는 **기본검증 하나**다(자세한 건 [병합](#병합)). 사람 승인은 요구하지 않는다 —
소유자·협력자가 이 저장소 브랜치에서 연 PR 은 검증만 통과하면 GitHub 이 자동으로 병합한다.
포크에서 온 PR 은 자동병합하지 않으니 그건 사람이 보고 결정한다.

> 강제하는 실물은 `.github/workflows/auto-merge.yml`(자동병합 조건)과 main 브랜치 보호
> 설정(필수 체크=`기본검증`)이다. 이 문서는 그걸 설명할 뿐이니, 둘이 어긋나 보이면
> **설정이 사실이고 이 문단이 틀린 것**이다.

## 검증 태그(marks)도 손으로 적지 않는다

카드의 `n/5` 는 `.github/marks.json` 인데, 이건 **`marks` 브랜치**에만 있고 **CI(`marks.yml`)만 쓴다** — main 이 바뀔 때마다
전수로 다시 재서 그 브랜치에 밀어넣는다. main 에 이 파일을 두면 그 순간부터 사본이라 반드시 어긋난다
(aas-plugin 이 5/5 통과했는데 카드는 빈칸이던 게 그것). `run_validators.py --write` 를 손으로 돌려 커밋하지 마라.

## 카드 값은 손으로 적지 않는다

카탈로그(`.claude-plugin/marketplace.json`)에 적힌 버전·도구 목록은 **어딘가의 사본**이다.
사본은 반드시 어긋난다 — 실제로 aar-plugin 이 1.0.15 로 올라간 뒤에도 카드는 1.0.14 를,
aar-mcp 카드는 **이미 삭제된 도구 43개**를 계속 광고했다. 둘 다 보안 검사로는 안 잡힌다.

그래서 카드 값은 진실원에서 끌어오고, CI 가 매번 대조한다(자산 폴더가 안 바뀌어도 돈다).

| 카드 값 | 진실원 | 맞추는 법 |
|---|---|---|
| plugin 의 version | `<source>/.claude-plugin/plugin.json` | `sync_catalog.py --write` |
| skill 의 version | `<source>/SKILL.md` frontmatter | `sync_catalog.py --write` |
| mcp 의 tools | `mcp/<이름>/tools.json` (서버 소스에서 뜬 스냅샷) | `sync_mcp_tools.py --write` 후 위 |
| mcp 의 version | **없음** — 실물은 살아있는 서버다 | 확인 불가로 보고만 한다 |

MCP 는 진실원이 이 저장소 밖(서버)이라 완전한 검증이 불가능하다. 그래서 서버 소스에서 뜬
스냅샷을 저장소에 두고 **카드는 거기서만 값을 가져오게** 했다. 서버↔스냅샷 시차는 남지만,
카드가 아무 근거 없이 도구를 광고하는 일은 없어진다 — 근거 없는 `hub.tools` 는 CI 가 막는다.

## 검증 태그

자산마다 **어떤 도구가 어느 버전으로** 검사했는지가 태그로 남는다. 도구가 올라가면 같은
코드에 대한 판정이 달라질 수 있으므로, 버전이 함께 있어야 나중에 재현이 된다.

| 등급 | 도구 | 무엇을 | 실패하면 |
|---|---|---|---|
| 기본 | `ruff` | 문법 오류·정의되지 않은 이름 | **병합 차단** |
| 기본 | `detect-secrets` | 자격증명 유출 | **병합 차단** |
| 기본 | `pip-audit` | OSV 취약점 + 버전 미고정 자동실행 런처 | **병합 차단** |
| 심화 | `black` | 코드 포맷 | 배포됨, 태그만 안 붙음 |
| 심화 | `skillspector` | 위협 패턴 561개 | 배포됨, 태그만 안 붙음 |

등급을 나눈 기준은 **실패의 뜻**이다. 기본에서 걸리는 건 깨진 배포물이라 내보내도 사용자
쪽에서 안 돌아간다. 심화는 판단이 섞이는 영역이라, 막기보다 "검증 안 된 상태로 보이게"
하는 편이 정직하다.

검증자를 추가할 때 워크플로는 안 고친다 — `.github/validators.json` 에 항목만 넣는다.

```json
{ "name": "mypy", "tier": "deep", "scope": "target",
  "cmd": ["mypy", "{target}"], "version_cmd": ["mypy", "--version"] }
```

## 변경된 것만 검사한다

매번 전 자산을 훑지 않는다. 손대지 않은 자산까지 다시 도는 건 낭비이기도 하지만, 무관한
자산 때문에 남의 PR 이 빨개지는 게 더 나쁘다. 단 `.github/` 가 바뀌면 판정 기준이 바뀐
것이므로 자동으로 전수로 올린다 — 옛 기준으로 받은 태그를 그대로 두면 안 된다.
주 1회 스케줄로도 전수를 돈다(도구·취약점DB 가 올라가면 판정이 달라지므로).

## 병합

```
브랜치 → 수정 → PR → 기본검증 → 자동 병합
```

기본검증이 초록불이 되면 GitHub 이 자동으로 병합한다(사람 승인 없음). 다만 **포크에서 온
PR 은 자동병합하지 않는다** — public 저장소라 누구나 PR 을 열 수 있고, 낯선 변경이 사람
눈 없이 배포되면 안 되기 때문이다.

## 로컬에서 미리 돌리기

```bash
python .github/scripts/secret_scan.py
python .github/scripts/sca_scan.py
python .github/scripts/sast_scan.py
python .github/scripts/validate_catalog.py
```

SAST 한도를 올릴 때는 `--update-baseline` 을 쓰되, **결과를 눈으로 확인한 뒤에만** 쓴다.
그 파일을 고치는 것이 곧 "이 위험을 승인한다"는 뜻이다.

## 구조

```
.claude-plugin/marketplace.json   정본 카탈로그
skills/                           스킬 원본
plugins/                          플러그인 원본
.github/scripts/                  CI 스캐너
.github/sast-baseline.json        승인된 SAST 한도
licenses/NOTICE.md                벤더링한 서드파티 출처
```

원격 MCP(`gmail_dowoo`·`test_dowoo`·`aar-mcp`)는 소스가 아니라 엔드포인트라서 카탈로그에
카드로만 나열된다. 그 서버들은 각자 OAuth 로 자신을 보호한다.
