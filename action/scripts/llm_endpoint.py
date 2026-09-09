#!/usr/bin/env python3
"""LLM 엔드포인트 — 감시자(llm_scan.py)가 모델을 부르는 유일한 통로.

왜 둘로 나눴나: 사내 FabriX 는 접근 IP 를 /32 로 잠그고 사내망 경로가 있어야 닿는다.
GitHub 호스티드 러너는 egress IP 가 매번 바뀌고 사내망 밖이라 FabriX 를 못 부른다
(.github/workflows/fabrix-probe.yml 이 그걸 확인하는 워크플로다). 그래서 공개 저장소
CI 에서는 Ollama 를 쓰고, 사내 self-hosted 러너나 개발자 PC 에서는 FabriX 를 쓴다.
감시자는 어느 쪽인지 모른다 — `from_env()` 가 골라 준다.

표준 라이브러리만 쓴다. 검사자가 서드파티를 끌어오면 검사자 자체가 공급망이 된다.

    LLM_PROVIDER=ollama   OLLAMA_BASE_URL  OLLAMA_MODEL
    LLM_PROVIDER=fabrix   FABRIX_BASE_URL  X_FABRIX_CLIENT  X_OPENAPI_TOKEN
                          FABRIX_MODEL_ID(비우면 /v1/models 의 첫 모델)  FABRIX_USER_EMAIL

    python action/scripts/llm_endpoint.py --ping          # 닿는지만
    python action/scripts/llm_endpoint.py --say "안녕"    # 실제 호출
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

PROVIDERS = ("ollama", "fabrix")


class LLMError(RuntimeError):
    """엔드포인트에 못 닿았거나 응답이 이상하다. 감시자는 이걸 '판정 불가'로 다룬다."""


def _http(method: str, url: str, headers: dict[str, str], body: dict | None,
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
    """공통 계약. chat(messages) -> 모델이 낸 텍스트."""

    provider = "base"

    def __init__(self, base_url: str, model: str, timeout: float = 180.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    # -- 구현체가 채우는 것 --------------------------------------------------
    def chat(self, messages: list[dict], *, temperature: float = 0.0,
             max_tokens: int = 1024, json_mode: bool = False) -> str:
        raise NotImplementedError

    def ping(self) -> str:
        """닿으면 한 줄 설명을 돌려주고, 못 닿으면 LLMError."""
        raise NotImplementedError

    # -- 공통 --------------------------------------------------------------
    def describe(self) -> str:
        return f"{self.provider} {self.model} @ {self.base_url}"

    def version_tag(self) -> str:
        """태그에 박히는 식별자. 어느 모델이 판정했는지가 검사기 버전만큼 중요하다.
        run_validators 의 VERSION_RE 가 읽을 수 있는 문자만 남긴다."""
        safe = re.sub(r"[^a-z0-9.\-]", "-", self.model.lower())
        return f"{self.provider}.{safe}"


class OllamaEndpoint(LLMEndpoint):
    """Ollama 네이티브 API (/api/chat). 공개 CI 와 로컬 개발의 기본값."""

    provider = "ollama"
    DEFAULT_URL = "http://localhost:11434"
    DEFAULT_MODEL = "qwen2.5:3b"

    @classmethod
    def from_env(cls) -> "OllamaEndpoint":
        return cls(os.environ.get("OLLAMA_BASE_URL") or cls.DEFAULT_URL,
                   os.environ.get("OLLAMA_MODEL") or cls.DEFAULT_MODEL,
                   float(os.environ.get("LLM_TIMEOUT") or 300))

    def chat(self, messages, *, temperature=0.0, max_tokens=1024, json_mode=False) -> str:
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        if json_mode:
            body["format"] = "json"
        out = _http("POST", f"{self.base_url}/api/chat", {}, body, self.timeout)
        try:
            return out["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError(f"ollama 응답 형식이 다릅니다: {str(out)[:200]}") from exc

    def ping(self) -> str:
        out = _http("GET", f"{self.base_url}/api/tags", {}, None, min(self.timeout, 15))
        names = [m.get("name", "") for m in out.get("models", [])]
        have = self.model in names or any(n.startswith(self.model) for n in names)
        state = "있음" if have else "없음 — ollama pull 필요"
        return f"ollama OK @ {self.base_url} · 모델 {len(names)}개 · {self.model} {state}"


class FabrixEndpoint(LLMEndpoint):
    """삼성SDS FabriX LLM Serving API. OpenAI 호환이지만 인증은 헤더 두 개로 한다.

    Trial 은 10 RPM 이다. 429 는 한도 문제지 설정 문제가 아니다.
    """

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
        out = _http("GET", f"{self.base_url}/v1/models", self._headers(), None, self.timeout)
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
        out = _http("POST", f"{self.base_url}/chat/completions", headers, body, self.timeout)
        try:
            return out["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"fabrix 응답 형식이 다릅니다: {str(out)[:200]}") from exc

    def ping(self) -> str:
        ids = self.models()
        return f"fabrix OK @ {self.base_url} · 모델 {len(ids)}개 · 사용: {self._model_id()}"


def from_env(provider: str | None = None) -> LLMEndpoint:
    """LLM_PROVIDER 로 고른다. 안 정하면 ollama — 공개 CI 에서 유일하게 닿는 쪽이다."""
    p = (provider or os.environ.get("LLM_PROVIDER") or "ollama").strip().lower()
    if p == "ollama":
        return OllamaEndpoint.from_env()
    if p == "fabrix":
        return FabrixEndpoint.from_env()
    raise LLMError(f"모르는 LLM_PROVIDER: {p} (가능: {', '.join(PROVIDERS)})")


def main() -> int:
    ap = argparse.ArgumentParser(prog="llm_endpoint")
    ap.add_argument("--provider", choices=PROVIDERS, default=None)
    ap.add_argument("--ping", action="store_true")
    ap.add_argument("--say", default="", help="이 문장을 보내고 답을 찍는다")
    args = ap.parse_args()
    try:
        ep = from_env(args.provider)
        print(ep.describe())
        if args.ping or not args.say:
            print(ep.ping())
        if args.say:
            print(ep.chat([{"role": "user", "content": args.say}], max_tokens=200))
    except LLMError as exc:
        print(f"실패: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
