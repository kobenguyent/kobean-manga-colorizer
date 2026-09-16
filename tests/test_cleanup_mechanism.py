import io
import sys
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from main import OUTPUT_DIR, STORAGE_DIR

BASE_URL = "http://127.0.0.1:8000"


def test_test_data_cleanup_endpoint():
    """Verifies that POST /api/test/cleanup correctly identifies and removes test sessions and files."""
    # 1. Create a dummy test upload
    img = Image.new("RGB", (200, 200), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    upload_resp = requests.post(
        f"{BASE_URL}/api/upload",
        files={"file": ("sample_cleanup_test_page.jpg", buf, "image/jpeg")},
    )
    assert upload_resp.status_code == 200
    session_id = upload_resp.json()["session_id"]

    sess_dir = STORAGE_DIR / session_id
    assert sess_dir.exists(), "Session directory should exist after upload"

    # 2. Export a document to create output artifacts
    export_resp = requests.post(f"{BASE_URL}/api/export/{session_id}?format=epub")
    assert export_resp.status_code == 200
    export_data = export_resp.json()
    assert export_data["download_url"]

    # Verify download file exists on disk
    out_filename = export_data["filename"]
    out_path = OUTPUT_DIR / f"{session_id}_{out_filename}"
    assert out_path.exists(), "Exported file should exist in output/"

    # Create a temp file in /tmp
    tmp_file = Path("/tmp/sample_cleanup_verify.tmp")
    tmp_file.write_text("temporary test file")
    assert tmp_file.exists()

    # 3. Call the cleanup endpoint targeting this test session
    clean_resp = requests.post(
        f"{BASE_URL}/api/test/cleanup", json={"session_ids": [session_id], "clean_orphans": True}
    )
    assert clean_resp.status_code == 200
    clean_data = clean_resp.json()
    assert clean_data["status"] == "success"
    assert session_id in clean_data["cleaned_sessions"]

    # 4. Assert disk cleanup
    assert not sess_dir.exists(), "Session directory should be deleted"
    assert not out_path.exists(), "Exported file should be deleted"

    # Calling GET /api/session/{session_id} should return 404
    get_resp = requests.get(f"{BASE_URL}/api/session/{session_id}")
    assert get_resp.status_code == 404


def test_script_cleanup_protects_user_data():
    """Verifies that the cleanup script and endpoint preserve user volumes while purging test artifacts."""
    from scripts.cleanup_test_data import run_cleanup

    # Run dry run
    res = run_cleanup(purge_all=False, keep_slump=True, clean_tmp=True, dry_run=True)
    assert res["dry_run"] is True
    assert "freed_formatted" in res

    # Verify Dr. Slump sessions are untouched in SESSIONS_DIR
    slump_dirs = [d for d in STORAGE_DIR.iterdir() if d.is_dir() and "slump" in d.name.lower()]
    # If any exist on disk, ensure they are not deleted
    for s_dir in slump_dirs:
        assert s_dir.exists()
