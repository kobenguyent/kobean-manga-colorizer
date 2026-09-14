import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import fitz
import numpy as np
import cv2
import requests
import time

def create_test_pdf(filepath: str, num_pages: int = 6):
    pdf = fitz.open()
    for i in range(num_pages):
        img = np.full((800, 600, 3), 255, dtype=np.uint8)
        cv2.rectangle(img, (50, 50), (550, 750), (0, 0, 0), 4)
        cv2.putText(img, f'MODEL TEST PAGE {i+1}', (60, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
        tmp_path = f'/tmp/switch_test_p{i}.png'
        cv2.imwrite(tmp_path, img)

        rect = fitz.Rect(0, 0, 600, 800)
        page = pdf.new_page(width=600, height=800)
        page.insert_image(rect, filename=tmp_path)
    pdf.save(filepath)
    pdf.close()

def run_test():
    sample_pdf = "/tmp/switch_test_manga.pdf"
    create_test_pdf(sample_pdf, num_pages=6)

    server_url = "http://127.0.0.1:8000"

    # 1. Upload file
    with open(sample_pdf, "rb") as f:
        resp = requests.post(f"{server_url}/api/upload", files={"file": ("switch_test.pdf", f, "application/pdf")})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    print(f"Uploaded PDF. Session ID: {session_id}")

    # 2. Start colorization with Model 1 (Google Nano)
    print("Starting Model 1 (Google Nano)...")
    start1 = requests.post(f"{server_url}/api/colorize/start", json={
        "session_id": session_id,
        "model_provider": "google_nano",
        "model_name": "nano-banana"
    })
    assert start1.status_code == 200

    time.sleep(0.3)

    # 3. Cancel midway
    print("Cancelling Model 1 midway...")
    cancel_resp = requests.post(f"{server_url}/api/colorize/cancel/{session_id}")
    assert cancel_resp.status_code == 200
    print("Cancelled successfully:", cancel_resp.json())

    # 4. Immediately select Model 2 (Apple Foundation) and start colorization
    print("Selecting Model 2 (Apple Foundation) and starting colorization...")
    start2 = requests.post(f"{server_url}/api/colorize/start", json={
        "session_id": session_id,
        "model_provider": "apple_foundation",
        "model_name": "apple-foundation-v1",
        "style": "anime_pastel"
    })
    assert start2.status_code == 200, f"Failed to start Model 2: {start2.text}"
    print("Model 2 started successfully!")

    # Poll session status until completed
    for _ in range(30):
        time.sleep(1)
        sess_info = requests.get(f"{server_url}/api/session/{session_id}").json()
        print(f"Status: {sess_info['status']} | Model: {sess_info.get('model_provider')} | Processed: {sess_info['processed_count']}/6")
        if sess_info["status"] == "completed":
            assert sess_info["model_provider"] == "apple_foundation"
            break

    print("CANCEL & NEW MODEL SELECTION TEST PASSED PERFECTLY!")

if __name__ == "__main__":
    run_test()
