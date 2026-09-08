---
name: scenario-capture
description: |
  Run an AgentReview S1 scenario LIVE and produce its report. Drive the user PC VM —
  user-window-pc (Windows) or user-linux-pc (Linux), whichever OS the target SaaS supports —
  and the AgentReview console THROUGH THE CONSOLE IN YOUR OWN BROWSER, capturing each screen
  yourself and POSTing it to /api/v1/evidence — never an off-screen browser. Prove a
  security control (proxy traversal, egress, tenant-restriction header→403, DLP→451, OTel,
  tool audit) by capturing before/after/proxy frames live, then build the report into the
  CURRENT SESSION folder. Use when asked to "run / record / capture an S1 scenario", "시나리오 찍어".
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
---

# AgentReview S1 시나리오 — 라이브 실증 & 보고서 스킬

S1(환경 실증) 시나리오를 **콘솔을 연 내 브라우저에서 직접** 수행·캡처하고,
그 캡처로 보고서를 **현재 세션 폴더**에 만든다.

## 🚨 절대 규칙 (어기면 그동안의 사고 재발)
- **off-screen 금지.** Xvfb·ffmpeg·x11grab·playwright·자체 브라우저(`launch_*`)·Bash로 화면 띄우기 전부 금지.
  모든 행위는 **내 브라우저로 콘솔을 열어** 하고, 캡처는 내가 떠서 `/api/v1/evidence` 로 POST 한다(절차는 `aar_review/refs/capture-and-workflow.md`).
- **출력 = 현재 세션 폴더** `Auto_Report/sessions/<env>-<env생성일>/<시나리오>/`. (`html_report` 가 거기로 만든다.)
- **`backup/videos/` 는 read·write 둘 다 금지** — 거긴 옛 마스터 **honeypot**(베끼나 안 베끼나 검증용). 거기서 cp·복사·발행하면 즉시 실패.
- **과거 보고서 베끼기 금지.** 산출물은 *이번 리뷰에서 직접 한 라이브 캡처*만. 같은 세션 보고서만 참조 가능. (공통수칙 §3-1)
- 안 찍었으면 솔직히 "이번 리뷰 미실증". **없는 게 베끼는 것보다 낫다.**
- 🚨 **신선도 판정은 내용(md5) 기반 — mtime≠신선도.** 외부 프로세스가 현재 세션 폴더에 타세션 캡처를 byte-identical 로 주입하는 오염이 실재한다(2026-06-11) — 라벨/mtime/경로로는 못 잡는다. 발행 전 타세션 md5 인덱스와 전수 대조해 byte-identical 은 격리·재캡처.
- 🚨 **흑색/공백 프레임은 증거가 아니다.** 장시간 세션 후 RDP iframe 이 순흑으로만 렌더되는 도구결함 존재 — 캡처 직전 화면을 눈으로 확인, 검정이면 저장 금지(1회 재시도 → 안 되면 도구결함으로 보고·한계 고지, 대상 SaaS 결함으로 오기재 금지).

---

## 0-A. 매크로 도구 — 좌표는 "진짜 앱 UI 관측"에만, 준비·콘솔은 도구로
좌표 클릭·타이핑은 **대상 앱 UI 를 실제로 관측**할 때만 쓴다(ChatGPT 앱에 질의 입력, Store 클릭 등 RDP 캔버스 조작). **준비·콘솔조작에 좌표를 쓰지 마라** — 실측상 도구호출의 71%가 픽셀조작이었고, 근본원인이 (a) 준비(PowerShell·파일생성·환경체크·MCP설치)를 RDP 터미널에 좌표로 타이핑("PS 를 GPT 창에 치는" 사고), (b) 콘솔조작(정책·flow검색·clear)을 좌표클릭, (c) ToolSearch 파편, (d) 헛촬영(registry ID 드리프트·clear 산발)이었다. 아래로 갈음:

- 🚨 **명령은 RDP 화면 안 PowerShell 에서 직접 친다.** 헤드리스 실행 경로는 **없앴다** — az run-command 는 항상 SYSTEM 이라 유저 세션·per-user 앱·HKCU 를 못 봐 헛돌았고, 그걸 대체하려던 유저 컨텍스트 exec 채널도 **에이전트 스케줄태스크 등록이 자주 깨져**(SYSTEM→유저 넘기는 이음매) 못 쓴다. 어차피 사람이 봐야 하는 화면이니 거기서 친다. 절차는 §1 터미널 규칙(포커스→타이핑→Enter 확인).
- 🚨🚨 **증적 = 관측주체의 실제 화면을 내가 캡처해 올린 것만 인정.** 텍스트를 터미널 이미지로 그려내던 `shell_evidence` 는 **날조 위험으로 삭제됨**(모델이 output 을 손으로 써서 "쉘에서 친 것처럼" 가짜 증적을 만들 수 있었다 — 2026-08-12 S1-ALL-07-mon-proxy 보고서가 6개 증적 전부 이 방식의 날조였음). 터미널에서 명령을 친 것은 **실행**이지, 그 출력 텍스트가 증적이 되는 게 아니다(화면 캡처가 증적이다).
  - 🚨🚨 **별도 관측주체(사내 프록시·OTel/Loki·Compliance)가 "봤다/기록했다"는 증적을 스크립트로 조회해 print 한 화면은 절대 금지.** (2026-07 moncanary.py 사고: `sudo python3 /tmp/moncanary.py` 가 프록시 flow 를 조회해 `FLOWS=3` + `판정:[O]질의 [O]응답` 까지 **스스로 찍어낸** 걸 "경계 프록시 평문 관측" 증적으로 붙임 → 자기증언·재현불가·조작가능 = 제3자 감사 채택 불가.) **프록시 관측 = 콘솔 L7-proxy 뷰어에 마커 필터→flow 클릭→요청/응답 detail 이 뜬 그 화면(캡처해 업로드). OTel = log-server(Grafana/Loki Explore)에 쿼리→이벤트가 뜬 그 화면. Compliance = 공식문서 스키마 페이지.** 판정은 그 관측주체 화면에서 사람이 읽는 것이지, 스크립트가 print 하는 게 아니다.
- 🚨 **콘솔 조작 = MCP 도구** — L7 정책 등록/삭제·flow 검색·clear/archive 는 `policy("create"|"list"|"delete", env, …)` · `clear_capture` · `archive_capture`. **콘솔 웹UI 좌표클릭·Bash sed 로 dlp 파일 직접편집 금지.**
- 🚨 **촬영 시작 = `scenario_start(env, scenario_id)` 1콜** — registry.json 으로 ID 존재검증(구버전 ID 헛촬영 방지) + clear_capture(flow 버퍼 비움) + recommended_tools(이 시나리오 필요 도구) 반환. 구 ID 로 찍기 전 반드시 이걸로 최신 registry 확인.
- 🚨 **ToolSearch 파편 금지** — 필요한 도구는 scenario_start 의 recommended_tools 로 시작에 한 번에 파악(MCP 서버는 모든 도구를 항상 노출, 번들 재로드 불필요). 시나리오마다 재검색 X.
- 🚨 **html_report 는 self_check 신뢰** — Bash 로 세션폴더 ls/find/cat json/md5 뒤지지 마라. html_report 응답의 self_check 가 evidence·stale·이미지·archive 검증을 돌려준다(missing_captures·stale_rejected 만 확인).
- 🚨🚨 **CLI형 SaaS(Claude CLI·Codex CLI·gemini-cli 등)를 평가할 땐 예외** — 이때는 **터미널(PowerShell) 자체가 피평가 앱**이다. **피평가 CLI 구동(로그인·프롬프트 입력·응답 확인)도 가시 RDP 터미널에서** 한다(§1 터미널 절차) — GUI SaaS 에서 앱 입력창에 질의를 치는 것과 동일한 "앱 UI 관측"이다. 🚨 **피평가 CLI 를 헤드리스(az run-command 등)로 실행하지 마라**: (a) 사람이 못 봄(화면 관측 대전제 위반), (b) 대화형 세션이 아니라 CLI 의 실제 동작/트래픽이 다를 수 있다, (c) 🩸 **az run-command 는 `nt authority\system`(또는 다른 프로필)로 도는 별개 세션이라, 사용자가 로그인해 화면에 띄워둔 그 CLI 의 인증이 없다** → "GEMINI_API_KEY 없음/로그인 안 됨" 같은 **거짓 실패**가 뜬다(2026-07-23 실사고: gemini 는 agentreview 세션에 로그인돼 정상 작동 중이었는데, SYSTEM shell 로 `gemini -p` 돌려 "로그인 안 됨" 오판, 화면은 건드리지도 않음). 즉 **설치·config·키파일 배치도, CLI 실행·로그인·프롬프트 주고받기도 전부 가시 RDP 터미널**에서 한다(keys API/좌표).
  🚨🚨 **shell/az 로 CLI 를 돌린 출력(또는 그 출력을 print 하는 자작 스크립트 화면)은 증적으로 절대 인정 못 받는다** — (1) 사용자가 로그인한 실제 세션이 아닌 헤드리스 별세션이라 "그 화면의 그 CLI" 를 증명하지 못하고, (2) 터미널 print 는 조작자가 무엇이든 찍을 수 있어(자기증언·재현불가) 제3자 감사에서 채택 불가([[feedback_verify_action_before_concluding]] 의 moncanary.py 사고와 같은 클래스). **증적은 반드시 사람이 보는 가시 RDP 터미널에 프롬프트 넣고 응답이 뜬 그 화면 + 프록시 뷰어 flow detail** 이어야 한다. 프록시 egress flow 는 어느 쪽이든 잡히지만, CLI 동작 증적 화면은 **가시 터미널**이어야 한다.
- 🚨 **조작 후 반드시 실측 확인하고 넘어가라** — keys/type/click 후 **스크린샷으로 화면에 실제 반영됐는지**(엔터 눌려 제출됐는지·앱이 응답을 띄웠는지) 확인한다. keys API 는 pub/sub(`delivered_when:ui-tab-open`)라 지연·미반영이 잦고 특히 **엔터가 씹힌다** → 프롬프트 후 빈 텍스트+`press_enter` 한번 더, 그리고 스샷으로 제출 확인. "보냈으니 됐겠지"로 넘어가면 다음 캡쳐가 헛것이 된다. **부정 판정("안 잡힘/안 됨/로그인 안 됨")은 선행조작(clear→트리거 반영확인→충분대기→재조회)을 다 하고서만** — stale 화면줄(옛 에러)을 현재상태로 오독 금지. 상세 [[feedback_verify_action_before_concluding]].

**표준 흐름(네트워크 증적 시나리오)**: `scenario_start → (준비=RDP PowerShell) → 관측 action(RDP 화면에서) → search marker(프록시 flow) → 화면 캡처 후 /api/v1/evidence 로 POST → archive_capture → html_report`. **모든 시나리오 끝에 archive_capture + cleanup(등록한 정책룰 policy("delete", env, rule_id=…))을 try/finally 로 강제** — 다음 before 오염·사용자 세션 훼손 방지.

**부정(negative) 결론 전 체크리스트**: "안 보임 → 안 됨"으로 단정 금지. ① clear_capture 했나 ② 올바른 host/표면·flow 필터인가 ③ 충분히 기다렸나(설치·전파 지연) ④ 다른 채널(WS/SSE·다른 도메인·L4)로 나간 건 아닌가 — 넷 다 짚은 뒤에만 "미관측" 판정.

---

## 0. 환경 좌표 (매번 확인)
- 콘솔 URL = 로컬이면 `http://localhost:5174/`, 원격이면 `https://dowmain.org/agentreview`. API = `http://localhost:8080/api/v1`.
- 실행 중 env / 세션명: env=`<환경명>` → 세션=사용자가 만든 이름(리포트 생성 시 그대로 전달).
- log-server(OTel): env outputs 의 `otel_grafana_url` / `otel_loki_push_url`.

## 1. user PC 구동 (Windows/Linux · 내 브라우저로, read→판단→행동→확인)
user PC 는 Guacamole RDP **이미지 스트림**(DOM 없음). 콘솔을 거쳐 연다:
1. 콘솔을 열고 → env 행 클릭 → **user PC 컴포넌트** 클릭(콘솔 클릭으로 연다, raw guacamole URL 금지).
2. 화면을 캡처해 확인 → 대상(앱의 입력창/버튼) 좌표를 눈으로 찾음.
3. 클릭(먼저 RDP 영역을 hover→click 해 포커스) → 타이핑은 keys API 가 안정적:
   `POST /envs/{env}/{vm}/keys {"text":"...","press_enter":true}`.
4. 다시 캡처해 결과 확인. **추측 금지 — 눌렀으면 반드시 다시 찍어 확인.** 틀리면 2로.
- 좌표는 매번 다를 수 있으니 캐싱 말고 그때그때 스크린샷에서 찾는다. 15s 대기 후 앱 foreground(로그인/빈바탕 아님) 확인하고 진행.

> 🖥️ **어느 PC 에서 할지 (Windows/Linux 라우팅 — 대상 SaaS 마다 다름).** user PC 는 두 OS 변형이다: **user-window-pc**(Windows) / **user-linux-pc**(Linux), 관리자 행위는 **admin-window-pc**(Windows). `{vm}` = 이 셋 중 하나. 어떤 SaaS·기능은 Windows 에만, 어떤 건 Linux 에만, 어떤 건 양쪽에 배포된다 — **대상(과 그 표면)이 실제로 도는 OS 를 S0 리서치로 확인해 맞는 PC 에서 실행**하라.
> - 대상이 한쪽 OS 에만 있으면 **반드시 그 PC**. 미지원 OS 에 억지로 = 설치 실패·빈 화면 → 그건 대상 결함이 아니라 **PC 선택 오류**(빈/가짜 결과로 발행 금지). 양쪽 지원이면 아무 쪽이나(쓴 쪽을 캡션/보고에 기록).
> - 조작 방식(RDP 픽셀·콘솔클릭·keys API)은 두 변형 **동일**. OS 차이만: 터미널 = Windows PowerShell/cmd ↔ Linux shell(bash); 프록시 = Windows 는 런타임 재확인 필요할 수 있고 Linux 는 provisioning 시 이미 적용됨.

> 🚨 **콘솔 UI 가 한 지점에서 막혀도 env-tree 는 단일관문이 아니다** — 그 단계만 API 로 우회하고 계속 진행하라(2026-06 라이브 완주로 검증): RDP = `GET /api/v1/envs/{env}/{vm}/rdp-url` 가 발급한 **토큰 URL** 을 열고(금지는 raw/추측 guacamole URL 뿐), flow = `/envs/{env}/network-proxy/api/flows`, 룰 = `/envs/{env}/dlp/rules`. 좌표만 바꿔가며 같은 클릭을 반복하지 마라 — 막힌 건 좌표가 아니다.

> 🚨 **명령은 전부 이 경로다** — 준비(설치·파일생성·환경체크)든 관측이든 RDP 터미널에서 친다. 헤드리스 우회로는 없앴다.
> 🚨 **다만 창을 반드시 확인하고 쳐라** — 좌표로 포커스를 잘못 잡아 **명령이 대상 앱 입력창에 새어 들어간 사고**가 있었다(GPT 창에 PowerShell 을 친 것). 터미널을 한 번 클릭해 포커스를 확실히 잡고, 친 뒤 화면으로 확인한다.
>
> 🚨 **터미널(PowerShell/cmd/bash) 명령 실행 — RDP 라 Enter 가 잘 안 먹는다(검증된 절차):**
> ① 명령을 입력한 뒤, **터미널 화면 영역을 한 번 클릭해 포커스**를 확실히 잡는다(SendKeysBar 입력창이 아니라 **터미널 그 자체**를 클릭).
> ② **Enter 를 2~3번** 친다 — RDP/Guacamole 는 키 전달이 불안정해 첫 Enter 가 씹히는 경우가 많다(브라우저 키 입력을 반복하거나, keys API `press_enter:true`).
> ③ **스크린샷으로 프롬프트가 다음 줄로 넘어갔는지(=실행됨)** 확인. 안 넘어갔으면 **다시 클릭+Enter**. (명령만 보내고 무한 대기 금지 — 워치독이 잡지만 너 스스로 확인해라.)
> ④ 설치/다운로드처럼 오래 걸리면 주기적으로 스크린샷으로 진행을 보고, **완료 전 다음 명령 금지**.

## 2. 콘솔 탭 — 무엇을 / 어떻게 (콘솔 클릭 또는 API)
| UI 탭 | 하는 일 | 라우트 |
|---|---|---|
| user-window-pc / user-linux-pc / admin-window-pc | Guacamole RDP(픽셀) — OS 는 대상 지원에 맞춰(§1) | `/{vm}/rdp-url`,`/{vm}/keys` |
| L7-proxy | 복호화 트래픽 라이브 뷰 | `/network-proxy/*` (iframe: Live/Saved/Archives·Export) |
| L7-policy | DLP block/allow/redact + **헤더 인젝션** | `/dlp/rules` (action) |
| L4-proxy/policy | 복호화 전 SNI/IP/포트 뷰·차단 | `/network-proxy/events`,`/dlp/rules`(l4block) |
| log-server | Grafana+Loki | `/grafana/*`, Loki `:3100` |

L7-policy 룰(콘솔 클릭 권장; 빠르게는 API):
```bash
# 테넌트 헤더 인젝션: action=inject  (헤더명/값/도메인은 S0-05 가 찾은 그 SaaS 실제값 사용)
POST /envs/$ENV/dlp/rules {"name":"tenant","action":"inject","direction":"request","inject_mode":"set",
  "header":"<S0가 찾은 헤더>","value":"<비허용 org>","pattern":"<대상 도메인>","location":"host","enabled":true}
# DLP 차단: action=block / L4 차단: action=l4block
```
새 애드온(inject/l4block) 실동작은 **그 env 를 새로 만들거나 reset 한 경우에만**(옛 VM 은 룰 무시).
OTel: Loki `query_range` 로 `{service_name="<대상 서비스명>"}` + `<대상 텔레메트리 네임스페이스>.*` 조회(Grafana iframe 보다 확실). 서비스명·네임스페이스는 그 SaaS 마다 다르니 **S0 리서치가 찾아둔 실측값**을 쓴다(하드코딩 금지).

## 3. 캡처 = 내가 떠서 올린다 (off-screen mp4 아님)
라이브 화면을 그 순간 떠서 `/api/v1/evidence` 로 POST 한다(절차는 `aar_review/refs/capture-and-workflow.md`) → `runs/operator-evidence/` 에 쌓임.
S1 은 최소 **before(룰 전 정상) / after(룰 후 차단) / proxy(L7-proxy 복호화 차단 flow) / 차단본문** 을 각각 캡처.
(**절대 backup/videos 에서 옛 mp4 를 끌어오지 않는다.**)

## 4. 시나리오별 머니샷 (캐노니컬 S1-exp-open-NN)
| 시나리오 | 라이브로 보여줄 변화(before→after) + money shot |
|---|---|
| 01-proxy | user PC(§1 OS) 질의 → L7-proxy 에 그 호스트 flow 복호화 |
| 02-egress | 질의 1사이클 → L7-proxy 호스트 목록/L4 SNI. **🚨 보고서에 `table` 블록으로 목적지 전수 표**(`archive.py hosts_tsv`): 대상이 동작할 때 어디로 통신하는지 리스트로 쫙. 사진/영상/설명만 넣지 마라 |
| 03-tenant | L7-policy inject(전 200) → 재전송 → **서버측 차단** flow(주입헤더+차단응답). 값은 S0-05 인용 |
| 04-dlp | L7-policy block(전 200) → 재전송 → 451 + `{blocked,rule_name,matched}` |
| 05-otel | log-server Loki 에서 대상 텔레메트리 이벤트(네임스페이스는 S0 실측값; 주입 데모면 캡션 명시) |
| 06-tool | user PC(§1 OS) 툴 실행 → L7-proxy completion flow req/resp 본문(SSE) |
| 07-orgsetup | 조직 설정 항목 순회 스크린샷(소유자) |

## 5. 4단계 규율 (순서 고정 · 거짓보고 방지)
1. **실험** — 녹화 전 메커니즘이 **진짜 되는지** 하드증거(flows API 복호화 본문·status·Loki·차단응답)로 확인. **행동 전/후 *변화*를 둘 다 관측**(룰 전 200 → 룰 후 403). 안 되면 멈추고 원인부터 고친다. 검증 안 된 걸 캡처하지 않는다.
2. **정리** — 1에서 *실제로 본* before/after/그 차이를 적는다. 여기 없는 건 보고서에도 못 쓴다.
3. **라이브 캡처** — 내 브라우저로 before 화면 → 행동 → after 화면 → proxy/본문을 각각 캡처해 올린다. 직전 정리: 앱 상태 리셋(배너/모달 잔상 제거·New chat), `clear_capture(env)`(옛 트래픽/히스토리 숨김), RDP 앱 foreground 확인. DLP 룰은 **try/finally 로 항상 삭제**(다음 before 오염·사용자 세션 복구).
   🚨 **녹화 자막 = 관측된 사실만.** 결과 단계 자막(차단/허용/상태코드)은 그 프레임에 실제로 보이는 status 를 확인한 *뒤* 그것과 일치하게 깐다 — 계획서의 기대값("③ 403 차단")을 미리 깔지 마라. 기대와 다른 관측(주입에도 통과 등)은 실패가 아니라 **발견**이다: 자막을 관측대로 고쳐 깔고, 틀린 자막이 이미 박힌 구간은 재녹화(안 그러면 verifier FAIL 로 그 발견의 증거 자체가 죽는다).
4. **보고서** — `html_report`(또는 `report.py`)로 **세션 폴더**에 만든다. before/after/timeline `file` 은 방금 찍은 캡처 라벨. **캡처에 없는 장면은 절대 쓰지 않는다.** 머니샷이 캡처에 안 보이면 3 실패 → 1로 돌아간다. **🚨 프레임 없으면 주장 없음.**

## 6. 보고서 산출 (세션 폴더 · html_report)
- 출력 = `Auto_Report/sessions/<env>-<생성일>/<시나리오>/{report.html, report.json, img/}`.
- `report.json`: `before_after`/`timeline` 프레임(방금 캡처) + `analysis`(빌드 시 이 env 아카이브에 archive.py 실행돼 박힘, 날조 불가) + `why`/`failure_angle`.
- `report.py build <세션폴더>` 가 html 생성. analysis cmd 는 `runs/envs/<env>/captures/archives/...` 의 **이번 env 실데이터**를 집계.
- **금지 재확인**: `backup/videos` 에서 report/mp4/img 를 cp 하지 마라(honeypot). 다른 세션 폴더도 참조 금지. 같은 세션만.

## 7. 시나리오별 실패 모드 (실제 겪음 — 재발 방지)
**공통**: 브라우저 chrome 노이즈가 캡처에 섞이지 않게 콘솔은 전체화면(focus)으로 본다. user PC RDP 가 로그인/빈바탕으로 뜨면 15s 대기+캔버스 클릭 포커스+스크린샷 확인.
- **03-tenant(최다실패)**: before 에 이전 차단 배너 잔상 → 녹화 직전 앱 reload 로 제거·깨끗 로드 확인. L7-policy 의 `sync_error`(SSH exit255)는 SSH 동기화 경로 실패일 뿐 — 룰은 rules.json 으로 적용됨, **검증에서 차단 응답을 직접 읽어 확인**. money shot: 필터 `tenant_restriction_violation` → flow 클릭 → 주입헤더 + 차단본문. 차단상태 Ctrl+R 금지(흰화면), 복구는 Ctrl+R.
- **04-dlp**: block 룰은 mitm 이 rules 재독해야 451 — 안 그러면 200 으로 샘. 전/후 같은 메시지로 변화 확인.
- **05-otel**: 주입 스키마 데모면 캡션 명시. Grafana `:3000` 직접 404 → API 프록시 딥링크 `/envs/{env}/grafana/explore?...`. 캡션 ~7s 밀림 보정.
- **06-tool**: 증거 = 모델 호출 completion flow(메시지 전송→생성). filter `completion` → POST·대상 SaaS 호스트 매칭 `.last` 클릭(구take 배제). `#detail pre.body` first=요청(프롬프트+tools), last=응답(SSE).

---

## 🚨 증적 = 화면 캡쳐(스크린샷)로만. grep/print 텍스트는 증적 아님

모니터링 가시성 리포트(프록시/OTel/Compliance)의 판정 근거는 **반드시 실제 화면을 스크린샷으로 캡쳐해 img/에 넣고 shot 블록으로 박는다.** `grep -oE`·`python print` 텍스트 출력은 "어떻게 캡쳐됐는지"가 안 보여 증적으로 불인정(사용자 명시). 한 리뷰당 증적 사진 최소 10장+, **아티팩트마다 개별로**(4개면 4개 각각 proxy·OTel 따로).

### 캡쳐 방법 (콘솔을 내 브라우저로 열어 조작 — 별도 브라우저 띄우기 금지)
- **초기화 먼저**: 트리거(런) **시작 전에** 콘솔 → env → **L7-proxy → 우상단 "초기화"** 눌러 flow 버퍼 비운다(안 그러면 10000 링버퍼가 넘쳐 런 flow가 밀려나감). 버퍼 상단 "10002/10000" 처럼 넘으면 오래된 게 사라진다.
- **프록시 증적**: 콘솔 → env → **L7-proxy** → 우상단 **"헤더/본문 전체 검색" 필터**에 그 아티팩트 **마커 문자열**(예 `DEMO-12-COWORKREMOTE`) 입력 → 매칭 flow 목록 캡쳐 → flow **클릭**해 우측 **detail(요청/응답 헤더+본문 전문)** 캡쳐. 이게 "어떻게 캡쳐됐는지"까지 보이는 진짜 증적. (원격 MCP 툴콜은 `claude.ai/.../mcp/servers/<id>/tools/call`, 대화·로컬 결과는 `api.anthropic.com/v1/messages` 로 잡힌다.)
- **OTel 증적**: 콘솔 → env → **log-server**(=Grafana Explore/Loki 임베드). **Code** 토글 → 쿼리 에디터에 `{service_name="<대상 서비스명>"}`(S0 실측값) 입력 → **Shift+Enter** 실행 → 히스토그램+이벤트 라인 캡쳐 → tool_result 이벤트 **클릭 펼쳐** `tool_input`(입력 평문) vs `tool_result_size_bytes`(출력 크기만) 캡쳐. (Grafana 외부IP 직링크는 root_url 리다이렉트로 404 → 반드시 log-server 컴포넌트로 열 것.)
- **공식문서 증적**: 내 브라우저의 별도 탭으로 그 제품 **공식 문서** URL 을 열어 그 문장이 보이게 스크롤 후 스크린샷. **"공식문서에 있으니 O/X"는 금지 — 그 문서 페이지를 캡쳐해 박아야 근거.** 문서가 "미포함/안 잡힘"을 명시하면 그건 **없다는 근거 = X**(물음표 아님).

### 판정 규칙(재확인)
- O/X/-/? 4개만. **이 보고서에 캡쳐로 박힌 것만 근거**. 캡쳐 없이 확인 불가면 ?. 문서가 명시적으로 부정하면 X.
- 이유 칸 = 완결문장("…첨부돼 있으므로, X 라고 판정하였습니다").
- OTel 내용: 입력 평문이나 출력은 `tool_result_size_bytes`(크기)만 → 내용 X.
- 🔑 cowork/code(local-agent) 는 대화·툴 입출력을 **client-side `/v1/messages`·claude.ai** 로 흘려 사내 프록시가 SSL-bump로 평문 캡쳐(프록시 O). 원격 MCP **서버 직접 접속만** server-side. "cowork=서버측이라 프록시 X"는 틀림(실측 반증).
