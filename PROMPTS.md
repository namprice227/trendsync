# TripStory Prompt Architecture

The product is staged. Scene understanding creates evidence-linked memory first; story planning selects beats second; narration writes from those selected beats; edit assembly maps lines back to source windows.

## 1. Scene Understanding

Goal: convert one analyzed source window into grounded scene memory.

System constraints:

- Describe only observable visual or audio evidence.
- Prefer transcript and live audio evidence when present.
- Mark uncertainty in `risks`; do not hide it in the summary.
- Extract narrative usefulness, not just objects.
- Return strict JSON only.

Required output shape:

```json
{
  "scene_id": "string",
  "who_is_present": ["string"],
  "what_is_happening": "string",
  "where_it_happens": "string",
  "what_is_said": "string",
  "tone": "string",
  "narrative_role_candidates": ["hook", "setup", "progression", "payoff", "b_roll"],
  "ambient_audio_should_be_preserved": true,
  "evidence": [
    {"type": "transcript", "value": "string"},
    {"type": "visual", "value": "string"}
  ],
  "risks": ["string"]
}
```

Current implementation note: `scene_memory.py` builds the canonical local scene-memory artifact from `media_intelligence.py` analysis and smart windows. External VLM output enriches the same fields when configured.

## 2. Story Planner

Goal: choose the smallest useful set of scenes for the target duration before narration is written.

System constraints:

- `scene_memories` is the primary source of truth.
- Use `smart_windows` only to map selected scenes to source timestamps.
- Honor `pinned_favorite_clip_ids` and `pinned_scene_ids` when present.
- Avoid `excluded_clip_ids` and `excluded_scene_ids` unless every available option was excluded.
- Prefer transition quality and story clarity over exhaustive coverage.
- Return strict JSON only.

Planner output:

```json
{
  "story_beats": [
    {
      "beat_id": "beat_01",
      "purpose": "hook",
      "scene_ids": ["clip1_scene_001"],
      "reason": "clear arrival energy and grounded transcript",
      "estimated_duration_sec": 5,
      "transition_in": "cold_open",
      "transition_out": "move_into_setup"
    }
  ],
  "excluded_scenes": [
    {
      "scene_id": "clip3_scene_001",
      "reason": "redundant with a stronger market scene"
    }
  ],
  "risk_notes": ["clip2 has useful ambience but weak visual confidence"]
}
```

## 3. Narration Writer

Goal: write sparse creator-style voiceover from selected beats only.

System constraints:

- Use only evidence from selected `story_beats` and their grounded scenes.
- Do not narrate every visual detail.
- Keep each line short and spoken.
- Do not include timestamps, filenames, scene counts, face counts, resolution, or quality labels in audience-facing text.
- Use soft language when evidence is uncertain.
- Avoid documentary tone unless requested.

Writer output:

```json
{
  "narration_lines": [
    {
      "line_id": "line_01",
      "beat_id": "beat_01",
      "text": "We finally got there, and the whole place was already buzzing.",
      "duration_estimate_sec": 4,
      "grounded_scene_ids": ["clip1_scene_001"],
      "confidence": 0.84
    }
  ],
  "voiceover_script": "We finally got there, and the whole place was already buzzing."
}
```

## 4. Edit Assembly

Goal: map narration lines to source clip windows.

System constraints:

- Prefer the selected scene's `source_window_id`.
- Preserve useful live audio under narration.
- Avoid rapid overcutting unless the selected style demands it.
- Keep `edit_decisions` and `voiceover_segments` aligned by `segment_id`.

Output shape:

```json
{
  "edit_decisions": [
    {
      "segment_id": "seg_001",
      "beat_id": "beat_01",
      "scene_id": "clip1_scene_001",
      "clip_id": "clip1",
      "clip": "market.mp4",
      "window_id": "win_001",
      "start_time": 2,
      "duration": 5,
      "role": "hook",
      "reason": "the pinned scene has the clearest market arrival energy",
      "transition": "hard_cut",
      "caption": "Bangkok market",
      "audio_strategy": "duck original ambience under narration"
    }
  ]
}
```

Current implementation note: `trip_story.py` asks a text model for `story_beats`, `narration_lines`, `voiceover_segments`, and `edit_decisions` in one JSON response for MVP latency, but it stores and normalizes them as separate inspectable layers.
