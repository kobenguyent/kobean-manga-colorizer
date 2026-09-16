import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import io
import zipfile

import fitz
import requests


def run_export_formats_test():
    server = "http://127.0.0.1:8000"

    # Create a small 2-page test PDF
    pdf = fitz.open()
    import cv2
    import numpy as np

    for i in range(2):
        img = np.full((800, 600, 3), 255, dtype=np.uint8)
        cv2.putText(
            img, f"EXPORT TEST P{i + 1}", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2
        )
        tmp_img = f"/tmp/exp_page_{i}.png"
        cv2.imwrite(tmp_img, img)
        rect = fitz.Rect(0, 0, 600, 800)
        p = pdf.new_page(width=600, height=800)
        p.insert_image(rect, filename=tmp_img)
    pdf_path = "/tmp/test_export_doc.pdf"
    pdf.save(pdf_path)
    pdf.close()

    # 1. Upload
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            f"{server}/api/upload", files={"file": ("test_export_doc.pdf", f, "application/pdf")}
        )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    print(f"Uploaded test document! Session: {session_id}")

    # Colorize Page 0
    resp_prev = requests.post(
        f"{server}/api/colorize/preview",
        json={"session_id": session_id, "page_index": 0, "model_provider": "google_nano"},
    )
    assert resp_prev.status_code == 200
    print("Colorized Page 0 preview ready!")

    # 2. Test PDF Export
    resp_pdf = requests.post(f"{server}/api/export/{session_id}?format=pdf")
    assert resp_pdf.status_code == 200
    pdf_info = resp_pdf.json()
    assert pdf_info["filename"].endswith(".pdf")
    dl_pdf = requests.get(f"{server}{pdf_info['download_url']}")
    assert dl_pdf.status_code == 200
    doc_pdf = fitz.open(stream=dl_pdf.content, filetype="pdf")
    assert len(doc_pdf) == 2
    doc_pdf.close()
    print("PDF export option PASSED!")

    # 3. Test EPUB Export
    resp_epub = requests.post(f"{server}/api/export/{session_id}?format=epub")
    assert resp_epub.status_code == 200
    epub_info = resp_epub.json()
    assert epub_info["filename"].endswith(".epub")
    dl_epub = requests.get(f"{server}{epub_info['download_url']}")
    assert dl_epub.status_code == 200
    doc_epub = fitz.open(stream=dl_epub.content, filetype="epub")
    assert len(doc_epub) == 2
    doc_epub.close()
    print("EPUB export option PASSED!")

    # 4. Test ZIP Export
    resp_zip = requests.post(f"{server}/api/export/{session_id}?format=zip")
    assert resp_zip.status_code == 200
    zip_info = resp_zip.json()
    assert zip_info["filename"].endswith(".zip")
    dl_zip = requests.get(f"{server}{zip_info['download_url']}")
    assert dl_zip.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(dl_zip.content))
    assert len(zf.namelist()) == 2
    print("ZIP export option PASSED!")

    print("ALL FORMAT EXPORT TESTS PASSED PERFECTLY!")


def test_export_formats():
    run_export_formats_test()


if __name__ == "__main__":
    run_export_formats_test()
