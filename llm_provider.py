from __future__ import annotations

import os
from typing import Any

import requests


PROVIDER_PRESETS = {
    "local": {
        "base_url": "",
        "model": "local-fallback",
        "api_key_env": "",
        "model_env": "",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_env": "OPENAI_API_KEY",
        "model_env": "TRIPSTORY_OPENAI_MODEL",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
        "api_key_env": "GEMINI_API_KEY",
        "model_env": "TRIPSTORY_GEMINI_MODEL",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_env": "TRIPSTORY_DEEPSEEK_MODEL",
    },
}


class LLMProvider:
    """Vendor-neutral chat client.

    Uses provider presets or any OpenAI-compatible chat completions endpoint
    when configured. Falls back to deterministic local text when no endpoint is
    available.
    """

    def __init__(
        self,
        provider: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ) -> None:
        raw_provider = provider or os.environ.get("TRIPSTORY_LLM_PROVIDER")
        if not raw_provider:
            raw_provider = "custom" if os.environ.get("TRIPSTORY_LLM_URL") else "local"
        self.provider = raw_provider.strip().lower()
        if self.provider == "openai-compatible":
            self.provider = "custom"

        preset = PROVIDER_PRESETS.get(self.provider, {})
        provider_api_key_env = preset.get("api_key_env") or ""
        provider_model_env = preset.get("model_env") or ""

        self.base_url = (
            base_url
            or os.environ.get("TRIPSTORY_LLM_URL")
            or preset.get("base_url")
            or ""
        ).rstrip("/")
        self.api_key = (
            api_key
            or (os.environ.get(provider_api_key_env) if provider_api_key_env else None)
            or os.environ.get("TRIPSTORY_LLM_API_KEY")
        )
        self.model = (
            model
            or (os.environ.get(provider_model_env) if provider_model_env else None)
            or os.environ.get("TRIPSTORY_LLM_MODEL")
            or preset.get("model")
            or "local-fallback"
        )
        self.timeout = timeout or int(os.environ.get("TRIPSTORY_LLM_TIMEOUT", "45"))

    @property
    def configured(self) -> bool:
        if not self.base_url or self.provider == "local":
            return False
        if self.provider in PROVIDER_PRESETS:
            return bool(self.api_key)
        return True

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
