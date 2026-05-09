from config import VLLM_API_URL, SCRIPT_MODEL, SCRIPT_TIMEOUT, vlm_request_with_retry

def generate_script(style_profile: dict, model_name: str = None):
    if model_name is None:
        model_name = SCRIPT_MODEL
    """
    Uses Few-Shot Style Transfer to generate a TikTok script and caption based on the visual style.
    Falls back to a mock if vLLM isn't running.
    """
    clothing = style_profile.get("clothing", "casual")
    setting = style_profile.get("setting", "everyday")
    
    system_prompt = (
        "You are an expert TikTok scriptwriter and copywriter. "
        "Your task is to write a short video script and caption matching a specific visual style. "
        "Here are some examples:\n"
        "Input Style: Clothing: Streetwear, Setting: Night city street\n"
        "Output:\n"
        "Caption: Night runs hit different 🌃👟 #streetwear #nightvibes\n"
        "Script/Hook: 'You asked for the fit breakdown, here it is...'\n\n"
        "Input Style: Clothing: Cozy sweater, Setting: Coffee shop\n"
        "Output:\n"
        "Caption: Sunday morning slow living ☕️📖 #cozy #vlog\n"
        "Script/Hook: 'Come spend a slow Sunday morning with me...'\n\n"
        "Now, generate a Script and Caption for the following style:\n"
        f"Input Style: Clothing: {clothing}, Setting: {setting}\n"
        "Reply ONLY with the Caption and Script/Hook format shown above."
    )
    
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": "Generate the script and caption."
            }
        ],
        "max_tokens": 200,
        "chat_template_kwargs": {"enable_thinking": False}
    }
    
    try:
        data = vlm_request_with_retry(VLLM_API_URL, payload, timeout=SCRIPT_TIMEOUT)
        content = data['choices'][0]['message']['content'].strip()
        # Strip <think> blocks if present
        import re
        content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
        return content
    except Exception as e:
        print(f"Scriptwriter API failed (falling back to mock): {str(e)}")
        return (
            f"Caption: Just vibing in my {clothing} 🎬✨ #trend #viral\n"
            f"Script/Hook: 'Wait for the beat drop...'"
        )

if __name__ == "__main__":
    # Test
    print(generate_script({"clothing": "suit", "setting": "office"}))
