---
name: remote-plugin-dowoo-skill
description: >-
  무해한 원격 플러그인 스킬. 사용자가 "remote-plugin-dowoo 실행" 또는 "원격 플러그인 도우"를 요청하면
  이 스킬을 사용한다. 고정 식별 마커를 출력하고 label을 대문자로 변환하는 사소한 텍스트 변환만 한다.
  원격 git 마켓플레이스에서 설치된 플러그인 소속 스킬임을 식별하기 위한 것으로, 민감정보·비밀과 무관하다.
---

# remote-plugin-dowoo-skill

무해한 진단용 스킬(원격 플러그인 `remote-plugin-dowoo` 소속). 실제 데이터·비밀을 만들지 않는다.
목적은 "원격 git 마켓플레이스에서 설치된 플러그인의 스킬이 호출됐다"는 사실이 관측 가능한지 식별 마커로 남기는 것.

## 사용 시점
- "remote-plugin-dowoo 실행"
- "원격 플러그인 도우 실행 label=<라벨>"

## 동작 (부작용 없이)
1. 다음 마커를 한 줄로 정확히 출력한다:

   `REMOTE-PLUGIN-DOWOO-OK :: label=<LABEL> :: upper=<LABEL_UPPERCASED>`

   `<LABEL>`=사용자가 준 label(없으면 `demo`), `<LABEL_UPPERCASED>`=대문자.
2. 이 출력이 무해한 **원격 플러그인** `remote-plugin-dowoo`의 스킬에 의해 생성됐음을 한 문장으로 밝힌다.
3. 외부 네트워크 호출·비밀 생성은 하지 않는다.
