# Product Requirements Document (PRD): TripStory AI

## 1. Product Vision & Wedge
**The Wedge:** "Turn a pile of clips into a first-cut narrated vlog in minutes."

TripStory AI is an agentic, multi-stage pipeline designed to take raw, unorganized holiday or event footage and automatically generate a cohesive, narrated vlog-style rough cut. Rather than relying on "clever AI video magic" or real-time director feedback, the product focuses on fundamentally human elements of storytelling: intelligent beat selection, narrative coherence, sparse but effective narration, and strong TTS (Text-to-Speech).

## 2. Target Audience
- Casual creators and travelers who capture gigabytes of phone footage but lack the time or editing skills to assemble it into a cohesive story.
- Social media users looking for an effortless way to summarize trips or events with a personal, vlog-style touch.

## 3. Core Value Proposition
- **Narrative Coherence:** By planning the entire story arc before rendering, the product ensures the video has a logical beginning, middle, and end.
- **Cost & Compute Efficiency:** Optimized for an A1000 GPU setup by utilizing a "scene memory" text manifest. Heavy vision tasks are done sparsely, while fast, cheap text LLMs handle the complex story planning.
- **Regenerative Control:** Users can tweak the narration, tone, or style without needing to re-analyze gigabytes of video.

## 4. User Journey
1. **Upload & Context:** The user uploads a batch of video clips and provides brief context (e.g., "Weekend in Tromso, saw the northern lights, ate great seafood").
2. **Preprocessing (The Wait):** The system extracts audio, detects cuts, evaluates blurriness/quality, and uses a Vision model to generate brief text summaries of key frames.
3. **Planning & Review:** The Story Planner (LLM) reads the text manifest of the clips and generates a JSON story arc, selecting the best beats and writing a script. The user can review this plan, regenerate the script, or exclude certain scenes.
4. **Rough Cut Export:** The system generates TTS narration, trims the clips using FFmpeg based on the exact edit decisions, mixes the audio, and provides a draft video export.

## 5. MVP Milestones
**Milestone 1: Grounded Scene Memory**
- Upload flow and media preprocessing.
- ASR (Audio Speech Recognition) for existing dialogue.
- Scene understanding (extracting text summaries from frames).
- Scene JSON viewer (developer/admin validation of memory).

**Milestone 2: Story Planner**
- Automatic beat selection based on quality and relevance.
- Story arc JSON generation (beginning, middle, end).
- Pinned/excluded scene controls.

**Milestone 3: Narration Generation**
- Grounded script output (narration matches the visual manifest).
- Multiple style profiles (e.g., energetic, cinematic, documentary).
- Regenerate button for script tweaks.

**Milestone 4: Rough Cut Export**
- Edit Decision List (EDL) translation for FFmpeg.
- Text-to-Speech (TTS) integration.
- Final draft video export and timeline assembly.

## 6. Non-Goals for MVP
- **Real-time directing:** We are explicitly moving away from the legacy TrendFlow real-time feedback loop.
- **Fancy end-to-end video magic:** No heavy generative video transitions or AI-generated B-roll. The focus is on editing real footage well.
- **Complex NLE features:** We are providing a *first cut*, not replacing Premiere Pro. Features like complex color grading or multi-track audio mixing are out of scope.

## 7. Success Metrics
- **Time to First Cut:** Users should receive a planned timeline within minutes of upload completion.
- **Narration Quality:** The first 15 seconds must feel like something a human would actually say (restrained, grounded, not reading metadata).
- **Regeneration Rate:** How often users choose to regenerate the script (a lower rate indicates better initial planner quality, though some regeneration is expected and encouraged).
