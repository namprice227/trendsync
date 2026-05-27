
import os
import sys
from llm_provider import LLMProvider

def test_llm():
    print(f"Testing LLM Provider: {os.environ.get('TRIPSTORY_LLM_PROVIDER', 'default')}")
    provider = LLMProvider()
    print(f"Configured: {provider.configured}")
    print(f"Base URL: {provider.base_url}")
    print(f"Model: {provider.model}")
    
    if not provider.configured:
        print("LLM is not configured. Local fallback will be used.")
        return

    messages = [{"role": "user", "content": "Hello, this is a test. Please respond with 'OK' if you can read this."}]
    try:
        response = provider.chat(messages, max_tokens=100)
        print(f"Response: '{response}'")
        if response == "":
            print("Warning: Received empty response from provider.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_llm()
