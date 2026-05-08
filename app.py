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
    "required_shots": 0,
    "current_shot_idx": 0,
    "recorded_clips": [],
    "is_recording": False,
    "cuts": [],
    "final_video_path": None
}

def process_trend_link(url):
    """Handler for Tab 1: Analyzer"""
    try:
        skill_dir, style, context = analyze_trend(url)
        app_state["skill_dir"] = skill_dir
        app_state["cuts"] = context["cuts"]

        # Calculate number of required shots based on cuts
        num_shots = len(context["cuts"]) - 1 if len(context["cuts"]) > 1 else 1
        app_state["required_shots"] = num_shots
        app_state["current_shot_idx"] = 0
        app_state["recorded_clips"] = []

        metadata_display = json.dumps(context, indent=2)
        status = f"Analysis Complete! Found {num_shots} required shots based on cuts."
        
        style_guide = f"### AI Style Guide\n* **What to wear:** {style.get('clothing', 'N/A')}\n* **Where to shoot:** {style.get('setting', 'N/A')}\n* **Camera Framing:** {style.get('camera_angle', 'N/A')}"
        
        # Generate script using Few-Shot style transfer
        generated_script = generate_script(style)
        
        return metadata_display, status, style_guide, generated_script
    except Exception as e:
        return f"Error: {str(e)}", "Failed to analyze.", "", ""

def studio_feedback_loop(frame):
    """
    Handler for Tab 2: The Studio.
    Takes a webcam frame from Gradio, sends it to VLM, and returns the frame + feedback text.
    """
    if frame is None:
        return frame, "Waiting for camera..."

    # Check if we've completed all shots
    if app_state["required_shots"] > 0 and app_state["current_shot_idx"] >= app_state["required_shots"]:
         return frame, "All shots completed! Go to the Render tab."

    if app_state["is_recording"]:
        return frame, "Recording in progress... please wait."

    # Process frame for VLM
    # OpenCV uses BGR, Gradio frames are RGB. Convert for encoding.
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

    # Get feedback (this is a blocking call, in a production app you'd run this asynchronously to not freeze the UI)
    feedback = get_vlm_feedback(base64_img, system_prompt=system_prompt)

    # Check if perfect and trigger recording
    if "perfect" in feedback.lower() and app_state["skill_dir"] is not None:
        def start_recording():
            app_state["is_recording"] = True
            shot_idx = app_state["current_shot_idx"]

            # Determine duration
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

        # Start recording in a background thread so the UI doesn't completely block
        threading.Thread(target=start_recording).start()
        feedback = "Perfect! Recording started..."

    status_text = f"Shot {app_state['current_shot_idx'] + 1} / {app_state['required_shots']} | Director: {feedback}"
    return frame, status_text

def render_project():
    """Handler for Tab 3: Render"""
    if not app_state["skill_dir"]:
        return None, "Error: No trend profile loaded. Go back to Step 1."

    if not app_state["recorded_clips"]:
        return None, "Error: No clips recorded. Go to The Studio."

    try:
        output_file = render_final_video(app_state["recorded_clips"], app_state["skill_dir"])
        app_state["final_video_path"] = output_file
        return output_file, "Render complete! Ready to post."
    except Exception as e:
        return None, f"Render failed: {str(e)}"

def judge_video():
    """Handler for Evaluation"""
    if not app_state.get("final_video_path"):
        return "Error: No final video found. Assemble it first."
    
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

# Build the Gradio UI
with gr.Blocks(title="TrendFlow AI") as demo:
    gr.Markdown("# 🎬 TrendFlow AI: The Autonomous TikTok Director & Editor")

    with gr.Tabs():
        # Tab 1: Analyzer
        with gr.Tab("Step 1: Trend Analyzer"):
            gr.Markdown("Paste a link to a trending TikTok/Reel to extract beats and cuts.")
            with gr.Row():
                url_input = gr.Textbox(label="TikTok/Reel URL")
                analyze_btn = gr.Button("Analyze Trend")

            with gr.Row():
                with gr.Column():
                    metadata_output = gr.Code(label="Extracted Context (context.json)", language="json")
                with gr.Column():
                    status_text_1 = gr.Textbox(label="Status", interactive=False)
                    style_guide_output = gr.Markdown("### AI Style Guide\n*(Run analysis to see advice)*")
                    script_output = gr.Textbox(label="Generated Script & Caption", interactive=False, lines=4)

            analyze_btn.click(
                fn=process_trend_link,
                inputs=url_input,
                outputs=[metadata_output, status_text_1, style_guide_output, script_output]
            )

        # Tab 2: The Studio
        with gr.Tab("Step 2: The Studio"):
            gr.Markdown("Turn on your camera. The AI Director will guide you and auto-record when the shot is perfect.")

            with gr.Row():
                # For hackathon demo purposes, we use a streaming Image component acting as a frame-by-frame processor.
                # gr.Image(sources=["webcam"]) provides a live camera feed.
                camera_input = gr.Image(sources=["webcam"], streaming=True, label="Live Camera Feed")

            director_feedback = gr.Textbox(label="AI Director Feedback", interactive=False, text_align="center")

            # The streaming interface continuously sends frames to the function
            camera_input.stream(
                fn=studio_feedback_loop,
                inputs=camera_input,
                outputs=[camera_input, director_feedback]
            )

        # Tab 3: Render Output
        with gr.Tab("Step 3: Final Output"):
            gr.Markdown("Assemble your captured shots into the final synced video and get AI evaluation.")
            render_btn = gr.Button("Assemble Final Video")

            status_text_3 = gr.Textbox(label="Render Status", interactive=False)
            final_video_output = gr.Video(label="Final Synced Video")
            
            judge_btn = gr.Button("Judge My Video")
            judge_output = gr.Textbox(label="Director's Evaluation", interactive=False, lines=4)

            render_btn.click(
                fn=render_project,
                inputs=None,
                outputs=[final_video_output, status_text_3]
            )
            judge_btn.click(
                fn=judge_video,
                inputs=None,
                outputs=judge_output
            )

if __name__ == "__main__":
    # Launch on 0.0.0.0 to allow external access (useful for instances/Spaces)
    demo.launch(server_name="0.0.0.0", server_port=7860, share=True)