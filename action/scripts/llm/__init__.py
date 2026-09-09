"""LLM 엔드포인트 패키지 — 감시자(llm_scan.py)가 모델을 부르는 유일한 통로.

    llm/
      base.py      공통 계약(LLMEndpoint) · HTTP 조각 · LLMError
      ollama/      Ollama 객체 — 로컬 Ollama 와 Ollama Cloud(https://ollama.com) 둘 다
      fabrix/      FabriX 객체 — 사내 self-hosted 러너·개발자 PC 전용

왜 둘로 나눴나: 사내 FabriX 는 접근 IP 를 /32 로 잠그고 사내망 경로가 있어야 닿는다.
GitHub 호스티드 러너는 egress IP 가 매번 바뀌고 사내망 밖이라 FabriX 를 못 부른다
(.github/workflows/fabrix-probe.yml 이 그걸 확인한 워크플로다). 그래서 공개 CI 는
ollama 객체로 Ollama Cloud 의 glm-5.3 을 부르고, 사내에서는 fabrix 객체를 쓴다.
감시자는 어느 쪽인지 모른다 — `from_env()` 가 LLM_PROVIDER 를 보고 골라 준다.

표준 라이브러리만 쓴다. 검사자가 서드파티를 끌어오면 검사자 자체가 공급망이 된다.

    LLM_PROVIDER=ollama   OLLAMA_API_KEY  OLLAMA_BASE_URL(기본 https://ollama.com)  OLLAMA_MODEL(기본 glm-5.3)
    LLM_PROVIDER=fabrix   FABRIX_BASE_URL  X_FABRIX_CLIENT  X_OPENAPI_TOKEN  FABRIX_MODEL_ID  FABRIX_USER_EMAIL
"""

from __future__ import annotations

import os

from .base import LLMEndpoint, LLMError
from .fabrix import FabrixEndpoint
from .ollama import OllamaEndpoint

PROVIDERS = ("ollama", "fabrix")

__all__ = ["LLMEndpoint", "LLMError", "OllamaEndpoint", "FabrixEndpoint", "PROVIDERS", "from_env"]


def from_env(provider: str | None = None) -> LLMEndpoint:
    """LLM_PROVIDER 로 고른다. 안 정하면 ollama — 공개 CI 에서 유일하게 닿는 쪽이다."""
    p = (provider or os.environ.get("LLM_PROVIDER") or "ollama").strip().lower()
    if p == "ollama":
        return OllamaEndpoint.from_env()
    if p == "fabrix":
        return FabrixEndpoint.from_env()
    raise LLMError(f"모르는 LLM_PROVIDER: {p} (가능: {', '.join(PROVIDERS)})")
