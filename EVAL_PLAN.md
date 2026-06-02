# TripStory Evaluation Plan

To ensure the TripStory pipeline actually produces a "human-feeling vlog cut" and improves over time, we must evaluate the outputs across three specific vectors: **Scene Memory Quality, Planner Quality,** and **Narration Restraint.**

This evaluation plan utilizes a combination of deterministic checks, "LLM-as-a-Judge" scripts, and manual QA.

---

## 1. Scene Memory Quality (Intelligence Layer)
**Goal:** Ensure the VLM and preprocessing tools extract accurate, useful data without hallucinating.

### Metrics:
- **Hallucination Rate:** Does the `visual_evidence` text mention objects or actions that are not in the raw video?
- **Cut Alignment:** Do the `smart_windows` accurately represent continuous shots without jarring mid-window cuts?
- **Completeness:** Are glaring flaws (e.g., extreme blur, loud wind noise) correctly flagged in the JSON?

### Evaluation Method:
- **Dataset:** Maintain a static benchmark suite of 50 short clips with known edge cases (shaky, dark, fast pans, explicit subjects).
- **Test:** Run the intelligence extraction on the suite. Use a deterministic script to verify flags (e.g., "dark") and a strong LLM-Judge to compare the `visual_evidence` against human-written ground truth summaries.

---

## 2. Planner Quality (Narrative Coherence)
**Goal:** Ensure the text LLM creates a logical story arc from the JSON manifest.

### Metrics:
- **Arc Structure:** Does the video have a clear hook (first 5 seconds), contextual body, and outro?
- **Beat Selection:** Did the planner choose the highest-scoring `smart_windows` while avoiding clips flagged as "shaky" or "blurry"?
- **Instruction Following:** Did the output strictly adhere to the requested `target_duration_seconds` and schema shape?

### Evaluation Method:
- **Deterministic Validation:** Ensure the sum of the `edit_decisions` durations falls within +/- 10% of the requested target. Ensure no "avoid" flagged clips were selected unless absolutely necessary to fill time.
- **LLM-as-a-Judge:** Feed the generated `story_plan` to a critic LLM. Prompt: *"Score this story arc from 1-10 on logical progression. Does the hook make sense? Does the middle drag?"*

---

## 3. Narration Restraint
**Goal:** Ensure the TTS voiceover sounds like a human vlogger, not a metadata readout.

### Metrics:
- **Metadata Leakage:** The script must *never* contain words like "clip", "duration", "resolution", "seconds", or "quality".
- **Density:** The voiceover should not talk non-stop. There should be "breathing room" (ambient audio) between segments.
- **Tone Alignment:** Does the text match the user's requested tone (e.g., "cinematic", "energetic")?

### Evaluation Method:
- **Regex/Keyword Blocking:** Automate a CI test that fails if `voiceover_script` contains forbidden metadata terms.
- **Density Check:** Calculate `(total TTS audio duration) / (total video duration)`. Flag if the ratio exceeds 0.6 (i.e., talking for more than 60% of the video).
- **Human Review:** Randomly sample 5% of generated videos and grade the "first 15 seconds" rule: *Did the first 15 seconds feel like a human would actually say it?*
