from fastmcp import FastMCP
from analyzer import analyze_trend
from renderer import render_final_video
from evaluator import evaluate_final_video
from scriptwriter import generate_script
import os
import json

# Create an MCP server
mcp = FastMCP("TrendFlowAI")

@mcp.tool()
def extract_trend_skill(url: str) -> str:
    """
    Downloads a TikTok/Reel from the URL, extracts audio, beats, and cuts, and generates a style/skill profile.
    Returns the path to the extracted skill directory.
    """
    try:
        skill_dir, _, _ = analyze_trend(url, output_dir="temp")
        return f"Trend successfully analyzed and saved to: {skill_dir}"
    except Exception as e:
        return f"Failed to analyze trend: {str(e)}"

@mcp.tool()
def render_video(clip_paths_csv: str, skill_dir: str) -> str:
    """
    Assembles a list of user-recorded video clips (comma-separated paths) into a final trend video,
    using the beat-syncing rules from the specified skill directory.
    Returns the path to the rendered video.
    """
    try:
        clips = [c.strip() for c in clip_paths_csv.split(',')]
        output_file = render_final_video(clips, skill_dir)
        return f"Video perfectly synced and rendered at: {output_file}"
    except Exception as e:
        return f"Failed to render video: {str(e)}"

@mcp.tool()
def evaluate_rendered_video(video_path: str, skill_dir: str) -> str:
    """
    Evaluates the final rendered video against the intended style profile from the skill directory.
    Returns the AI Director's score and critique.
    """
    try:
        from skill_manager import load_skill
        trend_name = os.path.basename(skill_dir)
        frontmatter, _, _ = load_skill(trend_name)
        
        feedback = evaluate_final_video(video_path, frontmatter)
        return feedback
    except Exception as e:
        return f"Failed to evaluate video: {str(e)}"

@mcp.tool()
def generate_trend_script(skill_dir: str) -> str:
    """
    Generates a TikTok script and viral caption based on the style profile
    extracted from the given skill directory.
    Returns the generated script and caption text.
    """
    try:
        from skill_manager import load_skill
        trend_name = os.path.basename(skill_dir)
        frontmatter, _, _ = load_skill(trend_name)
        
        script = generate_script(frontmatter)
        return script
    except Exception as e:
        return f"Failed to generate script: {str(e)}"

if __name__ == "__main__":
    # Start the MCP stdio server
    mcp.run()
