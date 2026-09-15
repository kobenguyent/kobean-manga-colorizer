import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import fitz
import numpy as np
import cv2
import requests
import time

def create_large_test_pdf(filepath: str, num_pages: int = 10):
    pdf = fitz.open()
    for i in range(num_pages):
        img = np.full((800, 600, 3), 255, dtype=np.uint8)
        cv2.rectangle(img, (50, 50), (550, 750), (0, 0, 0), 4)
        cv2.putText(img, f'PAGE {i+1}', (100, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
        tmp_path = f'/tmp/cancel_test_p{i}.png'
        cv2.imwrite(tmp_path, img)

        rect = fitz.Rect(0, 0, 600, 800)
        page = pdf.new_page(width=600, height=800)
        page.insert_image(rect, filename=tmp_path)
    pdf.save(filepath)
    pdf.close()

def run_cancel_test():
    sample_pdf = "/tmp/cancel_test_manga.pdf"
    create_large_test_pdf(sample_pdf, num_pages=25)

    server_url = "http://127.0.0.1:8000"

    # 1. Upload
    with open(sample_pdf, "rb") as f:
        resp = requests.post(f"{server_url}/api/upload", files={"file": ("cancel_test.pdf", f, "application/pdf")})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    print(f"Uploaded 25-page test PDF! Session: {session_id}")

    # 2. Start Colorization
    requests.post(f"{server_url}/api/colorize/start", json={
        "session_id": session_id,
        "model_provider": "local_smart"
    })
    print("Colorization started...")

    # Wait until in-flight, then trigger cancel
    time.sleep(0.08)
    print("Sending cancel request...")
    cancel_resp = requests.post(f"{server_url}/api/colorize/cancel/{session_id}")
    assert cancel_resp.status_code == 200
    print("Cancel API response:", cancel_resp.json())


    # Wait and verify session status becomes 'cancelled'
    time.sleep(1.5)
    sess_info = requests.get(f"{server_url}/api/session/{session_id}").json()
    print(f"Final session status: {sess_info['status']}, Processed count: {sess_info['processed_count']}/10")

    assert sess_info["status"] == "cancelled", f"Expected cancelled status, got {sess_info['status']}"
    assert sess_info["processed_count"] < 10, "Task should have stopped before colorizing all 10 pages"
    print("CANCEL FUNCTIONALITY TEST PASSED SUCCESSFULLY!")

def test_cancel():
    run_cancel_test()

if __name__ == "__main__":
    run_cancel_test()
