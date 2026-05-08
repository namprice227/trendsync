import gradio as gr
import json
import os
import cv2
import threading
import time

# Import our modular components
from analyzer import analyze_trend
from director import get_vlm_feedback, encode_image_base64, capture_shot
from renderer import render_final_video
from evaluator import evaluate_final_video
from scriptwriter import generate_script

# Global state for the hackathon prototype
app_state = {
    "skill_dir": None,
    "style": None,
    "required_shots": 0,
    "current_shot_idx": 0,
    "recorded_clips": [],
    "is_recording": False,
    "cuts": [],
    "final_video_path": None
}

# --- Custom CSS ---
custom_css = """
.gradio-container {
    max-width: 1200px !important;
    margin: auto !important;
}
.header-title {
    text-align: center;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 2.5em !important;
    font-weight: 800 !important;
    margin-bottom: 0 !important;
}
.header-subtitle {
    text-align: center;
    color: #666;
    font-size: 1.1em;
    margin-top: 0 !important;
}
.step-banner {
    background: linear-gradient(135deg, #667eea22, #764ba222);
    border-left: 4px solid #667eea;
    padding: 12px 16px;
    border-radius: 8px;
    margin-bottom: 12px;
}
.next-step-banner {
    background: linear-gradient(135deg, #00c85322, #00e67622);
    border-left: 4px solid #00c853;
    padding: 12px 16px;
    border-radius: 8px;
    margin-top: 12px;
    text-align: center;
}
.warn-banner {
    background: linear-gradient(135deg, #ff980022, #ff572222);
    border-left: 4px solid #ff9800;
    padding: 12px 16px;
    border-radius: 8px;
}
.progress-text {
    font-size: 1.3em;
    font-weight: bold;
    text-align: center;
}
"""

# --- Helper: format style values ---
def fmt(val):
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    return str(val)

# --- Tab 1: Analyzer ---
def process_trend_link(url, progress=gr.Progress()):
    """Handler for Tab 1: Analyzer"""
    try:
        progress(0, desc="Downloading video...")
        skill_dir, style, context = analyze_trend(url)
        app_state["skill_dir"] = skill_dir
        app_state["style"] = style
        app_state["cuts"] = context["cuts"]

        # Calculate number of required shots based on cuts
        num_shots = len(context["cuts"]) - 1 if len(context["cuts"]) > 1 else 1
        app_state["required_shots"] = num_shots
        app_state["current_shot_idx"] = 0
        app_state["recorded_clips"] = []

        progress(1.0, desc="Analysis complete!")

        metadata_display = json.dumps(context, indent=2)
        
        clothing = fmt(style.get('clothing', 'N/A'))
        setting = fmt(style.get('setting', 'N/A'))
        camera = fmt(style.get('camera_angle', 'N/A'))
        bpm = context.get('bpm', 'N/A')
        
        # Build the results summary
        results_md = f"""### ✅ Analysis Complete!

**Found {num_shots} shots** to recreate this trend.

---

### 🎬 AI Style Guide

| | Recommendation |
|---|---|
| 👗 **What to wear** | {clothing} |
| 📍 **Where to shoot** | {setting} |
| 📷 **Camera framing** | {camera} |
| 🎵 **BPM** | {bpm} |

---

### 📋 What You Need to Do

1. Dress according to the style guide above
2. Set up your camera in the recommended setting
3. **Go to Step 2: The Studio** tab
4. The AI Director will guide you shot by shot
5. It will auto-record when your framing is perfect
"""

        # Generate script using Few-Shot style transfer
        generated_script = generate_script(style)
        
        next_step = "✅ **Ready!** Go to **Step 2: The Studio** to start filming."
        
        return metadata_display, results_md, generated_script, next_step
    except Exception as e:
        error_md = f"### ❌ Error\n\n`{str(e)}`\n\nPlease check the URL and try again."
        return "", error_md, "", ""

# --- Tab 2: The Studio ---
def studio_feedback_loop(frame):
    """
    Handler for Tab 2: The Studio.
    Takes a webcam frame from Gradio, sends it to VLM, and returns the frame + feedback text.
    """
    if frame is None:
        return frame, "⏳ Waiting for camera feed...", "Connect your webcam above to begin."

    if not app_state["skill_dir"]:
        return frame, "⚠️ No trend analyzed yet", "Go to **Step 1** first and analyze a TikTok trend."

    total = app_state["required_shots"]
    current = app_state["current_shot_idx"]

    # Check if we've completed all shots
    if total > 0 and current >= total:
        return (
            frame,
            f"🎉 All {total} shots complete!",
            "All shots captured! Go to **Step 3: Final Output** to assemble your video."
        )

    if app_state["is_recording"]:
        return frame, "🔴 Recording...", f"Recording shot {current + 1}/{total} — hold still!"

    # Process frame for VLM
    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    base64_img = encode_image_base64(frame_bgr)

    # Load system prompt from skill
    system_prompt = None
    if app_state["skill_dir"]:
        try:
            from skill_manager import load_skill
            trend_name = os.path.basename(app_state["skill_dir"])
            frontmatter, markdown_body, context = load_skill(trend_name)
            system_prompt = markdown_body
        except Exception as e:
            print("Failed to load skill:", e)

    feedback = get_vlm_feedback(base64_img, system_prompt=system_prompt)

    # Check if perfect and trigger recording
    if "perfect" in feedback.lower() and app_state["skill_dir"] is not None:
        def start_recording():
            app_state["is_recording"] = True
            shot_idx = app_state["current_shot_idx"]

            cuts = app_state["cuts"]
            if shot_idx < len(cuts) - 1:
                duration = cuts[shot_idx + 1] - cuts[shot_idx]
            else:
                duration = 3.0

            os.makedirs("recorded_shots", exist_ok=True)
            output_path = os.path.join("recorded_shots", f"shot_{shot_idx}.mp4")

            print(f"Triggering recording for shot {shot_idx} (Duration: {duration}s)")
            capture_shot(duration, output_path)

            app_state["recorded_clips"].append(output_path)
            app_state["current_shot_idx"] += 1
            app_state["is_recording"] = False

        threading.Thread(target=start_recording).start()
        feedback = "✅ Perfect! Recording started..."

    progress_text = f"📸 Shot {current + 1} / {total}"
    detail = f"**Director says:** {feedback}"
    return frame, progress_text, detail

# --- Tab 3: Render ---
def render_project():
    """Handler for Tab 3: Render"""
    if not app_state["skill_dir"]:
        return None, "⚠️ No trend analyzed. Go to **Step 1** first."

    if not app_state["recorded_clips"]:
        return None, "⚠️ No clips recorded. Go to **Step 2: The Studio** to film your shots."

    try:
        output_file = render_final_video(app_state["recorded_clips"], app_state["skill_dir"])
        app_state["final_video_path"] = output_file
        return output_file, "✅ Render complete! Your video is ready. Click **Judge My Video** for AI feedback."
    except Exception as e:
        return None, f"❌ Render failed: `{str(e)}`"

def judge_video():
    """Handler for Evaluation"""
    if not app_state.get("final_video_path"):
        return "⚠️ No final video found. Click **Assemble Final Video** first."
    
    style_profile = None
    if app_state["skill_dir"]:
        try:
            from skill_manager import load_skill
            trend_name = os.path.basename(app_state["skill_dir"])
            frontmatter, _, _ = load_skill(trend_name)
            style_profile = frontmatter
        except:
            pass
            
    feedback = evaluate_final_video(app_state["final_video_path"], style_profile)
    return feedback

# ==========================================
# BUILD THE GRADIO UI
# ==========================================
with gr.Blocks(title="TrendFlow AI — Autonomous TikTok Director", css=custom_css, theme=gr.themes.Soft()) as demo:
    
    # --- Header ---
    gr.Markdown("# 🎬 TrendFlow AI", elem_classes=["header-title"])
    gr.Markdown("Autonomous TikTok Director & Editor — Powered by AMD MI300X + Qwen VLM", elem_classes=["header-subtitle"])

    with gr.Tabs() as tabs:
        # ==========================================
        # TAB 1: TREND ANALYZER
        # ==========================================
        with gr.Tab("① Analyze Trend", id="tab1"):
            gr.Markdown("""
<div class="step-banner">
<strong>Step 1:</strong> Paste a TikTok or Reel URL. The AI will download it, extract the audio beats, detect scene cuts, 
and use vision AI to analyze the style — clothing, setting, and camera angles.
</div>
""")
            
            with gr.Row():
                with gr.Column(scale=3):
                    url_input = gr.Textbox(
                        label="TikTok/Reel URL",
                        placeholder="https://www.tiktok.com/@user/video/123456789...",
                        lines=1
                    )
                with gr.Column(scale=1):
                    analyze_btn = gr.Button("🔍 Analyze Trend", variant="primary", size="lg")

            with gr.Row():
                with gr.Column(scale=2):
                    results_md = gr.Markdown("### Waiting for analysis...\n\nPaste a URL above and click **Analyze Trend** to begin.")
                    script_output = gr.Textbox(label="📝 Generated Script & Caption", interactive=False, lines=4)
                    next_step_md = gr.Markdown("")
                with gr.Column(scale=1):
                    metadata_output = gr.Code(label="Raw Context (context.json)", language="json", lines=20)

            analyze_btn.click(
                fn=process_trend_link,
                inputs=url_input,
                outputs=[metadata_output, results_md, script_output, next_step_md]
            )

        # ==========================================
        # TAB 2: THE STUDIO
        # ==========================================
        with gr.Tab("② The Studio", id="tab2"):
            gr.Markdown("""
<div class="step-banner">
<strong>Step 2:</strong> Turn on your webcam below. The AI Director watches your camera feed in real-time and tells you 
what to adjust (lighting, framing, outfit). When it says <strong>"Perfect"</strong>, it automatically records 
the shot for the exact duration needed.
</div>
""")

            # Status at the top
            with gr.Row():
                with gr.Column():
                    shot_progress = gr.Textbox(
                        label="Progress",
                        value="Waiting to start...",
                        interactive=False,
                        elem_classes=["progress-text"]
                    )

            with gr.Row():
                with gr.Column(scale=2):
                    camera_input = gr.Image(
                        sources=["webcam"],
                        streaming=True,
                        label="📹 Live Camera Feed",
                        height=400
                    )
                with gr.Column(scale=1):
                    director_feedback = gr.Markdown(
                        value="""### 🎥 AI Director

Waiting for camera feed...

---

**Tips:**
- Make sure you have good lighting
- Center yourself in the frame  
- Wear the outfit from the Style Guide
- The AI will auto-record when ready
""")

            camera_input.stream(
                fn=studio_feedback_loop,
                inputs=camera_input,
                outputs=[camera_input, shot_progress, director_feedback]
            )

        # ==========================================
        # TAB 3: FINAL OUTPUT
        # ==========================================
        with gr.Tab("③ Final Output", id="tab3"):
            gr.Markdown("""
<div class="step-banner">
<strong>Step 3:</strong> Assemble your recorded shots into a finished video with beat-synced cuts and the original audio. 
Then let the AI judge your result!
</div>
""")

            with gr.Row():
                with gr.Column():
                    render_btn = gr.Button("🎬 Assemble Final Video", variant="primary", size="lg")
                    render_status = gr.Markdown("Click **Assemble Final Video** to stitch your recorded shots together.")
                    
            final_video_output = gr.Video(label="🎥 Your Final Video", height=450)
            
            gr.Markdown("---")
            
            with gr.Row():
                with gr.Column():
                    judge_btn = gr.Button("⭐ Judge My Video", variant="secondary", size="lg")
                    judge_output = gr.Markdown("After assembling, click **Judge My Video** for an AI score and critique.")

            render_btn.click(
                fn=render_project,
                inputs=None,
                outputs=[final_video_output, render_status]
            )
            judge_btn.click(
                fn=judge_video,
                inputs=None,
                outputs=judge_output
            )

    # --- Footer ---
    gr.Markdown("""
---
<center>

**TrendFlow AI** — Built for the [AMD Developer Hackathon](https://lablab.ai) | Powered by AMD MI300X + ROCm + vLLM

</center>
""")

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=True)