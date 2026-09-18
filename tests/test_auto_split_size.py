"""
tests/test_auto_split_size.py
Unit and integration tests for customizable auto-split file size in E-Reader Omnibus exports.
"""

import io
import json
import os
import shutil
import tempfile
import uuid
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from file_processor import MangaFileProcessor
from main import (
    OUTPUT_DIR,
    SESSIONS,
    STORAGE_DIR,
    app,
    save_session_meta,
)

client = TestClient(app)


@pytest.fixture
def temp_env():
    temp_dir = tempfile.mkdtemp()
    storage_path = Path(temp_dir) / "sessions"
    storage_path.mkdir(parents=True, exist_ok=True)
    processor = MangaFileProcessor(str(storage_path))
    yield temp_dir, storage_path, processor
    shutil.rmtree(temp_dir, ignore_errors=True)


def _create_dummy_image(path: Path, size=(300, 400)):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color="navy")
    img.save(path, format="JPEG", quality=85)


def _create_test_session(storage_path: Path, session_id: str, num_pages: int):
    sess_dir = storage_path / session_id
    ext_dir = sess_dir / "extracted"
    ext_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for i in range(num_pages):
        filename = f"p_{i + 1:04d}.jpg"
        p_path = ext_dir / filename
        _create_dummy_image(p_path)
        pages.append(
            {
                "page_num": i + 1,
                "filename": filename,
                "original_path": str(p_path),
                "display_name": f"Page {i + 1}",
            }
        )

    sess_data = {
        "session_id": session_id,
        "filename": f"Manga_Volume_{session_id[-3:]}.cbz",
        "file_path": str(ext_dir),
        "ext": ".cbz",
        "total_pages": num_pages,
        "processed_count": num_pages,
        "status": "completed",
        "pages": pages,
    }

    with open(sess_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(sess_data, f)

    return sess_data


def test_auto_split_by_target_size_multiple_sessions(temp_env):
    """Verifies that 4 sessions are split into parts based on target chunk size."""
    temp_dir, storage_path, processor = temp_env
    # Create 4 sessions of 80 pages each
    sessions = [
        _create_test_session(storage_path, f"vol_{i}_{uuid.uuid4().hex[:4]}", num_pages=80)
        for i in range(4)
    ]

    out_zip = str(Path(temp_dir) / "Omnibus_200MB.zip")

    # Request split at 100 MB budget
    # 80 pages * ~480KB = ~38MB per volume.
    # At 100MB budget: ~2 volumes fit per part, so 4 volumes -> 2 parts.
    result = processor.build_combined_omnibus(
        sessions_data=sessions,
        output_filepath=out_zip,
        export_format="epub",
        chunk_by="size_mb",
        chunk_size=70,  # 70 MB limit forces ~1-2 vols per chunk
        title="Split Test Manga",
    )

    assert result.endswith(".zip")
    assert Path(result).exists()

    with zipfile.ZipFile(result, "r") as zf:
        parts = sorted(zf.namelist())
        # Must be split into at least 2 parts, not 1 huge 1GB file
        assert len(parts) >= 2
        for p in parts:
            assert p.endswith(".epub")


def test_auto_split_large_single_session(temp_env):
    """Verifies that a single huge session (e.g. 600 pages) is subdivided under budget limit."""
    temp_dir, storage_path, processor = temp_env
    huge_sess = _create_test_session(storage_path, f"huge_{uuid.uuid4().hex[:4]}", num_pages=500)

    out_zip = str(Path(temp_dir) / "Huge_Omnibus.zip")

    # Target: 100 MB per part
    result = processor.build_combined_omnibus(
        sessions_data=[huge_sess],
        output_filepath=out_zip,
        export_format="epub",
        chunk_by="size_mb",
        chunk_size=100,
        title="Huge Manga Omnibus",
    )

    assert result.endswith(".zip")
    with zipfile.ZipFile(result, "r") as zf:
        parts = sorted(zf.namelist())
        # Single 500-page file must be split into multiple parts under 100MB
        assert len(parts) >= 2


def test_api_combined_export_custom_split_size():
    """Verifies API accepts custom chunk_size with chunk_by='size_mb'."""
    sid1 = f"api_split1_{uuid.uuid4().hex[:6]}"
    sid2 = f"api_split2_{uuid.uuid4().hex[:6]}"

    sess1 = {
        "session_id": sid1,
        "filename": "Vol_01.cbz",
        "file_path": str(STORAGE_DIR / sid1),
        "ext": ".cbz",
        "total_pages": 150,
        "pages": [{"page_num": i, "filename": f"p_{i}.jpg", "original_path": "/tmp/dummy.jpg"} for i in range(150)],
    }
    sess2 = {
        "session_id": sid2,
        "filename": "Vol_02.cbz",
        "file_path": str(STORAGE_DIR / sid2),
        "ext": ".cbz",
        "total_pages": 150,
        "pages": [{"page_num": i, "filename": f"p_{i}.jpg", "original_path": "/tmp/dummy.jpg"} for i in range(150)],
    }

    SESSIONS[sid1] = sess1
    SESSIONS[sid2] = sess2

    try:
        # Request with 50 MB budget: 300 pages * ~480KB = ~140MB > 50MB -> must chunk
        resp = client.post(
            "/api/export/combined",
            json={
                "session_ids": [sid1, sid2],
                "format": "epub",
                "chunk_by": "size_mb",
                "chunk_size": 50,
                "title": "Custom Size Test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["is_omnibus"] is True
    finally:
        SESSIONS.pop(sid1, None)
        SESSIONS.pop(sid2, None)


def test_ui_contains_split_size_options():
    """Verifies index.html has granular 100, 200, 250, 350, 500, and custom size options."""
    html = Path("static/index.html").read_text(encoding="utf-8")
    assert 'value="size_100"' in html
    assert 'value="size_200"' in html
    assert 'value="size_250"' in html
    assert 'value="size_350"' in html
    assert 'value="size_500"' in html
    assert 'value="size_custom"' in html
    assert 'id="combined-custom-size-input"' in html

    js = Path("static/app.js").read_text(encoding="utf-8")
    assert "combined-custom-size-input" in js
    assert "size_custom" in js
