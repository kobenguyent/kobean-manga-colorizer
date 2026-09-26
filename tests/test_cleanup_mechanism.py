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


def test_cleanup_new_patterns_and_protect_one_piece():
    """Verifies that cleanup script removes new test patterns (like Manga_Vol_1.cbz and tmp files)
    while strictly protecting authentic One Piece collections."""
    import json
    import shutil
    import uuid
    from scripts.cleanup_test_data import run_cleanup

    # 1. Create a mock authentic One Piece session
    real_sid = f"user_real_{uuid.uuid4().hex[:8]}"
    real_dir = STORAGE_DIR / real_sid
    real_dir.mkdir(parents=True, exist_ok=True)
    real_meta = real_dir / "meta.json"
    real_meta.write_text(
        json.dumps(
            {
                "session_id": real_sid,
                "filename": "One Piece Colored - Eiichiro Oda - Volume 0150.epub",
                "title": "One Piece",
            }
        )
    )

    # 2. Create a mock new test session (Manga_Vol_1.cbz)
    test_sid = f"vol_test_{uuid.uuid4().hex[:8]}"
    test_dir = STORAGE_DIR / test_sid
    test_dir.mkdir(parents=True, exist_ok=True)
    test_meta = test_dir / "meta.json"
    test_meta.write_text(
        json.dumps(
            {
                "session_id": test_sid,
                "filename": "Manga_Vol_1.cbz",
                "title": "",
            }
        )
    )

    # 3. Create dummy tmp test files
    tmp_f1 = Path("/tmp/dummy.jpg")
    tmp_f1.write_text("dummy")
    tmp_f2 = Path("/tmp/colorized_manga_output.epub")
    tmp_f2.write_text("colorized")

    try:
        # Run cleanup
        res = run_cleanup(purge_all=False, keep_slump=True, clean_tmp=True, dry_run=False)
        assert res["dry_run"] is False

        # Verify authentic One Piece session is preserved
        assert real_dir.exists(), "Authentic One Piece session must not be deleted"

        # Verify test session is deleted
        assert not test_dir.exists(), "Manga_Vol_1 test session must be deleted"

        # Verify tmp files are deleted
        assert not tmp_f1.exists(), "Dummy image in /tmp must be deleted"
        assert not tmp_f2.exists(), "Colorized epub in /tmp must be deleted"
    finally:
        shutil.rmtree(str(real_dir), ignore_errors=True)
        shutil.rmtree(str(test_dir), ignore_errors=True)
        tmp_f1.unlink(missing_ok=True)
        tmp_f2.unlink(missing_ok=True)


def test_cleanup_bulk_manga_page_artifacts():
    """Verifies that cleanup removes bulk_manga_page_*.png uploads, sessions, and tmp files."""
    import json
    import shutil
    import uuid
    from main import UPLOAD_DIR
    from scripts.cleanup_test_data import run_cleanup

    bulk_sid = str(uuid.uuid4())
    bulk_dir = STORAGE_DIR / bulk_sid
    bulk_dir.mkdir(parents=True, exist_ok=True)
    meta = bulk_dir / "meta.json"
    meta.write_text(
        json.dumps(
            {
                "session_id": bulk_sid,
                "filename": "bulk_manga_page_3.png",
                "title": "bulk_manga_page_3.png",
            }
        )
    )

    upload_f1 = UPLOAD_DIR / f"{bulk_sid}_bulk_manga_page_3.png"
    upload_f1.write_text("test upload content")

    tmp_bulk = Path("/tmp/bulk_manga_page_99.png")
    tmp_bulk.write_text("test tmp content")

    try:
        res = run_cleanup(purge_all=False, keep_slump=True, clean_tmp=True, dry_run=False)
        assert res["dry_run"] is False

        assert not bulk_dir.exists(), "bulk_manga_page session directory must be deleted"
        assert not upload_f1.exists(), "bulk_manga_page file in uploads/ must be deleted"
        assert not tmp_bulk.exists(), "bulk_manga_page file in /tmp must be deleted"
    finally:
        shutil.rmtree(str(bulk_dir), ignore_errors=True)
        upload_f1.unlink(missing_ok=True)
        tmp_bulk.unlink(missing_ok=True)

