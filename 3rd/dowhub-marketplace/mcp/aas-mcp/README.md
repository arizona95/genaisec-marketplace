# aas-mcp — Agent Auto Sensing 저장소 MCP

- URL: https://dowhub.org/aas-mcp/ (OAuth) · 로컬 stdio: `python3 SDSreviewBLUE/agentsensing/aas_mcp.py`
- 도구 1개 `sensing(action=…)` — 목표(target_*)·범위 URL(url_*)·워터마크·변화(change_*)·요청서(request_*)·로그.
- 쓰는 쪽: aas-plugin 의 `/aas_scope`·`/aas_search` 뿐. aar-mcp 와 무관(aar 는 나중에 이 DB 를 읽어 검토).
- 보는 곳: https://dowmain.org/agentsensing/ (읽기 전용 웹).
- 서버 소스: `SDSreviewBLUE/agentsensing/aas_mcp.py` + `AgentReviewPlugin/plugin/sensing_store.py`(SQLite `runs/aas.sqlite`).
