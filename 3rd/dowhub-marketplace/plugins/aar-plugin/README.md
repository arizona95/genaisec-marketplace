# aar-plugin — AgentAutoReview

AI 앱 **보안 리뷰 워크플로**를 Claude Code 플러그인 하나로. Atlassian 모델(`plugin.json` +
`.mcp.json` 리모트 MCP + `skills/`).

## 스킬 6종
- **`/aar_review`** — env 적용 시나리오 **전수** 라이브 실증. 커버리지 원장으로 스코프를 강제해,
  전부 ✅/⛔ 되기 전엔 "완료" 불가(20%-완료-선언 재발 차단). 새 SaaS·대규모 업데이트 시.
- **`/aar_update`** — 이 SaaS 를 **주기적(주 1회) 추적**. 지난번 대비 델타만 — 메뉴·세션·세팅·보존
  4트리와 영향 보고서를 갱신.
- **`/aar_fix`** — 이 대화에서 지적받은 것을 근거로 리뷰 규범을 고친다. 마무리로 `aar-compounder`
  서브에이전트가 가이드 전체의 대전제를 감사한다.
- **`/aar_explain`** — 리뷰 결과를 아무것도 모르는 사람에게 **HTML 아티팩트**로 설명(큰 그림, 적은 글씨).
- **`/aar_menu`** — 원천 트리(menu/session/settings/retention)의 **항목 하나**만 조사해 보고서를 쓰고
  그 노드에 태그로 붙인다. 뷰어에서 빈 항목의 `📋 복사` 가 `/aar_menu <트리> <경로>` 한 줄을 준다.
- **`scenario-capture`** — S1 한 건을 라이브로 수행·캡처해 리포트까지. (전수는 `/aar_review`)

> 스킬 목록을 여기 손으로 적는다 — `skills/` 폴더와 어긋나면 그건 문서가 틀린 것이다.
> 실제 개수는 `skill("list")`(MCP) 로 확인한다.

## 서브에이전트 2종
- **`aar-reviewer`** — 발행 직전 읽기전용 게이트(대상 드리프트·tier 귀속 정직성·커버리지·증거 3종).
- **`aar-compounder`** — 가이드 코퍼스 전체의 대전제 감사(`/aar_fix` 마무리).

## 리모트 MCP
- **.mcp.json** → **aar-mcp**(`https://dowhub.org/aar-mcp/`, OAuth). 설치 시 도구가 함께 붙고,
  **도구·로직은 서버측 자동 업데이트**.

## 설치
개별 저장소는 폐지됐다(2026-08-27). 스킬·플러그인·MCP 는 **마켓플레이스 하나**에서 나간다.
```
/plugin marketplace add https://github.com/arizona95/dowhub-marketplace.git
/plugin install aar-plugin
```
> 예전 `arizona95/aar-plugin.git` 으로 등록해 뒀다면 그 마켓플레이스는 더 이상 없다 —
> `/plugin marketplace remove aar-marketplace` 후 위 URL 로 다시 추가한다.

## 업데이트
- **aar-mcp 도구/로직** → dowhub.org 서버만 갱신 = 전 사용자 자동 반영.
- **스킬 내용** → 마켓플레이스에 **브랜치로 올려 PR** → CI(기본검증 통과) + 소유자 승인 → main 병합.
  버전을 안 올리면 클라이언트가 "최신"으로 보고 안 당겨온다 — `plugin.json` 과 카탈로그의
  `version` 을 **같이** 올린다.
