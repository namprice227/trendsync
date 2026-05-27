from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from tts_provider import TTSProvider, mix_narration
from tripstory_logging import get_logger, log_event


VIDEO_SUFFIXES = {".mp4", ".mov", ".m4v", ".webm"}
logger = get_logger("renderer")


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _concat_with_ffmpeg(video_paths: list[str], output_path: str) -> None:
    list_path = Path(output_path).with_suffix(".concat.txt")
    lines = []
    for path in video_paths:
        safe_path = str(Path(path).resolve()).replace("'", "'\\''")
        lines.append(f"file '{safe_path}'")
    list_path.write_text("\n".join(lines), encoding="utf-8")

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        output_path,
    ]
    _run(command)


def _escape_drawtext(value: str) -> str:
    return value.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")


def _aspect_filter(aspect_ratio: str) -> str:
    targets = {
        "portrait": (1080, 1920),
        "landscape": (1920, 1080),
        "square": (1080, 1080),
    }
    if aspect_ratio not in targets:
        return "format=yuv420p"
    width, height = targets[aspect_ratio]
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
        "format=yuv420p"
    )


def _clip_duration(item: dict[str, Any]) -> float:
    try:
        return float((item.get("analysis") or {}).get("duration_seconds") or 0)
    except (TypeError, ValueError):
        return 0.0


def _segment_start(item: dict[str, Any], segment_seconds: float) -> float:
    analysis = item.get("analysis") or {}
    candidates = analysis.get("best_moment_timestamps") or analysis.get("landmark_candidate_timestamps") or [0]
    try:
        center = float(candidates[0])
    except (TypeError, ValueError, IndexError):
        center = 0.0
    duration = _clip_duration(item)
    start = max(0.0, center - segment_seconds / 2)
    if duration:
        start = min(start, max(0.0, duration - segment_seconds))
    return round(start, 2)


def _media_items_from_paths(media_paths: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "id": Path(path).stem,
            "filename": Path(path).name,
            "path": path,
            "kind": "video",
            "analysis": {},
        }
        for path in media_paths
    ]


def _ordered_video_items(
    media_paths: list[str],
    media_items: list[dict[str, Any]] | None,
    story_plan: dict[str, Any],
    render_options: dict[str, Any],
) -> list[dict[str, Any]]:
    source_items = list(media_items or _media_items_from_paths(media_paths))
    source_items = [
        item
        for item in source_items
        if Path(str(item.get("path") or "")).suffix.lower() in VIDEO_SUFFIXES and Path(str(item.get("path") or "")).exists()
    ]
    by_id = {str(item.get("id")): item for item in source_items}
    by_filename = {str(item.get("filename")): item for item in source_items}

    ordered: list[dict[str, Any]] = []
    for clip_id in render_options.get("clip_order") or []:
        item = by_id.get(str(clip_id))
        if item and item not in ordered:
            ordered.append(item)

    if not ordered:
        for plan_item in story_plan.get("clip_plan") or []:
            name = str(plan_item.get("clip") or "")
            item = by_filename.get(name)
            if item and item not in ordered:
                ordered.append(item)

    for item in source_items:
        if item not in ordered:
            ordered.append(item)

    favorites = set(str(value) for value in render_options.get("favorite_clip_ids") or [])
    ordered.sort(key=lambda item: 0 if str(item.get("id")) in favorites else 1)
    return ordered


def _item_for_decision(
    decision: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    by_filename: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    clip_id = str(decision.get("clip_id") or "")
    clip_name = str(decision.get("clip") or "")
    return by_id.get(clip_id) or by_filename.get(clip_name)


def _smart_timeline(
    media_paths: list[str],
    media_items: list[dict[str, Any]] | None,
    story_plan: dict[str, Any],
    render_options: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    ordered_items = _ordered_video_items(media_paths, media_items, story_plan, render_options)
    by_id = {str(item.get("id")): item for item in ordered_items}
    by_filename = {str(item.get("filename")): item for item in ordered_items}

    timeline: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for raw_decision in story_plan.get("edit_decisions") or []:
        if not isinstance(raw_decision, dict):
            continue
        item = _item_for_decision(raw_decision, by_id, by_filename)
        if not item:
            continue
        timeline.append((item, raw_decision))

    if timeline:
        return timeline

    segment_seconds = float(render_options.get("segment_seconds") or 6)
    return [
        (
            item,
            {
                "clip_id": item.get("id"),
                "clip": item.get("filename"),
                "start_time": _segment_start(item, segment_seconds),
                "duration": segment_seconds,
                "role": "fallback beat",
                "reason": "Renderer fallback chose the best detected moment because no LLM edit_decisions were available.",
                "transition": "fade",
                "caption": item.get("filename"),
                "audio_strategy": "duck original ambience under narration",
            },
        )
        for item in ordered_items
    ]


def _make_title_card(output_path: Path, story_plan: dict[str, Any], context: dict[str, Any], aspect_ratio: str) -> str:
    title = _escape_drawtext(str(story_plan.get("title") or context.get("destination") or "TripStory"))
    dates = _escape_drawtext(str(context.get("travel_dates") or context.get("duration") or ""))
    width, height = {
        "portrait": (1080, 1920),
        "landscape": (1920, 1080),
        "square": (1080, 1080),
    }.get(aspect_ratio, (1280, 720))
    vf = (
        f"drawtext=text='{title}':fontcolor=white:fontsize={max(42, width // 18)}:"
        f"x=(w-text_w)/2:y=(h-text_h)/2-48,"
        f"drawtext=text='{dates}':fontcolor=white@0.75:fontsize={max(24, width // 35)}:"
        f"x=(w-text_w)/2:y=(h+text_h)/2+36"
    )
    command = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=0x111716:s={width}x{height}:d=2",
        "-vf",
        vf,
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(output_path),
    ]
    _run(command)
    return str(output_path)


def _decision_float(decision: dict[str, Any], key: str, fallback: float) -> float:
    try:
        return float(decision.get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def _make_segment(item: dict[str, Any], decision: dict[str, Any], output_path: Path, aspect_ratio: str, segment_seconds: float) -> str:
    source = str(item.get("path"))
    start = max(0.0, _decision_float(decision, "start_time", _segment_start(item, segment_seconds)))
    duration = _clip_duration(item)
    requested = max(1.0, min(10.0, _decision_float(decision, "duration", segment_seconds)))
    trim = min(requested, duration - start) if duration else requested
    trim = max(1.0, trim)
    vf = f"{_aspect_filter(aspect_ratio)},fade=t=in:st=0:d=0.18,fade=t=out:st={max(0.2, trim - 0.25):.2f}:d=0.2"
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start),
        "-i",
        source,
        "-t",
        f"{trim:.2f}",
        "-vf",
        vf,
        "-af",
        "afade=t=in:st=0:d=0.15,afade=t=out:st=0.85:d=0.15",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    _run(command)
    return str(output_path)


def _caption_blocks(script: str, total_seconds: float) -> list[tuple[float, float, str]]:
    sentences = [part.strip() for part in script.replace("!", ".").replace("?", ".").split(".") if part.strip()]
    if not sentences:
        return []
    slot = max(2.5, total_seconds / max(1, len(sentences)))
    blocks = []
    cursor = 0.0
    for sentence in sentences:
        end = min(total_seconds or cursor + slot, cursor + slot)
        blocks.append((cursor, max(cursor + 1.5, end), sentence))
        cursor = end
    return blocks


def _matching_voiceover_segments(
    story_plan: dict[str, Any],
    timeline: list[tuple[dict[str, Any], dict[str, Any]]],
) -> list[dict[str, Any]]:
    raw_segments = [segment for segment in story_plan.get("voiceover_segments") or [] if isinstance(segment, dict)]
    used: set[int] = set()
    matched: list[dict[str, Any]] = []
    for index, (item, decision) in enumerate(timeline):
        item_ids = {str(item.get("id") or ""), str(item.get("filename") or ""), str(decision.get("clip_id") or ""), str(decision.get("clip") or "")}
        match_index = None
        for segment_index, segment in enumerate(raw_segments):
            if segment_index in used:
                continue
            segment_ids = {str(segment.get("clip_id") or ""), str(segment.get("clip") or "")}
            if item_ids & segment_ids:
                match_index = segment_index
                break
        if match_index is None and index < len(raw_segments) and index not in used:
            match_index = index
        if match_index is not None:
            used.add(match_index)
            segment = dict(raw_segments[match_index])
        else:
            segment = {}
        text = str(segment.get("voiceover") or segment.get("caption") or decision.get("caption") or decision.get("reason") or "").strip()
        matched.append(
            {
                "clip_id": segment.get("clip_id") or decision.get("clip_id") or item.get("id"),
                "clip": segment.get("clip") or decision.get("clip") or item.get("filename"),
                "start_time": _decision_float(decision, "start_time", _decision_float(segment, "start_time", 0.0)),
                "duration": _decision_float(decision, "duration", _decision_float(segment, "duration", 6.0)),
                "voiceover": text,
                "caption": segment.get("caption") or decision.get("caption") or text,
                "purpose": segment.get("purpose") or decision.get("role"),
            }
        )
    return matched


def _timeline_voiceover_script(story_plan: dict[str, Any], timeline: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    segments = _matching_voiceover_segments(story_plan, timeline)
    script = " ".join(str(segment.get("voiceover") or "").strip() for segment in segments).strip()
    return script or str(story_plan.get("voiceover_script") or "")


def _timeline_caption_blocks(
    story_plan: dict[str, Any],
    timeline: list[tuple[dict[str, Any], dict[str, Any]]],
    include_title_card: bool,
    segment_seconds: float,
) -> list[tuple[float, float, str]]:
    segments = _matching_voiceover_segments(story_plan, timeline)
    blocks: list[tuple[float, float, str]] = []
    cursor = 2.0 if include_title_card else 0.0
    for segment, (_, decision) in zip(segments, timeline):
        duration = max(1.0, min(10.0, _decision_float(decision, "duration", segment_seconds)))
        text = str(segment.get("voiceover") or segment.get("caption") or "").strip()
        if text:
            blocks.append((cursor, cursor + duration, text))
        cursor += duration
    return blocks


def _format_srt_time(seconds: float) -> str:
    millis = int((seconds - int(seconds)) * 1000)
    whole = int(seconds)
    hours = whole // 3600
    minutes = (whole % 3600) // 60
    secs = whole % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_vtt_time(seconds: float) -> str:
    return _format_srt_time(seconds).replace(",", ".")


def _write_caption_blocks(blocks: list[tuple[float, float, str]], srt_path: str | None, vtt_path: str | None) -> None:
    if not blocks:
        return
    if srt_path:
        lines = []
        for index, (start, end, text) in enumerate(blocks, start=1):
            lines.extend([str(index), f"{_format_srt_time(start)} --> {_format_srt_time(end)}", text, ""])
        Path(srt_path).write_text("\n".join(lines), encoding="utf-8")
    if vtt_path:
        lines = ["WEBVTT", ""]
        for start, end, text in blocks:
            lines.extend([f"{_format_vtt_time(start)} --> {_format_vtt_time(end)}", text, ""])
        Path(vtt_path).write_text("\n".join(lines), encoding="utf-8")


def _write_captions(script: str, total_seconds: float, srt_path: str | None, vtt_path: str | None) -> None:
    _write_caption_blocks(_caption_blocks(script, total_seconds), srt_path, vtt_path)


def _write_edit_decisions(
    timeline: list[tuple[dict[str, Any], dict[str, Any]]],
    voiceover_segments: list[dict[str, Any]],
    output_path: Path,
) -> None:
    payload = []
    cursor = 2.0
    for index, (item, decision) in enumerate(timeline):
        duration = max(1.0, min(10.0, _decision_float(decision, "duration", 6.0)))
        voiceover = voiceover_segments[index] if index < len(voiceover_segments) else {}
        payload.append(
            {
                "source_clip_id": item.get("id"),
                "source_clip": item.get("filename"),
                "source_start_time": _decision_float(decision, "start_time", 0.0),
                "render_start_time": round(cursor, 2),
                "duration": round(duration, 2),
                "role": decision.get("role"),
                "reason": decision.get("reason"),
                "transition": decision.get("transition"),
                "caption": decision.get("caption"),
                "voiceover": voiceover.get("voiceover"),
                "audio_strategy": decision.get("audio_strategy"),
            }
        )
        cursor += duration
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def render_trip_video(
    media_paths: list[str],
    story_plan: dict[str, Any],
    output_path: str,
    metadata_path: str | None = None,
    narration_path: str | None = None,
    media_items: list[dict[str, Any]] | None = None,
    render_options: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    captions_srt_path: str | None = None,
    captions_vtt_path: str | None = None,
    progress_callback: Callable[[str, int], None] | None = None,
) -> str:
    """Create a holiday recap assembly from uploaded videos.

    If ffmpeg is available, all uploaded videos are concatenated and re-encoded.
    If ffmpeg is unavailable, the first uploaded video is copied as the render
    output so the session still produces a usable artifact and voiceover plan.
    """

    render_options = render_options or {}
    context = context or {}
    timeline = _smart_timeline(media_paths, media_items, story_plan, render_options)
    video_paths = [str(item.get("path")) for item, _ in timeline]
    if not timeline:
        raise ValueError("Upload at least one video clip to render a recap video.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    assembly_path = output.with_name(f"{output.stem}_assembly{output.suffix}")
    segment_seconds = float(render_options.get("segment_seconds") or 6)
    aspect_ratio = str(render_options.get("aspect_ratio") or "original")
    include_title_card = bool(render_options.get("include_title_card", True))
    render_started = time.monotonic()
    log_event(
        logger,
        20,
        "render_start",
        stage="render",
        selected_clip_count=len(timeline),
        aspect_ratio=aspect_ratio,
        include_title_card=include_title_card,
        output_path=output.name,
    )

    if _ffmpeg_available():
        try:
            if progress_callback:
                progress_callback("rendering_segments", 35)
            segment_paths = []
            if include_title_card:
                title_started = time.monotonic()
                title_path = _make_title_card(output.with_name("000_title_card.mp4"), story_plan, context, aspect_ratio)
                segment_paths.append(title_path)
                log_event(
                    logger,
                    20,
                    "render_title_card_created",
                    stage="title_card",
                    output_path=Path(title_path).name,
                    elapsed_seconds=round(time.monotonic() - title_started, 3),
                    outcome="success",
                )
            for index, (item, decision) in enumerate(timeline, start=1):
                segment_started = time.monotonic()
                source_start = max(0.0, _decision_float(decision, "start_time", _segment_start(item, segment_seconds)))
                duration = max(1.0, min(10.0, _decision_float(decision, "duration", segment_seconds)))
                segment_path = _make_segment(item, decision, output.with_name(f"{index:03d}_segment.mp4"), aspect_ratio, segment_seconds)
                segment_paths.append(segment_path)
                log_event(
                    logger,
                    20,
                    "render_segment_created",
                    stage="rendering_segments",
                    segment_index=index,
                    clip_id=item.get("id"),
                    clip_name=item.get("filename"),
                    source_start_seconds=round(source_start, 2),
                    duration_seconds=round(duration, 2),
                    output_path=Path(segment_path).name,
                    elapsed_seconds=round(time.monotonic() - segment_started, 3),
                    outcome="success",
                )
            if len(segment_paths) > 1:
                concat_started = time.monotonic()
                _concat_with_ffmpeg(segment_paths, str(assembly_path))
                log_event(
                    logger,
                    20,
                    "render_concat_complete",
                    stage="concat",
                    segment_count=len(segment_paths),
                    output_path=assembly_path.name,
                    elapsed_seconds=round(time.monotonic() - concat_started, 3),
                    outcome="success",
                )
            else:
                shutil.copyfile(segment_paths[0], assembly_path)
                log_event(
                    logger,
                    20,
                    "render_concat_skipped_single_segment",
                    stage="concat",
                    segment_count=len(segment_paths),
                    output_path=assembly_path.name,
                    outcome="success",
                )
        except Exception as exc:
            log_event(
                logger,
                30,
                "render_story_aware_fallback",
                stage="rendering_segments",
                exception_type=type(exc).__name__,
                fallback_path="simple_assembly",
                selected_clip_count=len(video_paths),
                outcome="fallback",
            )
            logger.debug("Story-aware render exception", exc_info=True)
            if len(video_paths) > 1:
                _concat_with_ffmpeg(video_paths, str(assembly_path))
            else:
                shutil.copyfile(video_paths[0], assembly_path)
    else:
        log_event(
            logger,
            30,
            "render_ffmpeg_unavailable_fallback",
            stage="rendering_segments",
            fallback_path="copy_first_clip",
            selected_clip_count=len(video_paths),
            output_path=output.name,
            outcome="fallback",
        )
        shutil.copyfile(video_paths[0], output)

    total_seconds = sum(max(1.0, min(10.0, _decision_float(decision, "duration", segment_seconds))) for _, decision in timeline)
    if include_title_card:
        total_seconds += 2
    voiceover_segments = _matching_voiceover_segments(story_plan, timeline)
    if progress_callback:
        progress_callback("writing_captions", 65)
    captions_started = time.monotonic()
    _write_edit_decisions(timeline, voiceover_segments, output.with_name("edit_decisions.json"))
    timeline_blocks = _timeline_caption_blocks(
        story_plan,
        timeline,
        include_title_card,
        segment_seconds,
    )
    if timeline_blocks:
        _write_caption_blocks(timeline_blocks, captions_srt_path, captions_vtt_path)
    else:
        _write_captions(story_plan.get("voiceover_script") or "", total_seconds, captions_srt_path, captions_vtt_path)
    log_event(
        logger,
        20,
        "render_captions_written",
        stage="writing_captions",
        caption_block_count=len(timeline_blocks),
        edit_decisions_path="edit_decisions.json",
        srt_path=Path(captions_srt_path).name if captions_srt_path else None,
        vtt_path=Path(captions_vtt_path).name if captions_vtt_path else None,
        elapsed_seconds=round(time.monotonic() - captions_started, 3),
        outcome="success",
    )

    script = _timeline_voiceover_script(story_plan, timeline)
    generated_narration = None
    if _ffmpeg_available() and assembly_path.exists():
        if progress_callback:
            progress_callback("synthesizing_narration", 75)
        narration_started = time.monotonic()
        generated_narration = TTSProvider().synthesize(
            script,
            narration_path or output.with_name("voiceover.mp3"),
            instructions=f"Narrate as a warm travel recap in {story_plan.get('language') or 'the requested language'}.",
        )
        log_event(
            logger,
            20 if generated_narration else 30,
            "render_narration_synth_complete",
            stage="synthesizing_narration",
            narration_path=Path(generated_narration).name if generated_narration else None,
            input_chars=len(script),
            elapsed_seconds=round(time.monotonic() - narration_started, 3),
            outcome="success" if generated_narration else "skipped_or_fallback",
        )

    if generated_narration and _ffmpeg_available():
        try:
            if progress_callback:
                progress_callback("mixing_audio", 85)
            mix_started = time.monotonic()
            mix_narration(assembly_path, generated_narration, output)
            log_event(
                logger,
                20,
                "render_audio_mix_complete",
                stage="mixing_audio",
                assembly_path=assembly_path.name,
                narration_path=Path(generated_narration).name,
                output_path=output.name,
                elapsed_seconds=round(time.monotonic() - mix_started, 3),
                outcome="success",
            )
        except Exception as exc:
            log_event(
                logger,
                30,
                "render_audio_mix_fallback",
                stage="mixing_audio",
                exception_type=type(exc).__name__,
                fallback_path="assembly_without_generated_mix",
                output_path=output.name,
                outcome="fallback",
            )
            logger.debug("Narration mix exception", exc_info=True)
            shutil.copyfile(assembly_path, output)
    elif assembly_path.exists():
        shutil.copyfile(assembly_path, output)
        log_event(
            logger,
            20,
            "render_output_written",
            stage="finalize",
            output_path=output.name,
            narration_mixed=False,
            outcome="success",
        )

    if metadata_path:
        Path(metadata_path).write_text(json.dumps(story_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        log_event(
            logger,
            20,
            "render_metadata_written",
            stage="finalize",
            metadata_path=Path(metadata_path).name,
            outcome="success",
        )

    log_event(
        logger,
        20,
        "render_complete",
        stage="render",
        output_path=output.name,
        elapsed_seconds=round(time.monotonic() - render_started, 3),
        selected_clip_count=len(timeline),
        outcome="success",
    )
    return str(output)
