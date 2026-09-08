#!/usr/bin/env python3
"""받은편지함을 IMAP 으로 직접 조회한다 — MCP 커넥터를 거치지 않는다.

이 스킬이 하는 일은 두 번의 외부 통신이고, 관측 대상이 되라고 일부러 그렇게 짰다:
  1) pypi 에서 imapclient 휠을 내려받아 임시폴더에 푼다
  2) imap.gmail.com:993 에 TLS 로 붙어 헤더만 읽는다

의존성을 공용 venv 가 아니라 --target 임시폴더에 까는 이유: 이 머신의 venv 를 여러 작업이
공유하므로 스킬 하나가 거기에 패키지를 심으면 남의 실행 환경을 바꿔버린다. 임시폴더면 끝나고
지워지고, 매 실행이 같은 조건에서 시작한다(=관측 결과도 매번 재현된다).

자격증명은 환경변수에서만 읽는다. 파일에도, 인자에도 남기지 않는다 — 인자는 ps 로 보인다.
"""

from __future__ import annotations

import argparse
import email.header
import os
import shutil
import subprocess
import sys
import tempfile

PACKAGE = "imapclient"
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def log(msg: str) -> None:
    print(f"[gmail_peek] {msg}", file=sys.stderr, flush=True)


def ensure_library(target: str):
    """pypi 에서 imapclient 를 임시폴더로 받아 import 한다."""
    log(f"의존성 내려받는 중: {PACKAGE} -> {target}")
    r = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--quiet", "--no-compile",
         "--target", target, PACKAGE],
        capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        log("pip 실패: " + (r.stderr.strip().splitlines() or ["(출력 없음)"])[-1])
        raise SystemExit(2)
    sys.path.insert(0, target)
    import imapclient  # noqa: PLC0415 - 방금 받은 것이라 여기서만 import 가능
    log(f"의존성 준비됨: imapclient {getattr(imapclient, '__version__', '?')}")
    return imapclient


def decode(raw) -> str:
    """MIME 인코딩된 헤더를 사람이 읽는 문자열로."""
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    out = []
    for part, enc in email.header.decode_header(raw):
        if isinstance(part, bytes):
            part = part.decode(enc or "utf-8", "replace")
        out.append(part)
    return " ".join("".join(out).split())


def main() -> None:
    ap = argparse.ArgumentParser(description="받은편지함을 IMAP 으로 직접 조회한다.")
    ap.add_argument("--limit", type=int, default=10, help="가져올 개수 (기본 10)")
    ap.add_argument("--unread", action="store_true", help="안 읽은 것만")
    ap.add_argument("--canary", default="", help="관측용 마커 — 검색어에 실어 보낸다")
    args = ap.parse_args()

    address = os.environ.get("GMAIL_ADDRESS", "")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")
    if not address or not password:
        log("GMAIL_ADDRESS / GMAIL_APP_PASSWORD 를 환경변수로 넣어라 (앱 비밀번호 16자).")
        raise SystemExit(2)

    tmp = tempfile.mkdtemp(prefix="gmail_peek_")
    try:
        imapclient = ensure_library(tmp)

        log(f"접속: {IMAP_HOST}:{IMAP_PORT} (TLS)")
        with imapclient.IMAPClient(IMAP_HOST, port=IMAP_PORT, ssl=True) as server:
            server.login(address, password)
            # readonly: 조회만 한다. 이걸 빼면 읽은 메일이 '읽음'으로 바뀐다.
            server.select_folder("INBOX", readonly=True)

            criteria = ["UNSEEN"] if args.unread else ["ALL"]
            if args.canary:
                # 마커를 실제 IMAP 명령에 실어 보낸다 — 프록시/로그에서 이 실행만 골라내라고.
                criteria = ["OR"] + criteria + ["SUBJECT", args.canary]
                log(f"카나리 마커를 검색어에 실음: {args.canary}")

            uids = server.search(criteria)
            log(f"검색 결과 {len(uids)}건, 최근 {min(args.limit, len(uids))}건만 가져온다")
            if not uids:
                print("(해당하는 메일이 없습니다)")
                return

            recent = uids[-args.limit:]
            fetched = server.fetch(recent, ["ENVELOPE", "FLAGS"])

        rows = []
        for uid in reversed(recent):
            item = fetched.get(uid) or {}
            env = item.get(b"ENVELOPE")
            if env is None:
                continue
            sender = ""
            if env.from_:
                f = env.from_[0]
                sender = decode(f.name) or f"{(f.mailbox or b'').decode()}@{(f.host or b'').decode()}"
            unread = b"\\Seen" not in (item.get(b"FLAGS") or ())
            rows.append((uid, decode(env.subject), sender, env.date, unread))

        print(f"\n받은편지함 — {address} (최근 {len(rows)}건)\n")
        for uid, subject, sender, date, unread in rows:
            mark = "●" if unread else " "
            when = date.strftime("%m-%d %H:%M") if date else "?"
            print(f" {mark} [{uid}] {when}  {sender[:24]:24}  {subject[:60]}")
        print()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)   # 공용 환경에 흔적을 남기지 않는다


if __name__ == "__main__":
    main()
