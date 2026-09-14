import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
import unittest
import os
import shutil
import cv2
import numpy as np
import requests

from main import SESSIONS, STORAGE_DIR, UPLOAD_DIR, save_session_meta

BASE_URL = "http://127.0.0.1:8000"

class TestDeleteFeatures(unittest.TestCase):
    def test_delete_page_endpoint(self):
        """Test deleting a single page from a document session via DELETE /api/session/{id}/page/{index}."""
        session_id = f"test-del-page-{uuid.uuid4().hex[:8]}"
        sess_dir = STORAGE_DIR / session_id
        orig_dir = sess_dir / "original"
        orig_dir.mkdir(parents=True, exist_ok=True)

        pages = []
        for i in range(3):
            fn = f"page_{i+1:04d}.png"
            p_path = orig_dir / fn
            cv2.imwrite(str(p_path), np.zeros((100, 100, 3), dtype=np.uint8))
            pages.append({
                "page_index": i,
                "display_name": f"Page {i+1}",
                "filename": fn,
                "original_path": str(p_path),
                "width": 100,
                "height": 100,
                "status": "pending",
                "colorized_url": None
            })

        SESSIONS[session_id] = {
            "session_id": session_id,
            "filename": "test_pages.pdf",
            "file_path": "",
            "ext": ".pdf",
            "total_pages": 3,
            "pages": pages,
            "status": "idle",
            "processed_count": 0
        }
        save_session_meta(session_id)

        # Verify page 2 exists on disk
        self.assertTrue((orig_dir / "page_0002.png").exists())

        # Delete Page 1 (middle page: page_0002.png)
        resp = requests.delete(f"{BASE_URL}/api/session/{session_id}/page/1")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["total_pages"], 2)

        # Verify file was deleted from disk
        self.assertFalse((orig_dir / "page_0002.png").exists())

        # Verify remaining pages re-indexed
        updated_pages = data["session"]["pages"]
        self.assertEqual(len(updated_pages), 2)
        self.assertEqual(updated_pages[0]["page_index"], 0)
        self.assertEqual(updated_pages[0]["display_name"], "Page 1")
        self.assertEqual(updated_pages[1]["page_index"], 1)
        self.assertEqual(updated_pages[1]["display_name"], "Page 2")

        # Cleanup
        shutil.rmtree(str(sess_dir), ignore_errors=True)
        SESSIONS.pop(session_id, None)

    def test_delete_session_endpoint(self):
        """Test deleting a document session and verifying all files on disk are removed."""
        session_id = f"test-del-doc-{uuid.uuid4().hex[:8]}"
        sess_dir = STORAGE_DIR / session_id
        orig_dir = sess_dir / "original"
        orig_dir.mkdir(parents=True, exist_ok=True)
        dummy_file = orig_dir / "page_0001.png"
        cv2.imwrite(str(dummy_file), np.zeros((100, 100, 3), dtype=np.uint8))

        # Create dummy upload file
        upload_path = UPLOAD_DIR / f"{session_id}_dummy.pdf"
        with open(upload_path, "w") as f:
            f.write("dummy content")

        SESSIONS[session_id] = {
            "session_id": session_id,
            "filename": "dummy.pdf",
            "file_path": str(upload_path),
            "ext": ".pdf",
            "total_pages": 1,
            "pages": [{"page_index": 0, "filename": "page_0001.png", "original_path": str(dummy_file)}],
            "status": "idle",
            "processed_count": 0
        }
        save_session_meta(session_id)

        self.assertTrue(sess_dir.exists())
        self.assertTrue(upload_path.exists())

        # Delete session
        resp = requests.delete(f"{BASE_URL}/api/session/{session_id}")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "success")

        # Verify disk cleanup
        self.assertFalse(sess_dir.exists())
        self.assertFalse(upload_path.exists())

        # Calling GET /api/session/{session_id} should now return 404
        get_resp = requests.get(f"{BASE_URL}/api/session/{session_id}")
        self.assertEqual(get_resp.status_code, 404)

if __name__ == "__main__":
    unittest.main()
