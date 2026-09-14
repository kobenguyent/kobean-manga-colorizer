import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import zipfile
import cv2
import numpy as np
import requests
import time

def create_sample_manga_epub(filepath: str):
    """Creates a sample .epub zip archive with images and HTML content."""
    with zipfile.ZipFile(filepath, 'w') as zf:
        # Create 2 B&W images
        for i in range(2):
            img = np.full((700, 500, 3), 255, dtype=np.uint8)
            cv2.rectangle(img, (20, 20), (480, 680), (0, 0, 0), 4)
            cv2.putText(img, f'EPUB MANGA PAGE {i+1}', (40, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
            cv2.circle(img, (250, 350), 60, (0, 0, 0), 4)
            
            img_bytes = cv2.imencode('.png', img)[1].tobytes()
            zf.writestr(f'OEBPS/images/page_{i+1:02d}.png', img_bytes)

        # Standard EPUB structure files
        zf.writestr('mimetype', 'application/epub+zip')
        zf.writestr('META-INF/container.xml', '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        zf.writestr('OEBPS/content.opf', '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0"><metadata><title>Sample Manga</title></metadata><manifest><item id="img1" href="images/page_01.png" media-type="image/png"/><item id="img2" href="images/page_02.png" media-type="image/png"/></manifest></package>')

    print(f"Created sample EPUB at {filepath}")

def run_epub_test():
    sample_epub = "/tmp/sample_manga.epub"
    create_sample_manga_epub(sample_epub)

    server_url = "http://127.0.0.1:8000"

    # 1. Upload EPUB
    with open(sample_epub, "rb") as f:
        resp = requests.post(f"{server_url}/api/upload", files={"file": ("sample_manga.epub", f, "application/epub+zip")})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    print(f"EPUB Uploaded! Session: {session_id}, Pages: {resp.json()['total_pages']}")

    # 2. Colorize
    requests.post(f"{server_url}/api/colorize/start", json={
        "session_id": session_id,
        "model_provider": "local_smart",
        "style": "anime_pastel"
    })

    # Poll status
    for _ in range(30):
        time.sleep(1)
        sess_info = requests.get(f"{server_url}/api/session/{session_id}").json()
        if sess_info["status"] == "completed":
            break

    # 3. Export EPUB
    exp = requests.post(f"{server_url}/api/export/{session_id}").json()
    print("EPUB Export URL:", exp["download_url"])

    out_epub = "/tmp/colorized_manga_output.epub"
    dl = requests.get(f"{server_url}{exp['download_url']}")
    with open(out_epub, "wb") as f:
        f.write(dl.content)

    # Verify EPUB zip contents
    with zipfile.ZipFile(out_epub, 'r') as zf:
        names = zf.namelist()
        assert 'OEBPS/images/page_01.png' in names
        assert 'OEBPS/images/page_02.png' in names
    print("EPUB INTEGRATION TEST PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_epub_test()
