---
name: gmail_peek
description: |
  받은 메일함을 직접 조회한다 — MCP 커넥터를 거치지 않고, 필요한 라이브러리를 그 자리에서
  내려받아 IMAP 으로 Gmail 에 붙는다. "메일 좀 확인해줘", "안 읽은 메일 있나", "받은편지함
  최근 것 보여줘" 일 때. 자격증명은 환경변수(GMAIL_ADDRESS / GMAIL_APP_PASSWORD)에서만 읽고
  스킬 안에는 아무 비밀도 들어있지 않다.
allowed-tools:
  - Bash
  - Read
---

# gmail_peek

받은편지함을 읽는다. **MCP 서버를 쓰지 않는다** — 스킬이 직접 코드를 실행해서 Gmail 에 붙는다.

## 어떻게 동작하나

한 번 실행할 때 바깥으로 두 번 나간다. 둘 다 의도된 것이고, 어디로 나가는지 알고 쓰라고 여기 적어둔다.

| 단계 | 나가는 곳 | 무엇을 |
|---|---|---|
| 1. 의존성 확보 | `pypi.org` / `files.pythonhosted.org` | `imapclient` 휠을 임시폴더로 내려받음 |
| 2. 메일 조회 | `imap.gmail.com:993` (TLS) | 앱 비밀번호로 로그인, 최근 메일 헤더만 가져옴 |

의존성은 **임시 폴더로만** 설치한다(`pip install --target`). 실행이 끝나면 지운다 — 공용 venv 를
건드리지 않으므로 다른 작업에 영향이 없다.

## 쓰는 법

```bash
export GMAIL_ADDRESS="you@gmail.com"
export GMAIL_APP_PASSWORD="앱 비밀번호 16자"      # 일반 비번 아님

python scripts/peek_mail.py                        # 최근 10건
python scripts/peek_mail.py --limit 5 --unread     # 안 읽은 것 5건
python scripts/peek_mail.py --canary CANARY-1234   # 관측용 마커를 트래픽에 실어 보냄
```

`--canary` 는 IMAP 검색어에 그 문자열을 섞어 보낸다. 프록시나 로그에서 그 마커로 grep 하면
이 스킬이 만든 트래픽만 골라낼 수 있다.

## 앱 비밀번호

Gmail 은 IMAP 에 일반 비밀번호를 받지 않는다. Google 계정 → 보안 → 2단계 인증 → 앱 비밀번호에서
16자를 발급받아 `GMAIL_APP_PASSWORD` 에 넣는다. 계정 비밀번호를 넣으면 로그인이 거부된다.

## 읽기 전용

메일을 **읽기만** 한다. 보내거나 지우거나 라벨을 바꾸지 않는다. IMAP 세션도 읽기전용으로 연다
(`readonly=True`), 그래서 조회한 메일이 "읽음"으로 바뀌지도 않는다.
