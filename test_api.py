import sys
import json
import time
import shutil
import requests
import threading

API_BASE = "http://127.0.0.1:8000"

def listen_to_stream(job_id):
    try:
        # Import sseclient here to keep dependencies simple if user doesn't have it,
        # but we can also just parse raw SSE lines.
        import sseclient
        
        response = requests.get(f"{API_BASE}/execution-jobs/{job_id}/stream", stream=True)
        client = sseclient.SSEClient(response)
        
        for event in client.events():
            try:
                data = json.loads(event.data)
                event_type = data.get("type")
                payload = data.get("data", {})
                
                if event_type == "agent_turn":
                    print(f"\n🧠 Agent (Node: {payload.get('node')}):")
                    if payload.get('content'):
                        print(f"Thought: {payload.get('content')}")
                    for tc in payload.get('tool_calls', []):
                        print(f"🛠️  Calling Tool: {tc.get('name')} with args: {tc.get('args')}")
                elif event_type == "tool_result":
                    print(f"✅ Tool '{payload.get('tool_name')}' Result:")
                    print(payload.get('result')[:200] + ("..." if len(payload.get('result', '')) > 200 else ""))
                elif event_type == "sandbox_output":
                    # Print raw output chunks directly
                    stream = payload.get("stream", "stdout")
                    chunk = payload.get("chunk", "")
                    if stream == "stdout":
                        sys.stdout.write(chunk)
                    else:
                        sys.stderr.write(chunk)
                    sys.stdout.flush()
                elif event_type == "approval_required":
                    print(f"\n⚠️ APPROVAL REQUIRED:")
                    print(f"Agent wants to write to {payload.get('filepath')}")
                    print("--- Content ---")
                    print(payload.get('content'))
                    print("---------------")
                    
                    # Programmatically auto-approve for testing!
                    print("✅ Auto-approving request...")
                    requests.post(
                        f"{API_BASE}/execution-jobs/{job_id}/approval", 
                        json={"approved": True}
                    )
                elif event_type == "execution_result":
                    print(f"\n🏁 Execution finished (Success: {payload.get('success')})")
                elif event_type == "job_completed":
                    print("\n🎉 Job Completed!")
                    break
                elif event_type == "job_failed":
                    print(f"\n❌ Job Failed: {payload.get('error')}")
                    break
            except json.JSONDecodeError:
                pass
    except ImportError:
        print("Please install sseclient-py to run this script: pip install sseclient-py")

def main():
    # Use one of the existing repos from code_repo
    repo_to_test = "code_repo/test_repo"
    zip_path = "test_repo.zip"
    
    print(f"Zipping {repo_to_test}...")
    shutil.make_archive("test_repo", 'zip', repo_to_test)
    
    print("Submitting job to FastAPI server...")
    with open(zip_path, "rb") as f:
        files = {"repo_zip": ("test_repo.zip", f, "application/zip")}
        data = {
            "instruction": "Please find and execute the main script. If it fails, fix the code.",
            "chat_session_id": "test_session_1"
        }
        resp = requests.post(f"{API_BASE}/execution-jobs", files=files, data=data)
        
    if resp.status_code != 200:
        print("Failed to start job:", resp.text)
        return
        
    job_id = resp.json()["job_id"]
    print(f"✅ Job created: {job_id}\n")
    print("Listening to SSE stream...")
    
    # Start listening to the stream
    listen_to_stream(job_id)

if __name__ == "__main__":
    main()
