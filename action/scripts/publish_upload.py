#!/usr/bin/env python3
"""업로드 파일 하나를 브랜치 → PR 로 만든다. 비개발자의 "올리기" 버튼 뒤에서 도는 것.

    python action/scripts/publish_upload.py <파일> --repo <origin 이 잡힌 클론>

흐름: origin/main 을 당겨 **detached worktree** 를 만든다(작업 트리는 절대 건드리지 않는다 —
대시보드 서버가 그 트리에서 돌고 있고, 다른 세션이 편집 중일 수 있다) → ingest 로 자산을 놓고
카탈로그 항목을 넣는다 → sync_catalog --write 로 카드 값을 진실원에서 채운다 → validate_catalog 로
불변식을 확인한다(여기서 실패하면 push 하지 않는다) → 커밋 → `upload/<이름>-<UTC시각>` 으로 push →
`gh pr create --base main`. 그 뒤는 저장소의 기존 흐름이다: auto-merge.yml 이 예약하고, 기본검증이
초록이면 GitHub 이 병합하며, 걸린 자산은 게이트가 PR 에서 뺀다. 브랜치는 저장소 설정
(delete_branch_on_merge)이 지운다.

결과는 stdout 에 JSON 한 줄. 종료코드 0 = PR 생성, 3 = 판별 불가(Pass), 1 = 그 밖의 실패.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ingest  # noqa: E402

AUTHOR = ("genaisec-upload", "genaisec-upload@users.noreply.github.com")
# push 는 ssh 로 한다. origin 은 https 인데 이 호스트엔 https 자격증명이 없고(터미널 없는 서비스라
# 물어볼 수도 없다), gh 는 ssh 키로 인증돼 있다. 저장소 설정을 건드리지 않고 URL 만 바꿔 민다.
PUSH_URL = "git@github.com:arizona95/genaisec-marketplace.git"


class Fail(Exception):
    pass


def run(*cmd: str, cwd: Path | None = None, timeout: int = 180, check: bool = True) -> str:
    r = subprocess.run(list(cmd), cwd=str(cwd) if cwd else None, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    if check and r.returncode != 0:
        raise Fail(f"{' '.join(cmd[:3])} 실패: {(r.stderr or r.stdout).strip()[:600]}")
    return r.stdout


def publish(file: Path, repo: Path) -> dict:
    a = ingest.inspect(file)                       # Pass 는 그대로 위로
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    branch = f"upload/{a.name}-{stamp}"
    wt = Path(tempfile.mkdtemp(prefix="upload-wt-"))
    pushed = False
    try:
        run("git", "fetch", "-q", "origin", "main", cwd=repo)
        run("git", "worktree", "add", "-q", "--detach", str(wt), "origin/main", cwd=repo)
        dest = ingest.place(a, wt)
        py = sys.executable
        run(py, str(HERE / "sync_catalog.py"), "--write", cwd=wt)
        out = run(py, str(HERE / "validate_catalog.py"), cwd=wt, check=False)
        if "통과" not in out:
            raise Fail("카탈로그 불변식 위반 — push 하지 않음:\n" + out.strip()[:800])
        run("git", "add", "-A", cwd=wt)
        if not run("git", "status", "--porcelain", cwd=wt).strip():
            raise Fail("origin/main 과 내용이 같다 — 바뀐 것이 없어 PR 을 만들지 않는다")
        title = f"업로드: {a.kind} {a.name} {a.version}".strip()
        body = (f"대시보드 업로드 → 자동 PR.\n\n"
                f"- 종류: **{a.kind}**\n- 이름: `{a.name}`\n- 버전: {a.version}\n"
                f"- 원본 파일: `{file.name}`\n- 경로: `{dest.relative_to(wt).as_posix()}`\n"
                + ("".join(f"- 정규화: {n}\n" for n in a.notes))
                + "\n기본검증을 통과하면 auto-merge 가 병합하고, 걸린 자산은 게이트가 이 PR 에서 뺀다.")
        run("git", "-c", f"user.name={AUTHOR[0]}", "-c", f"user.email={AUTHOR[1]}",
            "commit", "-q", "-m", title, "-m", body, cwd=wt)
        sha = run("git", "rev-parse", "--short", "HEAD", cwd=wt).strip()
        run("git", "push", "-q", PUSH_URL, f"HEAD:refs/heads/{branch}", cwd=wt, timeout=300)
        pushed = True
        pr_url = run("gh", "pr", "create", "--base", "main", "--head", branch,
                     "--title", title, "--body", body, cwd=wt, timeout=120).strip().splitlines()[-1]
        number = int(pr_url.rstrip("/").rsplit("/", 1)[-1])
        return {"ok": True, "kind": a.kind, "name": a.name, "version": a.version, "branch": branch,
                "sha": sha, "pr": number, "pr_url": pr_url, "notes": a.notes}
    except Exception:
        if pushed:
            # PR 을 못 만들었으면 브랜치를 남기지 않는다 — 고아 브랜치는 아무도 안 본다.
            subprocess.run(["git", "push", "-q", PUSH_URL, "--delete", branch], cwd=str(repo),
                           capture_output=True, timeout=120)
        raise
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=str(repo),
                       capture_output=True, timeout=60)
        shutil.rmtree(wt, ignore_errors=True)
        a.cleanup()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--repo", default=str(HERE.parents[1]))
    args = ap.parse_args()
    try:
        print(json.dumps(publish(Path(args.file), Path(args.repo).resolve()), ensure_ascii=False))
        return 0
    except ingest.Pass as e:
        print(json.dumps({"ok": False, "pass": True, "reason": str(e)}, ensure_ascii=False))
        return 3
    except (Fail, subprocess.TimeoutExpired, OSError) as e:
        print(json.dumps({"ok": False, "reason": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
