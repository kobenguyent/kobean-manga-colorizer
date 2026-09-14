import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import fitz
from PIL import Image
import requests
import zipfile
import io

SERVER_URL = "http://127.0.0.1:8000"

def create_sample_pdf(filepath: str, title: str, num_pages: int = 2):
    doc = fitz.open()
    for i in range(num_pages):
        img = Image.new("RGB", (600, 800), color=(255, 255, 255))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.rectangle([50, 50, 550, 750], outline=(0, 0, 0), width=3)
        draw.text((100, 100), f"{title} - Page {i+1}", fill=(0, 0, 0))
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        
        pdf_img = fitz.open(stream=img_bytes.getvalue(), filetype="png")
        rect = pdf_img[0].rect
        pdf_page = doc.new_page(width=rect.width, height=rect.height)
        pdf_page.insert_image(rect, stream=img_bytes.getvalue())
        pdf_img.close()
    
    doc.save(filepath)
    doc.close()

def create_sample_epub(filepath: str, title: str, num_pages: int = 2):
    with zipfile.ZipFile(filepath, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        z.writestr('META-INF/container.xml', '''<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>''')
        manifest = ['<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>']
        spine = []
        for i in range(num_pages):
            img = Image.new("RGB", (600, 800), color=(255, 255, 255))
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            draw.rectangle([50, 50, 550, 750], outline=(0, 0, 0), width=3)
            draw.text((100, 100), f"{title} - EPUB Page {i+1}", fill=(0, 0, 0))
            img_bytes = io.BytesIO()
            img.save(img_bytes, format="PNG")
            
            img_name = f"page_{i+1}.png"
            z.writestr(f"OEBPS/images/{img_name}", img_bytes.getvalue())
            manifest.append(f'<item id="img_{i+1}" href="images/{img_name}" media-type="image/png"/>')
            
            xhtml = f'<html><body><img src="images/{img_name}"/></body></html>'
            z.writestr(f"OEBPS/page_{i+1}.xhtml", xhtml)
            manifest.append(f'<item id="page_{i+1}" href="page_{i+1}.xhtml" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="page_{i+1}"/>')

        opf = f'''<?xml version="1.0"?>
<package version="2.0" xmlns="http://www.idpf.org/2007/opf" unique-identifier="BookId">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:identifier id="BookId">urn:uuid:test</dc:identifier>
  </metadata>
  <manifest>{"".join(manifest)}</manifest>
  <spine>{"".join(spine)}</spine>
</package>'''
        z.writestr("OEBPS/content.opf", opf)

def run_tests():
    print("--- 1. Creating sample PDF and EPUB ---")
    pdf_path = "/tmp/test_vol1.pdf"
    epub_path = "/tmp/test_vol2.epub"
    create_sample_pdf(pdf_path, "Vol 1", num_pages=2)
    create_sample_epub(epub_path, "Vol 2", num_pages=2)

    print("--- 2. Uploading multiple files simultaneously to /api/upload ---")
    with open(pdf_path, "rb") as f1, open(epub_path, "rb") as f2:
        files = [
            ("files", ("test_vol1.pdf", f1, "application/pdf")),
            ("files", ("test_vol2.epub", f2, "application/epub+zip"))
        ]
        resp = requests.post(f"{SERVER_URL}/api/upload", files=files)

    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    data = resp.json()
    print("Upload response keys:", list(data.keys()))
    assert "batch_id" in data, "Missing batch_id"
    assert data["total_files"] == 2, f"Expected 2 files, got {data.get('total_files')}"
    assert len(data["sessions"]) == 2, f"Expected 2 sessions in summary, got {len(data['sessions'])}"
    print("Uploaded 2 files! Sessions:", [s["filename"] for s in data["sessions"]])

    session_ids = [s["session_id"] for s in data["sessions"]]
    pdf_session_id = session_ids[0]
    epub_session_id = session_ids[1]

    print("\n--- 3. Testing /api/sessions list endpoint ---")
    resp_list = requests.get(f"{SERVER_URL}/api/sessions")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    found_ids = [s["session_id"] for s in list_data["sessions"]]
    assert pdf_session_id in found_ids
    assert epub_session_id in found_ids
    print(f"Verified /api/sessions contains {len(list_data['sessions'])} sessions.")

    print("\n--- 4. Preview / colorize a page on each document ---")
    for sid in session_ids:
        prev_resp = requests.post(f"{SERVER_URL}/api/colorize/preview", json={
            "session_id": sid,
            "page_index": 0,
            "model_provider": "google_nano",
            "model_name": "gemini-2.0-flash",
            "style": "gemini_anime"
        })
        assert prev_resp.status_code == 200, f"Preview failed: {prev_resp.text}"
        print(f"Preview generated for session {sid}: {prev_resp.json().get('colorized_url')}")

    print("\n--- 5. Testing Batch Export: Auto (Keep Original Formats: PDF as PDF, EPUB as EPUB) ---")
    export_resp = requests.post(f"{SERVER_URL}/api/export/batch", json={
        "session_ids": session_ids,
        "format": "auto"
    })
    assert export_resp.status_code == 200, f"Batch export failed: {export_resp.text}"
    exp_data = export_resp.json()
    assert exp_data["status"] == "success"
    print("Batch Export Auto Response:", exp_data)

    dl_resp = requests.get(f"{SERVER_URL}{exp_data['download_url']}")
    assert dl_resp.status_code == 200
    assert len(dl_resp.content) > 1000
    
    # Verify archive contents
    with zipfile.ZipFile(io.BytesIO(dl_resp.content)) as z:
        names = z.namelist()
        print("Archive files (Auto):", names)
        assert any(n.endswith(".pdf") for n in names), "Missing PDF in collection"
        assert any(n.endswith(".epub") for n in names), "Missing EPUB in collection"
    print("Batch Export Auto verified successfully!")

    print("\n--- 6. Testing Batch Export: All as EPUBs ---")
    epub_export_resp = requests.post(f"{SERVER_URL}/api/export/batch", json={
        "session_ids": session_ids,
        "format": "epub"
    })
    assert epub_export_resp.status_code == 200
    exp_epub_data = epub_export_resp.json()
    dl_epub = requests.get(f"{SERVER_URL}{exp_epub_data['download_url']}")
    assert dl_epub.status_code == 200
    with zipfile.ZipFile(io.BytesIO(dl_epub.content)) as z:
        names = z.namelist()
        print("Archive files (All EPUBs):", names)
        assert all(n.endswith(".epub") for n in names), "Not all files are EPUBs"
    print("Batch Export All EPUBs verified successfully!")

    print("\n--- 7. Testing Batch Export: All as PDFs ---")
    pdf_export_resp = requests.post(f"{SERVER_URL}/api/export/batch", json={
        "session_ids": session_ids,
        "format": "pdf"
    })
    assert pdf_export_resp.status_code == 200
    exp_pdf_data = pdf_export_resp.json()
    dl_pdf = requests.get(f"{SERVER_URL}{exp_pdf_data['download_url']}")
    assert dl_pdf.status_code == 200
    with zipfile.ZipFile(io.BytesIO(dl_pdf.content)) as z:
        names = z.namelist()
        print("Archive files (All PDFs):", names)
        assert all(n.endswith(".pdf") for n in names), "Not all files are PDFs"
    print("Batch Export All PDFs verified successfully!")

    print("\n==============================================")
    print("ALL MULTI-FILE AND BATCH EXPORT TESTS PASSED!")
    print("==============================================")

if __name__ == "__main__":
    run_tests()
