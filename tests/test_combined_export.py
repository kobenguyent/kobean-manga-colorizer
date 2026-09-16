import json
import time

import fitz
import requests

BASE_URL = "http://127.0.0.1:8000"


def ensure_test_sessions():
    resp = requests.get(f"{BASE_URL}/api/sessions")
    sessions = resp.json().get("sessions", []) if resp.status_code == 200 else []
    needed = 2 - len(sessions)
    for _i in range(max(0, needed)):
        idx = len(sessions) + 1
        pdf_path = f"/tmp/sample_combined_vol_{idx}.pdf"
        doc = fitz.open()
        p = doc.new_page(width=400, height=600)
        p.insert_text((50, 100), f"Vol {idx} Manga Page", fontsize=16)
        doc.save(pdf_path)
        doc.close()
        with open(pdf_path, "rb") as f:
            up_resp = requests.post(
                f"{BASE_URL}/api/upload",
                files={"file": (f"sample_combined_vol_{idx}.pdf", f, "application/pdf")},
            )
        assert up_resp.status_code == 200
        resp = requests.get(f"{BASE_URL}/api/sessions")
        sessions = resp.json().get("sessions", [])
    return [sessions[0]["session_id"], sessions[1]["session_id"]]


def test_combined_export_progress_and_cancel():
    # 1. Get or create existing sessions
    session_ids = ensure_test_sessions()
    print(f"Testing with sessions: {session_ids}")

    # 2. Test start and progress stream
    print("\n--- Testing Progress Stream ---")
    start_resp = requests.post(
        f"{BASE_URL}/api/export/combined",
        json={"session_ids": session_ids, "format": "epub", "title": "Progress Test Manga"},
    )
    assert start_resp.status_code == 200, f"Failed to start: {start_resp.text}"
    job_info = start_resp.json()
    assert job_info["status"] == "started"
    job_id = job_info["job_id"]
    print(f"Export started with job_id: {job_id}")

    # Listen to SSE stream
    stream_url = f"{BASE_URL}/api/export/combined/stream/{job_id}"
    sse_resp = requests.get(stream_url, stream=True)
    assert sse_resp.status_code == 200

    received_progress = False
    completed = False
    download_url = None

    for line in sse_resp.iter_lines(decode_unicode=True):
        if not line:
            continue
        if line.startswith("data: "):
            data = json.loads(line[6:])
            print("SSE event:", data.get("type"), data.get("percent", ""), data.get("status", ""))
            if data.get("type") == "progress":
                received_progress = True
            elif data.get("type") == "completed":
                completed = True
                download_url = data.get("download_url")
                break
            elif data.get("type") == "error":
                raise RuntimeError(f"Export failed: {data}")

    assert received_progress, "Did not receive progress events!"
    assert completed, "Did not complete successfully!"
    print(f"Export completed! Download URL: {download_url}")

    # Verify download URL works
    dl_resp = requests.get(f"{BASE_URL}{download_url}")
    assert dl_resp.status_code == 200
    print(f"Verified download URL! Bytes received: {len(dl_resp.content)}")

    # 3. Test cancellation
    print("\n--- Testing Cancellation ---")
    start_resp2 = requests.post(
        f"{BASE_URL}/api/export/combined",
        json={"session_ids": session_ids, "format": "pdf", "title": "Cancel Test Manga"},
    )
    assert start_resp2.status_code == 200
    job_id2 = start_resp2.json()["job_id"]
    print(f"Started export for cancellation test with job_id: {job_id2}")

    # Immediately request cancel
    time.sleep(0.05)
    cancel_resp = requests.post(f"{BASE_URL}/api/export/combined/cancel/{job_id2}")
    assert cancel_resp.status_code == 200
    print("Sent cancel request, response:", cancel_resp.json())

    # Check status endpoint
    time.sleep(0.5)
    status_resp = requests.get(f"{BASE_URL}/api/export/combined/status/{job_id2}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    print("Job status after cancellation:", status_data)
    assert status_data["status"] == "cancelled"

    print("\n✅ All progress & cancellation tests PASSED successfully!")


if __name__ == "__main__":
    test_combined_export_progress_and_cancel()
