import io
import json
import re
import uuid
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image

from main import app, SESSIONS

client = TestClient(app)


def create_dummy_png_bytes(text: str = "Test") -> bytes:
    img = Image.new("RGB", (100, 100), color=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_bulk_chunked_upload_backend():
    """Verify backend accepts bulk uploads (> 5 files in chunked form)."""
    # Create 8 dummy image files to simulate a bulk chunk
    files = []
    for i in range(8):
        png_bytes = create_dummy_png_bytes(f"BulkPage_{i+1}")
        files.append(("files", (f"bulk_manga_page_{i+1}.png", png_bytes, "image/png")))

    batch_id = str(uuid.uuid4())
    response = client.post("/api/upload", data={"batch_id": batch_id}, files=files)
    assert response.status_code == 200, response.text
    data = response.json()

    assert data["status"] == "success"
    assert data["batch_id"] == batch_id
    assert data["total_files"] == 8
    assert len(data["sessions"]) == 8
    assert "session_id" in data
    assert data["session_id"] == data["sessions"][0]["session_id"]

    # Verify session detail endpoint works for first uploaded session
    first_id = data["session_id"]
    sess_res = client.get(f"/api/session/{first_id}")
    assert sess_res.status_code == 200
    sess_data = sess_res.json()
    assert sess_data["session_id"] == first_id
    assert sess_data["filename"] == "bulk_manga_page_1.png"


def test_static_app_js_bulk_upload_contract():
    """Verify static/app.js contracts for bulk upload."""
    app_js_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
    assert app_js_path.exists()
    content = app_js_path.read_text(encoding="utf-8")

    # 1. Ensure handleFileSelection defines addBtn before validFiles.length > 5
    fn_match = re.search(r"async function handleFileSelection\(fileOrFiles\)\s*\{(.*?)\n\}", content, re.DOTALL)
    assert fn_match is not None, "handleFileSelection not found in static/app.js"
    fn_body = fn_match.group(1)

    add_btn_pos = fn_body.find('const addBtn = document.getElementById("btn-add-files");')
    threshold_pos = fn_body.find("if (validFiles.length > 5)")

    assert add_btn_pos != -1, "addBtn declaration missing in handleFileSelection"
    assert threshold_pos != -1, "validFiles.length > 5 check missing in handleFileSelection"
    assert add_btn_pos < threshold_pos, "TDZ bug! addBtn must be declared BEFORE if (validFiles.length > 5)"

    # 2. Ensure handleBulkChunkedUpload guards renderDashboard and handles targetSessionId
    bulk_match = re.search(r"async function handleBulkChunkedUpload\(files\)\s*\{(.*?)\n\}", content, re.DOTALL)
    assert bulk_match is not None, "handleBulkChunkedUpload not found in static/app.js"
    bulk_body = bulk_match.group(1)

    assert "targetSessionId" in bulk_body, "targetSessionId fallback logic missing in handleBulkChunkedUpload"
    assert "if (currentSession) {\n    renderDashboard();\n  }" in bulk_body or "if (currentSession) {\n    renderDashboard();" in bulk_body, \
        "renderDashboard must be guarded in handleBulkChunkedUpload"

    # 3. Ensure renderDashboard guards against null currentSession
    render_dash_match = re.search(r"function renderDashboard\(\)\s*\{(.*?)\n\}", content, re.DOTALL)
    assert render_dash_match is not None, "renderDashboard not found in static/app.js"
    render_dash_body = render_dash_match.group(1)

    assert "if (!currentSession)" in render_dash_body, "renderDashboard must guard against null currentSession"
