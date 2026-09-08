#!/usr/bin/env python3
"""세션 폴더의 리포트들을 operator 와 같은 '카드형 리스트' 로 묶은 자기완결 HTML 을 만든다.
   → <session>/보고서목록.html. 전체 다운로드(세션 zip)에 함께 들어가 오프라인에서 카드로 보고
   각 report.html 을 상대링크로 연다.
   usage: python session_index.py <session_dir>   ·   또는 build_session_index(session_dir) import.
"""
import os, sys, json, html

# operator index.html 의 repGroup 과 동일 그룹핑(순서·라벨 일치).
_G_ALL       = (1, "S1 · 환경 무관 — 제품/조직 동작(설정·프로세스·서명·거버넌스)")
_G_EXP_OPEN  = (2, "S1 · exp-open — 직접 허용(프록시 통과·통제)")
_G_EXP_CLOSE = (3, "S1 · exp-close — 프록시 강제")
_G_INLINE    = (4, "S1 · inline — 투명 가로채기")
_G_LLM       = (5, "S1 · llm — 게이트웨이")

def _group(n, env=""):
    if n.startswith("S0-"):           return (0, "S0 · 공개정보 웹 리서치 — 인증·데이터정책·설치·통제 메커니즘")
    # 과거 통합 시나리오(S1-mon-*/S1-gov-*/S1-org-*)는 환경 슬롯이 없어 실행 env 로 섹션을 갈랐다.
    # 이제 전부 환경 무관 슬롯인 S1-ALL-NN 으로 표준화됐으므로(2026-08), 아래 S1-ALL- 분기로 처리된다.
    if n.startswith("S1-ALL-"):       return _G_ALL
    if n.startswith("S1-exp-open-"):  return _G_EXP_OPEN
    if n.startswith("S1-exp-close-"): return _G_EXP_CLOSE
    if n.startswith("S1-inline-"):    return _G_INLINE
    if n.startswith("S1-llm-"):       return _G_LLM
    if n.startswith("S2"):            return (6, "S2 · 환경 비교")
    if n.startswith("S3"):            return (7, "S3 · 종합 — 도입 판정")  # S3-1 = 종합(s3-1 스킬: docx+요약html)
    # 특수(한시) 리포트 — registry 시나리오가 아니라 서피스별로 자유 ID 를 쓰는 조사
    # (예: MCP-mon 아티팩트×채널 매트릭스). 서피스 비교가 목적이라 한 섹션에 모은다.
    if n.startswith("S1-"):           return (8, "S1 · 특수 조사 (서피스별 · 한시)")
    return (9, "기타")

def _esc(s): return html.escape(str(s or ""))

def _fmt_size(b):
    b = int(b or 0)
    return f"{b//1024} KB" if b < 1048576 else f"{b/1048576:.1f} MB"

def _report_meta(rdir):
    """report.json 의 title/summary + 썸네일/영상/archive.zip 크기."""
    title = summary = env = ""
    try:
        j = json.load(open(os.path.join(rdir, "report.json"), encoding="utf-8"))
        title, summary, env = j.get("title", ""), j.get("summary", ""), j.get("env", "")
    except Exception:
        pass
    thumb = video = ""
    imgd = os.path.join(rdir, "img")
    if os.path.isdir(imgd):
        for fn in sorted(os.listdir(imgd)):
            low = fn.lower()
            if not thumb and not fn.startswith("_") and (low.endswith(".jpg") or low.endswith(".png")):
                thumb = "img/" + fn
            if not video and low.endswith(".mp4"):
                video = "img/" + fn
    zsz = 0
    zp = os.path.join(rdir, "archive.zip")
    if os.path.isfile(zp):
        zsz = os.path.getsize(zp)
    return title, summary, thumb, video, zsz, env

CSS = """
*{box-sizing:border-box}body{margin:0;background:#0b0f1a;color:#e6edf7;font-family:system-ui,'Segoe UI',sans-serif;padding:22px 26px}
h1{font-size:18px;margin:0 0 4px}.sub{color:#8b97ad;font-size:12.5px;margin-bottom:20px}
.rghead{font-size:13px;font-weight:700;color:#cdd9ee;border-bottom:1px solid #1e2942;padding-bottom:7px;margin:22px 0 12px;display:flex;align-items:center;gap:8px}
.rghead small{color:#8b97ad;font-weight:500}
.rgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}
.rcard{background:#111827;border:1px solid #1e2942;border-radius:11px;overflow:hidden}
.rcard:hover{border-color:#3b82f6}
.rthumb{height:124px;background:#0b0f1a center/cover no-repeat;border-bottom:1px solid #1e2942;display:block}
.rnoshot{height:124px;display:flex;align-items:center;justify-content:center;color:#8b97ad;font-size:11px;border-bottom:1px solid #1e2942}
.rbody{padding:10px 12px}
.rtitle{font-size:12.5px;font-weight:700;color:#e6edf7;line-height:1.38;margin-bottom:5px;text-decoration:none;display:block}
.rsum{font-size:11.5px;color:#8b97ad;line-height:1.55;margin-bottom:8px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.ractions{display:flex;align-items:center;gap:12px;font-size:12px}
.ractions a{color:#60a5fa;text-decoration:none;font-weight:600}
.ractions a.dlbtn{color:#fbbf24}.ractions a.vbtn{color:#34d399}
"""

def build_session_index(session_dir):
    session_dir = os.path.abspath(session_dir)
    session = os.path.basename(session_dir.rstrip("/"))
    reps = []
    for name in sorted(os.listdir(session_dir)):
        rdir = os.path.join(session_dir, name)
        if not os.path.isdir(rdir) or name.startswith("."):   # 점 폴더 = 빌드 스테이징(R10) — 목록에 안 낸다
            continue
        if not (os.path.isfile(os.path.join(rdir, "report.html")) or os.path.isfile(os.path.join(rdir, "report.json"))):
            continue
        title, summary, thumb, video, zsz, env = _report_meta(rdir)
        reps.append((name, title or name, summary, thumb, video, zsz, env))
    # 그룹핑 — 통합 시나리오(mon/gov/org)는 실행 env(r[6])로 환경 섹션에 합친다.
    groups = {}
    for r in reps:
        k, label = _group(r[0], r[6])
        groups.setdefault(k, [label, []])[1].append(r)
    sects = []
    for k in sorted(groups):
        label, items = groups[k]
        cards = []
        for name, title, summary, thumb, video, zsz, env in items:
            b = _esc(name)
            shot = (f'<a class="rthumb" style="background-image:url(\'{b}/{_esc(thumb)}\')" href="{b}/report.html"></a>'
                    if thumb else f'<a class="rnoshot" href="{b}/report.html">캡처 없음</a>')
            vid = f'<a class="vbtn" href="{b}/{_esc(video)}">▶ 영상</a>' if video else ""
            dl = (f'<a class="dlbtn" href="{b}/archive.zip" download="{_esc(session)}-{b}.zip">⬇ {_fmt_size(zsz)}</a>'
                  if zsz else "")
            sm = f'<div class="rsum">{_esc(summary)}</div>' if summary else ""
            cards.append(f'<div class="rcard">{shot}<div class="rbody">'
                         f'<a class="rtitle" href="{b}/report.html">{_esc(title)}</a>{sm}'
                         f'<div class="ractions">{dl}<a href="{b}/report.html">새 탭↗</a>{vid}</div></div></div>')
        sects.append(f'<div class="rghead">{_esc(label)}<small>{len(items)}개</small></div>'
                     f'<div class="rgrid">{"".join(cards)}</div>')
    body = "".join(sects) or '<div class="sub">리포트가 없습니다.</div>'
    doc = (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
           f'<meta name="viewport" content="width=device-width,initial-scale=1">'
           f'<title>{_esc(session)} — 보고서 목록</title><style>{CSS}</style></head><body>'
           f'<h1>📁 {_esc(session)} — 보고서 목록</h1>'
           f'<div class="sub">이 세션의 리포트 {len(reps)}개. 카드를 클릭하면 각 보고서(report.html)가 열립니다.</div>'
           f'{body}</body></html>')
    # 파일명은 ASCII(index.html) — zip 에 한글 파일명을 넣으면 Go zip writer 가 UTF-8 플래그를
    # 안 켜 mojibake 로 풀린다. 내용/제목은 한글 그대로. index.html = 압축 풀고 "먼저 열기" 진입점.
    out = os.path.join(session_dir, "index.html")
    open(out, "w", encoding="utf-8").write(doc)
    return out

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: session_index.py <session_dir>")
    print("✓", build_session_index(sys.argv[1]))
