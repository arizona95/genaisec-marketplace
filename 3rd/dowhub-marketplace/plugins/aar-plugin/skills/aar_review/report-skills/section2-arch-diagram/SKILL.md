# HTML Architecture Diagram Function Skill

> **목적**: 검토 대상 SaaS 의 **서비스 구성도 / 동작방식 흐름도** 를 HTML 로 작성하고 Chrome MCP 로 캡처하여 docx 에 삽입한다.
> **산출물**: 캡처 PNG 이미지 (구성도 1~2장) + `Review/Function/htmlArchitectureDiagram_<YYYYMMDD>.docx` (1~2 페이지, 사용한 HTML 원본 + 캡처 결과)
> **사용처**: SaaS 보안검토 본 보고서의 **2. 서비스 구성** + **[별첨7] □ 서비스 개요** 작성 시 호출.

---

## 0. 트리거

- "서비스 구성도 그려줘" / "Architecture diagram" / "[본문 2. 서비스 구성] 작성"

---

## 1. 사전 준비

| 확인 사항 | 방법 |
|---|---|
| 검토 대상 SaaS 의 동작 흐름 파악 | 공식 문서 + 트래픽 캡처 (`apiEndpointCatalog` 결과) |
| 표시할 구성요소 5~10개 식별 | 사용자 PC / Proxy / IdP / SIEM / SaaS Server / 모델 / 외부 도구 등 |

---

## 2. 절차

### Phase A — HTML 작성
1. 단일 HTML 파일 (인라인 CSS) 생성 — 위치: `outputs/diagrams/<saas>_arch.html`
2. 권장 라이브러리: 순수 HTML+CSS+SVG (외부 의존 X). 박스·화살표·라벨로 구성.
3. 화살표 위에 통신 내용 (로그인 / 추론 요청·응답 / 로그 송신 등) 짧게 라벨링.
4. 두 종류를 만든다:
   - **본문 2장용**: 전체 관점 (사용자 PC ↔ Proxy/IdP/SIEM ↔ SaaS Server ↔ 모델)
   - **별첨7 □ 서비스 개요용**: 설치/통신 흐름 관점 (포트·도메인·예외 도메인 표시)

### Phase B — Chrome MCP 캡처
5. `tabs_create_mcp(url: "file:///.../diagrams/<saas>_arch.html")` 또는 임시 서버 URL
6. `resize_window(1200, 700, tabId)` (구성도 가로폭 일정하게)
7. `computer(action: "screenshot", tabId, save_to_disk: true)` → PNG 저장
8. (필요 시) 확대가 필요하면 **HTML 쪽 크기를 키워** 다시 찍는다 — 캡처 후 잘라 키우면 흐려진다.

### Phase C — docx 삽입
9. 캡처 PNG 를 본 보고서 / 별첨7 의 이미지 자리표시자 위치에 삽입
10. HTML 원본은 `Review/Function/htmlArchitectureDiagram_<YYYYMMDD>.docx` 에 코드블록으로 보관 (수정 가능하도록)

---

## 3. HTML 작성 표준

```html
<!doctype html><html><head><meta charset="utf-8"><style>
  body { font-family: 'Malgun Gothic', sans-serif; padding: 24px; background: #fff; }
  .box { display:inline-block; padding: 8px 14px; border:1.5px solid #444; border-radius: 8px; background:#f4f7fa; }
  .arrow { position: relative; }
  /* 화살표/연결선은 SVG 또는 div+CSS */
</style></head><body>
  <svg viewBox="0 0 1100 600" width="1100" height="600">
    <!-- 박스 -->
    <rect x="40" y="80" width="160" height="60" fill="#f4f7fa" stroke="#444" stroke-width="1.5" rx="8"/>
    <text x="120" y="115" text-anchor="middle">사용자 PC</text>
    <!-- 화살표 -->
    <line x1="200" y1="110" x2="380" y2="110" stroke="#666" stroke-width="1.5" marker-end="url(#arr)"/>
    <text x="290" y="100" text-anchor="middle" font-size="12">HTTPS 추론</text>
    <defs><marker id="arr" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">
      <path d="M0,0 L0,6 L9,3 z" fill="#666"/></marker></defs>
    <!-- 추가 박스/연결 -->
  </svg>
</body></html>
```

권장 색상 / 굵기:
- 박스 테두리: `#444`, 1.5px
- 박스 배경: `#f4f7fa`
- 화살표: `#666`, 1.5px
- 라벨: 기본 검정 12px

---

## 4. 캡처 파일명 규칙

`diagram_<용도>_<순번>.png`
- 용도: `overview` (본문 2장) / `flow` (별첨7 □ 서비스 개요)

---

## 5. 결과 판정

본 Function 자체는 결과 코드가 없다. 본문 2장 / 별첨7 그림이 들어가면 됨.

---

## 6. 자주 만나는 이슈

| 증상 | 대처 |
|---|---|
| 캡처 잘릴 때 | `resize_window` 로 가로 1200~1400px 고정 후 스크롤 X 위치에서 캡처 |
| 한글 폰트 깨짐 | `Malgun Gothic` / `Noto Sans KR` 명시 |
| 박스 배치가 어색 | SVG `viewBox` 와 `text-anchor`, `dominant-baseline` 활용 |
| 너무 많은 요소 | 본문 2장 = 핵심 5~7 박스, 별첨7 = 7~10 박스로 분리 |

---

## 7. 사용 예

```text
[대상] Claude Cowork 본문 2장 구성도
[요소 7개] 사용자 PC / Cowork VM(Hyper-V) / 사내 Proxy / IdP / SIEM / Claude Server / 모델
[화살표] 로그인 / 추론 / Audit 송신
[캡처] outputs/diagrams/claude_cowork_arch.html → 1200x700 → PNG
[결과] 본문 2장에 PNG 1장 삽입
```
