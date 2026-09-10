#!/usr/bin/env python3
"""marketplace-ui 로컬 서버 — 저장소와의 동기화를 보장하는 유일한 방법으로 만든다.

왜 정적 파일이 아니라 서버인가: 정적 HTML 이 raw.githubusercontent 를 읽으면 CDN 캐시(수 분)를
거치고, 데이터를 내장하면 그 순간부터 사본이다. 사본은 반드시 어긋난다. 이 서버는 요청과 무관하게
일정 주기로 `git fetch` 를 하고, **로컬 체크아웃이 아니라 origin/<브랜치> 의 git 객체를 직접**
읽는다(`git show origin/main:<path>`). 그래서 어느 클론에서 띄워도, 작업 트리가 더러워도, 항상
원격의 최신 커밋을 보여준다.

실시간: fetch 결과 origin 참조(main·dev·history)가 바뀌면 SSE(/api/events)로 브라우저에 밀어준다.
브라우저는 그 신호에 다시 그린다. 새로고침 버튼은 /api/refresh 로 즉시 fetch 를 강제한다.

이력의 진실원은 `history` 브랜치(CI 의 history.yml 만 쓴다). 카탈로그의 진실원은 각 브랜치의
.claude-plugin/marketplace.json 이다. 이 서버는 어느 것도 저장하지 않는다.

    python ui/server.py                       # 이 저장소, 127.0.0.1:8787, 15초 주기
    python ui/server.py --repo ../다른클론 --port 9000 --interval 10

GITHUB_TOKEN 이 환경변수에 있으면 CI 실행 상태(GitHub API)를 30초마다, 없으면 120초마다 본다.
표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent / "action" / "scripts"
HISTORY_BRANCH = "history"
UPLOAD_EXT = (".zip", ".skill", ".mcpb")
UPLOAD_MAX = 50 * 1024 * 1024
UPLOAD_LOCK = threading.Lock()     # 업로드는 한 번에 하나 — 같은 클론에서 fetch·worktree 가 겹치지 않게
REPO_API = "https://api.github.com/repos/arizona95/genaisec-marketplace"


def sh(repo: Path, *args: str, timeout: int = 60) -> tuple[int, str]:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout if r.returncode == 0 else r.stderr).strip()


class Repo:
    """origin 을 주기적으로 당겨 오고, 객체를 직접 읽는다. 작업 트리는 건드리지 않는다."""

    def __init__(self, path: Path, interval: float):
        self.path = path
        self.interval = interval
        self.version = 0                 # origin 참조가 바뀔 때마다 +1 (SSE 가 이걸 알린다)
        self.heads: dict[str, str] = {}
        self.synced_at = ""
        self.last_error = ""
        self.ci: list[dict] = []
        self.ci_at = ""
        self._cond = threading.Condition()
        self._token = os.environ.get("GITHUB_TOKEN", "")
        self._ci_interval = 30 if self._token else 120

    # -- 동기화 ---------------------------------------------------------------
    def fetch(self) -> bool:
        code, out = sh(self.path, "fetch", "-q", "--prune", "origin", timeout=120)
        if code != 0:
            self.last_error = out[:300]
            return False
        self.last_error = ""
        code, out = sh(self.path, "for-each-ref", "--format=%(refname:short) %(objectname:short)",
                       "refs/remotes/origin")
        heads = {}
        for line in out.splitlines():
            ref, _, sha = line.partition(" ")
            name = ref.removeprefix("origin/")
            # origin/HEAD 는 짧은 이름이 "origin" 으로 나온다 — 브랜치가 아니다.
            if name not in ("HEAD", "origin"):
                heads[name] = sha
        changed = heads != self.heads
        with self._cond:
            self.heads = heads
            self.synced_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            if changed:
                self.version += 1
                self._cond.notify_all()
        return changed

    def poll_ci(self) -> None:
        req = urllib.request.Request(f"{REPO_API}/actions/runs?per_page=8",
                                     headers={"Accept": "application/vnd.github+json",
                                              **({"Authorization": f"Bearer {self._token}"} if self._token else {})})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                runs = json.loads(resp.read().decode("utf-8")).get("workflow_runs", [])
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            return
        ci = [{"name": r.get("name"), "branch": r.get("head_branch"), "status": r.get("status"),
               "conclusion": r.get("conclusion"), "event": r.get("event"), "url": r.get("html_url"),
               "sha": (r.get("head_sha") or "")[:7], "updated": r.get("updated_at")}
              for r in runs]
        with self._cond:
            if ci != self.ci:
                self.ci = ci
                self.version += 1
                self._cond.notify_all()
            self.ci_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def loop(self) -> None:
        last_ci = 0.0
        while True:
            self.fetch()
            if time.time() - last_ci >= self._ci_interval:
                self.poll_ci()
                last_ci = time.time()
            time.sleep(self.interval)

    def wait_change(self, since: int, timeout: float) -> int:
        with self._cond:
            self._cond.wait_for(lambda: self.version != since, timeout=timeout)
            return self.version

    # -- 읽기 -------------------------------------------------------------------
    def branches(self) -> list[str]:
        return sorted(b for b in self.heads if b != HISTORY_BRANCH)

    def show(self, ref: str, path: str) -> str | None:
        code, out = sh(self.path, "show", f"{ref}:{path}")
        return out if code == 0 else None

    def catalog(self, branch: str) -> dict | None:
        raw = self.show(f"origin/{branch}", ".claude-plugin/marketplace.json")
        return json.loads(raw) if raw else None

    def history(self, branch: str, name: str) -> dict | list | None:
        raw = self.show(f"origin/{HISTORY_BRANCH}", f"{branch}/{name}")
        return json.loads(raw) if raw else None

    def state(self) -> dict:
        return {
            "version": self.version,
            "heads": self.heads,
            "branches": self.branches(),
            "history_branch": HISTORY_BRANCH in self.heads,
            "synced_at": self.synced_at,
            "interval": self.interval,
            "last_error": self.last_error,
            "ci": self.ci,
            "ci_at": self.ci_at,
            "repo": str(self.path),
        }


REPO: Repo


def publish_upload(filename: str, data: bytes) -> tuple[int, dict]:
    """업로드 바이트를 임시 파일로 두고 publish_upload.py 를 돌린다. (HTTP 코드, 결과 JSON)."""
    safe = Path(filename).name
    if Path(safe).suffix.lower() not in UPLOAD_EXT:
        return 400, {"ok": False, "pass": True,
                     "reason": f"허용 확장자는 {', '.join(UPLOAD_EXT)} 뿐이다: {safe}"}
    if len(data) > UPLOAD_MAX:
        return 413, {"ok": False, "pass": True, "reason": f"{UPLOAD_MAX // (1024 * 1024)}MB 를 넘는다"}
    tmp = Path(tempfile.mkdtemp(prefix="upload-"))
    try:
        f = tmp / safe
        f.write_bytes(data)
        with UPLOAD_LOCK:
            r = subprocess.run([sys.executable, str(SCRIPTS / "publish_upload.py"), str(f),
                                "--repo", str(REPO.path)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=600)
        line = (r.stdout.strip().splitlines() or [""])[-1]
        try:
            out = json.loads(line)
        except json.JSONDecodeError:
            out = {"ok": False, "reason": (r.stderr or r.stdout).strip()[-800:] or "출력 없음"}
        code = 200 if r.returncode == 0 else (422 if r.returncode == 3 else 500)
        return code, out
    except subprocess.TimeoutExpired:
        return 504, {"ok": False, "reason": "시간 초과(600초)"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pr_status(number: int) -> tuple[int, dict]:
    """gh 로 PR 상태 + 체크 롤업. 사람이 보는 건 이것뿐이라 gh 의 JSON 을 얇게 추린다."""
    try:
        r = subprocess.run(["gh", "pr", "view", str(number), "--repo", "arizona95/genaisec-marketplace",
                            "--json", "number,state,mergedAt,url,headRefName,title,statusCheckRollup,autoMergeRequest"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 502, {"error": str(e)}
    if r.returncode != 0:
        return 502, {"error": r.stderr.strip()[:300]}
    d = json.loads(r.stdout)
    checks = [{"name": c.get("name") or c.get("context"), "status": c.get("status"),
               "conclusion": c.get("conclusion") or c.get("state"), "url": c.get("detailsUrl") or c.get("targetUrl")}
              for c in d.get("statusCheckRollup") or []]
    # 브랜치가 아직 있는지 — 병합 뒤 저장소 설정(delete_branch_on_merge)이 지우는 걸 눈으로 확인시킨다.
    code, _ = sh(REPO.path, "ls-remote", "--exit-code", "--heads", "origin", d.get("headRefName", ""), timeout=60)
    return 200, {"number": d.get("number"), "state": d.get("state"), "merged_at": d.get("mergedAt"),
                 "url": d.get("url"), "branch": d.get("headRefName"), "branch_exists": code == 0,
                 "title": d.get("title"), "auto_merge": bool(d.get("autoMergeRequest")), "checks": checks}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: D102
        # 오류 경로에서는 args[0] 이 HTTPStatus 다 — 먼저 문자열로 만든 뒤 본다.
        line = fmt % args
        if "/api/events" in line:
            return
        sys.stderr.write("[ui] " + line + chr(10))

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        url = urllib.parse.urlsplit(self.path)
        q = urllib.parse.parse_qs(url.query)
        branch = (q.get("branch") or ["main"])[0]
        if ".." in branch or "/" in branch:
            return self._json({"error": "bad branch"}, 400)

        if url.path in ("/", "/index.html"):
            page = HERE / "index.html"
            if not page.is_file():
                return self._send(200, "ui/index.html 이 없습니다. API 는 동작합니다: /api/state".encode("utf-8"),
                                  "text/plain; charset=utf-8")
            return self._send(200, page.read_bytes(), "text/html; charset=utf-8")
        if url.path == "/api/state":
            return self._json(REPO.state())
        if url.path == "/api/catalog":
            doc = REPO.catalog(branch)
            return self._json(doc if doc else {"error": f"origin/{branch} 에 카탈로그가 없습니다"},
                              200 if doc else 404)
        if url.path == "/api/history/latest":
            doc = REPO.history(branch, "latest.json")
            return self._json(doc if doc else {"error": "이력 없음"}, 200 if doc else 404)
        if url.path == "/api/history/index":
            doc = REPO.history(branch, "index.json")
            return self._json(doc if doc is not None else [], 200)
        if url.path == "/api/history/run":
            rid = (q.get("id") or [""])[0]
            if not rid or "/" in rid or ".." in rid:
                return self._json({"error": "bad id"}, 400)
            doc = REPO.history(branch, f"runs/{rid}.json")
            return self._json(doc if doc else {"error": "없는 실행"}, 200 if doc else 404)
        if url.path == "/api/events":
            return self._events(int((q.get("since") or ["0"])[0]))
        if url.path == "/api/upload/pr":
            try:
                n = int((q.get("n") or ["0"])[0])
            except ValueError:
                n = 0
            if n <= 0:
                return self._json({"error": "bad pr"}, 400)
            code, doc = pr_status(n)
            return self._json(doc, code)
        if url.path == "/api/upload/rules":
            return self._json({"ext": list(UPLOAD_EXT), "max_bytes": UPLOAD_MAX})
        self._send(404, b"not found", "text/plain")

    def do_POST(self):  # noqa: N802
        # 본문을 반드시 비운다. keep-alive 연결에서 본문을 안 읽고 응답하면 남은 바이트가 다음 요청의
        # 시작으로 파싱돼 501(Unsupported method) 이 난다 — 프록시 뒤에서 Cloudflare RUM 비컨
        # (POST /cdn-cgi/rum, JSON 본문)이 그대로 넘어와 실제로 겪었다.
        length = int(self.headers.get("Content-Length") or 0)
        url = urllib.parse.urlsplit(self.path)
        if url.path == "/api/upload":
            # 본문 = 파일 바이트 그대로(multipart 아님). 파일명은 ?name= 으로.
            name = (urllib.parse.parse_qs(url.query).get("name") or [""])[0]
            if length > UPLOAD_MAX:
                self._drain(length)
                return self._json({"ok": False, "pass": True, "reason": f"{UPLOAD_MAX // (1024 * 1024)}MB 를 넘는다"}, 413)
            data = self.rfile.read(length) if length > 0 else b""
            if not name or not data:
                return self._json({"ok": False, "pass": True, "reason": "파일명(?name=)과 본문이 필요하다"}, 400)
            code, out = publish_upload(name, data)
            return self._json(out, code)
        self._drain(length)
        if self.path == "/api/refresh":
            changed = REPO.fetch()
            REPO.poll_ci()
            return self._json({"changed": changed, **REPO.state()})
        self._send(404, b"not found", "text/plain")

    def _drain(self, length: int) -> None:
        while length > 0:
            chunk = self.rfile.read(min(length, 65536))
            if not chunk:
                break
            length -= len(chunk)

    def _events(self, since: int) -> None:
        """SSE. 참조가 바뀌면 version 을 보내고, 조용하면 15초마다 심장박동."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        v = since
        try:
            while True:
                nv = REPO.wait_change(v, timeout=15)
                if nv != v:
                    v = nv
                    self.wfile.write(f"data: {json.dumps({'version': v})}\n\n".encode("utf-8"))
                else:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            return


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(HERE.parent), help="origin 이 잡힌 아무 클론")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--interval", type=float, default=15.0, help="git fetch 주기(초)")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    code, _ = sh(repo, "rev-parse", "--git-dir")
    if code != 0:
        print(f"git 저장소가 아닙니다: {repo}")
        return 2
    global REPO
    REPO = Repo(repo, args.interval)
    print(f"[ui] repo={repo}")
    REPO.fetch()
    REPO.poll_ci()
    threading.Thread(target=REPO.loop, daemon=True).start()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[ui] http://{args.host}:{args.port}  (fetch 주기 {args.interval:g}s · 브랜치 {REPO.branches()} · "
          f"history {'있음' if REPO.state()['history_branch'] else '아직 없음'})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())