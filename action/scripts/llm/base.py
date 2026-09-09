"""공통 계약. 구현체(ollama/ · fabrix/)는 chat() 과 ping() 만 채운다."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    """엔드포인트에 못 닿았거나 응답이 이상하다. 감시자는 이걸 '판정 불가'로 다룬다."""


def http_json(method: str, url: str, headers: dict[str, str], body: dict | None,
              timeout: float) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise LLMError(f"HTTP {exc.code} {url}: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise LLMError(f"연결 실패 {url}: {exc}") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError(f"JSON 이 아닌 응답 {url}: {raw[:200]}") from exc


class LLMEndpoint:
    """chat(messages) -> 모델이 낸 텍스트. ping() -> 닿으면 한 줄 설명, 못 닿으면 LLMError."""

    provider = "base"

    def __init__(self, base_url: str, model: str, timeout: float = 180.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(self, messages: list[dict], *, temperature: float = 0.0,
             max_tokens: int = 1024, json_mode: bool = False) -> str:
        raise NotImplementedError

    def ping(self) -> str:
        raise NotImplementedError

    def describe(self) -> str:
        return f"{self.provider} {self.model} @ {self.base_url}"

    def version_tag(self) -> str:
        """태그에 박히는 식별자. 어느 모델이 판정했는지가 검사기 버전만큼 중요하다.
        run_validators 의 VERSION_RE 가 읽을 수 있는 문자만 남긴다."""
        safe = re.sub(r"[^a-z0-9.\-]", "-", self.model.lower())
        return f"{self.provider}.{safe}"
