import os
from moviepy.editor import VideoFileClip, concatenate_videoclips, AudioFileClip

def render_final_video(clips_paths: list, profile_path: str, output_path: str = "final_trend.mp4"):
    """
    Assembles user clips, trims them to match trend cuts, and overlays original audio.
    """
    print("Loading trend profile for rendering...")
    import json
    with open(profile_path, "r") as f:
        profile = json.load(f)

    cuts = profile["cuts"]
    audio_path = profile["audio_path"]

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
            # Fallback for the last clip if not explicitly bounded
            duration = 3.0
        else:
            duration = 3.0

        # Load and trim clip
        try:
            v_clip = VideoFileClip(clip_path)
            # Ensure clip isn't shorter than required duration; if it is, use max length.
            trim_end = min(duration, v_clip.duration)
            v_clip = v_clip.subclip(0, trim_end)
            processed_clips.append(v_clip)
        except Exception as e:
            print(f"Failed to process clip {clip_path}: {str(e)}")

    if not processed_clips:
        raise ValueError("No valid clips were provided for rendering.")

    print("Concatenating clips...")
    final_video = concatenate_videoclips(processed_clips, method="compose")

    print(f"Applying original audio from {audio_path}...")
    try:
        audio_clip = AudioFileClip(audio_path)
        # Match audio duration to final video duration
        audio_clip = audio_clip.subclip(0, min(audio_clip.duration, final_video.duration))
        final_video = final_video.set_audio(audio_clip)
    except Exception as e:
        print(f"Warning: Failed to apply audio: {str(e)}")

    print(f"Exporting final video to {output_path}...")
    final_video.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp-audio.m4a",
        remove_temp=True,
        logger=None # Suppress verbose moviepy output
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