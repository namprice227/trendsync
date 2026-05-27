from __future__ import annotations

import os
import random
import threading
import time
from typing import Any

import requests

from tripstory_logging import api_payload_logging_enabled, approximate_tokens, get_logger, log_event, redacted_snippet


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
        "model": "deepseek-v4-pro",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_env": "TRIPSTORY_DEEPSEEK_MODEL",
    },
}

_chat_lock = threading.Lock()
_last_request_at = 0.0
logger = get_logger("llm")


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
            if os.environ.get("TRIPSTORY_LLM_URL"):
                raw_provider = "custom"
            elif os.environ.get("DEEPSEEK_API_KEY"):
                raw_provider = "deepseek"
            elif os.environ.get("GEMINI_API_KEY"):
                raw_provider = "gemini"
            elif os.environ.get("OPENAI_API_KEY"):
                raw_provider = "openai"
            else:
                raw_provider = "local"
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
        self.min_interval = float(os.environ.get("TRIPSTORY_LLM_MIN_INTERVAL_SECONDS", "3"))
        self.max_retries = int(os.environ.get("TRIPSTORY_LLM_MAX_RETRIES", "2"))
        self.reasoning_effort = (
            os.environ.get(f"TRIPSTORY_{self.provider.upper()}_REASONING_EFFORT")
            or os.environ.get("TRIPSTORY_LLM_REASONING_EFFORT")
            or ""
        ).strip()
        self.thinking_type = (
            os.environ.get(f"TRIPSTORY_{self.provider.upper()}_THINKING")
            or os.environ.get("TRIPSTORY_LLM_THINKING")
            or ""
        ).strip().lower()

    @property
    def configured(self) -> bool:
        if not self.base_url or self.provider == "local":
            return False
        if self.provider in PROVIDER_PRESETS:
            return bool(self.api_key)
        return True

    def chat(self, messages: list[dict[str, str]], max_tokens: int = 900) -> str | None:
        if not self.configured:
            log_event(
                logger,
                20,
                "llm_unconfigured",
                provider=self.provider,
                model=self.model,
                outcome="fallback",
            )
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
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.provider == "deepseek" and self.thinking_type:
            payload["thinking"] = {"type": self.thinking_type}
        input_chars = sum(len(str(message.get("content") or "")) for message in messages)
        input_tokens = approximate_tokens("".join(str(message.get("content") or "") for message in messages))
        payload_snippet = redacted_snippet(messages) if api_payload_logging_enabled() else None
        with _chat_lock:
            self._wait_for_turn()
            for attempt in range(self.max_retries + 1):
                started = time.monotonic()
                log_event(
                    logger,
                    20,
                    "llm_request_attempt",
                    provider=self.provider,
                    model=self.model,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    input_chars=input_chars,
                    approximate_input_tokens=input_tokens,
                    max_output_tokens=max_tokens,
                    payload_snippet=payload_snippet,
                )
                try:
                    response = requests.post(endpoint, json=payload, headers=headers, timeout=self.timeout)
                except requests.RequestException:
                    log_event(
                        logger,
                        40,
                        "llm_request_failed",
                        provider=self.provider,
                        model=self.model,
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        elapsed_seconds=round(time.monotonic() - started, 3),
                        outcome="request_exception",
                    )
                    logger.debug("LLM request exception", exc_info=True)
                    raise
                elapsed = round(time.monotonic() - started, 3)
                self._mark_request()
                if response.status_code != 429:
                    try:
                        response.raise_for_status()
                    except requests.RequestException:
                        log_event(
                            logger,
                            40,
                            "llm_request_failed",
                            provider=self.provider,
                            model=self.model,
                            attempt=attempt + 1,
                            max_retries=self.max_retries,
                            status_code=response.status_code,
                            elapsed_seconds=elapsed,
                            outcome="http_error",
                        )
                        raise
                    data = response.json()
                    content = data["choices"][0]["message"]["content"].strip()
                    log_event(
                        logger,
                        20,
                        "llm_request_complete",
                        provider=self.provider,
                        model=self.model,
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        status_code=response.status_code,
                        elapsed_seconds=elapsed,
                        output_chars=len(content),
                        approximate_output_tokens=approximate_tokens(content),
                        outcome="success",
                    )
                    return content
                if attempt >= self.max_retries:
                    log_event(
                        logger,
                        40,
                        "llm_request_failed",
                        provider=self.provider,
                        model=self.model,
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        status_code=response.status_code,
                        elapsed_seconds=elapsed,
                        outcome="rate_limited",
                    )
                    response.raise_for_status()
                delay = self._retry_delay(response, attempt)
                log_event(
                    logger,
                    30,
                    "llm_request_retry",
                    provider=self.provider,
                    model=self.model,
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    status_code=response.status_code,
                    retry_delay_seconds=round(delay, 3),
                    elapsed_seconds=elapsed,
                    outcome="retry",
                )
                time.sleep(delay)
        return None

    def _wait_for_turn(self) -> None:
        global _last_request_at
        elapsed = time.monotonic() - _last_request_at
        wait_seconds = self.min_interval - elapsed
        if wait_seconds > 0:
            time.sleep(wait_seconds)

    def _mark_request(self) -> None:
        global _last_request_at
        _last_request_at = time.monotonic()

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After")
        try:
            wait_seconds = float(retry_after) if retry_after else 0.0
        except ValueError:
            wait_seconds = 0.0
        if wait_seconds <= 0:
            wait_seconds = min(30.0, (2 ** attempt) * self.min_interval + random.uniform(0.25, 1.25))
        return wait_seconds
