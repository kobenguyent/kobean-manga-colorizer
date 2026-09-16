import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shutil
import unittest
import uuid

import cv2
import numpy as np
import requests

from main import OUTPUT_DIR, SESSIONS, STORAGE_DIR, UPLOAD_DIR, save_session_meta

BASE_URL = "http://127.0.0.1:8000"

try:
    requests.get(f"{BASE_URL}/api/sessions", timeout=0.2)
    USE_LIVE_SERVER = True
except Exception:
    USE_LIVE_SERVER = False

if not USE_LIVE_SERVER:
    from fastapi.testclient import TestClient

    from main import app

    test_client = TestClient(app)


def api_delete(path: str):
    if USE_LIVE_SERVER:
        return requests.delete(f"{BASE_URL}{path}")
    return test_client.delete(path)


def api_get(path: str):
    if USE_LIVE_SERVER:
        return requests.get(f"{BASE_URL}{path}")
    return test_client.get(path)


def api_post(path: str, json: dict = None):
    if USE_LIVE_SERVER:
        return requests.post(f"{BASE_URL}{path}", json=json)
    return test_client.post(path, json=json)


class TestDeleteFeatures(unittest.TestCase):
    def test_delete_page_endpoint(self):
        """Test deleting a single page from a document session via DELETE /api/session/{id}/page/{index}."""
        session_id = f"test-del-page-{uuid.uuid4().hex[:8]}"
        sess_dir = STORAGE_DIR / session_id
        orig_dir = sess_dir / "original"
        orig_dir.mkdir(parents=True, exist_ok=True)

        pages = []
        for i in range(3):
            fn = f"page_{i + 1:04d}.png"
            p_path = orig_dir / fn
            cv2.imwrite(str(p_path), np.zeros((100, 100, 3), dtype=np.uint8))
            pages.append(
                {
                    "page_index": i,
                    "display_name": f"Page {i + 1}",
                    "filename": fn,
                    "original_path": str(p_path),
                    "width": 100,
                    "height": 100,
                    "status": "pending",
                    "colorized_url": None,
                }
            )

        SESSIONS[session_id] = {
            "session_id": session_id,
            "filename": "test_pages.pdf",
            "file_path": "",
            "ext": ".pdf",
            "total_pages": 3,
            "pages": pages,
            "status": "idle",
            "processed_count": 0,
        }
        save_session_meta(session_id)

        # Verify page 2 exists on disk
        self.assertTrue((orig_dir / "page_0002.png").exists())

        # Delete Page 1 (middle page: page_0002.png)
        resp = api_delete(f"/api/session/{session_id}/page/1")
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
            "pages": [
                {"page_index": 0, "filename": "page_0001.png", "original_path": str(dummy_file)}
            ],
            "status": "idle",
            "processed_count": 0,
        }
        save_session_meta(session_id)

        self.assertTrue(sess_dir.exists())
        self.assertTrue(upload_path.exists())

        # Delete session
        resp = api_delete(f"/api/session/{session_id}")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "success")

        # Verify disk cleanup
        self.assertFalse(sess_dir.exists())
        self.assertFalse(upload_path.exists())

        # Calling GET /api/session/{session_id} should now return 404
        get_resp = api_get(f"/api/session/{session_id}")
        self.assertEqual(get_resp.status_code, 404)

    def test_bulk_delete_sessions_endpoint(self):
        """Test bulk deleting multiple sessions via POST /api/sessions/bulk-delete."""
        sids = [f"test-bulk-del-{uuid.uuid4().hex[:8]}" for _ in range(3)]
        dirs = []
        uploads = []
        outputs = []

        for sid in sids:
            s_dir = STORAGE_DIR / sid
            orig_dir = s_dir / "original"
            orig_dir.mkdir(parents=True, exist_ok=True)
            dummy_file = orig_dir / "page_0001.png"
            cv2.imwrite(str(dummy_file), np.zeros((100, 100, 3), dtype=np.uint8))
            dirs.append(s_dir)

            up_path = UPLOAD_DIR / f"{sid}_sample.pdf"
            with open(up_path, "w") as f:
                f.write("test upload")
            uploads.append(up_path)

            out_path = OUTPUT_DIR / f"{sid}_export.zip"
            with open(out_path, "w") as f:
                f.write("test export")
            outputs.append(out_path)

            SESSIONS[sid] = {
                "session_id": sid,
                "filename": f"{sid}.pdf",
                "file_path": str(up_path),
                "ext": ".pdf",
                "total_pages": 1,
                "pages": [
                    {
                        "page_index": 0,
                        "filename": "page_0001.png",
                        "original_path": str(dummy_file),
                    }
                ],
                "status": "idle",
                "processed_count": 0,
            }
            save_session_meta(sid)

        # All 3 exist
        for d in dirs:
            self.assertTrue(d.exists())
        for u in uploads:
            self.assertTrue(u.exists())
        for o in outputs:
            self.assertTrue(o.exists())

        # Bulk delete first 2 sessions
        target_sids = [sids[0], sids[1]]
        resp = api_post("/api/sessions/bulk-delete", json={"session_ids": target_sids})
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["count"], 2)
        self.assertIn(sids[0], data["deleted_session_ids"])
        self.assertIn(sids[1], data["deleted_session_ids"])

        # Verify disk cleanup for deleted sessions
        self.assertFalse(dirs[0].exists())
        self.assertFalse(dirs[1].exists())
        self.assertFalse(uploads[0].exists())
        self.assertFalse(uploads[1].exists())
        self.assertFalse(outputs[0].exists())
        self.assertFalse(outputs[1].exists())

        # Verify 3rd session is completely untouched
        self.assertTrue(dirs[2].exists())
        self.assertTrue(uploads[2].exists())
        self.assertTrue(outputs[2].exists())
        get_resp = api_get(f"/api/session/{sids[2]}")
        self.assertEqual(get_resp.status_code, 200)

        # Cleanup 3rd session
        cleanup_resp = api_delete(f"/api/session/{sids[2]}")
        self.assertEqual(cleanup_resp.status_code, 200)

    def test_delete_sessions_with_query_params(self):
        """Test deleting sessions via DELETE /api/sessions?session_ids=sid1,sid2."""
        sids = [f"test-del-param-{uuid.uuid4().hex[:8]}" for _ in range(2)]
        dirs = []

        for sid in sids:
            s_dir = STORAGE_DIR / sid
            s_dir.mkdir(parents=True, exist_ok=True)
            dirs.append(s_dir)
            SESSIONS[sid] = {
                "session_id": sid,
                "filename": f"{sid}.pdf",
                "total_pages": 0,
                "pages": [],
                "status": "idle",
                "processed_count": 0,
            }
            save_session_meta(sid)

        for d in dirs:
            self.assertTrue(d.exists())

        resp = api_delete(f"/api/sessions?session_ids={sids[0]},{sids[1]}")
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["count"], 2)

        for d in dirs:
            self.assertFalse(d.exists())

    def test_bulk_delete_validation_and_edge_cases(self):
        """Test validation error for empty session_ids and graceful handling for non-existent IDs."""
        # Empty list without delete_all should return 400
        resp = api_post("/api/sessions/bulk-delete", json={"session_ids": []})
        self.assertEqual(resp.status_code, 400)

        # Non-existent session IDs should return success with deleted_session_ids handled
        fake_id = f"fake-session-{uuid.uuid4().hex[:8]}"
        resp = api_post("/api/sessions/bulk-delete", json={"session_ids": [fake_id]})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertIn(fake_id, data["deleted_session_ids"])


if __name__ == "__main__":
    unittest.main()
