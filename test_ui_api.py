from gradio_client import Client
import os

def test_ui():
    print("Connecting to Gradio app at http://localhost:7860...")
    try:
        client = Client("http://localhost:7860")
        print("Connected successfully!")
        
        # Test 1: Check available endpoints
        endpoints = client.view_api(all_endpoints=True, return_format="dict")
        print(f"Available endpoints: {list(endpoints.keys())}")
        
        # Test 2: Try to call process_trend_link with a dummy URL (might fail but we check the error)
        # We use a non-existent URL to see if the error handling in app.py works
        print("\nTesting /process_trend_link with dummy URL...")
        try:
            # According to app.py, process_trend_link returns 4 outputs
            result = client.predict(
                url="https://www.tiktok.com/@invalid/video/000",
                api_name="/process_trend_link"
            )
            print("Result received (unexpectedly success?):", result)
        except Exception as e:
            print(f"Caught expected error or status from process_trend_link: {str(e)}")
            # If it's a validation error or "Please check the URL", it means the UI logic is working
            if "Error" in str(e) or "invalid" in str(e).lower():
                print("UI Error handling seems to be working.")

        print("\nUI Backend test completed.")
        
    except Exception as e:
        print(f"Failed to connect or test UI: {e}")

if __name__ == "__main__":
    test_ui()
