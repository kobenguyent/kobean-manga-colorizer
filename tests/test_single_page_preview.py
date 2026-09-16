import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import fitz
import numpy as np
import requests


def create_preview_test_pdf(filepath: str):
    pdf = fitz.open()
    for i in range(4):
        img = np.full((800, 600, 3), 255, dtype=np.uint8)
        cv2.rectangle(img, (40, 40), (560, 760), (0, 0, 0), 4)
        cv2.putText(
            img, f"PREVIEW PAGE {i + 1}", (80, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2
        )
        tmp_path = f"/tmp/prev_p{i}.png"
        cv2.imwrite(tmp_path, img)

        rect = fitz.Rect(0, 0, 600, 800)
        page = pdf.new_page(width=600, height=800)
        page.insert_image(rect, filename=tmp_path)
    pdf.save(filepath)
    pdf.close()


def run_preview_test():
    sample_pdf = "/tmp/preview_manga_test.pdf"
    create_preview_test_pdf(sample_pdf)

    server_url = "http://127.0.0.1:8000"

    # 1. Upload
    with open(sample_pdf, "rb") as f:
        resp = requests.post(
            f"{server_url}/api/upload", files={"file": ("preview_manga.pdf", f, "application/pdf")}
        )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    print(f"Uploaded file! Session: {session_id}")

    # 2. Preview Page 0 (Google Nano)
    print("Testing single-page preview on Page 0 (Google Nano)...")
    prev_resp1 = requests.post(
        f"{server_url}/api/colorize/preview",
        json={
            "session_id": session_id,
            "page_index": 0,
            "model_provider": "google_nano",
            "style": "shonen_vivid",
        },
    )
    assert prev_resp1.status_code == 200, f"Preview page 0 failed: {prev_resp1.text}"
    print("Page 0 preview response:", prev_resp1.json())
    assert prev_resp1.json()["page_info"]["status"] == "colorized"

    # 3. Preview Page 2 (Apple AI)
    print("Testing single-page preview on Page 2 (Apple AI)...")
    prev_resp2 = requests.post(
        f"{server_url}/api/colorize/preview",
        json={
            "session_id": session_id,
            "page_index": 2,
            "model_provider": "apple_foundation",
            "style": "anime_pastel",
        },
    )
    assert prev_resp2.status_code == 200, f"Preview page 2 failed: {prev_resp2.text}"
    print("Page 2 preview response:", prev_resp2.json())
    assert prev_resp2.json()["page_info"]["status"] == "colorized"

    print("SINGLE PAGE PREVIEW TEST PASSED PERFECTLY!")


def test_single_page_preview():
    run_preview_test()


if __name__ == "__main__":
    run_preview_test()
