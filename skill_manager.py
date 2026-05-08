import os
import json
import yaml

SKILLS_DIR = os.path.join(".storyline", "skills")

def save_skill(trend_name: str, style_profile: dict, context: dict):
    """
    Saves the extracted trend style and context into a Skill archive.
    Creates .storyline/skills/{trend_name}/SKILL.md and context.json
    """
    skill_dir = os.path.join(SKILLS_DIR, trend_name)
    os.makedirs(skill_dir, exist_ok=True)
    
    # Save context (beats, cuts, audio_path)
    context_path = os.path.join(skill_dir, "context.json")
    with open(context_path, "w") as f:
        json.dump(context, f, indent=4)
        
    # Build SKILL.md with YAML frontmatter
    frontmatter = {
        "name": trend_name,
        "description": f"Style profile for replicating {trend_name}.",
        "clothing": style_profile.get("clothing", "N/A"),
        "setting": style_profile.get("setting", "N/A"),
        "camera_angle": style_profile.get("camera_angle", "N/A")
    }
    
    markdown_body = f"""
# Director Prompt
You are an expert cinematographer directing a live user.
Evaluate their live camera feed to ensure they match the following style:
- **Clothing/Outfit**: {frontmatter['clothing']}
- **Setting/Environment**: {frontmatter['setting']}
- **Camera Angle/Framing**: {frontmatter['camera_angle']}

Give short, punchy feedback (e.g., 'Move left', 'Change your shirt', 'Fix the lighting').
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
