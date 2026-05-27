from __future__ import annotations

import base64
import os
import random
import subprocess
import threading
import time
import wave
from pathlib import Path

import requests

from tripstory_logging import api_payload_logging_enabled, get_logger, log_event, redacted_snippet
from media_tools import ffmpeg_bin, ffprobe_bin


_tts_lock = threading.Lock()
_last_tts_request_at = 0.0
logger = get_logger("tts")
FFMPEG_AUDIO_MIX_TIMEOUT = int(os.environ.get("TRIPSTORY_FFMPEG_AUDIO_MIX_TIMEOUT", "300"))


class TTSProvider:
    """Server-side text-to-speech client.

    The frontend never receives provider keys. TTS is enabled with
    `TRIPSTORY_TTS_PROVIDER=openai` or `TRIPSTORY_TTS_PROVIDER=gemini`.
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
            if os.environ.get("OPENAI_API_KEY"):
                raw_provider = "openai"
            elif os.environ.get("GEMINI_API_KEY"):
                raw_provider = "gemini"
            else:
                raw_provider = "disabled"
        self.provider = raw_provider.strip().lower()
        key_env = "GEMINI_API_KEY" if self.provider == "gemini" else "OPENAI_API_KEY"
        self.api_key = api_key or os.environ.get(key_env)
        default_model = "gemini-3.1-flash-tts-preview" if self.provider == "gemini" else "gpt-4o-mini-tts"
        default_voice = "Kore" if self.provider == "gemini" else "coral"
        self.model = model or os.environ.get("TRIPSTORY_TTS_MODEL") or default_model
        self.voice = voice or os.environ.get("TRIPSTORY_TTS_VOICE") or default_voice
        self.timeout = timeout or int(os.environ.get("TRIPSTORY_TTS_TIMEOUT", "90"))
        self.min_interval = float(os.environ.get("TRIPSTORY_TTS_MIN_INTERVAL_SECONDS", "3"))
        self.max_retries = int(os.environ.get("TRIPSTORY_TTS_MAX_RETRIES", "2"))

    @property
    def configured(self) -> bool:
        return self.provider in {"openai", "gemini"} and bool(self.api_key)

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
        if self.provider == "gemini" and target.suffix.lower() != ".wav":
            target = target.with_suffix(".wav")
        target.parent.mkdir(parents=True, exist_ok=True)

        if self.provider == "gemini":
            return self._synthesize_gemini(cleaned, target, instructions)
        return self._synthesize_openai(cleaned, target, instructions)

    def _synthesize_openai(self, cleaned: str, target: Path, instructions: str | None) -> str | None:
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

    def _synthesize_gemini(self, cleaned: str, target: Path, instructions: str | None) -> str | None:
        prompt = cleaned[:4096]
        if instructions:
            prompt = f"{instructions.strip()}\n\nRead this narration exactly:\n{prompt}"
        payload: dict[str, object] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {
                            "voiceName": self.voice,
                        }
                    }
                },
            },
            "model": self.model,
        }
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

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
                        input_chars=len(prompt),
                        attempt=attempt + 1,
                        max_retries=self.max_retries,
                        payload_snippet=redacted_snippet(payload) if api_payload_logging_enabled() else None,
                    )
                    response = requests.post(
                        url,
                        headers={
                            "x-goog-api-key": self.api_key or "",
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
                            pcm = _gemini_pcm_bytes(response.json())
                        except (KeyError, TypeError, ValueError, requests.RequestException):
                            log_event(
                                logger,
                                40,
                                "tts_request_failed",
                                provider=self.provider,
                                model=self.model,
                                voice=self.voice,
                                input_chars=len(prompt),
                                attempt=attempt + 1,
                                max_retries=self.max_retries,
                                status_code=response.status_code,
                                elapsed_seconds=request_elapsed,
                                outcome="http_or_payload_error",
                            )
                            raise
                        _write_pcm_wave(target, pcm)
                        log_event(
                            logger,
                            20,
                            "tts_request_complete",
                            provider=self.provider,
                            model=self.model,
                            voice=self.voice,
                            input_chars=len(prompt),
                            attempt=attempt + 1,
                            max_retries=self.max_retries,
                            status_code=response.status_code,
                            elapsed_seconds=request_elapsed,
                            output_bytes=target.stat().st_size,
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
                        input_chars=len(prompt),
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
                        input_chars=len(prompt),
                        max_retries=self.max_retries,
                        status_code=response.status_code,
                        outcome="rate_limited",
                    )
                    response.raise_for_status()
            except (KeyError, TypeError, ValueError, requests.RequestException) as exc:
                log_event(
                    logger,
                    30,
                    "tts_unavailable_fallback",
                    provider=self.provider,
                    model=self.model,
                    voice=self.voice,
                    input_chars=len(prompt),
                    exception_type=type(exc).__name__,
                    outcome="fallback_without_narration",
                )
                logger.debug("TTS request exception", exc_info=True)
                return None
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


def _gemini_pcm_bytes(payload: dict) -> bytes:
    parts = payload["candidates"][0]["content"]["parts"]
    for part in parts:
        inline_data = part.get("inlineData") or part.get("inline_data")
        if inline_data and inline_data.get("data"):
            return base64.b64decode(inline_data["data"])
    raise ValueError("Gemini TTS response did not include inline audio data")


def _write_pcm_wave(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(pcm)


def audio_stream_exists(video_path: str | Path) -> bool:
    ffprobe = ffprobe_bin()
    if not ffprobe:
        return False
    command = [
        ffprobe,
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
        result = subprocess.run(command, check=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=FFMPEG_AUDIO_MIX_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "audio" in result.stdout


def mix_narration(video_path: str | Path, narration_path: str | Path, output_path: str | Path, duration_seconds: float | None = None) -> str:
    ffmpeg = ffmpeg_bin()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is not available. Set TRIPSTORY_FFMPEG_BIN or install ffmpeg in the active environment.")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    has_audio = audio_stream_exists(video_path)
    duration_args = ["-t", f"{duration_seconds:.2f}"] if duration_seconds and duration_seconds > 0 else []

    if has_audio:
        command = [
            ffmpeg,
            "-nostdin",
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
            *duration_args,
            str(target),
        ]
    else:
        command = [
            ffmpeg,
            "-nostdin",
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
            *duration_args,
            str(target),
        ]

    subprocess.run(command, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=FFMPEG_AUDIO_MIX_TIMEOUT)
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
