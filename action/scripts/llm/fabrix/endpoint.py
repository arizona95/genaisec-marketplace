"""삼성SDS FabriX LLM Serving API. OpenAI 호환이지만 인증은 헤더 두 개로 한다.

접근 가능 IP 를 /32 로 잠그고 사내망 경로가 있어야 닿는다 — GitHub 호스티드 러너에서는
못 부른다(.github/workflows/fabrix-probe.yml). Trial 은 10 RPM 이다. 429 는 한도 문제지
설정 문제가 아니다.
"""

from __future__ import annotations

import os

from ..base import LLMEndpoint, LLMError, http_json


class FabrixEndpoint(LLMEndpoint):
    provider = "fabrix"
    DEFAULT_URL = "https://nsds-api.fabrix-s.samsungsds.com/sds/trial/api-llm"

    def __init__(self, base_url: str, client: str, token: str, model: str = "",
                 user_email: str = "", timeout: float = 180.0):
        super().__init__(base_url, model, timeout)
        self.client = client
        self.token = token
        self.user_email = user_email

    @classmethod
    def from_env(cls) -> "FabrixEndpoint":
        client = os.environ.get("X_FABRIX_CLIENT", "")
        token = os.environ.get("X_OPENAPI_TOKEN", "")
        if not client or not token:
            raise LLMError("X_FABRIX_CLIENT / X_OPENAPI_TOKEN 이 비어 있습니다")
        return cls(os.environ.get("FABRIX_BASE_URL") or cls.DEFAULT_URL,
                   client, token,
                   os.environ.get("FABRIX_MODEL_ID", ""),
                   os.environ.get("FABRIX_USER_EMAIL", ""),
                   float(os.environ.get("LLM_TIMEOUT") or 180))

    def _headers(self) -> dict[str, str]:
        h = {"x-fabrix-client": self.client, "x-openapi-token": self.token}
        if self.user_email:
            h["x-generative-ai-user-email"] = self.user_email
        return h

    def models(self) -> list[str]:
        out = http_json("GET", f"{self.base_url}/v1/models", self._headers(), None, self.timeout)
        items = out if isinstance(out, list) else (out.get("data") or out.get("models") or [])
        return [str(m.get("modelId") or m.get("id") or "") for m in items if isinstance(m, dict)]

    def _model_id(self) -> str:
        if not self.model:
            ids = [m for m in self.models() if m]
            if not ids:
                raise LLMError("/v1/models 가 비어 있습니다 — FABRIX_MODEL_ID 를 지정하세요")
            self.model = ids[0]
        return self.model

    def chat(self, messages, *, temperature=0.0, max_tokens=1024, json_mode=False) -> str:
        headers = {**self._headers(), "x-llm-model-id": self._model_id()}
        body = {
            # FabriX 는 model 필드를 고정값으로 받고 실제 모델은 헤더로 고른다.
            "model": "/mnt/models",
            "messages": messages,
            "max_completion_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        out = http_json("POST", f"{self.base_url}/chat/completions", headers, body, self.timeout)
        try:
            return out["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"fabrix 응답 형식이 다릅니다: {str(out)[:200]}") from exc

    def ping(self) -> str:
        ids = self.models()
        return f"fabrix OK @ {self.base_url} · 모델 {len(ids)}개 · 사용: {self._model_id()}"
