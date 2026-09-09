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
action/history/                   검사 이력(marketplace-ui 가 읽는 유일한 입력)
.github/workflows/ci.yml          기본검증(병합 게이트) + 심화검증(태그)
```

## 검증

| 등급 | 검사 | 잡는 것 | 실패하면 |
|---|---|---|---|
| 기본 | inst-scan | 악성지시문 — 지시 무효화·비밀 유지 요구·권한 위장·URL 전송 명령 | **병합 차단** |
| 기본 | code-scan | 악성코드 — 동적 실행·자격증명 경로·외부 프로세스 | **병합 차단** |
| 기본 | leak-scan | 유출 — 승인 도메인 밖 전송·하드코딩 자격증명 | **병합 차단** |
| 심화 | black | 코드 포맷 | 태그만 안 붙음 |
| 심화 | skillspector | 위협 패턴 561개 대비 baseline 초과분 | 태그만 안 붙음 |
| 심화 | **llm-review** | 모델이 자산 전체를 읽고 위 세 가지를 한 번 더 판정 | 태그만 안 붙음 |

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

## 병합

```
dev 브랜치 → 수정 → PR(dev→main) → rebase-guard + 기본검증 → 병합
```

`rebase_guard.py` 는 검증자가 아니다. dev 가 main 최신 위에 있는지 본다 — 아니면 초록불이
병합될 코드에 대한 판정이 아니라 낡은 스냅샷에 대한 판정이다.

## 이 저장소에 들어오지 않는 것

워크스페이스에는 형제 폴더가 있고, **이 저장소는 추적하지 않는다.**

| 폴더 | 무엇 | 왜 밖에 있나 |
|---|---|---|
| `../3rd/` | 서드파티 저장소 사본 (`dowhub-marketplace` — 이 설계의 원본) | 남의 코드가 정본 카탈로그에 섞이면 무엇이 우리 배포물인지 흐려진다 |
| `../probe-server/` | 프로브 픽스처용 MCP 테스트 서버 | 배포물이 아니라 검사 도구다. CI 가 이걸 훑을 이유가 없다 |
| `../marketplace-ui/` | `action/history/` 를 읽는 UI | 배포물이 아니다 |

프로브 픽스처(`probe_*`)도 카탈로그에 등록하지 않는다 — 등록하면 `/plugin marketplace add`
로 누구나 설치할 수 있게 되고, 악성 픽스처가 그 경로로 나가면 그것 자체가 사고다.