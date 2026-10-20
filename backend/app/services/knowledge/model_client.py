"""Explicitly budgeted DeepSeek calls; no automatic paid retries."""
from __future__ import annotations

import asyncio
import json
import httpx

from app.core.prompts import guard_system_prompt, guard_user_content
from app.services.knowledge.budget import BudgetLedger, TokenRates


class DeepSeekClient:
    def __init__(self, *, api_key: str, model: str, rates: TokenRates,
                 ledger: BudgetLedger, timeout: float = 20,
                 base_url: str = "https://api.deepseek.com",
                 transport: httpx.AsyncBaseTransport | None = None):
        if not api_key or not model or timeout <= 0:
            raise ValueError("API key, model and positive timeout are required")
        from urllib.parse import urlsplit

        endpoint = urlsplit(base_url)
        if (endpoint.scheme not in {"http", "https"} or not endpoint.hostname or
                endpoint.username or endpoint.password or endpoint.query or endpoint.fragment):
            raise ValueError("API base URL must be an origin or API path without credentials")
        if endpoint.scheme == "http" and endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("unencrypted API access is only allowed on loopback")
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model = model
        self.rates = rates
        self.ledger = ledger
        self.timeout = timeout
        self.transport = transport

    async def generate_json(self, *, system: str, data: dict, max_output_tokens: int = 600) -> dict:
        if isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or not 1 <= max_output_tokens <= 2048:
            raise ValueError("output bound must be between 1 and 2048 tokens")
        messages = [
            {"role": "system", "content": guard_system_prompt(system + "\n仅返回 JSON 对象。")},
            {"role": "user", "content": guard_user_content(json.dumps(data, ensure_ascii=False))},
        ]
        # UTF-8 bytes + conservative protocol overhead form an upper input bound.
        input_bound = len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) + 2048
        if input_bound > 32000:
            raise ValueError("input exceeds the configured evidence budget")
        reservation = await asyncio.to_thread(self.ledger.reserve, self.model, input_bound,
                                              max_output_tokens, self.rates)
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self.model, "messages": messages,
                      "thinking": {"type": "disabled"}, "response_format": {"type": "json_object"},
                      "max_tokens": max_output_tokens, "stream": False},
            )
            # Do not expose response bodies or headers on provider errors.
            if response.status_code != 200:
                raise RuntimeError(f"model provider returned HTTP {response.status_code}; reservation retained")
            payload = response.json()
        usage = payload.get("usage", {})
        if "prompt_tokens" not in usage or "completion_tokens" not in usage:
            raise RuntimeError("provider omitted token usage; reservation retained")
        await asyncio.to_thread(self.ledger.settle, reservation, usage["prompt_tokens"],
                                usage["completion_tokens"], self.rates)
        try:
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("provider did not return a JSON object") from exc
        if not isinstance(parsed, dict):
            raise ValueError("provider did not return a JSON object")
        return parsed


class OllamaEmbeddingClient:
    def __init__(self, *, base_url: str, model: str, dimension: int,
                 timeout: float = 10, transport: httpx.AsyncBaseTransport | None = None):
        if not 1 <= dimension <= 16000 or not model:
            raise ValueError("embedding model and valid dimension are required")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.dimension = dimension
        self.timeout = timeout
        self.transport = transport

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import math

        if not texts or len(texts) > 32 or any(not isinstance(t, str) or not t.strip() or len(t) > 16000 for t in texts):
            raise ValueError("embedding requires 1–32 bounded nonempty texts")
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            response = await client.post(f"{self.base_url}/api/embed", json={
                "model": self.model, "input": texts, "truncate": False,
            })
            if response.status_code != 200:
                raise RuntimeError(f"embedding provider returned HTTP {response.status_code}")
            vectors = response.json().get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise ValueError("embedding provider returned mismatched rows")
        result = []
        for vector in vectors:
            if not isinstance(vector, list) or len(vector) != self.dimension or any(
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
                for value in vector
            ):
                raise ValueError("embedding vector has invalid dimension or values")
            norm = math.sqrt(sum(value * value for value in vector))
            if norm == 0:
                raise ValueError("embedding provider returned a zero vector")
            result.append([value / norm for value in vector])
        return result
