import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import fitz
import numpy as np
import cv2
import requests

def create_manga_test_page(filepath: str):
    pdf = fitz.open()
    img = np.full((800, 600, 3), 250, dtype=np.uint8)
    cv2.rectangle(img, (50, 50), (550, 750), (0, 0, 0), 4)
    cv2.putText(img, 'RESNEXT GENERATOR TEST', (60, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    tmp_path = '/tmp/resnext_p0.png'
    cv2.imwrite(tmp_path, img)

    rect = fitz.Rect(0, 0, 600, 800)
    page = pdf.new_page(width=600, height=800)
    page.insert_image(rect, filename=tmp_path)
    pdf.save(filepath)
    pdf.close()

def run_resnext_test():
    sample_pdf = "/tmp/resnext_manga_test.pdf"
    create_manga_test_page(sample_pdf)

    server_url = "http://127.0.0.1:8000"

    # 1. Upload
    with open(sample_pdf, "rb") as f:
        resp = requests.post(f"{server_url}/api/upload", files={"file": ("resnext_test.pdf", f, "application/pdf")})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    print(f"Uploaded file! Session: {session_id}")

    # 2. Preview using ResNeXt Generator
    print("Testing single-page preview with ResNeXt Deep Generator Network...")
    prev_resp = requests.post(f"{server_url}/api/colorize/preview", json={
        "session_id": session_id,
        "page_index": 0,
        "model_provider": "resnext_generator",
        "model_name": "resnext-50-manga",
        "style": "shonen_vivid"
    })
    assert prev_resp.status_code == 200, f"ResNeXt preview failed: {prev_resp.text}"
    result_data = prev_resp.json()
    print("ResNeXt Generator Response:", result_data)

    assert result_data["status"] == "success"
    assert "ResNeXt" in result_data["engine"]
    print("RESNEXT GENERATOR STAGE TEST PASSED PERFECTLY!")

def test_resnext_generator():
    run_resnext_test()

if __name__ == "__main__":
    run_resnext_test()

