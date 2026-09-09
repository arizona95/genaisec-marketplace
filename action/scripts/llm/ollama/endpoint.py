"""Ollama 네이티브 API (/api/chat). 로컬 Ollama 와 Ollama Cloud(https://ollama.com) 가 같은 모양이다.

GitHub 호스티드 러너(CPU, 7GB)는 GLM-5.3 같은 큰 모델을 못 올린다. 그래서 공개 CI 는
Ollama Cloud 에 OLLAMA_API_KEY 로 붙는다. 키는 Authorization 헤더로만 나가고, 저장소에는
없다(GitHub secret). 로컬 Ollama 를 쓰려면 OLLAMA_BASE_URL=http://localhost:11434 에
OLLAMA_MODEL 을 받은 모델로.
"""

from __future__ import annotations

import os

from ..base import LLMEndpoint, LLMError, http_json


class OllamaEndpoint(LLMEndpoint):
    provider = "ollama"
    DEFAULT_URL = "https://ollama.com"
    DEFAULT_MODEL = "glm-5.3"

    def __init__(self, base_url: str, model: str, timeout: float = 180.0, api_key: str = ""):
        super().__init__(base_url, model, timeout)
        self.api_key = api_key

    @classmethod
    def from_env(cls) -> "OllamaEndpoint":
        return cls(os.environ.get("OLLAMA_BASE_URL") or cls.DEFAULT_URL,
                   os.environ.get("OLLAMA_MODEL") or cls.DEFAULT_MODEL,
                   float(os.environ.get("LLM_TIMEOUT") or 300),
                   os.environ.get("OLLAMA_API_KEY", ""))

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def chat(self, messages, *, temperature=0.0, max_tokens=1024, json_mode=False) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        out = http_json("POST", f"{self.base_url}/api/chat", self._headers(), body, self.timeout)
        try:
            return out["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"ollama 응답 형식이 다릅니다: {str(out)[:200]}") from exc

    def ping(self) -> str:
        out = http_json("GET", f"{self.base_url}/api/tags", self._headers(), None, min(self.timeout, 15))
        names = [m.get("name", "") for m in out.get("models", [])]
        have = self.model in names or any(n.startswith(self.model) for n in names)
        if self.api_key:
            # Cloud 의 /api/tags 는 키 없이도 200 이라 인증을 증명하지 않는다. /api/chat 만 401 을 낸다.
            self.chat([{"role": "user", "content": "ping"}], max_tokens=1)
            state = "인증 OK"
        else:
            state = "있음" if have else "없음 — ollama pull 필요"
        return f"ollama OK @ {self.base_url} · 모델 {len(names)}개 · {self.model} {state}"
