# 업로드 → PR 자동등록 설계 (2026-09-10)

## 목적
비개발자가 git 클론 없이 마켓플레이스에 자산을 올린다. 대시보드(ui/)의 새 **업로드** 탭에 파일을
떨구면 서버가 skill / mcp / plugin 을 판별해 저장소 규격 폴더로 만들고, 임시 브랜치 → PR → (기존
auto-merge + 기본검증 게이트) → 병합 → 브랜치 자동 삭제까지 사람 손 없이 흐른다. 판별이 안 되면
아무것도 하지 않고 이유만 돌려준다(패스).

## 허용 파일
`.zip` · `.skill`(스킬 패키지, zip 컨테이너) · `.mcpb`(MCP 번들, zip 컨테이너). 그 외 확장자·50MB 초과·zip 이 아닌 내용은 거부.

## 접근 제어
게이트웨이 IP whitelist(shell 과 같은 목록). 업로드 = 소유자 PR = 자동병합이므로 페이지 자체를 잠근다.
서버(127.0.0.1:8787)는 로컬에서만 listen 한다.

## 구성요소
1. `action/scripts/ingest.py` — 순수 함수. 압축 해제된 폴더에서 자산 루트를 찾고(단일 최상위 폴더·`__MACOSX` 제거), 종류·이름을 판별하고, 저장소 규격으로 정규화해 `<base>/<name>/` 에 놓고, 카탈로그 항목을 추가/교체한다.
   - 판별: `.claude-plugin/plugin.json` 이 있으면 구성요소 집합으로 — `{skills}` 만이면 skill, `{mcp}` 만이면 mcp, 그 외(commands/agents/hooks 포함, 둘 이상)는 plugin. plugin.json 이 없으면 `.mcp.json` 또는 MCPB `manifest.json(server)` → mcp, `SKILL.md`(루트 또는 `skills/*/`) → skill, 아니면 **패스**.
   - 이름: plugin.json → manifest.json → SKILL.md frontmatter → 파일명 순, kebab-case 로 정규화(validate_catalog 의 KEBAB 규칙).
   - 정규화: skill 은 `skills/<name>/.claude-plugin/plugin.json` + `skills/<name>/skills/<name>/SKILL.md`(plugin.json 없으면 frontmatter 로 생성). mcp 는 plugin.json 없으면 manifest 에서 생성, `.mcp.json` 없으면 manifest.server 에서 생성, `server.py` 가 있으면 `tools.json` 스냅샷을 AST 로 뜬다(sync_mcp_tools 와 동일 규칙). plugin 은 그대로.
   - 카탈로그: `{name, source:"./<base>/<name>", hub:{type,status:"published"(,url)}}` 를 추가/교체 후 `sync_catalog.py --write` 로 버전·설명·도구를 진실원에서 채운다. 같은 이름이 있으면 **교체(업데이트)**.
2. `action/scripts/publish_upload.py` — git 오케스트레이션. `origin/main` 에서 detached worktree 를 만들고(작업 트리는 절대 안 건드린다), ingest → `validate_catalog.py`·`sync_catalog.py --check` 통과 확인 → 커밋(genaisec-upload) → `upload/<name>-<UTC시각>` 으로 push → `gh pr create --base main` → worktree 제거. 결과는 JSON 한 줄. 브랜치 삭제는 저장소 설정 `delete_branch_on_merge` 가 한다.
3. `ui/server.py` — `POST /api/upload?name=<파일명>`(본문 = 파일 바이트)로 받아 확장자·크기 검사 후 publish_upload 를 서브프로세스로 돌린다(동시 업로드는 락으로 직렬화). `GET /api/upload/pr?n=<번호>` 는 `gh pr view` 로 PR 상태·체크를 돌려준다.
4. `ui/index.html` — **업로드** 탭: 드롭존 + 파일 선택, 허용 확장자 명시, 업로드별 진행 카드(판별 → PR → 검사 → 병합/실패), 10초 폴링, localStorage 로 목록 유지.

## 실패 처리
- 판별 불가·확장자 위반·크기 초과 → 400 + 이유, 저장소에 아무 흔적 없음.
- 정규화 뒤 validate_catalog 실패 → push 하지 않고 이유 반환.
- push/PR 실패 → 원격 브랜치가 남았으면 지우고 이유 반환.
- 기본검증 실패 → 기존 게이트가 걸린 자산을 PR 에서 빼고 재검사(PR 이 비면 병합 없이 닫힘). UI 는 PR 체크 상태를 그대로 보여준다.

## 검증
- `action/tests/test_ingest.py`(unittest): 기존 probe 픽스처를 zip 으로 묶어 판별·정규화·카탈로그 교체를 검사.
- 실제 E2E: 새 이름의 무해한 skill 하나, mcp 하나를 공개 URL 로 업로드해 PR 생성 → CI 통과 → 자동병합 → 브랜치 삭제 → 대시보드 등록 현황 반영까지 확인.
