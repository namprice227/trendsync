import os
from moviepy import VideoFileClip, concatenate_videoclips, AudioFileClip

def snap_cuts_to_beats(cuts: list, beats: list, threshold: float = 0.2) -> list:
    """
    Aligns raw video cuts to the nearest musical beat for perfectly synced edits.
    Inspired by FireRed-OpenStoryline's smart beat-syncing logic.
    """
    if not beats:
        return cuts
        
    snapped_cuts = [0.0]
    for cut in cuts[1:]:
        closest_beat = min(beats, key=lambda b: abs(b - cut))
        if abs(closest_beat - cut) <= threshold:
            snapped_cuts.append(closest_beat)
        else:
            snapped_cuts.append(cut)
    return snapped_cuts

def _apply_crossfade(clips: list, fade_duration: float = 0.3):
    """
    Fix 4: Applies crossfade transitions between clips.
    Each clip fades out and the next fades in for a smooth blend.
    """
    if len(clips) <= 1 or fade_duration <= 0:
        return concatenate_videoclips(clips, method="compose")
    
    faded_clips = []
    for i, clip in enumerate(clips):
        # Skip fade for very short clips
        if clip.duration <= fade_duration * 2:
            faded_clips.append(clip)
            continue
        
        c = clip
        if i > 0:  # Fade in (not the first clip)
            c = c.with_effects([lambda clip: clip.crossfadein(fade_duration)])
        if i < len(clips) - 1:  # Fade out (not the last clip)
            c = c.with_effects([lambda clip: clip.crossfadeout(fade_duration)])
        faded_clips.append(c)
    
    return concatenate_videoclips(faded_clips, method="compose")

def render_final_video(clips_paths: list, skill_dir: str, output_path: str = "final_trend.mp4"):
    """
    Assembles user clips, trims them to match trend cuts, and overlays original audio.
    Applies beat-syncing and optional crossfade transitions (Fix 4).
    """
    print("Loading skill context for rendering...")
    import json
    
    context_path = os.path.join(skill_dir, "context.json")
    with open(context_path, "r") as f:
        context = json.load(f)

    raw_cuts = context["cuts"]
    beats = context.get("beats", [])
    audio_path = context["audio_path"]
    
    # Check if transitions should be applied
    # Load style from SKILL.md frontmatter if available
    has_transition = False
    try:
        skill_md_path = os.path.join(skill_dir, "SKILL.md")
        if os.path.exists(skill_md_path):
            with open(skill_md_path, "r") as f:
                content = f.read()
                if "key_transition:" in content:
                    import re
                    match = re.search(r'key_transition:\s*(.+)', content)
                    if match and match.group(1).strip().lower() not in ("none", "'none'", "\"none\""):
                        has_transition = True
                        print(f"Transition detected — applying crossfade effects")
    except Exception:
        pass
    
    # Apply OpenStoryline-style beat snapping
    cuts = snap_cuts_to_beats(raw_cuts, beats)

    if len(clips_paths) != (len(cuts) - 1 if len(cuts) > 1 else len(cuts)):
        print("Warning: Mismatch between number of recorded clips and required shots.")

    print("Assembling video clips...")
    processed_clips = []

    for i, clip_path in enumerate(clips_paths):
        if not os.path.exists(clip_path):
            continue

        # Determine the required duration for this clip based on cuts
        if i < len(cuts) - 1:
            duration = cuts[i+1] - cuts[i]
        elif len(cuts) > 0 and i == len(cuts) - 1:
            duration = 3.0
        else:
            duration = 3.0

        # Load and trim clip
        try:
            v_clip = VideoFileClip(clip_path)
            trim_end = min(duration, v_clip.duration)
            v_clip = v_clip.subclipped(0, trim_end)
            processed_clips.append(v_clip)
        except Exception as e:
            print(f"Failed to process clip {clip_path}: {str(e)}")

    if not processed_clips:
        raise ValueError("No valid clips were provided for rendering.")

    # Fix 4: Use crossfade if transition detected, else simple concat
    print("Concatenating clips...")
    if has_transition:
        final_video = _apply_crossfade(processed_clips, fade_duration=0.3)
    else:
        final_video = concatenate_videoclips(processed_clips, method="compose")

    print(f"Applying original audio from {audio_path}...")
    try:
        audio_clip = AudioFileClip(audio_path)
        audio_clip = audio_clip.subclipped(0, min(audio_clip.duration, final_video.duration))
        final_video = final_video.with_audio(audio_clip)
    except Exception as e:
        print(f"Warning: Failed to apply audio: {str(e)}")

    print(f"Exporting final video to {output_path}...")
    final_video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp-audio.m4a",
        remove_temp=True,
        logger=None
    )

    # Clean up memory
    for clip in processed_clips:
        clip.close()
    if 'audio_clip' in locals():
        audio_clip.close()
    final_video.close()

    print("Render complete!")
    return output_path

if __name__ == "__main__":
    print("Renderer module loaded. Use app.py for the full UI.")