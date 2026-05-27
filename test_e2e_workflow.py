
import os
import sys
import time
import requests
from pathlib import Path

API_URL = "http://127.0.0.1:8010"

def wait_for_job(session_id: str, timeout: int = 300) -> dict:
    started = time.time()
    while time.time() - started < timeout:
        response = requests.get(f"{API_URL}/sessions/{session_id}")
        response.raise_for_status()
        session = response.json()
        job = session.get("active_job")
        
        if not job:
            return session
            
        if job.get("state") == "complete":
            return session
            
        if job.get("state") == "failed":
            raise RuntimeError(f"Job failed: {job.get('error')}")
            
        print(f"Waiting... job state: {job.get('state')}, progress: {job.get('progress_percent')}%")
        time.sleep(2)
        
    raise TimeoutError("Job timed out")

def run_e2e_test():
    print("1. Creating session...")
    response = requests.post(f"{API_URL}/sessions")
    response.raise_for_status()
    session = response.json()
    session_id = session["id"]
    print(f"Session created: {session_id}")
    
    print("\n2. Updating context...")
    context_data = {
        "destination": "Test Destination",
        "duration": "1 day",
        "places_visited": "Test Park",
        "language": "en"
    }
    response = requests.post(f"{API_URL}/sessions/{session_id}/context", json=context_data)
    response.raise_for_status()
    
    print("\n3. Uploading dummy media...")
    # Create a small dummy video file
    dummy_video = Path("dummy.mp4")
    if not dummy_video.exists():
        os.system("ffmpeg -f lavfi -i color=c=blue:s=320x240:d=2 -vf \"drawtext=text='Test Video':fontsize=30:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2\" -c:v libx264 dummy.mp4 < /dev/null > /dev/null 2>&1")
    
    with open(dummy_video, "rb") as f:
        files = [("files", ("dummy.mp4", f, "video/mp4"))]
        response = requests.post(f"{API_URL}/sessions/{session_id}/media", files=files)
        response.raise_for_status()
    print("Media uploaded.")
    
    print("\n4. Triggering story generation...")
    response = requests.post(f"{API_URL}/sessions/{session_id}/generate-story")
    response.raise_for_status()
    
    print("Waiting for story generation to complete...")
    session = wait_for_job(session_id)
    print("Story generated successfully.")
    
    print("\n5. Triggering render...")
    response = requests.post(f"{API_URL}/sessions/{session_id}/render")
    response.raise_for_status()
    
    print("Waiting for render to complete...")
    session = wait_for_job(session_id)
    
    final_video = session.get("final_video_url")
    if final_video:
        print(f"\nSUCCESS! Final video generated: {final_video}")
    else:
        print("\nFAILURE: Render job completed but no final video URL was found.")

if __name__ == "__main__":
    try:
        run_e2e_test()
    except Exception as e:
        print(f"Error during E2E test: {e}")
        sys.exit(1)
