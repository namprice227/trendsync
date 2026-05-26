from __future__ import annotations

import os
from typing import Any

import requests


class LLMProvider:
    """Vendor-neutral chat client.

    Uses any OpenAI-compatible chat completions endpoint when configured.
    Falls back to deterministic local text when no endpoint is available.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("TRIPSTORY_LLM_URL") or "").rstrip("/")
        self.api_key = api_key or os.environ.get("TRIPSTORY_LLM_API_KEY")
        self.model = model or os.environ.get("TRIPSTORY_LLM_MODEL") or "local-fallback"
        self.timeout = timeout or int(os.environ.get("TRIPSTORY_LLM_TIMEOUT", "45"))

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 900) -> str | None:
        if not self.configured:
            return None

        endpoint = self.base_url
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        response = requests.post(endpoint, json=payload, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
