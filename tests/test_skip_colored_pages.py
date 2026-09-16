import shutil
import uuid

import requests
from PIL import Image

from colorizer_engine import is_colored_page
from main import SESSIONS, STORAGE_DIR

BASE_URL = "http://127.0.0.1:8000"


def test_is_colored_page_detection(tmp_path):
    """Verifies that is_colored_page correctly identifies colored vs grayscale/B&W images."""
    color_path = tmp_path / "color_cover.jpg"
    bw_path = tmp_path / "bw_manga_page.jpg"

    # 1. Vibrant colored image (e.g. Manga cover)
    img_color = Image.new("RGB", (400, 600), color=(220, 60, 40))
    img_color.save(color_path, format="JPEG", quality=95)

    # 2. Pure B&W grayscale image with lineart
    img_bw = Image.new("RGB", (400, 600), color=(255, 255, 255))
    # Draw some black lines
    for y in range(0, 600, 10):
        for x in range(400):
            img_bw.putpixel((x, y), (0, 0, 0))
    img_bw.save(bw_path, format="JPEG", quality=95)

    assert is_colored_page(str(color_path)) is True
    assert is_colored_page(str(bw_path)) is False


def test_skip_if_colored_endpoint(tmp_path):
    """Tests that POST /api/colorize/start preserves colored pages without re-colorizing them."""
    # Create a test session with 1 colored page and 1 B&W page
    session_id = f"test_skip_colored_{uuid.uuid4().hex[:8]}"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    color_dir = sess_dir / "colorized"
    orig_dir.mkdir(parents=True, exist_ok=True)

    p1_path = orig_dir / "page_0001.jpg"
    p2_path = orig_dir / "page_0002.jpg"

    # Page 1 is colored
    img1 = Image.new("RGB", (300, 400), color=(230, 80, 50))
    img1.save(p1_path, format="JPEG", quality=90)

    # Page 2 is B&W
    img2 = Image.new("RGB", (300, 400), color=(240, 240, 240))
    img2.save(p2_path, format="JPEG", quality=90)

    sess = {
        "session_id": session_id,
        "filename": "test_manga_with_cover.pdf",
        "total_pages": 2,
        "processed_count": 0,
        "status": "idle",
        "pages": [
            {
                "page_index": 0,
                "display_name": "Page 1",
                "filename": "page_0001.jpg",
                "original_path": str(p1_path),
                "status": "pending",
            },
            {
                "page_index": 1,
                "display_name": "Page 2",
                "filename": "page_0002.jpg",
                "original_path": str(p2_path),
                "status": "pending",
            },
        ],
    }
    SESSIONS[session_id] = sess
    import json

    with open(sess_dir / "meta.json", "w") as f:
        json.dump(sess, f)

    try:
        resp = requests.post(
            f"{BASE_URL}/api/colorize/start",
            json={
                "session_id": session_id,
                "model_provider": "local_smart",
                "skip_if_colored": True,
            },
        )
        assert resp.status_code == 200

        # Wait for processing to complete
        import time

        for _ in range(50):
            time.sleep(0.2)
            r = requests.get(f"{BASE_URL}/api/session/{session_id}")
            if r.status_code == 200 and r.json().get("status") == "completed":
                break

        updated_sess = requests.get(f"{BASE_URL}/api/session/{session_id}").json()
        assert updated_sess["status"] == "completed"

        p1_meta = updated_sess["pages"][0]
        p2_meta = updated_sess["pages"][1]

        # Page 1 was colored -> must have skipped_colored True and original file preserved
        assert p1_meta.get("skipped_colored") is True
        assert (color_dir / "page_0001.jpg").exists()

        # Page 1 preserved original pixel data exactly
        with Image.open(color_dir / "page_0001.jpg") as out1, Image.open(p1_path) as in1:
            assert out1.size == in1.size

        # Page 2 was B&W -> processed by model
        assert p2_meta.get("skipped_colored") is not True
        assert (color_dir / "page_0002.jpg").exists()

    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(session_id, None)


def test_batch_colorization_respects_skip_if_colored():
    """Verifies that batch colorization forwards and respects skip_if_colored."""
    session_id = f"test_batch_skip_{uuid.uuid4().hex[:8]}"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)

    p1_path = orig_dir / "page_0001.jpg"
    img1 = Image.new("RGB", (200, 300), color=(255, 100, 50))
    img1.save(p1_path, format="JPEG")

    sess = {
        "session_id": session_id,
        "filename": "test_batch_color.pdf",
        "total_pages": 1,
        "processed_count": 0,
        "status": "idle",
        "pages": [
            {
                "page_index": 0,
                "display_name": "Page 1",
                "filename": "page_0001.jpg",
                "original_path": str(p1_path),
                "status": "pending",
            }
        ],
    }
    SESSIONS[session_id] = sess
    import json

    with open(sess_dir / "meta.json", "w") as f:
        json.dump(sess, f)

    try:
        resp = requests.post(
            f"{BASE_URL}/api/colorize/batch/start",
            json={
                "session_ids": [session_id],
                "model_provider": "local_smart",
                "skip_if_colored": True,
            },
        )
        assert resp.status_code == 200

        import time

        for _ in range(50):
            time.sleep(0.2)
            r = requests.get(f"{BASE_URL}/api/session/{session_id}")
            if r.status_code == 200 and r.json().get("status") == "completed":
                break

        final_sess = requests.get(f"{BASE_URL}/api/session/{session_id}").json()
        assert final_sess["status"] == "completed"
        assert final_sess["pages"][0].get("skipped_colored") is True

    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(session_id, None)
