from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any


_CONFIGURED = False
_SECRET_PATTERN = re.compile(r"(sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]+)", re.IGNORECASE)


def configure_logging() -> None:
    """Configure TripStory logging from environment once per process."""

    global _CONFIGURED

    level_name = os.environ.get("TRIPSTORY_LOG_LEVEL", "INFO").strip().upper() or "INFO"
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    logger = logging.getLogger("tripstory")
    logger.setLevel(level)
    logger.propagate = True

    if not logger.handlers:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    log_file = os.environ.get("TRIPSTORY_LOG_FILE", "").strip()
    if log_file and not any(isinstance(handler, logging.FileHandler) and handler.baseFilename == str(Path(log_file).resolve()) for handler in logger.handlers):
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"tripstory.{name}")


def api_payload_logging_enabled() -> bool:
    return os.environ.get("TRIPSTORY_LOG_API_PAYLOADS", "").strip().lower() in {"1", "true", "yes", "on"}


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def http_request_logging_enabled() -> bool:
    return _env_flag("TRIPSTORY_LOG_HTTP_REQUESTS", True)


def approximate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, round(len(text) / 4))


def redacted_snippet(value: Any, limit: int = 180) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    except TypeError:
        text = str(value)
    text = _SECRET_PATTERN.sub("[redacted]", text)
    text = re.sub(r"([a-z][a-z0-9+.-]*://[^:/\s]+:)[^@\s]+@", r"\1[redacted]@", text, flags=re.IGNORECASE)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    safe_fields = {
        key: value
        for key, value in fields.items()
        if value is not None and value != "" and key.lower() not in {"api_key", "authorization", "headers", "prompt", "script"}
    }
    encoded = json.dumps(safe_fields, ensure_ascii=False, sort_keys=True, default=str)
    logger.log(level, "%s %s", event, encoded)
