"""
tests/test_export_original_combined.py
Unit and integration tests for exporting original uncolorized versions
from 'Export as Single E-Reader Copy' (EPUB, MOBI, PDF, Omnibus).
"""

import io
import json
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

import fitz
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from file_processor import MangaFileProcessor
from main import (
    COMBINED_EXPORTS,
    OUTPUT_DIR,
    SESSIONS,
    STORAGE_DIR,
    app,
    get_or_restore_session,
    save_session_meta,
)

client = TestClient(app)


@pytest.fixture
def temp_environment():
    temp_dir = tempfile.mkdtemp()
    storage_path = Path(temp_dir) / "sessions"
    storage_path.mkdir(parents=True, exist_ok=True)
    processor = MangaFileProcessor(str(storage_path))
    yield temp_dir, storage_path, processor
    shutil.rmtree(temp_dir, ignore_errors=True)


def _create_solid_image(path: Path, color: tuple[int, int, int], size=(200, 300)):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color=color)
    img.save(path, format="JPEG", quality=90)


def _create_mock_session(storage_path: Path, session_id: str, num_pages=2):
    """
    Creates a session where:
    - original_path has BLUE pixels (0, 0, 255)
    - colorized/ has RED pixels (255, 0, 0)
    This allows us to deterministically verify whether original or colorized was used.
    """
    sess_dir = storage_path / session_id
    extracted_dir = sess_dir / "extracted"
    colorized_dir = sess_dir / "colorized"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    colorized_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for i in range(num_pages):
        filename = f"page_{i + 1:04d}.jpg"
        orig_file = extracted_dir / filename
        color_file = colorized_dir / filename

        # Original is blue (0, 0, 255)
        _create_solid_image(orig_file, (0, 0, 255))
        # Colorized is red (255, 0, 0)
        _create_solid_image(color_file, (255, 0, 0))

        pages.append(
            {
                "page_num": i + 1,
                "filename": filename,
                "original_path": str(orig_file),
                "display_name": f"Page {i + 1}",
            }
        )

    session_data = {
        "session_id": session_id,
        "filename": f"Volume_{session_id[-4:]}.cbz",
        "file_path": str(extracted_dir),
        "ext": ".cbz",
        "total_pages": num_pages,
        "processed_count": num_pages,
        "status": "completed",
        "pages": pages,
    }

    with open(sess_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(session_data, f)

    return session_data


# ─────────────────────────────────────────────────────────────────────
# 1. File Processor Engine Tests: build_combined_epub
# ─────────────────────────────────────────────────────────────────────


def test_build_combined_epub_export_original_flag(temp_environment):
    temp_dir, storage_path, processor = temp_environment
    session_id = f"sess_epub_{uuid.uuid4().hex[:6]}"
    sess_data = _create_mock_session(storage_path, session_id, num_pages=2)

    epub_colorized = Path(temp_dir) / "colorized.epub"
    epub_original = Path(temp_dir) / "original.epub"

    # Export with export_original=False
    processor.build_combined_epub(
        [sess_data],
        str(epub_colorized),
        title="Colorized Test",
        export_original=False,
    )
    assert epub_colorized.exists()

    # Verify colorized EPUB contains RED pixels
    with zipfile.ZipFile(epub_colorized, "r") as zf:
        first_img_name = [n for n in zf.namelist() if n.startswith("OEBPS/images/")][0]
        img_data = zf.read(first_img_name)
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        pixel = img.getpixel((50, 50))
        assert pixel[0] > 180 and pixel[2] < 80, f"Expected red, got {pixel}"

    # Export with export_original=True
    processor.build_combined_epub(
        [sess_data],
        str(epub_original),
        title="Original Test",
        export_original=True,
    )
    assert epub_original.exists()

    # Verify original EPUB contains BLUE pixels
    with zipfile.ZipFile(epub_original, "r") as zf:
        first_img_name = [n for n in zf.namelist() if n.startswith("OEBPS/images/")][0]
        img_data = zf.read(first_img_name)
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        pixel = img.getpixel((50, 50))
        assert pixel[2] > 180 and pixel[0] < 80, f"Expected blue, got {pixel}"


# ─────────────────────────────────────────────────────────────────────
# 2. File Processor Engine Tests: build_combined_pdf
# ─────────────────────────────────────────────────────────────────────


def test_build_combined_pdf_export_original_flag(temp_environment):
    temp_dir, storage_path, processor = temp_environment
    session_id = f"sess_pdf_{uuid.uuid4().hex[:6]}"
    sess_data = _create_mock_session(storage_path, session_id, num_pages=2)

    pdf_colorized = Path(temp_dir) / "colorized.pdf"
    pdf_original = Path(temp_dir) / "original.pdf"

    # Export colorized
    processor.build_combined_pdf(
        [sess_data],
        str(pdf_colorized),
        title="Colorized Test",
        export_original=False,
    )
    assert pdf_colorized.exists()

    doc_col = fitz.open(str(pdf_colorized))
    pix_col = doc_col[0].get_pixmap()
    # Check pixel at (50, 50)
    col_r, col_g, col_b = pix_col.pixel(50, 50)[:3]
    doc_col.close()
    assert col_r > 180 and col_b < 80, f"Expected red colorized, got {(col_r, col_g, col_b)}"

    # Export original
    processor.build_combined_pdf(
        [sess_data],
        str(pdf_original),
        title="Original Test",
        export_original=True,
    )
    assert pdf_original.exists()

    doc_orig = fitz.open(str(pdf_original))
    pix_orig = doc_orig[0].get_pixmap()
    orig_r, orig_g, orig_b = pix_orig.pixel(50, 50)[:3]
    doc_orig.close()
    assert orig_b > 180 and orig_r < 80, f"Expected blue original, got {(orig_r, orig_g, orig_b)}"


# ─────────────────────────────────────────────────────────────────────
# 3. File Processor Engine Tests: build_combined_mobi
# ─────────────────────────────────────────────────────────────────────


def test_build_combined_mobi_export_original_flag(temp_environment):
    temp_dir, storage_path, processor = temp_environment
    session_id = f"sess_mobi_{uuid.uuid4().hex[:6]}"
    sess_data = _create_mock_session(storage_path, session_id, num_pages=2)

    mobi_original = Path(temp_dir) / "original.mobi"

    processor.build_combined_mobi(
        [sess_data],
        str(mobi_original),
        title="Original Mobi",
        export_original=True,
    )
    assert mobi_original.exists()
    assert mobi_original.stat().st_size > 0

    # Verify MOBI header
    with open(mobi_original, "rb") as f:
        content = f.read(100)
        assert b"BOOK" in content or b"MOBI" in content


# ─────────────────────────────────────────────────────────────────────
# 4. File Processor Engine Tests: build_combined_omnibus (single & multi)
# ─────────────────────────────────────────────────────────────────────


def test_build_combined_omnibus_single_and_multi_chunk(temp_environment):
    temp_dir, storage_path, processor = temp_environment
    sess1 = _create_mock_session(storage_path, f"sess1_{uuid.uuid4().hex[:4]}", num_pages=2)
    sess2 = _create_mock_session(storage_path, f"sess2_{uuid.uuid4().hex[:4]}", num_pages=2)

    # 1. Single chunk (default)
    single_out = Path(temp_dir) / "single_original.epub"
    processor.build_combined_omnibus(
        [sess1, sess2],
        str(single_out),
        export_format="epub",
        export_original=True,
    )
    assert single_out.exists()
    with zipfile.ZipFile(single_out, "r") as zf:
        first_img = [n for n in zf.namelist() if n.startswith("OEBPS/images/")][0]
        img = Image.open(io.BytesIO(zf.read(first_img))).convert("RGB")
        pixel = img.getpixel((50, 50))
        assert pixel[2] > 180, f"Expected blue original, got {pixel}"

    # 2. Multi-chunk (chunk_by='volumes', chunk_size=1)
    multi_out = Path(temp_dir) / "multi_original.zip"
    processor.build_combined_omnibus(
        [sess1, sess2],
        str(multi_out),
        export_format="epub",
        chunk_by="volumes",
        chunk_size=1,
        export_original=True,
    )
    assert multi_out.exists()
    with zipfile.ZipFile(multi_out, "r") as zf:
        names = zf.namelist()
        assert len(names) == 2
        assert all(n.endswith(".epub") for n in names)


# ─────────────────────────────────────────────────────────────────────
# 5. FastAPI Integration Endpoint Tests: /api/export/combined
# ─────────────────────────────────────────────────────────────────────


def test_api_export_combined_original_sync():
    """Verifies synchronous /api/export/combined with export_original=True."""
    sid = f"api_orig_sync_{uuid.uuid4().hex[:6]}"
    sess_dir = STORAGE_DIR / sid
    extracted_dir = sess_dir / "extracted"
    colorized_dir = sess_dir / "colorized"
    extracted_dir.mkdir(parents=True, exist_ok=True)
    colorized_dir.mkdir(parents=True, exist_ok=True)

    _create_solid_image(extracted_dir / "page_0001.jpg", (0, 0, 255))
    _create_solid_image(colorized_dir / "page_0001.jpg", (255, 0, 0))

    sess_data = {
        "session_id": sid,
        "filename": "OnePiece_Vol_01.cbz",
        "file_path": str(extracted_dir),
        "ext": ".cbz",
        "total_pages": 1,
        "processed_count": 1,
        "status": "completed",
        "pages": [
            {
                "page_num": 1,
                "filename": "page_0001.jpg",
                "original_path": str(extracted_dir / "page_0001.jpg"),
                "display_name": "Page 1",
            }
        ],
    }
    SESSIONS[sid] = sess_data
    save_session_meta(sid)

    try:
        # Request combined export with export_original=True
        resp = client.post(
            "/api/export/combined",
            json={
                "session_ids": [sid],
                "format": "epub",
                "sync": True,
                "export_original": True,
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "success"
        assert "Original_" in data["filename"]
        assert data["title"] == "Manga Collection"

        # Download the created EPUB and verify the image is the ORIGINAL blue one
        dl_resp = client.get(data["download_url"])
        assert dl_resp.status_code == 200
        with zipfile.ZipFile(io.BytesIO(dl_resp.content), "r") as zf:
            img_names = [n for n in zf.namelist() if n.startswith("OEBPS/images/")]
            assert len(img_names) > 0
            img = Image.open(io.BytesIO(zf.read(img_names[0]))).convert("RGB")
            pixel = img.getpixel((50, 50))
            assert pixel[2] > 180, f"Expected blue original page, got {pixel}"

    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(sid, None)


# ─────────────────────────────────────────────────────────────────────
# 6. Frontend UI Assets Verification
# ─────────────────────────────────────────────────────────────────────


def test_frontend_has_export_original_elements():
    """Ensures index.html and app.js contain the Export Original Versions controls."""
    html_path = Path("static/index.html")
    assert html_path.exists()
    html_content = html_path.read_text(encoding="utf-8")

    assert 'id="combined-original-check"' in html_content
    assert "Export Original Versions" in html_content
    assert "No colorization needed" in html_content

    js_path = Path("static/app.js")
    assert js_path.exists()
    js_content = js_path.read_text(encoding="utf-8")

    assert "combined-original-check" in js_content
    assert "export_original: isOriginal" in js_content
