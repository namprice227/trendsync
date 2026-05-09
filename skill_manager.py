import os
import json
import yaml
import numpy as np

SKILLS_DIR = os.path.join(".storyline", "skills")

def save_skill(trend_name: str, style_profile: dict, context: dict, reference_poses: list = None):
    """
    Saves the extracted trend style and context into a Skill archive.
    Creates .storyline/skills/{trend_name}/SKILL.md, context.json, and reference_poses.npy
    """
    skill_dir = os.path.join(SKILLS_DIR, trend_name)
    os.makedirs(skill_dir, exist_ok=True)
    
    # Save context (beats, cuts, audio_path, camera_motion)
    context_path = os.path.join(skill_dir, "context.json")
    with open(context_path, "w") as f:
        json.dump(context, f, indent=4)
    
    # Save reference poses as numpy array if available
    if reference_poses:
        poses_path = os.path.join(skill_dir, "reference_poses.json")
        with open(poses_path, "w") as f:
            json.dump(reference_poses, f)
        print(f"Saved {len(reference_poses)} reference poses to {poses_path}")
        
    # Build SKILL.md with YAML frontmatter
    frontmatter = {
        "name": trend_name,
        "description": f"Style profile for replicating {trend_name}.",
        "video_type": style_profile.get("video_type", "N/A"),
        "clothing": style_profile.get("clothing", "N/A"),
        "setting": style_profile.get("setting", "N/A"),
        "camera_angle": style_profile.get("camera_angle", "N/A"),
        "key_transition": style_profile.get("key_transition", "none"),
    }
    
    # Build camera motion summary for the director prompt
    camera_motion = context.get("camera_motion", [])
    motion_instructions = ""
    if camera_motion:
        # Summarize dominant motions
        motion_counts = {}
        for entry in camera_motion:
            m = entry["motion"]
            if m != "static":
                motion_counts[m] = motion_counts.get(m, 0) + 1
        if motion_counts:
            motion_list = ", ".join([f"{motion} ({count}x)" for motion, count in sorted(motion_counts.items(), key=lambda x: -x[1])])
            motion_instructions = f"\n- **Camera Movement**: The reference video uses these camera motions: {motion_list}. Guide the user to replicate them."
    
    narrative = style_profile.get("narrative", "")
    narrative_line = f"\n- **Video Narrative**: {narrative}" if narrative else ""
    
    recreation_tips = style_profile.get("recreation_tips", "")
    tips_line = f"\n- **Recreation Tips**: {recreation_tips}" if recreation_tips else ""
    
    markdown_body = f"""
# Director Prompt
You are an expert cinematographer directing a live user to recreate a TikTok trend.
Evaluate their live camera feed to ensure they match the following style:
- **Video Type**: {frontmatter.get('video_type', 'N/A')}
- **Clothing/Outfit**: {frontmatter['clothing']}
- **Setting/Environment**: {frontmatter['setting']}
- **Camera Angle/Framing**: {frontmatter['camera_angle']}
- **Key Transition**: {frontmatter.get('key_transition', 'none')}{narrative_line}{motion_instructions}{tips_line}

Give short, punchy feedback (e.g., 'Move left', 'Change your shirt', 'Fix the lighting', 'Pan right now').
If the framing and style are completely perfect, reply ONLY with the word "Perfect".
"""
    
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    with open(skill_md_path, "w") as f:
        f.write("---\n")
        yaml.dump(frontmatter, f, default_flow_style=False, sort_keys=False)
        f.write("---\n")
        f.write(markdown_body)
        
    return skill_dir

def load_skill(trend_name: str):
    """
    Loads a skill archive from .storyline/skills/{trend_name}/
    Returns (frontmatter, markdown_body, context)
    """
    skill_dir = os.path.join(SKILLS_DIR, trend_name)
    context_path = os.path.join(skill_dir, "context.json")
    skill_md_path = os.path.join(skill_dir, "SKILL.md")
    
    if not os.path.exists(skill_md_path):
        raise FileNotFoundError(f"Skill {trend_name} not found.")
        
    with open(context_path, "r") as f:
        context = json.load(f)
        
    with open(skill_md_path, "r") as f:
        content = f.read()
        
    # Parse YAML frontmatter
    parts = content.split("---")
    if len(parts) >= 3:
        frontmatter = yaml.safe_load(parts[1])
        markdown_body = parts[2].strip()
    else:
        frontmatter = {}
        markdown_body = content
        
    return frontmatter, markdown_body, context

def load_reference_poses(trend_name: str):
    """
    Loads the reference pose data from a Skill archive.
    Returns list of pose snapshots or empty list if not available.
    """
    skill_dir = os.path.join(SKILLS_DIR, trend_name)
    poses_path = os.path.join(skill_dir, "reference_poses.json")
    
    if not os.path.exists(poses_path):
        return []
    
    with open(poses_path, "r") as f:
        return json.load(f)
