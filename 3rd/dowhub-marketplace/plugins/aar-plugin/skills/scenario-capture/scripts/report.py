"""Scenario HTML report builder — enforces "no frame, no claim".

The report's images are extracted **from the final mp4 at the exact timestamps
written in report.json**. So if the spec says "t=102 → 403 blocked" but the video
at t=102 shows a normal reply, the embedded frame will plainly show the normal
reply — the lie is impossible to hide. Workflow:

  1. probe:  python report.py grab <folder> <t1> <t2> ...   # dump probe frames to img/_probe/
             → Read them, decide the real timestamps + what each frame ACTUALLY shows
  2. write:  edit <folder>/report.json  (title / before_after / timeline / why / failure)
  3. build:  python report.py build <folder>                # extract final frames + render report.html

report.json schema (all 'file' are written into <folder>/img/ by build):
{
  "title":   "시나리오 03 — Anthropic 테넌트 제한",
  "env":     "claude-exp-env",
  "summary": "한 줄 요약",
  "before_after": {
    "before":  {"file": "ba_before.jpg", "t": 52,  "caption": "..."},
    "after":   {"file": "ba_after.jpg",  "t": 102, "caption": "..."},
    "changed": "같은 행동이 무엇으로 바뀌었나"
  },
  "timeline": [ {"file": "t1.jpg", "t": 12, "what": "이 프레임에 실제로 보이는 것"} , ... ],
  "investigation": {                  # 조사 과정(SaaS-agnostic) — 순서가 핵심:
    "intro": "공식문서 참조(틀릴 수 있음) → 판단 → 직접 실증(진실)",  # ① 문서 기웃 ② 판단 ③ 실증.
    "steps": [                        # kind=doc/think/test. doc·test 는 file 캡처 필수(없으면 ⚠배너).
      {"kind": "doc",   "file": "docs-dlp.jpg", "caption": "공식문서를 좌측 브라우저로 열어 캡처",
       "found": "캡처 화면에 실제 보이는 원문 글귀", "proves": "그 글귀가 왜 이걸 증명하는지",
       "source": "https://docs.<saas>/..."},   # 증거 3종 세트 = file(캡처)+found(글귀)+proves(증명)
      {"kind": "think", "text": "그래서 URL 의 org UUID 를 끊으면 된다고 판단"},
      {"kind": "test",  "file": "t_proxy.jpg", "caption": "직접 실행한 451 차단 화면",
       "result": "문서대로 동작 확인 (혹은 문서와 달랐다 — 그게 진실)"}
    ]
  },                                  # 증적 캡처를 img/ 에 넣는다. 옛 키 evidence 도 호환.
  "analysis": {                       # 패킷 분석 = web UI 아님, 아카이브 폴더를 bash 로 집계
    "title":   "아카이브 패킷 분석 (bash)",
    "intro":   "캡처를 POST /api/export 로 아카이브 떠서 그 폴더의 flow JSON 을 집계한 것",
    "archive": "runs/envs/<env>/captures/archives/<folder>",
    "blocks":  [ {"caption": "egress 집계", "cmd": "python3 aar-plugin/skills/scenario-capture/scripts/archive.py hosts <env>/<folder>"}, ... ]
  },                                  # 각 cmd 는 build 시 cwd=repo 에서 '실제로 실행'되어 출력이 그대로 박힘
  "blocks": [                         # 자유 구성 블록(순서·반복 자유). type: heading/before_after/
                                      # timeline/investigation(doc)/video/analysis/table.
    {"type": "table", "caption": "egress 목적지 전수",   # 표(리스트) — 사진/영상/설명만으론 부족할 때.
     "columns": ["목적지 (scheme://host:port)", "건수", "method", "주요 경로", "상태코드"],
     "cmd": "python3 aar-plugin/skills/scenario-capture/scripts/archive.py hosts_tsv <env>/<folder>"}
    # cmd stdout(탭구분 TSV)을 표 행으로 렌더(실데이터·날조불가). 정적이면 cmd 대신 "rows":[[...],...].
  ],
  "why":            ["프레임/분석 근거 설명", ...],
  "failure_angle":  ["직전 실패 + 무엇을 고쳤나", ...]
}
"""
import re
import sys, os, json, glob, html, subprocess, datetime, pathlib

FFMPEG_IMG = "linuxserver/ffmpeg"   # dockerized ffmpeg/ffprobe (no local install needed)



# ── 분석 블록 실행기 ─────────────────────────────────────────────────────────
# 🚨 예전엔 `subprocess.run(cmd, shell=True, cwd=repo)` 였다. 그 cmd 는 리포트 블록에서 오고,
#    블록은 모델이 만들거나 operator 의 무인증 /build_report 로 들어온다 — 즉 **셸 명령이
#    아무 게이트 없이 서버 사용자 권한으로 실행**됐다. Claude Code 라면 Bash 는 권한 프롬프트를
#    거치는데, 이 경로는 그걸 통째로 우회한다.
#    설계 의도(=숫자를 날조할 수 없게 실제로 돌려서 박는다)는 유지하되, **셸을 없애고 이 폴더의
#    분석 스크립트만** 돌린다. 파이프·리다이렉트·`-c` 는 애초에 분석 스크립트가 아니다.
_ANALYSIS_DIR = os.path.dirname(os.path.abspath(__file__))
_SHELL_META = ("|", ";", "&", ">", "<", "`", "$(", "\n", "\r")
# 🚨 분석 블록이 돌릴 수 있는 스크립트는 이 **고정 목록**뿐이다(R13). 전엔 같은 폴더의 모든 .py 를
#    허용해 `python3 report.py build …`(빌더 자신)·테스트 스크립트도 분석으로 실행됐다.
_ANALYZERS = ("archive.py", "cli_dlp.py", "cli_egress.py", "cli_otel.py", "cli_tenant.py", "cli_tool.py")
# 빌드 한 번 동안의 분석 실패 목록 — build() 가 비우고, 렌더러가 채우고, 끝에 결과로 내보낸다.
_ANALYSIS_FAILURES = []


def _analysis_argv(cmd):
    """분석 cmd 문자열 → 실행 가능한 argv. 못 돌릴 것이면 (None, 사유)."""
    import shlex
    if not cmd or not cmd.strip():
        return None, "빈 명령"
    for meta in _SHELL_META:
        if meta in cmd:
            return None, (f"셸 문법({meta!r})은 실행하지 않는다 — 분석 블록은 "
                          f"scenario-capture/scripts 의 분석 스크립트만 돌린다")
    try:
        argv = shlex.split(cmd)
    except ValueError as e:
        return None, f"명령을 파싱할 수 없다: {e}"
    if len(argv) < 2:
        return None, "형식은 `python3 <분석스크립트> <인자…>` 다"
    if os.path.basename(argv[0]) not in ("python", "python3"):
        return None, f"허용되지 않은 실행파일: {argv[0]!r} (python3 만)"
    if argv[1].startswith("-"):
        return None, f"옵션 실행({argv[1]!r})은 허용하지 않는다 — 스크립트 파일이어야 한다"
    # 🚨 경로는 **무시하고 파일명만** 본다. 옛 리포트의 cmd 는 .claude/skills/... 같은 지금은
    #    없는 경로를 갖고 있는데, 파일명으로 현재 폴더에서 찾으면 그대로 다시 돌릴 수 있고
    #    동시에 폴더 밖 실행을 원천 차단할 수 있다.
    name = os.path.basename(argv[1])
    if not name.endswith(".py"):
        return None, f"분석 스크립트가 아니다: {argv[1]!r}"
    if name not in _ANALYZERS:
        return None, f"허용된 분석 스크립트가 아니다: {name} (사용 가능: {', '.join(_ANALYZERS)})"
    target = os.path.join(_ANALYSIS_DIR, name)
    if not os.path.isfile(target):
        return None, f"분석 스크립트 파일이 없다: {name}"
    return [sys.executable, target] + argv[2:], None


def _run_analysis_result(cmd, cwd):
    """분석 명령을 셸 없이 실행 → {ok, exit_code, output, error}. 거부·예외·timeout·exit≠0 전부 ok=False.
    (R13: 전엔 실패도 문자열로 바꿔 stdout 처럼 박혀 빌드가 성공으로 끝났다.)"""
    argv, why = _analysis_argv(cmd)
    if argv is None:
        return {"ok": False, "exit_code": None, "output": "", "error": f"rejected: {why}"}
    try:
        env = dict(os.environ)
        env.setdefault("AGENTREVIEW_REPO_ROOT", cwd or "")
        res = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=120, env=env)
        out = (res.stdout + res.stderr).rstrip()
        if res.returncode != 0:
            return {"ok": False, "exit_code": res.returncode, "output": out,
                    "error": f"exit {res.returncode}"}
        return {"ok": True, "exit_code": 0, "output": out or "(no output)", "error": ""}
    except subprocess.TimeoutExpired:
        return {"ok": False, "exit_code": None, "output": "", "error": "timeout 120s"}
    except Exception as e:                                   # noqa: BLE001
        return {"ok": False, "exit_code": None, "output": "", "error": f"failed: {e}"}


def _run_analysis(cmd, cwd):
    """렌더용: 결과 문자열. 실패는 `[analysis FAILED: …]` 로 박고 _ANALYSIS_FAILURES 에 기록한다 —
    빌드는 이걸 결과(build_result.json)로 내보내고 operator/MCP 가 발행을 막는다."""
    r = _run_analysis_result(cmd, cwd)
    if r["ok"]:
        return r["output"]
    _ANALYSIS_FAILURES.append({"cmd": cmd, "error": r["error"], "exit_code": r["exit_code"],
                               "output": (r["output"] or "")[-800:]})
    return f"[analysis FAILED: {r['error']}]" + (("\n" + r["output"]) if r["output"] else "")


def _pathstr(p):
    """태그 path(list 또는 'a/b/c') → 'a/b/c'."""
    if isinstance(p, (list, tuple)):
        return "/".join(str(x) for x in p)
    return str(p)


def _block_tags(b):
    """한 블록의 구조 태그 → [(tree_id, path_str)]. server.py._block_tags 와 동일 규칙 유지.
      · b['menu']            → ('menu', path)                 [하위호환]
      · b['tag']  = {tree,path}
      · b['tags'] = [{tree,path}, …]                          [한 블록 다중 구조]
    tree 생략 시 'menu'."""
    if not isinstance(b, dict):
        return []
    out = []
    if b.get("menu"):
        out.append(("menu", _pathstr(b["menu"])))
    cand = []
    if isinstance(b.get("tag"), dict):
        cand.append(b["tag"])
    if isinstance(b.get("tags"), list):
        cand.extend(t for t in b["tags"] if isinstance(t, dict))
    for t in cand:
        if t.get("path"):
            out.append((str(t.get("tree") or "menu"), _pathstr(t["path"])))
    return out


def _mp4(folder):
    # Observational reports (egress/tool host/MCP audits) have no video — that's fine.
    # before_after/timeline reports still need their mp4; missing frames surface as ⚠.
    m = sorted(glob.glob(os.path.join(folder, "*.mp4")))
    return m[0] if m else None


def _duration(folder, mp4):
    out = subprocess.run(
        ["docker", "run", "--rm", "-v", f"{folder}:/v", "--entrypoint", "ffprobe", FFMPEG_IMG,
         "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         f"/v/{os.path.basename(mp4)}"],
        capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def _extract(folder, mp4, t, outrel, width=1280, q=3):
    """Extract one frame at time t (seconds) → folder/outrel (relative path)."""
    outp = os.path.join(folder, outrel)
    os.makedirs(os.path.dirname(outp), exist_ok=True)
    subprocess.run(
        ["docker", "run", "--rm", "-v", f"{folder}:/v", "--entrypoint", "ffmpeg", FFMPEG_IMG,
         "-ss", str(t), "-i", f"/v/{os.path.basename(mp4)}", "-frames:v", "1",
         "-vf", f"scale={width}:-1", "-q:v", str(q), "-y", f"/v/{outrel}"],
        capture_output=True)
    return os.path.exists(outp)


def grab(folder, times):
    """Dump downscaled probe frames for visual analysis (not the final report)."""
    mp4 = _mp4(folder)
    dur = _duration(folder, mp4)
    print(f"mp4={os.path.basename(mp4)} dur={dur:.1f}s — probing {len(times)} frames")
    for t in times:
        rel = f"img/_probe/p_{t}.jpg"
        ok = _extract(folder, mp4, t, rel, width=1024, q=6)
        print(("  ok " if ok else "  FAIL ") + rel)


# ───────────────────────── HTML rendering ─────────────────────────
CSS = """
:root{--bg:#e8f1fb;--card:#ffffff;--ink:#1f2a37;--mut:#5b6b7f;--ok:#16a34a;--bad:#dc2626;--blue:#2563eb}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
 font:15px/1.6 -apple-system,Segoe UI,Roboto,'Noto Sans KR',sans-serif}
img{max-width:100%;height:auto}  /* 전역 방어 — 큰 캡처(공식문서 등)가 컨테이너를 절대 못 넘게 */
.wrap{max-width:1080px;margin:0 auto;padding:32px 24px 80px}
h1{font-size:24px;margin:0 0 4px;color:#0f3a6b}.meta{color:var(--mut);font-size:13px;margin-bottom:28px}
h2{font-size:18px;margin:40px 0 14px;border-left:4px solid var(--blue);padding-left:10px;color:#13294b}
/* 메뉴 태그 섹션: 어디부터 어디까지가 그 메뉴 태그인지 눈에 보이게(경계+배지), 앵커로 오면 하이라이트 */
.menuanchor{position:relative;border:1px solid #bcd7f5;border-left:4px solid var(--blue);
 background:#f2f8ff;border-radius:8px;padding:10px 14px 6px;margin:16px 0}
.menuanchor-tag{display:inline-block;font-size:12px;font-weight:700;color:#fff;background:var(--blue);
 border-radius:6px;padding:2px 9px;margin-bottom:8px}
.menuanchor:target{border-color:#f59e0b;border-left-color:#f59e0b;animation:mflash 1.6s ease-out}
@keyframes mflash{0%{background:#fff2cc;box-shadow:0 0 0 3px #f59e0b}100%{background:#f2f8ff;box-shadow:none}}
.sum p{margin:0 0 11px;line-height:1.75}.sum p:last-child{margin-bottom:0}
.sum{background:var(--card);border-radius:10px;padding:14px 18px;color:#334155;
 box-shadow:0 1px 4px rgba(30,58,95,.10)}
video.rec{width:100%;display:block;border-radius:10px;margin:16px 0 0;background:#000;
 box-shadow:0 1px 4px rgba(30,58,95,.18)}
.inv{display:flex;flex-direction:column;gap:14px}
.inv .step{background:var(--card);border-radius:10px;overflow:hidden;
 box-shadow:0 1px 4px rgba(30,58,95,.10);border-left:4px solid #cbd5e1}
.inv .doc{border-left-color:#f59e0b}.inv .think{border-left-color:#64748b}.inv .test{border-left-color:var(--ok)}
.inv .badge{display:inline-block;font-weight:700;font-size:12px;padding:4px 10px;border-radius:0 0 8px 0}
.inv .doc .badge{background:#fef3c7;color:#92400e}
.inv .think .badge{background:#e2e8f0;color:#334155}
.inv .test .badge{background:#dcfce7;color:#166534}
.inv img{width:100%;display:block;margin-top:8px}
.inv .body{padding:10px 14px 14px;font-size:14px;color:#334155}
.inv .ref{font-size:12.5px;color:#92400e;margin-top:6px}
.inv .quote{margin:8px 0 0;padding:8px 12px;background:#fffbeb;border-left:3px solid #f59e0b;
 font-style:italic;color:#78350f;font-size:13.5px;border-radius:0 6px 6px 0}
.inv .res{font-size:12.5px;color:#166534;margin-top:6px;font-weight:600}
.inv .src{font:11.5px monospace;color:var(--mut);word-break:break-all;margin-top:6px}
.srcurl{font-size:11.5px;margin-top:6px;color:var(--mut)}
.srcurl a{color:#2563eb;word-break:break-all;text-decoration:none}
.srcurl a:hover{text-decoration:underline}
.invintro{background:#dbeafe;border:1px solid #93c5fd;border-radius:8px;padding:10px 14px;
 font-size:13.5px;color:#1e3a8a;margin-bottom:10px}
.invmiss{background:#fee2e2;border:1px solid #fca5a5;border-radius:8px;padding:10px 14px;
 font-size:13px;color:#991b1b;margin:8px 14px 0}
.ba{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.ba .col{background:var(--card);border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(30,58,95,.10)}
.ba .tag{padding:8px 12px;font-weight:700;font-size:13px}
.ba .before .tag{background:#dcfce7;color:#166534}.ba .after .tag{background:#fee2e2;color:#991b1b}
.ba img,.tl img{width:100%;display:block}
.ba .cap{padding:10px 12px;font-size:13px;color:#334155}
.changed{margin:12px 0 0;background:#dbeafe;border:1px solid #93c5fd;border-radius:8px;
 padding:10px 14px;font-size:14px;color:#1e3a8a}
.tl{display:flex;flex-direction:column;gap:18px}
.tl .row{background:var(--card);border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(30,58,95,.10)}
.tl .t{display:inline-block;background:#dbeafe;color:#1e40af;font-weight:700;
 font-size:12px;padding:3px 9px;border-radius:6px;margin:10px 0 0 12px}
.tl .what{padding:8px 14px 14px;font-size:14px;color:#334155}
ul.why{padding-left:0;list-style:none}ul.why li{background:var(--card);border-radius:8px;
 padding:10px 14px;margin:8px 0;border-left:3px solid var(--ok);box-shadow:0 1px 4px rgba(30,58,95,.08)}
ul.fail li{border-left-color:var(--bad)}
table.al{border-collapse:collapse;width:100%;background:var(--card);border-radius:10px;
 overflow:hidden;box-shadow:0 1px 4px rgba(30,58,95,.10);font-size:14px}
table.al th{background:#dbeafe;color:#13294b;text-align:left;padding:9px 12px;font-weight:700}
table.al td{padding:9px 12px;border-top:1px solid #e6eef7;color:#334155;vertical-align:top}
table.al td.ok{color:#166534;font-weight:600}table.al td.no{color:#b45309;font-weight:600}
pre.term{background:#0f2238;color:#d6e4f5;border-radius:10px;padding:14px 16px;overflow:auto;
 font:12.5px/1.5 'SFMono-Regular',Consolas,'Liberation Mono',monospace;box-shadow:0 1px 4px rgba(30,58,95,.18);margin:10px 0}
pre.term .p{color:#7dd3fc}
.aintro{background:#dbeafe;border:1px solid #93c5fd;border-radius:8px;padding:10px 14px;font-size:13.5px;color:#1e3a8a;margin-bottom:8px}
.apath{font:12px monospace;color:var(--mut);margin:2px 0 10px}
.acmd{color:#0f3a6b;font-weight:600;font-size:13px;margin:16px 0 2px}
.note{color:var(--mut);font-size:12px;margin-top:30px;border-top:1px solid #c3d4e6;padding-top:12px}
.dl{margin:16px 0 4px}.dl a{display:inline-block;background:var(--card);border:1px solid #c3d4e6;border-radius:8px;
 padding:9px 16px;color:#1e3a5f;font-weight:700;text-decoration:none}.dl a:hover{background:#eef4fb}
.dlsz{color:var(--mut);font-size:12px;margin-left:8px}
table.rt{width:100%;border-collapse:collapse;margin:8px 0 18px;font-size:13px;display:block;overflow-x:auto;border:2px solid #475569}
table.rt th,table.rt td{border:1px solid #64748b;padding:6px 10px;text-align:left;vertical-align:top;white-space:nowrap}
table.rt th{background:#e2e8f0;color:#1e293b;font-weight:700;position:sticky;top:0;border-bottom:2px solid #475569}
table.rt tbody tr:nth-child(even){background:#f1f5f9}
table.rt td:first-child{font-family:monospace}
"""


# build() 가 현재 폴더를 세팅 → _img 가 이미지 파일 mtime 으로 캐시버스터를 붙인다.
# 같은 파일명으로 재캡처(흑색→실화면) 시 브라우저가 옛 캐시를 계속 보여주던 문제 방지.
_FOLDER = None


_IMG_EXT = ("", ".jpg", ".jpeg", ".png")


def _resolve_img(folder, name):
    """캡처 참조 1건을 실제 파일명으로 해소한다(없으면 None).
    🚨 참조는 **확장자 없는 label**(증적 라벨)로 오는 게 흔하다 — blocks 든 investigation 이든
    **같은 규칙**으로 해소해야 한다(전엔 investigation 만 정확 일치를 요구해 실증 캡처를 '없음'으로 렌더).
    반환값은 img/ 아래 상대 파일명."""
    if not name:
        return None
    for e in _IMG_EXT:
        if os.path.exists(os.path.join(folder, "img", name + e)):
            return name + e
    return None


def _inv_steps(spec):
    """investigation(=evidence) 의 스텝 목록. 캡처를 참조하는 스텝만."""
    inv = spec.get("investigation") or spec.get("evidence") or {}
    return [x for x in (inv.get("steps") or []) if isinstance(x, dict) and x.get("file")]


def _rich(text):
    """요약·노트를 **읽히게** 렌더: 이스케이프 + `**굵게**`·백틱코드 + **문단 분리**.
    🚨 전엔 esc() 통짜 출력이라 ①②③ 항목이 한 덩어리 벽으로 붙어 안 읽혔다."""
    s = html.escape(str(text or ""))
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s, flags=re.S)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\s+(?=(?:<b>)?[\u2460-\u2473])", "\n\n", s)   # ①~⑳ 앞에서 문단 분리
    parts = [x.strip() for x in re.split(r"\n\s*\n", s) if x.strip()]
    return "".join(f"<p>{x}</p>" for x in parts)



def _img(rel, cls=""):
    if not rel:
        return ""
    ver = ""
    try:
        if _FOLDER:
            ver = f"?v={int(os.path.getmtime(os.path.join(_FOLDER, rel)))}"
    except Exception:
        ver = ""
    return f'<img class="{cls}" src="{html.escape(rel)}{ver}" alt="">'


def build(folder):
    global _FOLDER
    _FOLDER = folder  # _img 캐시버스터(파일 mtime)용
    del _ANALYSIS_FAILURES[:]
    spec_p = os.path.join(folder, "report.json")
    if not os.path.exists(spec_p):
        sys.exit(f"missing {spec_p} — write it first (see report.py docstring)")
    spec = json.load(open(spec_p, encoding="utf-8"))
    mp4 = _mp4(folder)
    dur = _duration(folder, mp4) if mp4 else 0.0

    # extract every referenced frame at its timestamp FROM THE FINAL mp4
    refs = []
    ba = spec.get("before_after") or {}
    for k in ("before", "after"):
        if ba.get(k):
            refs.append(ba[k])
    refs += spec.get("timeline", [])
    # free-form blocks (자유 구성) also carry image files (pre-saved captures) — exists-check them.
    for b in spec.get("blocks", []):
        if not isinstance(b, dict):
            continue
        if b.get("type") in ("before_after", "ba"):
            for s in ("before", "after"):
                if isinstance(b.get(s), dict) and b[s].get("file"):
                    refs.append({"file": b[s]["file"]})
        elif b.get("file") and b.get("type") != "video":
            refs.append({"file": b["file"]})
    # 🚨 investigation 스텝의 캡처도 **집계에 포함**한다 — 전엔 blocks 만 세어 로그의
    #    "N frames embedded / M MISSING" 가 실제와 어긋났다(문서 리서치 리포트는 0 으로 찍혔다).
    refs += [{"file": x["file"]} for x in _inv_steps(spec)]
    miss = []
    for r in refs:
        if r.get("t") is None:
            # pre-saved screenshot — the recording driver captured the EXACT before/after
            # moment (정상 응답 / 차단). No timestamp guessing; the file must already exist.
            if not _resolve_img(folder, r["file"]):
                miss.append(r["file"])
            continue
        if not mp4 or not _extract(folder, mp4, r["t"], "img/" + r["file"]):
            miss.append(r["file"])
    if miss:
        print("⚠️ frame MISSING for:", miss)

    esc = lambda s: html.escape(str(s))
    # analysis/table cmd 는 cwd=repo(SDSreviewBLUE root)에서 `aar-plugin/skills/scenario-capture/scripts/archive.py` 상대경로로
    # 돈다. 세션폴더 깊이(Auto_Report/sessions/<session>/<scenario> = 4단)가 고정이 아니므로 `../../..`
    # 하드코딩은 Auto_Report 로 잘못 잡힌다(2026-07 버그) → `aar-plugin/skills/scenario-capture` 가 보일
    # 때까지 상위로 걸어올라가 진짜 repo root 를 찾는다. 못 찾으면 옛 동작(../../..)으로 폴백.
    def _find_repo(start):
        # 1) operator 가 넘긴 명시 루트 2) 위로 올라가며 repo 표식(runs/envs 또는 Auto_Report) 3) 옛 규칙(상위 3단)
        explicit = os.environ.get("AGENTREVIEW_REPO_ROOT")
        if explicit and os.path.isdir(explicit):
            return os.path.abspath(explicit)
        d = os.path.abspath(start)
        for _ in range(8):
            if os.path.isdir(os.path.join(d, "runs", "envs")) or os.path.isdir(os.path.join(d, "Auto_Report")):
                return d
            nd = os.path.dirname(d)
            if nd == d:
                break
            d = nd
        return os.path.abspath(os.path.join(start, "..", "..", ".."))
    repo = _find_repo(folder)
    CIRCLE = "①②③④⑤⑥⑦⑧⑨⑩"
    _n = [0]
    def H2(title):
        c = CIRCLE[_n[0]] if _n[0] < len(CIRCLE) else f"({_n[0]+1})"
        _n[0] += 1
        return f"<h2>{c} {esc(title)}</h2>"
    P = []
    # 🚨 보고서 제목 앞에 시나리오 id(폴더명)를 표준 prefix 로 강제한다 — operator 가 빼먹거나 부분만 써도
    # 항상 "S1-ALL-14-gov-mcp-use — <설명>" 형태가 되게(빠지는 일 방지). 기존 앞쪽 id-유사 토큰은 제거 후 재부착.
    _sid = os.path.basename(folder.rstrip("/"))
    _t = (spec.get("title") or "").strip()
    _t = re.sub(r"^S\d[A-Za-z0-9._-]*\s*(?:[—\-·:]\s*)?", "", _t).strip()
    _title = f"{_sid} — {_t}" if _t else _sid
    P.append(f"<!doctype html><meta charset=utf-8><title>{esc(_title)}</title>")
    P.append(f"<style>{CSS}</style><div class=wrap>")
    P.append(f"<h1>{esc(_title)}</h1>")
    head = f"{esc(os.path.basename(mp4))} · {dur:.0f}s · " if mp4 else "분석 리포트(영상 없음) · "
    P.append(f"<div class=meta>{head}env={esc(spec.get('env',''))}"
             f" · 생성 {datetime.date.today()}</div>")
    if spec.get("summary"):
        P.append(f"<div class=sum>{_rich(spec['summary'])}</div>")

    # Full recording — embed the actual mp4 so the report carries the source video,
    # not just frames extracted from it. Frames remain the "no frame, no claim" proof;
    # the video lets a reviewer scrub the whole run and confirm the frames in context.
    if mp4:
        P.append(f"<video class=rec controls preload=metadata "
                 f"src=\"{esc(os.path.basename(mp4))}\"></video>")

    # ── 자유 구성 blocks (순서·반복·종류 자유) ─────────────────────────────────
    # spec["blocks"] = 시나리오에 맞게 operator 가 고른 블록들. 고정 타입 강제 없음.
    # 같은 종류를 여러 번 써도 되고(전/후 두 번 등), 영상은 필요할 때만(필수 아님).
    def _srcurl(u):   # 촬영 당시 브라우저 URL → 클릭 가능한 링크(캡처와 함께 기록된 .url)
        u = (u or "").strip()
        if not u:
            return ""
        # 🚨 콘솔/Guacamole RDP 뷰어 내부 URL(localhost·127.0.0.1·:5174/:5190·/remote/#/client·일회성
        # token=)은 보고서를 밖에서 열면 죽은 링크이고 토큰도 만료·세션귀속이라 링크로 박지 않는다.
        # S0 웹리서치처럼 실제 공개 URL(공식문서 등)일 때만 클릭 링크로 남긴다.
        low = u.lower()
        if any(x in low for x in ("localhost", "127.0.0.1", ":5174", ":5190",
                                  "/remote/#/client", "/remote/", "token=")):
            return ""
        return (f"<div class=srcurl>🔗 촬영 위치: <a href=\"{esc(u)}\" target=_blank rel=noopener>{esc(u)}</a></div>")

    def _block(b):
        if not isinstance(b, dict):
            return ""
        t = (b.get("type") or "").lower()
        if t in ("heading", "h2", "section"):
            return H2(b.get("text", ""))
        if t in ("note", "text", "p", "summary"):
            return f"<div class=sum>{_rich(b.get('text', ''))}</div>"
        if t in ("before_after", "ba"):
            out = ["<div class=ba>"]
            for side, lab in (("before", "BEFORE · 행동 전"), ("after", "AFTER · 행동 후")):
                r = b.get(side) or {}
                out.append(f"<div class='col {side}'><div class=tag>{lab}</div>"
                           f"{_img('img/' + r.get('file', ''))}<div class=cap>{esc(r.get('caption', ''))}</div>{_srcurl(r.get('url'))}</div>")
            out.append("</div>")
            if b.get("changed"):
                out.append(f"<div class=changed><b>무엇이 바뀌었나:</b> {esc(b['changed'])}</div>")
            return "".join(out)
        if t in ("shot", "frame", "image", "img"):
            return (f"<div class=tl><div class=row>{_img('img/' + b.get('file', ''))}"
                    f"<div class=what>{esc(b.get('caption', ''))}{_srcurl(b.get('url'))}</div></div></div>")
        if t == "doc":  # 공식문서 증거 3종 세트(캡처+글귀+증명) — 보통 S0 인용
            o = ["<div class=inv><div class='step doc'><span class=badge>📄 공식문서 (참조 · 틀릴 수 있음)</span>"]
            if b.get("file"):
                o.append(_img('img/' + b['file']))
            o.append(f"<div class=body>{esc(b.get('caption', ''))}")
            q = b.get("quote") or b.get("found")
            if q:
                o.append(f"<div class=quote>“{esc(q)}”</div>")
            if b.get("proves"):
                o.append(f"<div class=res>🎯 이 글귀가 증명하는 것: {esc(b['proves'])}</div>")
            if b.get("source"):
                o.append(f"<div class=src>출처: {esc(b['source'])}</div>")
            o.append(_srcurl(b.get("url")))
            o.append("</div></div></div>")
            return "".join(o)
        if t == "video":
            f = b.get("file", "")
            return f"<video class=rec controls preload=metadata src=\"{esc(f)}\"></video>" if f else ""
        if t in ("analysis", "bash", "cmd"):  # 빌드 시 cmd 실제 실행되어 박힘(날조 불가)
            cmd = b.get("cmd", "")
            cap = f"<div class=acmd>{esc(b['caption'])}</div>" if b.get("caption") else ""
            o = _run_analysis(cmd, repo)
            return cap + f"<pre class=term><span class=p>$ {esc(cmd)}</span>\n{esc(o)}</pre>"
        if t in ("table", "tbl"):
            # 표 블록. rows 를 직접 주거나(정적), cmd 를 주면 빌드 시 실행해 stdout 을 TSV(탭구분)로
            # 파싱해 행으로 박는다 → 실데이터 표(날조 불가, analysis 와 동일 원리). columns=헤더.
            cap = f"<div class=acmd>{esc(b['caption'])}</div>" if b.get("caption") else ""
            cols = b.get("columns") or []
            rows = b.get("rows")
            if rows is None and b.get("cmd"):
                out = _run_analysis(b["cmd"], repo)
                rows = [ln.split("\t") for ln in out.splitlines() if ln.strip()]
                if not rows:
                    rows = [["(no output)"]]
            rows = rows or []
            o = [cap, "<table class=rt>"]
            if cols:
                o.append("<thead><tr>" + "".join(f"<th>{esc(str(c))}</th>" for c in cols) + "</tr></thead>")
            o.append("<tbody>")
            for r in rows:
                cells = r if isinstance(r, (list, tuple)) else [r]
                o.append("<tr>" + "".join(f"<td>{esc(str(c))}</td>" for c in cells) + "</tr>")
            o.append("</tbody></table>")
            return "".join(o)
        return ""

    for b in spec.get("blocks", []):
        # 🚨 지역변수 이름을 'html' 로 쓰면 모듈 `import html` 이 build() 전체에서 가려져
        #    esc=lambda: html.escape(...) 가 NameError 로 터진다(2026-08 실사고). → blk 로.
        blk = _block(b)
        # 구조 세션 연결: 블록에 태그(어떤 트리의 경로)가 있으면 앵커 id 를 달아, 그 트리 뷰어의
        # '이 부분으로 열기'가 이 섹션으로 자동 스크롤되게 한다(slug = 뷰어/server.py 와 동일 규칙).
        # 지원: b['menu']=[..](하위호환, tree='menu') · b['tag']={tree,path} · b['tags']=[{tree,path},..]
        for (_tree, _pathstr) in _block_tags(b):
            import re as _re
            # slug: 트리 prefix + 경로. 유니코드 글자/숫자만 남기고 나머지는 -. Python \w(유니코드)와
            # JS \p{L}\p{N}_ 가 같은 결과를 내도록 규칙 일치(日本語 등 비한글 보존 — viewer 앵커와 동일).
            _sl = f"{_tree}-" + "-".join(str(_pathstr).split("/"))
            _sl = _re.sub(r"-+", "-", _re.sub(r"[^\w-]+", "-", _sl, flags=_re.UNICODE)).strip("-")
            _leaf = str(_pathstr).rstrip("/").split("/")[-1]
            # menu 는 기존 배지(🔖 leaf) 유지, 다른 구조는 트리명도 보여줌(🔖 tree · leaf).
            _badge = f"🔖 {esc(_leaf)}" if _tree == "menu" else f"🔖 {esc(_tree)} · {esc(_leaf)}"
            blk = (f'<div id="{_sl}" class=menuanchor data-tree="{esc(_tree)}" style="scroll-margin-top:14px" '
                   f'title="{esc(_tree)}: {esc(str(_pathstr))}">'
                   f'<div class=menuanchor-tag>{_badge}</div>{blk}</div>')
        P.append(blk)

    if ba.get("before") and ba.get("after"):
        P.append(H2("Before / After — 같은 행동, 무엇이 바뀌나") + "<div class=ba>")
        for side, label in (("before", "BEFORE · 행동 전"), ("after", "AFTER · 행동 후")):
            r = ba[side]
            tlab = f" (t≈{esc(r['t'])}s)" if r.get("t") is not None else ""
            P.append(f"<div class='col {side}'><div class=tag>{label}{tlab}</div>"
                     f"{_img('img/'+r['file'])}<div class=cap>{esc(r['caption'])}</div></div>")
        P.append("</div>")
        if ba.get("changed"):
            P.append(f"<div class=changed><b>무엇이 바뀌었나:</b> {esc(ba['changed'])}</div>")

    tbl = spec.get("table")
    if tbl:
        P.append(H2(tbl.get('title', '표')) + "<table class=al>")
        if tbl.get("columns"):
            P.append("<tr>" + "".join(f"<th>{esc(c)}</th>" for c in tbl["columns"]) + "</tr>")
        for row in tbl.get("rows", []):
            cells = "".join(
                (f"<td class='{esc(c[1])}'>{esc(c[0])}</td>" if isinstance(c, (list, tuple)) else f"<td>{esc(c)}</td>")
                for c in row)
            P.append("<tr>" + cells + "</tr>")
        P.append("</table>")
        if tbl.get("note"):
            P.append(f"<div class=changed>{esc(tbl['note'])}</div>")

    if spec.get("timeline"):
        P.append(H2("타임라인 — 각 프레임에 실제로 보이는 것") + "<div class=tl>")
        for r in spec["timeline"]:
            tspan = f"<span class=t>t≈{esc(r['t'])}s</span>" if r.get("t") is not None else ""
            P.append(f"<div class=row>{tspan}"
                     f"{_img('img/'+r['file'])}<div class=what>{esc(r['what'])}</div></div>")
        P.append("</div>")

    # Investigation chain — the SaaS-agnostic reasoning narrative, in ORDER:
    #   ① doc-peek (REFERENCE — docs may be WRONG, not truth)  →
    #   ② reasoning (so I hypothesized X)                      →
    #   ③ direct test (CAPTURE — this is the truth).
    # Each "doc"/"test" step carries a screenshot; a referenced file with no image
    # on disk renders as a RED banner so a claim without its capture can't pass.
    inv = spec.get("investigation") or spec.get("evidence")
    if inv:
        P.append(H2(inv.get("title", "조사 과정 — 공식문서 참조 → 직접 실증")))
        P.append(f"<div class=invintro>{esc(inv.get('intro', '먼저 리뷰 대상 SaaS 공식문서에서 방법을 찾아본다(참조 — 문서가 틀릴 수 있으니 진실이 아니다). 그 판단을 가지고 직접 실행해 캡처로 실증한다. 진실은 직접 실행 캡처다.'))}</div>")
        BADGE = {"doc": "📄 공식문서 (참조 · 틀릴 수 있음)", "think": "💡 판단", "test": "✅ 직접 실증 (진실)"}
        P.append("<div class=inv>")  # ★ 래퍼 — 이게 없으면 .inv img{width:100%} 등 CSS 가 안 먹어 큰 캡처가 화면을 뚫는다
        for s in inv.get("steps", []):
            kind = s.get("kind", "test")
            cls = kind if kind in ("doc", "think", "test") else "test"
            P.append(f"<div class='step {cls}'><span class=badge>{BADGE.get(kind, '✅ 실증')}</span>")
            if s.get("file"):
                # 🚨 step 의 file 은 **확장자 없는 label**(증적 라벨)로 오는 게 흔하다.
                #    전엔 정확히 그 이름만 찾아 .jpg 로 저장된 실제 캡처를 못 보고 "⚠️ 캡처 없음" 을
                #    100여 건 띄웠다(실증을 추정처럼 보이게 한 표시 결함). label → 확장자 후보 순으로 해소한다.
                _hit = _resolve_img(folder, s["file"])
                if _hit:
                    P.append(_img("img/" + _hit))
                else:
                    what = "공식문서" if kind == "doc" else "실증"
                    P.append(f"<div class=invmiss><b>⚠️ 캡처 없음:</b> <code>img/{esc(s['file'])}</code> — "
                             f"{what} 캡처가 있어야 근거로 인정. 없으면 추정.</div>")
            P.append(f"<div class=body>{esc(s.get('caption') or s.get('text') or '')}")
            # 증거 3종 세트: 캡처(위 img) + 화면 글귀(found, 인용) + 왜 증명하는지(proves).
            if s.get("found"):
                P.append(f"<div class=quote>“{esc(s['found'])}”</div>")
            if s.get("proves"):
                P.append(f"<div class=res>🎯 이 글귀가 증명하는 것: {esc(s['proves'])}</div>")
            if s.get("result"):
                P.append(f"<div class=res>✔ 직접 해본 결과: {esc(s['result'])}</div>")
            if s.get("source"):
                P.append(f"<div class=src>출처: {esc(s['source'])}</div>")
            P.append(_srcurl(s.get("url")))
            P.append("</div></div>")
        P.append("</div>")  # /.inv

    # Archive packet analysis — each cmd is RUN at build time (cwd=repo root) and its
    # real stdout is embedded. No archive / failing cmd ⇒ the error shows here verbatim.
    an = spec.get("analysis")
    if an:
        P.append(H2(an.get("title", "아카이브 패킷 분석 — web UI 아님, bash 로 집계")))
        if an.get("intro"):
            P.append(f"<div class=aintro>{esc(an['intro'])}</div>")
        if an.get("archive"):
            P.append(f"<div class=apath>archive: {esc(an['archive'])}</div>")
        for b in an.get("blocks", []):
            if b.get("caption"):
                P.append(f"<div class=acmd>{esc(b['caption'])}</div>")
            cmd = b.get("cmd", "")
            out = _run_analysis(cmd, repo)
            P.append(f"<pre class=term><span class=p>$ {esc(cmd)}</span>\n{esc(out)}</pre>")

    if spec.get("why"):
        P.append(H2("결과 요약") + "<ul class=why>")
        P += [f"<li>{esc(x)}</li>" for x in spec["why"]]
        P.append("</ul>")

    if spec.get("failure_angle"):
        P.append(H2("개선점") + "<ul class='why fail'>")
        P += [f"<li>{esc(x)}</li>" for x in spec["failure_angle"]]
        P.append("</ul>")

    P.append("<div class=note>전/후 화면은 녹화 드라이버가 그 순간 실제 캡처한 스크린샷(또는 영상에서 추출한 프레임)이고, "
             "bash 분석 출력은 빌드 시 실제 아카이브에서 집계된 것입니다. 캡처에 없는 내용은 이 리포트에 적지 않았습니다.</div>")

    P.append("</div>")  # /container

    out = os.path.join(folder, "report.html")
    open(out, "w", encoding="utf-8").write("".join(P))
    # 🚨 embedded = **실제로 들어간 수**(참조 총수 - 누락). 전엔 참조 총수를 embedded 로 찍어
    #    누락이 있어도 다 들어간 것처럼 보였다.
    print(f"✓ {out}  ({len(refs) - len(miss)} frames embedded" + (f", {len(miss)} MISSING" if miss else "") + ")")

    # ── 아카이브 zip (report.html 쓴 *뒤* 라야 zip 에 최신 report.html 이 들어간다) ──
    # 내용 = report.html · report.docx(.html) · img/ · report.json + 원본 flow 아카이브. 다운로드는
    # operator 카드의 ⬇ 버튼에서 '세션-리포트.zip' 이름으로 떨어진다(본문 인라인 링크 없음).
    build_archive_zip(folder, an, repo)
    # 빌드 결과(구조화) — operator/MCP 는 이 파일로 발행 가부를 정한다(R13: 분석 실패가 성공으로 안 보이게).
    result = {"ok": not miss and not _ANALYSIS_FAILURES, "missing_frames": list(miss),
              "analysis_failures": list(_ANALYSIS_FAILURES), "frames": len(refs) - len(miss)}
    with open(os.path.join(folder, "build_result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    if _ANALYSIS_FAILURES:
        print(f"✗ analysis failures: {len(_ANALYSIS_FAILURES)}")
        for f_ in _ANALYSIS_FAILURES:
            print(f"    $ {f_['cmd']}  → {f_['error']}")
    # 세션 카드목록 HTML 재생성(전체 다운로드 zip 에 '보고서목록.html' 로 포함됨).
    # 스테이징(공개 루트 밖 runs/report-staging) 빌드는 색인하지 않는다 — 발행 후 operator 가 공개 세션 폴더를 색인한다(R10).
    if os.sep + "report-staging" + os.sep not in os.path.abspath(folder) and not os.path.basename(folder).startswith("."):
        try:
            from session_index import build_session_index
            build_session_index(os.path.dirname(folder))
        except Exception as e:
            print(f"  (session index skip: {e})")
    return result


def build_archive_zip(folder, an, repo):
    import zipfile
    zpath = os.path.join(folder, "archive.zip")
    try:
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(folder):
                for fn in files:
                    if fn == "archive.zip":          # 자기 자신만 제외
                        continue
                    fp = os.path.join(root, fn)
                    z.write(fp, os.path.relpath(fp, folder))   # report.html·report.docx(.html)·img/·report.json
            if an and an.get("archive"):                        # 원본 flow 아카이브(있으면)
                # 2026-09-06 R04: archive 는 <repo>/runs/envs 아래여야만 넣는다. 절대경로·'..'·symlink 탈출은
                # 무시(예전엔 os.path.join 이 절대경로면 repo 를 버려 임의 디렉터리가 공개 ZIP 에 들어갔다).
                arc = str(an["archive"])
                envs_root = os.path.realpath(os.path.join(repo, "runs", "envs"))
                ap = os.path.realpath(os.path.join(repo, arc))
                # 2026-09-07 재검토: runs/envs 아래엔 terraform 상태·변수(비밀)도 있다. **캡처 아카이브 폴더**
                # (runs/envs/<env>/captures/archives/<folder>) 정확히 그 깊이만 허용하고, 데이터 파일 확장자만 넣는다.
                parts = arc.replace("\\", "/").strip("/").split("/")
                shape_ok = len(parts) == 6 and parts[:2] == ["runs", "envs"] and parts[3:5] == ["captures", "archives"]
                ok_arc = (not os.path.isabs(arc) and ".." not in parts and shape_ok
                          and ap.startswith(envs_root + os.sep) and os.path.isdir(ap))
                if not ok_arc:
                    print(f"  (archive skip: runs/envs/<env>/captures/archives/<folder> 형태가 아니거나 없음 {arc!r})")
                ARCHIVE_EXT = (".json", ".txt", ".har", ".log", ".md", ".csv", ".tsv", ".jsonl")
                MAX_FILES, MAX_BYTES = 5000, 500 * 1024 * 1024
                n_files = n_bytes = 0
                if ok_arc:
                    for root, dirs, files in os.walk(ap, followlinks=False):
                        for fn in files:
                            fp = os.path.join(root, fn)
                            if os.path.islink(fp) or not os.path.realpath(fp).startswith(ap + os.sep):
                                continue
                            if not fn.lower().endswith(ARCHIVE_EXT) or "tfstate" in fn or fn.endswith(".tfvars"):
                                continue
                            n_files += 1; n_bytes += os.path.getsize(fp)
                            if n_files > MAX_FILES or n_bytes > MAX_BYTES:
                                print(f"  (archive truncated at {n_files} files / {n_bytes} bytes)")
                                break
                            z.write(fp, os.path.join("flow-archive", os.path.relpath(fp, ap)))
                        else:
                            continue
                        break
    except Exception:
        pass


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("grab", "build"):
        sys.exit("usage: report.py grab <folder> <t1> <t2> ...  |  report.py build <folder>")
    cmd, folder = sys.argv[1], os.path.abspath(sys.argv[2])
    if cmd == "grab":
        grab(folder, [float(x) if "." in x else int(x) for x in sys.argv[3:]])
    else:
        r = build(folder)
        sys.exit(0 if r.get("ok") else 3)   # 3 = 프레임 누락/분석 실패(operator 가 발행 차단)
