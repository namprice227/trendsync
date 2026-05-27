from __future__ import annotations

import os
import random
import subprocess
import threading
import time
from pathlib import Path

import requests

from tripstory_logging import api_payload_logging_enabled, get_logger, log_event, redacted_snippet


_tts_lock = threading.Lock()
_last_tts_request_at = 0.0
logger = get_logger("tts")


class TTSProvider:
    """Server-side text-to-speech client.

    The frontend never receives provider keys. OpenAI TTS is enabled when
    `TRIPSTORY_TTS_PROVIDER=openai` or when `OPENAI_API_KEY` is present.
    """

    def __init__(
        self,
        provider: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        voice: str | None = None,
        timeout: int | None = None,
    ) -> None:
        raw_provider = provider or os.environ.get("TRIPSTORY_TTS_PROVIDER")
        if not raw_provider:
            raw_provider = "openai" if os.environ.get("OPENAI_API_KEY") else "disabled"
        self.provider = raw_provider.strip().lower()
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.model = model or os.environ.get("TRIPSTORY_TTS_MODEL") or "gpt-4o-mini-tts"
        self.voice = voice or os.environ.get("TRIPSTORY_TTS_VOICE") or "coral"
        self.timeout = timeout or int(os.environ.get("TRIPSTORY_TTS_TIMEOUT", "90"))
        self.min_interval = float(os.environ.get("TRIPSTORY_TTS_MIN_INTERVAL_SECONDS", "3"))
        self.max_retries = int(os.environ.get("TRIPSTORY_TTS_MAX_RETRIES", "2"))

    @property
    def configured(self) -> bool:
        return self.provider == "openai" and bool(self.api_key)

    def synthesize(self, text: str, output_path: str | Path, instructions: str | None = None) -> str | None:
        cleaned = " ".join((text or "").split())
        if not cleaned or not self.configured:
            log_event(
                logger,
                20,
                "tts_unconfigured",
                provider=self.provider,
                model=self.model,
                voice=self.voice,
                input_chars=len(cleaned),
                outcome="skipped",
            )
            return None

        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, str] = {
            "model": self.model,
            "voice": self.voice,
            "input": cleaned[:4096],
            "response_format": "mp3",
        }
        if instructions:
            payload["instructions"] = instructions[:500]

        global _last_tts_request_at
        with _tts_lock:
            try:
                for attempt in range(self.max_retries + 1):
                    elapsed = time.monotonic() - _last_tts_request_at
                    if elapsed < self.min_interval:
                        time.sleep(self.min_interval - elapsed)
                    started = time.monotonic()
                    log_event(
                        logger,
                        20,
                        "tts_request_attempt",
                        provider=self.provider,
                        model=self.model,
                        voice=self.voice,
                        input_chars=len(payload["input"]),
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        payload_snippet=redacted_snippet(payload) if api_payload_logging_enabled() else None,
                    )
                    response = requests.post(
                        "https://api.openai.com/v1/audio/speech",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=self.timeout,
                    )
                    request_elapsed = round(time.monotonic() - started, 3)
                    _last_tts_request_at = time.monotonic()
                    if response.status_code != 429:
                        try:
                            response.raise_for_status()
                        except requests.RequestException:
                            log_event(
                                logger,
                                40,
                                "tts_request_failed",
                                provider=self.provider,
                                model=self.model,
                                voice=self.voice,
                                input_chars=len(payload["input"]),
                                attempt=attempt + 1,
                                max_retries=self.max_retries,
                                status_code=response.status_code,
                                elapsed_seconds=request_elapsed,
                                outcome="http_error",
                            )
                            raise
                        log_event(
                            logger,
                            20,
                            "tts_request_complete",
                            provider=self.provider,
                            model=self.model,
                            voice=self.voice,
                            input_chars=len(payload["input"]),
                            attempt=attempt + 1,
                            max_retries=self.max_retries,
                            status_code=response.status_code,
                            elapsed_seconds=request_elapsed,
                            output_bytes=len(response.content),
                            outcome="success",
                        )
                        break
                    retry_after = response.headers.get("retry-after")
                    try:
                        delay = float(retry_after) if retry_after else 0.0
                    except ValueError:
                        delay = 0.0
                    retry_delay = delay or min(30.0, (2**attempt) + random.random())
                    log_event(
                        logger,
                        30,
                        "tts_request_retry",
                        provider=self.provider,
                        model=self.model,
                        voice=self.voice,
                        input_chars=len(payload["input"]),
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        status_code=response.status_code,
                        retry_delay_seconds=round(retry_delay, 3),
                        elapsed_seconds=request_elapsed,
                        outcome="retry",
                    )
                    time.sleep(retry_delay)
                else:
                    log_event(
                        logger,
                        40,
                        "tts_request_failed",
                        provider=self.provider,
                        model=self.model,
                        voice=self.voice,
                        input_chars=len(payload["input"]),
                        max_retries=self.max_retries,
                        status_code=response.status_code,
                        outcome="rate_limited",
                    )
                    response.raise_for_status()
            except requests.RequestException as exc:
                log_event(
                    logger,
                    30,
                    "tts_unavailable_fallback",
                    provider=self.provider,
                    model=self.model,
                    voice=self.voice,
                    input_chars=len(payload["input"]),
                    exception_type=type(exc).__name__,
                    outcome="fallback_without_narration",
                )
                logger.debug("TTS request exception", exc_info=True)
                return None
        target.write_bytes(response.content)
        log_event(
            logger,
            20,
            "tts_audio_written",
            provider=self.provider,
            model=self.model,
            voice=self.voice,
            output_path=target.name,
            output_bytes=target.stat().st_size,
            outcome="success",
        )
        return str(target)


def audio_stream_exists(video_path: str | Path) -> bool:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_type",
        "-of",
        "csv=p=0",
        str(video_path),
    ]
    try:
        result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    except OSError:
        return False
    return "audio" in result.stdout


def mix_narration(video_path: str | Path, narration_path: str | Path, output_path: str | Path) -> str:
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    has_audio = audio_stream_exists(video_path)

    if has_audio:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(narration_path),
            "-filter_complex",
            "[0:a]volume=0.22[a0];[1:a]volume=1.0[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(target),
        ]
    else:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(narration_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            "-movflags",
            "+faststart",
            str(target),
        ]

    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    log_event(
        logger,
        20,
        "audio_mix_complete",
        source_video=Path(video_path).name,
        narration=Path(narration_path).name,
        output_path=target.name,
        had_source_audio=has_audio,
        outcome="success",
    )
    return str(target)
