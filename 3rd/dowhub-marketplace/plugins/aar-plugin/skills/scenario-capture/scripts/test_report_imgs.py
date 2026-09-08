#!/usr/bin/env python3
"""report.py 캡처 참조 해소 + 집계 회귀 테스트 (self-contained · 외부 의존 없음).

왜 있나: investigation 스텝의 `file` 이 **확장자 없는 label** 로 오는데 렌더러가 정확 일치만
찾아, 실제로 존재하는 캡처를 "⚠️ 캡처 없음" 으로 100여 건 렌더한 사고(2026-08)가 있었다.
또 빌드 로그의 frames/MISSING 수치가 investigation 을 빼고 세어 실제와 어긋났다.
이 테스트가 그 두 가지를 고정한다.

실행: python3 test_report_imgs.py   (성공 시 'ALL PASS', 실패 시 non-zero exit)
"""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "report.py")
# 1x1 JPEG (최소 유효 파일) — 실제 이미지 내용은 테스트 대상이 아니다.
JPEG_1PX = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300ffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffc2000b080001000101011100ffc40014000100000000"
    "00000000000000000000000009ffda0008010100013f10")

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def build(folder):
    r = subprocess.run([sys.executable, REPORT, "build", folder],
                       capture_output=True, text=True)
    return r.stdout + r.stderr


def make_case(tmp, files, steps):
    """files: {파일명: bytes} · steps: [{kind,file,caption}] → 빌드 후 (log, html) 반환."""
    os.makedirs(os.path.join(tmp, "img"), exist_ok=True)
    for fn in files:
        with open(os.path.join(tmp, "img", fn), "wb") as f:
            f.write(JPEG_1PX)
    spec = {"title": "t", "summary": "s", "env": "e",
            "investigation": {"steps": steps}}
    with open(os.path.join(tmp, "report.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False)
    log = build(tmp)
    with open(os.path.join(tmp, "report.html"), encoding="utf-8") as f:
        return log, f.read()


def n_img(html):
    return len(re.findall(r"<img", html))


def embedded(log):
    m = re.search(r"\((\d+) frames embedded", log)
    return int(m.group(1)) if m else None


def missing(log):
    m = re.search(r"(\d+) MISSING", log)
    return int(m.group(1)) if m else 0


def main():
    print("report.py 캡처 해소·집계 회귀 테스트")

    # ① 확장자 없는 label → .jpg 해소
    with tempfile.TemporaryDirectory() as t:
        log, html = make_case(t, {"cap-a.jpg": 1},
                              [{"kind": "doc", "file": "cap-a", "caption": "c"}])
        check("① label(확장자 없음) → .jpg 해소", n_img(html) == 1 and "캡처 없음" not in html,
              f"img={n_img(html)}")

    # ② .jpeg
    with tempfile.TemporaryDirectory() as t:
        log, html = make_case(t, {"cap-b.jpeg": 1},
                              [{"kind": "test", "file": "cap-b", "caption": "c"}])
        check("② label → .jpeg 해소", n_img(html) == 1 and "캡처 없음" not in html)

    # ③ .png
    with tempfile.TemporaryDirectory() as t:
        log, html = make_case(t, {"cap-c.png": 1},
                              [{"kind": "test", "file": "cap-c", "caption": "c"}])
        check("③ label → .png 해소", n_img(html) == 1 and "캡처 없음" not in html)

    # ④ 명시적 .jpg 도 그대로 동작(하위호환)
    with tempfile.TemporaryDirectory() as t:
        log, html = make_case(t, {"cap-d.jpg": 1},
                              [{"kind": "doc", "file": "cap-d.jpg", "caption": "c"}])
        check("④ 명시적 .jpg 유지", n_img(html) == 1 and "캡처 없음" not in html)

    # ⑤ 진짜 없는 참조 → 빨간 경고(침묵 금지)
    with tempfile.TemporaryDirectory() as t:
        log, html = make_case(t, {}, [{"kind": "doc", "file": "nope", "caption": "c"}])
        check("⑤ 진짜 부재 → 경고 렌더", "캡처 없음" in html and n_img(html) == 0)

    # ⑥ 집계 = 실제와 일치 (investigation 포함, embedded 는 누락 제외)
    with tempfile.TemporaryDirectory() as t:
        log, html = make_case(t, {"e1.jpg": 1, "e2.jpg": 1},
                              [{"kind": "doc", "file": "e1", "caption": "c"},
                               {"kind": "test", "file": "e2", "caption": "c"},
                               {"kind": "doc", "file": "ghost", "caption": "c"}])
        check("⑥ embedded 수 = 실제 <img> 수", embedded(log) == n_img(html) == 2,
              f"log={embedded(log)} html={n_img(html)}")
        check("⑦ MISSING 수 = 부재 참조 수", missing(log) == 1, f"log MISSING={missing(log)}")

    print(("ALL PASS" if not FAILS else f"{len(FAILS)} FAILED: {FAILS}"))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
