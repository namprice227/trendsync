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
    
    # Save reference poses if available
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

    # B2: Generate per-scene director prompts
    cuts = context.get("cuts", [])
    scene_prompts = _generate_scene_prompts(style_profile, cuts, camera_motion, narrative)
    if scene_prompts:
        context["scene_prompts"] = scene_prompts

    # Save context (beats, cuts, audio_path, camera_motion, scene_prompts)
    context_path = os.path.join(skill_dir, "context.json")
    with open(context_path, "w") as f:
        json.dump(context, f, indent=4)
        
    return skill_dir

def _generate_scene_prompts(style_profile: dict, cuts: list, camera_motion: list, narrative: str) -> list:
    """
    B2: Generates shot-specific director prompts.
    Each shot gets a customized prompt based on its position in the narrative.
    """
    if len(cuts) < 2:
        return []

    num_shots = len(cuts) - 1
    prompts = []

    video_type = style_profile.get("video_type", "")
    clothing = style_profile.get("clothing", "N/A")
    setting = style_profile.get("setting", "N/A")
    transition = style_profile.get("key_transition", "none")
    camera_angle = style_profile.get("camera_angle", "N/A")

    for i in range(num_shots):
        shot_start = cuts[i]
        shot_end = cuts[i + 1] if i + 1 < len(cuts) else cuts[-1] + 3.0
        duration = shot_end - shot_start

        # Determine shot position in narrative
        if i == 0:
            position = "opening"
        elif i == num_shots - 1:
            position = "final/reveal"
        else:
            position = f"middle (shot {i+1})"

        # Find camera motion for this shot's timeframe
        shot_motions = [m["motion"] for m in camera_motion
                        if m["time"] >= shot_start and m["time"] < shot_end and m["motion"] != "static"]
        motion_str = f"Camera should: {', '.join(set(shot_motions))}" if shot_motions else "Camera: static"

        # Build shot-specific prompt
        prompt = (
            f"You are directing Shot {i+1}/{num_shots} ({position}, {duration:.1f}s).\n"
            f"Video type: {video_type}. {motion_str}.\n"
        )

        # Customize based on position in transition videos
        is_transition = any(t in video_type.lower() for t in ["transition", "reveal", "transform"])
        if is_transition:
            if i < num_shots // 2:
                prompt += f"This is a BEFORE shot. The user should wear: the FIRST outfit from '{clothing}'.\n"
            elif i == num_shots // 2 and transition.lower() != "none":
                prompt += f"This is the TRANSITION shot. Expected: {transition}.\n"
            else:
                prompt += f"This is an AFTER/REVEAL shot. The user should wear: the SECOND outfit from '{clothing}'.\n"
        else:
            prompt += f"Outfit: {clothing}. Setting: {setting}. Framing: {camera_angle}.\n"

        prompt += (
            "Give short feedback. If everything matches, reply ONLY with 'Perfect'."
        )
        prompts.append(prompt)

    print(f"Generated {len(prompts)} scene-specific director prompts")
    return prompts

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
