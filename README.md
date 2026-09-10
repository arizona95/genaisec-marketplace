# genaisec-marketplace

스킬·플러그인·MCP 의 **정본**. 여기 있는 것만 배포된다.

```
/plugin marketplace add https://github.com/arizona95/genaisec-marketplace.git
```

> 원래 사내 git(code.sdsdev.co.kr)에 있었다. 사내 관리자 설정이 Actions 를 막아 검사가 못 돌았고,
> 검사가 안 도는 정본은 정본이 아니라서 공개 GitHub 으로 옮겼다. 그래서 이 저장소에는
> **자격증명·사내 주소가 들어오면 안 된다** — leak-scan 이 그걸 지킨다.

## 구조

```
.claude-plugin/marketplace.json   정본 카탈로그
skills/                           스킬 원본
plugins/                          플러그인 원본
mcp/                              MCP 카드 (원격은 소스가 아니라 엔드포인트)
action/validators.json            검증자 등록표 — 검사를 붙일 때 여기만 고친다
action/scripts/                   검증자 · 카탈로그 동기화 · 이력 기록
.github/workflows/ci.yml          기본검증(병합 게이트) + 심화검증(태그)
.github/workflows/history.yml     검사 이력 기록 → history 브랜치 (CI 만 쓴다)
ui/server.py · ui/index.html      대시보드 — origin 을 직접 읽는다 · 업로드 탭
action/scripts/ingest.py          업로드 파일 → 자산 폴더 + 카탈로그 항목 (판별 규칙은 여기 한 곳)
action/scripts/publish_upload.py  업로드 → worktree → 브랜치 → PR
.github/workflows/cleanup-branch.yml  병합된 upload/* 브랜치 삭제
```

## 이력과 대시보드도 손으로 적지 않는다

검사 결과는 **`history` 브랜치**에만 있고 **CI(`history.yml`)만 쓴다** — push(main·dev)·주 1회·수동
실행 때 전 자산을 검증하고 `emit_history` 로 `<브랜치>/latest.json`·`index.json`·`runs/<run_id>.json`
을 누적한다. 레코드마다 커밋 해시가 박혀서, 같은 자산이 여러 커밋에서 차단→통과로 바뀌면 그 시도가
전부 남는다. main 에 이력 파일을 두면 그 순간부터 사본이라 반드시 어긋난다. `run_validators.py --write`
를 손으로 돌려 커밋하지 마라.

대시보드는 정적 파일이 아니라 로컬 서버다. raw 를 읽으면 CDN 캐시를 거치고, 데이터를 내장하면 사본이다.

```bash
python ui/server.py            # http://127.0.0.1:8787 · 15초마다 git fetch · 바뀌면 SSE 로 즉시 갱신
```

서버는 로컬 체크아웃이 아니라 `origin/<브랜치>` 와 `origin/history` 의 git 객체를 직접 읽는다. 어느
클론에서 띄워도 원격 최신을 보여주고, 아무것도 저장하지 않는다. 탭은 둘이다 — **등록 현황**(카탈로그에
등록된 것 + 최신 판정, skill→mcp→plugin 순) / **로그**(실행 목록과 실행별 자산 판정, 커밋 해시 포함).

## 검증

| 등급 | 검사 | 잡는 것 | 실패하면 |
|---|---|---|---|
| 기본 | inst-scan | 악성지시문 — 지시 무효화·비밀 유지 요구·권한 위장·URL 전송 명령 | **병합 차단** |
| 기본 | code-scan | 악성코드 — 동적 실행·자격증명 경로·외부 프로세스 | **병합 차단** |
| 기본 | leak-scan | 유출 — 승인 도메인 밖 전송·하드코딩 자격증명 | **병합 차단** |
| 심화 | black | 코드 포맷 | 태그만 안 붙음 |
| 심화 | skillspector | 위협 패턴 561개 대비 baseline 초과분 | 태그만 안 붙음 |
| 심화 | ~~llm-review~~ | 모델이 자산 전체를 읽고 위 세 가지를 한 번 더 판정 — **임시 비활성**(느려서) | — |

기본 3개는 악성 3종(mal_inst · mal_code · mal_url)과 1:1 이다. 정규식이라 재현되고, 그래서
병합을 막을 수 있다. 심화의 LLM 감시자는 형태를 바꾼 지시문·여러 줄에 걸친 유출처럼 패턴이
놓치는 걸 보되, 모델 판정은 재현이 완전하지 않아 막지 않고 태그로만 드러낸다.

### LLM 감시자의 엔드포인트는 둘이다

```
LLM_PROVIDER=ollama   OLLAMA_API_KEY  OLLAMA_BASE_URL(기본 https://ollama.com)  OLLAMA_MODEL(기본 glm-5.3)
LLM_PROVIDER=fabrix   X_FABRIX_CLIENT  X_OPENAPI_TOKEN  FABRIX_MODEL_ID  FABRIX_USER_EMAIL
```

공개 CI 는 **Ollama Cloud 의 GLM-5.3** 으로 돈다. 키는 저장소 secret `OLLAMA_API_KEY` 하나이고
포크 PR 에는 전달되지 않으므로, 그때는 러너 안에 작은 로컬 모델(`qwen2.5:3b`)을 띄워 대신
돈다 — 태그에 모델명이 박히니 어느 쪽이 판정했는지는 남는다(`llm-review@1.0.0+ollama.glm-5.3`).

사내 FabriX 는 접근 IP 를 /32 로 잠그고 사내망 경로가 있어야 닿는다. GitHub 호스티드 러너는
egress IP 가 매번 바뀌고 사내망 밖이라 못 부른다(`fabrix-probe.yml` 로 확인했다). 사내
self-hosted 러너나 개발자 PC 에서만 `LLM_PROVIDER=fabrix` 다. 감시자(`llm_scan.py`)는 어느
쪽인지 모른다 — `llm/` 패키지의 `from_env()`(`llm/ollama`, `llm/fabrix`) 가 골라 준다.

```bash
python action/scripts/llm_scan.py --ping              # 닿는지
python action/scripts/llm_scan.py skills/<이름>           # 한 자산 검토
python action/scripts/llm_scan.py skills/<이름> --show-prompt
```

## 업로드 — 클론 없이 올리기

대시보드의 **업로드** 탭에 파일을 떨구면 끝이다. 비개발자가 git 을 몰라도 같은 흐름(PR → 기본검증 →
병합)을 탄다. 사람이 하는 일은 파일을 올리는 것뿐이고, 나머지는 서버와 CI 가 한다.

```
파일(.zip / .skill / .mcpb) → 판별(skill·mcp·plugin) → upload/<이름>-<시각> 브랜치 → PR
  → auto-merge 예약 → 기본검증 통과 시 병합 → 브랜치 삭제(cleanup-branch.yml)
```

- 판별 규칙은 `action/scripts/ingest.py` 한 곳에 있다. `.claude-plugin/plugin.json` 이 있으면 구성요소로
  가르고(skills 만 → skill, .mcp.json 만 → mcp, 그 외 → plugin), 없으면 `.mcp.json`/MCPB `manifest.json` → mcp,
  `SKILL.md` → skill. 어느 것도 아니면 **아무것도 하지 않는다**(패스).
- 저장소 규격으로 맞춘다: 루트 SKILL.md 는 `skills/<이름>/skills/<이름>/` 로 감싸고 plugin.json 을 만든다.
  MCPB 는 manifest 에서 `.mcp.json` 을, 서버 소스에서 `tools.json` 스냅샷을 뜬다. 같은 이름은 **교체(업데이트)** 다.
- `publish_upload.py` 는 origin/main 에서 detached worktree 를 만들어 작업한다 — 대시보드가 도는 작업 트리를
  건드리지 않는다. `validate_catalog.py` 가 실패하면 push 하지 않는다.
- 페이지는 게이트웨이 IP whitelist 로 잠근다. 업로드 = 소유자 PR = 자동병합이기 때문이다.

main 은 보호 규칙으로 **기본검증 체크가 필수**다. 이게 없으면 `gh pr merge --auto` 가 검사를 기다리지
않고 즉시 병합한다(2026-09-10 실측 — PR #8·#9 가 CI 시작 5초 만에 병합됐다). 규칙은 저장소 설정이라
코드에 없다: `gh api repos/<owner>/<repo>/branches/main/protection` 으로 `required_status_checks.contexts` 에
`기본검증` 이 있는지 확인한다.

## 병합

```
dev 브랜치 → 수정 → PR(dev→main) → rebase-guard + 기본검증 → 병합
```

`rebase_guard.py` 는 검증자가 아니다. dev 가 main 최신 위에 있는지 본다 — 아니면 초록불이
병합될 코드에 대한 판정이 아니라 낡은 스냅샷에 대한 판정이다.

## 이 저장소에 들어오지 않는 것

워크스페이스에는 형제 폴더가 둘 더 있고, **둘 다 이 저장소가 추적하지 않는다.** 대시보드는 저장소 안 `ui/` 에 있다(`../marketplace-ui/start.cmd` 는 그걸 띄우는 런처).

| 폴더 | 무엇 | 왜 밖에 있나 |
|---|---|---|
| `../3rd/` | 서드파티 저장소 사본 (`dowhub-marketplace` — 이 설계의 원본) | 남의 코드가 정본 카탈로그에 섞이면 무엇이 우리 배포물인지 흐려진다 |
| `../probe-server/` | 프로브 픽스처용 MCP 테스트 서버 | 배포물이 아니라 검사 도구다. CI 가 이걸 훑을 이유가 없다 |

프로브 픽스처(`probe-*`)는 특별 취급하지 않는다 — 일반 자산과 똑같이 `skills/`·`plugins/`·`mcp/`
에 두고 카탈로그에 등록한다. 악성 픽스처는 기본검증에서 의도대로 차단되며, 그게 검사기가 동작한다는
증거다. 위험한 줄은 실행되지 않는 문자열 상수(DETECTION_TARGETS)에만 있다.