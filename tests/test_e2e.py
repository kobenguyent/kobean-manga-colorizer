import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import fitz
import numpy as np
import cv2
import requests
import time

def create_sample_manga_pdf(filepath: str, num_pages: int = 3):
    """Creates a sample PDF with black and white manga pages for testing."""
    pdf = fitz.open()
    for i in range(num_pages):
        # Create a 600x800 white canvas
        img = np.full((800, 600, 3), 255, dtype=np.uint8)
        # Draw panels & line art
        cv2.rectangle(img, (30, 30), (570, 360), (0, 0, 0), 4)
        cv2.rectangle(img, (30, 380), (270, 750), (0, 0, 0), 4)
        cv2.rectangle(img, (290, 380), (570, 750), (0, 0, 0), 4)

        # Draw character stick figure & text
        cv2.circle(img, (300, 180), 40, (0, 0, 0), 3)
        cv2.line(img, (300, 220), (300, 310), (0, 0, 0), 4)
        cv2.putText(img, f'MANGA CHAPTER {i+1}', (50, 80), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 3)
        cv2.putText(img, f'PAGE {i+1}', (320, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)

        tmp_img_path = f'/tmp/manga_test_p{i}.png'
        cv2.imwrite(tmp_img_path, img)

        rect = fitz.Rect(0, 0, 600, 800)
        page = pdf.new_page(width=600, height=800)
        page.insert_image(rect, filename=tmp_img_path)

    pdf.save(filepath)
    pdf.close()
    print(f"Created sample PDF at {filepath}")

def run_test():
    sample_pdf = "/tmp/sample_manga_volume.pdf"
    create_sample_manga_pdf(sample_pdf)

    server_url = "http://127.0.0.1:8000"

    # 1. Test Upload
    print("Uploading PDF to server...")
    with open(sample_pdf, "rb") as f:
        resp = requests.post(f"{server_url}/api/upload", files={"file": ("sample_manga.pdf", f, "application/pdf")})
    
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    session_data = resp.json()
    session_id = session_data["session_id"]
    print(f"Uploaded successfully! Session ID: {session_id}, Pages: {session_data['total_pages']}")

    # 2. Test Colorize
    print("Starting colorization worker (Local Smart Engine)...")
    colorize_payload = {
        "session_id": session_id,
        "model_provider": "local_smart",
        "model_name": "local-lab-v1",
        "style": "shonen_vivid",
        "saturation": 1.3,
        "contrast": 1.1,
        "line_preserve": 0.85
    }
    resp = requests.post(f"{server_url}/api/colorize/start", json=colorize_payload)
    assert resp.status_code == 200, f"Colorize start failed: {resp.text}"

    # Poll session status until completed
    for _ in range(30):
        time.sleep(1)
        sess_resp = requests.get(f"{server_url}/api/session/{session_id}")
        sess_info = sess_resp.json()
        print(f"Status: {sess_info['status']} | Processed: {sess_info['processed_count']}/{sess_info['total_pages']}")
        if sess_info["status"] == "completed":
            break

    # 3. Test Export
    print("Exporting colorized PDF...")
    export_resp = requests.post(f"{server_url}/api/export/{session_id}")
    assert export_resp.status_code == 200, f"Export failed: {export_resp.text}"
    export_data = export_resp.json()
    download_url = export_data["download_url"]
    print(f"Export successful! Download URL: {download_url}")

    # Download file
    dl_resp = requests.get(f"{server_url}{download_url}")
    assert dl_resp.status_code == 200, "Download failed"
    out_pdf_path = "/tmp/colorized_manga_output.pdf"
    with open(out_pdf_path, "wb") as f:
        f.write(dl_resp.content)

    # Verify generated PDF
    out_doc = fitz.open(out_pdf_path)
    print(f"Verified output PDF: {len(out_doc)} pages")
    out_doc.close()
    print("E2E INTEGRATION TEST PASSED SUCCESSFULLY!")

def test_e2e():
    run_test()

if __name__ == "__main__":
    run_test()
