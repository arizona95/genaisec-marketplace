# genaisec-marketplace

스킬·플러그인·MCP 의 **정본**. 여기 있는 것만 배포된다.

```
/plugin marketplace add https://code.sdsdev.co.kr/arizona95/genaisec-marketplace.git
```

## 구조

```
.claude-plugin/marketplace.json   정본 카탈로그
skills/                           스킬 원본
plugins/                          플러그인 원본
mcp/                              MCP 카드 (원격은 소스가 아니라 엔드포인트)
```

## 이 저장소에 들어오지 않는 것

워크스페이스에는 형제 폴더가 두 개 더 있고, **둘 다 이 저장소가 추적하지 않는다.**

| 폴더 | 무엇 | 왜 밖에 있나 |
|---|---|---|
| `../3rd/` | 서드파티 저장소 클론 (`dowhub-marketplace` 등) | 남의 코드가 정본 카탈로그에 섞이면 무엇이 우리 배포물인지 흐려진다 |
| `../probe-server/` | 프로브 픽스처용 MCP 테스트 서버 | 배포물이 아니라 검사 도구다. CI 가 이걸 훑을 이유가 없다 |

프로브 픽스처(`probe_*`)도 카탈로그에 등록하지 않는다 — 등록하면 `/plugin marketplace add`
로 누구나 설치할 수 있게 되고, 악성 픽스처가 그 경로로 나가면 그것 자체가 사고다.
