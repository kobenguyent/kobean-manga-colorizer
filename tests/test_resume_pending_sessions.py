import json
import os
import shutil
import time
import unittest
import uuid
from pathlib import Path
from PIL import Image
import requests

from main import BASE_DIR, SESSIONS, STORAGE_DIR, is_task_active

BASE_URL = "http://127.0.0.1:8000"


class TestResumePendingSessions(unittest.TestCase):
    def setUp(self):
        self.test_sessions_to_clean = []

    def tearDown(self):
        for sid in self.test_sessions_to_clean:
            try:
                requests.post(f"{BASE_URL}/api/colorize/cancel/{sid}", timeout=3)
            except requests.RequestException:
                pass
            try:
                requests.delete(f"{BASE_URL}/api/session/{sid}", timeout=3)
            except requests.RequestException:
                pass
            SESSIONS.pop(sid, None)
            sess_dir = STORAGE_DIR / sid
            if sess_dir.exists():
                shutil.rmtree(sess_dir, ignore_errors=True)

    def _create_mock_session(self, total_pages=3, colorized_count=1, initial_status="processing"):
        session_id = f"test_resume_{uuid.uuid4().hex[:8]}"
        self.test_sessions_to_clean.append(session_id)

        sess_dir = STORAGE_DIR / session_id
        orig_dir = sess_dir / "original"
        col_dir = sess_dir / "colorized"
        orig_dir.mkdir(parents=True, exist_ok=True)
        col_dir.mkdir(parents=True, exist_ok=True)

        pages = []
        for i in range(total_pages):
            p_name = f"page_{i + 1:04d}.jpg"
            p_path = orig_dir / p_name
            # Create a simple white image
            img = Image.new("RGB", (200, 200), color=(255, 255, 255))
            img.save(p_path, format="JPEG")

            is_done = i < colorized_count
            if is_done:
                col_path = col_dir / p_name
                img.save(col_path, format="JPEG")
                p_status = "colorized"
                col_url = f"/api/session/{session_id}/image/colorized/{p_name}"
            elif i == colorized_count and initial_status == "processing":
                p_status = "processing"
                col_url = None
            else:
                p_status = "pending"
                col_url = None

            pages.append({
                "page_index": i,
                "display_name": f"Page {i + 1}",
                "filename": p_name,
                "original_path": str(p_path),
                "status": p_status,
                "colorized_url": col_url,
            })

        meta = {
            "session_id": session_id,
            "filename": f"{session_id}.cbz",
            "file_path": str(orig_dir / "dummy.cbz"),
            "ext": ".cbz",
            "total_pages": total_pages,
            "processed_count": colorized_count,
            "status": initial_status,
            "model_provider": "local_smart",
            "model_name": "smart-color",
            "denoise_screentone": False,
            "pages": pages,
        }

        with open(sess_dir / "meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        return session_id, meta

    def test_dangling_session_sanitized_on_load(self):
        """Dangling session in 'processing' status without an active task is sanitized to 'pending'."""
        session_id, _ = self._create_mock_session(total_pages=3, colorized_count=1, initial_status="processing")

        # In-memory session not yet loaded, task is not active
        self.assertFalse(is_task_active(session_id))

        # Query GET /api/session/{session_id}
        res = requests.get(f"{BASE_URL}/api/session/{session_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Status must be sanitized from 'processing' to 'pending'
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["processed_count"], 1)

        # Page that was stuck in 'processing' must be reset to 'pending'
        self.assertEqual(data["pages"][1]["status"], "pending")
        self.assertEqual(data["pages"][0]["status"], "colorized")

        # Calling start_colorization must NOT return 400 "already in progress"
        start_res = requests.post(
            f"{BASE_URL}/api/colorize/start",
            json={
                "session_id": session_id,
                "model_provider": "local_smart",
                "model_name": "smart-color",
                "denoise_screentone": False,
            }
        )
        self.assertEqual(start_res.status_code, 200)
        self.assertEqual(start_res.json()["status"], "started")

    def test_dangling_session_sanitization_edge_cases_and_disk_persistence(self):
        """Sanitization covers partial/zero/full progress, stale pages, and persists to meta.json."""
        # 1. Partial progress dangling session -> pending, persisted to disk
        sid_partial, _ = self._create_mock_session(
            total_pages=3, colorized_count=1, initial_status="processing"
        )
        res = requests.get(f"{BASE_URL}/api/session/{sid_partial}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["processed_count"], 1)
        self.assertEqual(data["pages"][1]["status"], "pending")
        persisted = json.loads((STORAGE_DIR / sid_partial / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], "pending")
        self.assertEqual(persisted["pages"][1]["status"], "pending")

        # 2. Zero progress dangling session -> idle, persisted to disk
        sid_zero, _ = self._create_mock_session(
            total_pages=2, colorized_count=0, initial_status="processing"
        )
        res = requests.get(f"{BASE_URL}/api/session/{sid_zero}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "idle")
        self.assertEqual(data["processed_count"], 0)
        self.assertEqual(data["pages"][0]["status"], "pending")
        persisted = json.loads((STORAGE_DIR / sid_zero / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], "idle")
        self.assertEqual(persisted["pages"][0]["status"], "pending")

        # 3. Fully colorized dangling session -> completed, persisted to disk
        sid_full, _ = self._create_mock_session(
            total_pages=2, colorized_count=2, initial_status="processing"
        )
        res = requests.get(f"{BASE_URL}/api/session/{sid_full}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["processed_count"], 2)
        persisted = json.loads((STORAGE_DIR / sid_full / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["status"], "completed")

        # 4. Non-processing session with stale 'processing' page -> page reset & persisted
        sid_stale, meta_stale = self._create_mock_session(
            total_pages=2, colorized_count=1, initial_status="pending"
        )
        meta_stale["pages"][1]["status"] = "processing"
        (STORAGE_DIR / sid_stale / "meta.json").write_text(
            json.dumps(meta_stale, indent=2), encoding="utf-8"
        )
        res = requests.get(f"{BASE_URL}/api/session/{sid_stale}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["pages"][1]["status"], "pending")
        persisted = json.loads((STORAGE_DIR / sid_stale / "meta.json").read_text(encoding="utf-8"))
        self.assertEqual(persisted["pages"][1]["status"], "pending")

    def test_resume_endpoint_resumes_pending_pages(self):
        """POST /api/colorize/resume/{session_id} resumes colorizing remaining uncolored pages."""
        session_id, _ = self._create_mock_session(total_pages=2, colorized_count=1, initial_status="pending")

        # Call resume endpoint
        res = requests.post(f"{BASE_URL}/api/colorize/resume/{session_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(data["status"], ["resumed", "already_running"])

        # Wait for the remaining page to complete (up to 30s on slow CPU-only CI runners)
        check_data = {}
        for _ in range(60):
            check_res = requests.get(f"{BASE_URL}/api/session/{session_id}")
            if check_res.status_code == 200:
                check_data = check_res.json()
                if check_data.get("status") == "completed":
                    break
            time.sleep(0.5)

        # Verify session is completed and all pages are colorized
        self.assertEqual(check_data.get("status"), "completed")
        self.assertEqual(check_data.get("processed_count"), 2)

    def test_resume_already_completed_session(self):
        """Resuming an already completed session cleanly returns already_completed."""
        session_id, _ = self._create_mock_session(total_pages=2, colorized_count=2, initial_status="completed")

        res = requests.post(f"{BASE_URL}/api/colorize/resume/{session_id}")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "already_completed")

    def test_stream_auto_resume_drives_session(self):
        """Connecting to SSE stream with auto_resume=True resumes pending pages automatically."""
        session_id, _ = self._create_mock_session(total_pages=2, colorized_count=1, initial_status="pending")

        # Connect to stream with auto_resume=true (server emits SSE keepalive comments every 5s)
        resp = requests.get(f"{BASE_URL}/api/colorize/stream/{session_id}?auto_resume=true", stream=True, timeout=20)
        self.assertEqual(resp.status_code, 200)

        received_events = []
        deadline = time.monotonic() + 45.0
        for line in resp.iter_lines(decode_unicode=True):
            if time.monotonic() > deadline:
                break
            if line and line.startswith("data: "):
                event_data = json.loads(line[6:])
                received_events.append(event_data.get("type"))
                if event_data.get("type") in ["completed", "idle", "cancelled"]:
                    break

        self.assertIn("init", received_events)
        # Should drive completion of the remaining page
        self.assertTrue("page_update" in received_events or "completed" in received_events)

    def test_batch_resume_endpoint(self):
        """POST /api/colorize/batch/resume detects and resumes pending sessions."""
        sid1, _ = self._create_mock_session(total_pages=2, colorized_count=1, initial_status="pending")
        sid2, _ = self._create_mock_session(total_pages=2, colorized_count=2, initial_status="completed")

        res = requests.post(f"{BASE_URL}/api/colorize/batch/resume", json={"session_ids": [sid1, sid2]})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn(data["status"], ["started", "already_running"])
        if data["status"] == "started":
            # Only sid1 had pending pages, so only sid1 should be targeted
            self.assertEqual(data["session_ids"], [sid1])


if __name__ == "__main__":
    unittest.main()
