import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import cv2
import numpy as np
import requests

def create_sample_png(filepath: str):
    img = np.full((700, 500, 3), 250, dtype=np.uint8)
    cv2.rectangle(img, (30, 30), (470, 670), (0, 0, 0), 4)
    cv2.putText(img, 'SINGLE IMAGE TEST', (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    cv2.imwrite(filepath, img)
    print(f"Created sample PNG at {filepath}")

def run_test():
    sample_png = "/tmp/sample_manga_page.png"
    create_sample_png(sample_png)

    server_url = "http://127.0.0.1:8000"

    # 1. Upload PNG image
    with open(sample_png, "rb") as f:
        resp = requests.post(f"{server_url}/api/upload", files={"file": ("sample_manga_page.png", f, "image/png")})
    assert resp.status_code == 200, f"Image upload failed: {resp.text}"
    session_data = resp.json()
    session_id = session_data["session_id"]
    print(f"Uploaded PNG successfully! Session ID: {session_id}, Total Pages: {session_data['total_pages']}")

    # 2. Preview with ResNeXt Generator
    prev_resp = requests.post(f"{server_url}/api/colorize/preview", json={
        "session_id": session_id,
        "page_index": 0,
        "model_provider": "resnext_generator"
    })
    assert prev_resp.status_code == 200, f"Preview failed: {prev_resp.text}"
    print("Colorized preview URL:", prev_resp.json()["colorized_url"])

    # 3. Export single image
    export_resp = requests.post(f"{server_url}/api/export/{session_id}")
    assert export_resp.status_code == 200, f"Export failed: {export_resp.text}"
    export_data = export_resp.json()
    print("Export result:", export_data)

    dl = requests.get(f"{server_url}{export_data['download_url']}")
    assert dl.status_code == 200
    print("IMAGE FILE UPLOAD & COLORIZATION TEST PASSED PERFECTLY!")

if __name__ == "__main__":
    run_test()
