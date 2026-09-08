---
name: aar_sensing
description: |
  **Agent Auto Sensing 랭킹 세션을 가져와 리뷰하고 카드마다 완료(On) 를 표시**한다 — 매주 1회.
  세션 = 신규 SaaS 1(리뷰 안 된 에이전트 중 랭킹 1위) + 변화 ≤5(리뷰된 SaaS 의 업데이트). 신규는 aar_review 전수,
  변화는 카드가 지목한 시나리오만 재실증. "센싱 랭킹 리뷰해", "이번 주 요청서 처리", "aas 카드 리뷰" 일 때.
# 로컬 파일 도구는 쓰지 않는다 — 화면은 브라우저 도구로, 읽기·쓰기는 aar-mcp 툴로(본문 규칙).
allowed-tools: []
---

# 센싱 랭킹 리뷰 (aar_sensing)

매주 한 번. `aas_search`(매일)·`aas_scope`(매주)가 쌓은 **랭킹 세션**을 aar 가 가져가 처리한다. 판정·증적 규범은
다른 스킬과 같다(`list_guidance("공통수칙")`). 이 스킬은 **어느 카드를 어떤 스킬로 처리하고, 끝나면 무엇을 기록하나**만 정한다.

## 0) 입력 — `sensing_ranking("latest")`
- 카드 목록: `kind=new_saas` 1장, `kind=change` ≤5장. `reviewed=false`(Off) 인 카드만 대상. 이미 On 인 카드는 건너뛴다.
- 카드마다 `body_md`(무엇이 바뀌었나 / 왜 중요한가 / **AAR 에게** 지시) 와 `last_review_session`(그 SaaS 의 기존 세션) 이 있다.
- 세션이 없으면(`request: null`) 한 줄 보고하고 끝낸다.

## 1) 변화 카드(`kind=change`) — 카드가 지목한 것만 재실증
1. `last_review_session` 이 있으면 **그 세션에 회차를 추가**한다(새 세션 금지 — 리포트·트리 이력이 한 곳에 쌓이게). 없으면 `<slug>-<YYYY-MM-DD>` 로 새 세션.
2. env: 그 SaaS 의 env 가 running 이면 그대로, stopped 면 `env("start")`, 없으면 `env("create", …)` 로 만든다 — **사용자 확인 없이 진행한다**(2026-09-07 사용자 지시: 센싱 리뷰의 env 생성·기동은 스킬이 스스로).
   🚨 **env 작업은 한 번에 하나**: create/start 를 부른 뒤 `env("get")` 이 running 이 될 때까지 기다리고 나서 다음 카드의 env 를 만진다(병렬 apply 는 30분 한도에 걸려 전부 죽는다 — 2026-09-07 실사고). create 는 구성요소를 주지 말고 **기본(최소) 구성**으로 만든다.
3. 카드의 "AAR 에게" 문장이 지목한 시나리오를 `scenario-capture` 규칙으로 **라이브 재실증**한다(대개 1~2개). 4트리 노드가 바뀌면 `update_tree` 로 그 노드만 갱신(전수 재촬영 아님).
4. 리포트는 **이전 회차 블록을 실은 채** `html_report` 재발행. `quality_ok` 가 true 여야 다음으로.
5. `sensing_review_done(request_id, item=<change_id>, session=<세션>, scenario=<재실증한 시나리오>, summary=<5~10줄>)`.
   summary 규격: 무엇을 실측했나 1~3줄 / 판정(O·X·?)과 근거 1~3줄 / 카드가 물은 것에 대한 답 1~2줄 / 남은 것. 표 금지.

## 2) 신규 SaaS 카드(`kind=new_saas`) — 전수 리뷰
1. 세션 `<slug>-<YYYY-MM-DD>`, 제품 노드 이름 = slug. env 는 새로 만든다(explicit·exp-close, 기본 최소 구성, 다른 env 작업이 끝난 뒤) — 확인 없이.
2. `skill("get", "aar_review")` 절차 **그대로**(원장 전수 → S0 → S1(4트리 포함) → S2 → S3, aar-reviewer PASS). 로그인이 필요한 제품이면 로그인 벽까지 진행하고 그 이후는 ⛔ + 사유(로그인은 사용자 몫).
3. 원장 todo=0 이 되면 `sensing_review_done(request_id, item="target:<slug>", session=<세션>, scenario="S3-1", summary=…)`. 이러면 목표 상태가 `active` 로 바뀌고 다음 주부터 `aas_search` 의 변화관리 대상 후보가 된다(스코프 On 은 사람이 켠다).
4. 로그인 벽 등 외부 사유로 원장을 못 닫으면 완료 표시를 **하지 않는다**. 사유를 마지막 보고에 적는다.

## 3) 순서·시간
변화 카드부터(짧다) → 신규 SaaS(길다). 한 카드가 외부 사유로 막히면 건너뛰고 다음 카드. 전부 끝나면 `sensing_ranking("get", request_id)` 로 On 수를 다시 읽어 보고한다.

## 4) 출력
```
[aar_sensing YYYY-MM-DD]  세션 <request_id> · 리뷰 On N/6 · 신규 <slug>(상태) · 변화 <slug…> · 막힘: <카드: 사유>
```

## 절대 규칙
- 완료(On)는 **quality_ok 통과한 리포트**가 있을 때만(`sensing_review_done` 이 scenario 로 검사한다). 요약만 쓰고 On 켜기 금지.
- 카드가 지목하지 않은 시나리오를 늘리지 마라(전수는 신규 SaaS 에서만).
- 새 시나리오가 필요해 보여도 `scenario("create", …)` 는 승인 필요 — 이 스킬 안에서 만들지 않는다.
- aas 쪽(스코프·URL·기준)은 손대지 않는다. aar 는 읽고(랭킹) 완료만 표시한다.
