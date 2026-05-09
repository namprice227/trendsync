from gradio_client import Client
import os

def test_ui():
    app_url = os.environ.get("TRENDFLOW_GRADIO_URL", "http://localhost:7860")
    print(f"Connecting to Gradio app at {app_url}...")
    try:
        client = Client(app_url)
        print("Connected successfully!")
        
        # Test 1: Check available endpoints
        endpoints = client.view_api(all_endpoints=True, return_format="dict")
        print(f"Available endpoints: {list(endpoints.keys())}")
        
        # Test 2: Call safe endpoints that do not download videos or clear local work.
        print("\nTesting /render_project without app state...")
        render_result = client.predict(api_name="/render_project")
        print("render_project:", render_result)

        print("\nTesting /judge_video without app state...")
        judge_result = client.predict(api_name="/judge_video")
        print("judge_video:", judge_result)

        print("\nTesting /handle_clip_upload with no files...")
        upload_result = client.predict([], api_name="/handle_clip_upload")
        print("handle_clip_upload:", upload_result)

        print("\nTesting /preflight_check with no frame...")
        preflight_result = client.predict(None, api_name="/preflight_check")
        print("preflight_check:", preflight_result)

        print("\nUI Backend test completed.")
        
    except Exception as e:
        print(f"Failed to connect or test UI: {e}")

if __name__ == "__main__":
    test_ui()
