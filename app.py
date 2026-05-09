import gradio as gr
import json
import os
import cv2
import threading
import time

# Import our modular components
from analyzer import analyze_trend
from director import (
    get_vlm_feedback, encode_image_base64, capture_shot,
    PoseTracker, get_fast_feedback
)
from renderer import render_final_video
from evaluator import evaluate_final_video
from scriptwriter import generate_script
from skill_manager import load_reference_poses

# Global state for the hackathon prototype
app_state = {
    "skill_dir": None,
    "style": None,
    "required_shots": 0,
    "current_shot_idx": 0,
    "recorded_clips": [],
    "is_recording": False,
    "cuts": [],
    "final_video_path": None,
    "camera_motion": [],
    "reference_poses": [],
    "pose_tracker": None,
    "prev_gray": None,
    "studio_start_time": None,
    "last_vlm_time": 0,
    "last_vlm_feedback": "",
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
    """Handler for Tab 1: Analyzer — streams progress logs to the UI."""
    try:
        # Fix 3: Clean up previous session's temp files
        from config import cleanup_session
        cleanup_session()
        
        progress(0.05, desc="🗂️ Cleaning workspace...")
        progress(0.1, desc="📥 Downloading video...")
        
        skill_dir, style, context = analyze_trend(url)
        app_state["skill_dir"] = skill_dir
        app_state["style"] = style
        app_state["cuts"] = context["cuts"]
        app_state["camera_motion"] = context.get("camera_motion", [])
        
        progress(0.7, desc="🤸 Loading reference poses...")
        # Load reference poses for hybrid director
        trend_name = os.path.basename(skill_dir)
        app_state["reference_poses"] = load_reference_poses(trend_name)
        
        # Initialize pose tracker
        if app_state["pose_tracker"] is None:
            app_state["pose_tracker"] = PoseTracker()
        
        # Fix 2: Initialize depth estimator if available
        depth_profile = context.get("depth_profile", [])
        app_state["depth_profile"] = depth_profile
        if depth_profile and not app_state.get("depth_estimator"):
            try:
                from depth_estimator import DepthEstimator
                de = DepthEstimator()
                if de.available:
                    app_state["depth_estimator"] = de
                    print(f"[Depth] Loaded with {len(depth_profile)} reference samples")
            except Exception as e:
                print(f"[Depth] Not available: {e}")

        # Calculate number of required shots based on cuts
        num_shots = len(context["cuts"]) - 1 if len(context["cuts"]) > 1 else 1
        app_state["required_shots"] = num_shots
        app_state["current_shot_idx"] = 0
        app_state["recorded_clips"] = []
        
        # Reset studio state for fresh session
        app_state["prev_gray"] = None
        app_state["studio_start_time"] = None
        app_state["last_vlm_time"] = 0
        app_state["last_vlm_feedback"] = ""

        progress(0.85, desc="📝 Generating script...")

        metadata_display = json.dumps(context, indent=2)
        
        clothing = fmt(style.get('clothing', 'N/A'))
        setting = fmt(style.get('setting', 'N/A'))
        camera = fmt(style.get('camera_angle', 'N/A'))
        bpm = context.get('bpm', 'N/A')
        video_type = fmt(style.get('video_type', 'N/A'))
        narrative = fmt(style.get('narrative', ''))
        transition = fmt(style.get('key_transition', 'none'))
        tips = fmt(style.get('recreation_tips', ''))
        
        # Build the results summary
        results_md = f"""### ✅ Analysis Complete!

**Found {num_shots} shots** to recreate this trend.

---

### 🎯 Video Type: {video_type}

**📖 Story:** {narrative}

"""

        # Show transition info if present
        if transition and transition.lower() != 'none':
            results_md += f"""### ⚡ Key Transition

{transition}

---

"""

        results_md += f"""### 🎬 AI Style Guide

| | Recommendation |
|---|---|
| 👗 **What to wear** | {clothing} |
| 📍 **Where to shoot** | {setting} |
| 📷 **Camera framing** | {camera} |
| 🎵 **BPM** | {bpm} |

"""

        # Show recreation tips if present
        if tips:
            results_md += f"""---

### 💡 Recreation Tips

{tips}

"""

        results_md += """---

### 📋 Next Steps

1. Prepare your outfits according to the style guide
2. Set up your filming location  
3. **Go to Step 2: The Studio** to upload your clips
"""

        # Add camera motion summary if available
        camera_motion = context.get("camera_motion", [])
        if camera_motion:
            motion_counts = {}
            for entry in camera_motion:
                m = entry["motion"]
                motion_counts[m] = motion_counts.get(m, 0) + 1
            motion_lines = [f"  - **{k.replace('_', ' ').title()}**: {v} segments" for k, v in sorted(motion_counts.items(), key=lambda x: -x[1])]
            results_md += f"\n### 🎥 Camera Motion Profile\n\n" + "\n".join(motion_lines) + "\n"
        
        # Add pose extraction status
        ref_poses = app_state.get("reference_poses", [])
        if ref_poses:
            results_md += f"\n### 🤸 Pose Data\n\n✅ {len(ref_poses)} reference poses extracted — pose comparison enabled in Studio.\n"
        
        # Add beat-cut sync info
        beat_sync = context.get("beat_cut_sync", [])
        if beat_sync:
            synced = sum(1 for s in beat_sync if s.get("synced"))
            results_md += f"\n### 🎵 Beat-Cut Sync\n\n{synced}/{len(beat_sync)} scene cuts are rhythmically aligned with beats.\n"

        progress(0.95, desc="📝 Generating script...")
        # Generate script using Few-Shot style transfer
        generated_script = generate_script(style)
        
        next_step = "✅ **Ready!** Go to **Step 2: The Studio** to start filming."
        
        progress(1.0, desc="✅ Analysis complete!")
        return metadata_display, results_md, generated_script, next_step
    except Exception as e:
        error_md = f"### ❌ Error\n\n`{str(e)}`\n\nPlease check the URL and try again."
        return "", error_md, "", ""

# --- Tab 2: The Studio ---
def studio_feedback_loop(frame):
    """
    Hybrid Director: Fast CV feedback on every frame + Slow VLM feedback every 3 seconds.
    """
    if frame is None:
        return frame, "⏳ Waiting for camera feed...", "Connect your webcam above to begin."

    if not app_state["skill_dir"]:
        return frame, "⚠️ No trend analyzed yet", "Go to **Step 1** first and analyze a TikTok trend."

    total = app_state["required_shots"]
    current = app_state["current_shot_idx"]

    if total > 0 and current >= total:
        return (
            frame,
            f"🎉 All {total} shots complete!",
            "All shots captured! Go to **Step 3: Final Output** to assemble your video."
        )

    if app_state["is_recording"]:
        return frame, "🔴 Recording...", f"Recording shot {current + 1}/{total} — hold still!"

    # Track time since studio started
    if app_state["studio_start_time"] is None:
        app_state["studio_start_time"] = time.time()
    
    current_time = time.time() - app_state["studio_start_time"]
    
    # ===== FAST LOOP: CV-based feedback (every frame, CPU) =====
    frame_rgb = frame  # Gradio provides RGB
    fast_feedback, new_prev_gray = get_fast_feedback(
        frame_rgb,
        app_state.get("pose_tracker"),
        app_state.get("reference_poses", []),
        app_state.get("camera_motion", []),
        current_time,
        app_state.get("prev_gray")
    )
    app_state["prev_gray"] = new_prev_gray
    
    # Fix 2: Depth feedback (if DepthEstimator is available)
    depth_feedback = ""
    if app_state.get("depth_estimator") and app_state.get("depth_profile"):
        try:
            depth_est = app_state["depth_estimator"]
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            user_depth = depth_est.estimate_depth(frame_bgr)
            if user_depth is not None:
                ref_profile = app_state["depth_profile"]
                # Find closest reference depth sample
                closest = min(ref_profile, key=lambda p: abs(p["time"] - current_time))
                ref_mean = closest["mean_depth"]
                user_mean = float(user_depth.mean())
                diff = user_mean - ref_mean
                if abs(diff) > 0.15:
                    direction = "closer" if diff > 0 else "further back"
                    depth_feedback = f"📏 Move {direction} to match reference depth"
        except Exception:
            pass
    
    if depth_feedback and fast_feedback and fast_feedback != "Analyzing...":
        fast_feedback = f"{fast_feedback} | {depth_feedback}"
    elif depth_feedback:
        fast_feedback = depth_feedback
    
    # ===== SLOW LOOP: VLM-based feedback (every 3 seconds, GPU) =====
    from config import DIRECTOR_VLM_INTERVAL
    now = time.time()
    vlm_feedback = app_state.get("last_vlm_feedback", "")
    
    if now - app_state.get("last_vlm_time", 0) > DIRECTOR_VLM_INTERVAL:
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        base64_img = encode_image_base64(frame_bgr)
        
        # B2: Scene-aware director prompt — select by current shot index
        system_prompt = None
        if app_state["skill_dir"]:
            try:
                from skill_manager import load_skill
                trend_name = os.path.basename(app_state["skill_dir"])
                frontmatter, markdown_body, ctx = load_skill(trend_name)
                
                # Try to load scene-specific prompts
                scene_prompts = ctx.get("scene_prompts", [])
                if scene_prompts and current < len(scene_prompts):
                    system_prompt = scene_prompts[current]
                else:
                    system_prompt = markdown_body
            except Exception as e:
                print("Failed to load skill:", e)
        
        # B1: Inject CV observations into VLM prompt
        cv_context = fast_feedback if (fast_feedback and fast_feedback != "Analyzing...") else None
        vlm_feedback = get_vlm_feedback(base64_img, system_prompt=system_prompt, cv_context=cv_context)
        app_state["last_vlm_feedback"] = vlm_feedback
        app_state["last_vlm_time"] = now
        
        # Check if perfect and trigger recording
        if "perfect" in vlm_feedback.lower() and app_state["skill_dir"] is not None:
            def start_recording():
                app_state["is_recording"] = True
                shot_idx = app_state["current_shot_idx"]
                cuts = app_state["cuts"]
                duration = cuts[shot_idx + 1] - cuts[shot_idx] if shot_idx < len(cuts) - 1 else 3.0
                os.makedirs("recorded_shots", exist_ok=True)
                output_path = os.path.join("recorded_shots", f"shot_{shot_idx}.mp4")
                print(f"Recording shot {shot_idx} ({duration:.1f}s)")
                capture_shot(duration, output_path)
                app_state["recorded_clips"].append(output_path)
                app_state["current_shot_idx"] += 1
                app_state["is_recording"] = False

            threading.Thread(target=start_recording).start()
            vlm_feedback = "✅ Perfect! Recording started..."
    
    # Build combined feedback display
    progress_text = f"📸 Shot {current + 1} / {total}"
    
    detail_parts = []
    if fast_feedback and fast_feedback != "Analyzing...":
        detail_parts.append(f"**⚡ CV Feedback (real-time):** {fast_feedback}")
    if vlm_feedback:
        detail_parts.append(f"**🧠 AI Director (style):** {vlm_feedback}")
    
    detail = "\n\n".join(detail_parts) if detail_parts else "Analyzing..."
    
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
<strong>Step 2:</strong> Upload your filmed clips for AI review, or use the webcam for <strong>hybrid real-time directing</strong>. 
The system uses two feedback loops: <strong>⚡ Fast (CPU)</strong> — pose tracking + camera motion at 10fps, 
and <strong>🧠 Slow (GPU)</strong> — VLM style/outfit analysis every 3 seconds.
</div>
""")

            # Shot info
            shot_info = gr.Markdown("⏳ Analyze a trend in Step 1 first to see shot requirements here.")

            gr.Markdown("### 📤 Upload Your Clips")
            gr.Markdown("Film your shots on your phone or camera, then upload them here. The AI will review each one.")
            
            with gr.Row():
                with gr.Column(scale=2):
                    clip_upload = gr.File(
                        label="Upload video clips (one per shot)",
                        file_count="multiple",
                        file_types=["video"]
                    )
                with gr.Column(scale=1):
                    upload_btn = gr.Button("📥 Add Clips & Get AI Review", variant="primary", size="lg")
            
            upload_status = gr.Markdown("")
            ai_review = gr.Markdown("")
            
            gr.Markdown("---")
            gr.Markdown("### 📹 Or Use Webcam — Hybrid Director")
            gr.Markdown("Real-time **⚡ CV feedback** (pose alignment, camera motion) on every frame + **🧠 VLM style check** every 3 seconds.")
            
            # B3: Pre-flight check
            with gr.Row():
                preflight_btn = gr.Button("🔍 Pre-Flight Check (check outfit & lighting first)", variant="secondary")
            preflight_result = gr.Markdown("")
            
            with gr.Row():
                with gr.Column(scale=2):
                    camera_input = gr.Image(
                        sources=["webcam"],
                        streaming=True,
                        label="Live Camera Feed",
                        height=350
                    )
                with gr.Column(scale=1):
                    shot_progress = gr.Textbox(
                        label="Progress",
                        value="Waiting...",
                        interactive=False
                    )
                    director_feedback = gr.Markdown("Webcam feedback will appear here.")

            # Upload handler — B4: includes CV pose/motion analysis
            def handle_clip_upload(files):
                if not files:
                    return "⚠️ No files uploaded.", ""
                
                if not app_state["skill_dir"]:
                    return "⚠️ Go to **Step 1** first and analyze a trend.", ""
                
                from analyzer import analyze_camera_motion, extract_reference_poses
                
                os.makedirs("recorded_shots", exist_ok=True)
                app_state["recorded_clips"] = []
                
                reviews = []
                for i, f in enumerate(files):
                    import shutil
                    dest = os.path.join("recorded_shots", f"shot_{i}.mp4")
                    shutil.copy(f.name, dest)
                    app_state["recorded_clips"].append(dest)
                    
                    clip_review_parts = []
                    
                    try:
                        # B4: CV analysis on the uploaded clip
                        # Pose comparison via DTW
                        ref_poses = app_state.get("reference_poses", [])
                        if ref_poses and app_state.get("pose_tracker"):
                            user_poses = extract_reference_poses(dest)
                            if user_poses:
                                score = app_state["pose_tracker"].compute_dtw_score(
                                    [p["normalized"] for p in user_poses],
                                    [p["normalized"] for p in ref_poses]
                                )
                                pct = max(0, min(100, int((1 - score / 5.0) * 100)))
                                clip_review_parts.append(f"🤸 Pose match: **{pct}%**")
                        
                        # Camera motion comparison
                        ref_motion = app_state.get("camera_motion", [])
                        if ref_motion:
                            user_motion = analyze_camera_motion(dest)
                            ref_types = set(m["motion"] for m in ref_motion if m["motion"] != "static")
                            user_types = set(m["motion"] for m in user_motion if m["motion"] != "static")
                            if ref_types:
                                matched = ref_types & user_types
                                clip_review_parts.append(
                                    f"🎥 Camera motion: {len(matched)}/{len(ref_types)} moves matched"
                                )
                        
                        # VLM review (middle frame)
                        cap = cv2.VideoCapture(dest)
                        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, total_frames // 2))
                        ret, frame = cap.read()
                        cap.release()
                        
                        if ret:
                            base64_img = encode_image_base64(frame)
                            system_prompt = None
                            if app_state["skill_dir"]:
                                try:
                                    from skill_manager import load_skill
                                    trend_name = os.path.basename(app_state["skill_dir"])
                                    _, markdown_body, ctx = load_skill(trend_name)
                                    # B2: Use scene-specific prompt if available
                                    scene_prompts = ctx.get("scene_prompts", [])
                                    if scene_prompts and i < len(scene_prompts):
                                        system_prompt = scene_prompts[i]
                                    else:
                                        system_prompt = markdown_body
                                except:
                                    pass
                            
                            cv_summary = " | ".join(clip_review_parts) if clip_review_parts else None
                            feedback = get_vlm_feedback(base64_img, system_prompt=system_prompt, cv_context=cv_summary)
                            clip_review_parts.append(f"🧠 AI: {feedback}")
                        
                    except Exception as e:
                        clip_review_parts.append(f"⚠️ Review error: {str(e)}")
                    
                    review_text = " | ".join(clip_review_parts) if clip_review_parts else "Review failed"
                    reviews.append(f"**Clip {i+1}** (`{os.path.basename(f.name)}`): {review_text}")
                
                app_state["current_shot_idx"] = len(files)
                total = app_state["required_shots"]
                uploaded = len(files)
                
                status = f"✅ **{uploaded} clips uploaded!**"
                if uploaded < total:
                    status += f"\n\n⚠️ You need {total} shots but only uploaded {uploaded}."
                status += "\n\n**→ Go to Step 3 to assemble your final video.**"
                
                review_md = "### 🎥 AI Director Review\n\n" + "\n\n".join(reviews) if reviews else ""
                return status, review_md
            
            # B3: Pre-flight environment check handler
            def preflight_check(frame):
                if frame is None:
                    return "⚠️ No webcam frame available. Enable your webcam first."
                if not app_state["skill_dir"]:
                    return "⚠️ Analyze a trend in Step 1 first."
                
                checks = []
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                
                # Lighting check (simple brightness)
                gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                brightness = float(gray.mean())
                if brightness < 60:
                    checks.append("❌ **Lighting**: Too dark — turn on more lights")
                elif brightness > 220:
                    checks.append("❌ **Lighting**: Too bright — reduce exposure")
                else:
                    checks.append("✅ **Lighting**: Good")
                
                # Pose detection check
                if app_state.get("pose_tracker") and app_state["pose_tracker"].available:
                    pose = app_state["pose_tracker"].extract_pose(frame)
                    if pose:
                        checks.append("✅ **Person detected**: Body visible in frame")
                    else:
                        checks.append("❌ **Person not detected**: Step into frame")
                
                # VLM outfit/setting check
                base64_img = encode_image_base64(frame_bgr)
                system_prompt = None
                if app_state["skill_dir"]:
                    try:
                        from skill_manager import load_skill
                        trend_name = os.path.basename(app_state["skill_dir"])
                        _, markdown_body, _ = load_skill(trend_name)
                        system_prompt = (
                            markdown_body + 
                            "\n\nThis is a PRE-FLIGHT CHECK. Evaluate ONLY outfit and background. "
                            "List what matches and what needs to change. Do NOT say 'Perfect' yet."
                        )
                    except:
                        pass
                
                vlm_check = get_vlm_feedback(base64_img, system_prompt=system_prompt)
                checks.append(f"🧠 **AI Assessment**: {vlm_check}")
                
                return "### 🔍 Pre-Flight Check Results\n\n" + "\n\n".join(checks)
            
            upload_btn.click(
                fn=handle_clip_upload,
                inputs=clip_upload,
                outputs=[upload_status, ai_review]
            )
            
            preflight_btn.click(
                fn=preflight_check,
                inputs=camera_input,
                outputs=preflight_result
            )

            # Webcam streaming handler
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