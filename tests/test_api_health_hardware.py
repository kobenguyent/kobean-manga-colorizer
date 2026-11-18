import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import main  # noqa: E402


class _DummyActiveTask:
    def done(self) -> bool:
        return False


class _DummyDoneTask:
    def done(self) -> bool:
        return True


class TestApiHealthHardware(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(main.app)

    def test_health_endpoint_returns_expected_schema_and_live_state(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()

        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("service"), "kobean-manga-colorizer")
        self.assertEqual(data.get("version"), "1.0.0")
        self.assertIsInstance(data.get("active_colorization_tasks"), int)
        self.assertIsInstance(data.get("batch_running"), bool)
        self.assertIsInstance(data.get("total_sessions"), int)

        dummy_sid = "test-health-session"
        done_sid = "test-health-done-session"
        orig_batch_running = main.CURRENT_BATCH.get("is_running", False)
        orig_session = main.SESSIONS.get(dummy_sid)
        orig_task = main.ACTIVE_COLORIZATION_TASKS.get(dummy_sid)
        orig_done_task = main.ACTIVE_COLORIZATION_TASKS.get(done_sid)
        try:
            baseline_active = data["active_colorization_tasks"]
            main.CURRENT_BATCH["is_running"] = True
            main.SESSIONS[dummy_sid] = {"session_id": dummy_sid, "filename": "sample.cbz"}
            main.ACTIVE_COLORIZATION_TASKS[dummy_sid] = _DummyActiveTask()
            main.ACTIVE_COLORIZATION_TASKS[done_sid] = _DummyDoneTask()

            live_resp = self.client.get("/api/health")
            self.assertEqual(live_resp.status_code, 200, live_resp.text)
            live_data = live_resp.json()
            self.assertTrue(live_data["batch_running"])
            self.assertEqual(live_data["active_colorization_tasks"], baseline_active + 1)
            self.assertGreaterEqual(live_data["total_sessions"], 1)
        finally:
            main.CURRENT_BATCH["is_running"] = orig_batch_running
            if orig_session is None:
                main.SESSIONS.pop(dummy_sid, None)
            else:
                main.SESSIONS[dummy_sid] = orig_session
            if orig_task is None:
                main.ACTIVE_COLORIZATION_TASKS.pop(dummy_sid, None)
            else:
                main.ACTIVE_COLORIZATION_TASKS[dummy_sid] = orig_task
            if orig_done_task is None:
                main.ACTIVE_COLORIZATION_TASKS.pop(done_sid, None)
            else:
                main.ACTIVE_COLORIZATION_TASKS[done_sid] = orig_done_task

    def test_hardware_endpoint_returns_profile_and_storage(self):
        response = self.client.get("/api/hardware")
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()

        self.assertIn(data.get("device"), ("mps", "cuda", "cpu"))
        self.assertIsInstance(data.get("chip_name"), str)
        self.assertTrue(len(data["chip_name"]) > 0)
        self.assertIsInstance(data.get("ram_gb"), int)
        self.assertGreater(data["ram_gb"], 0)
        self.assertIsInstance(data.get("use_fp16"), bool)
        self.assertIsInstance(data.get("empty_cache_interval"), int)
        self.assertGreater(data["empty_cache_interval"], 0)
        self.assertIsInstance(data.get("preferred_size"), int)
        self.assertGreater(data["preferred_size"], 0)
        self.assertIsInstance(data.get("max_concurrency"), int)
        self.assertGreaterEqual(data["max_concurrency"], 1)
        self.assertIsInstance(data.get("generator_weights_ready"), bool)

        storage = data.get("storage")
        self.assertIsInstance(storage, dict)
        for key in ("sessions_dir", "uploads_dir", "output_dir"):
            self.assertIn(key, storage)
            self.assertIsInstance(storage[key], str)
            self.assertTrue(len(storage[key]) > 0)
        self.assertEqual(storage["sessions_dir"], str(main.STORAGE_DIR))
        self.assertEqual(storage["uploads_dir"], str(main.UPLOAD_DIR))
        self.assertEqual(storage["output_dir"], str(main.OUTPUT_DIR))

    def test_resolve_data_dirs_defaults_and_env_override(self):
        base_dir = Path("/tmp/kobean-base")
        self.assertEqual(
            main.resolve_data_dirs(base_dir, None),
            (base_dir / "uploads", base_dir / "sessions", base_dir / "output"),
        )
        self.assertEqual(
            main.resolve_data_dirs(base_dir, ""),
            (base_dir / "uploads", base_dir / "sessions", base_dir / "output"),
        )
        self.assertEqual(
            main.resolve_data_dirs(base_dir, "   "),
            (base_dir / "uploads", base_dir / "sessions", base_dir / "output"),
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            custom_root = Path(tmp_dir)
            with patch.dict(os.environ, {"KOBEAN_DATA_DIR": tmp_dir}):
                resolved = main.resolve_data_dirs(base_dir, os.environ.get("KOBEAN_DATA_DIR"))
            self.assertEqual(
                resolved,
                (
                    custom_root / "uploads",
                    custom_root / "sessions",
                    custom_root / "output",
                ),
            )

    def test_resolve_safe_child_path_blocks_traversal_and_allows_valid_children(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            root_dir = tmp_path / "sessions"
            sibling_dir = tmp_path / "sessions_evil"
            root_dir.mkdir()
            sibling_dir.mkdir()
            outside_file = sibling_dir / "secret.png"
            outside_file.write_bytes(b"secret")

            valid = main.resolve_safe_child_path(root_dir, "sess1", "original", "page_0001.png")
            self.assertEqual(valid, (root_dir / "sess1" / "original" / "page_0001.png").resolve())

            symlink_escape = root_dir / "escape_link"
            symlink_escape.symlink_to(sibling_dir)

            unsafe_inputs = [
                ("",),
                (".",),
                ("..",),
                ("%2e%2e",),
                ("%2E%2E%2Fsecret.png",),
                ("sub/file.png",),
                ("sub\\file.png",),
                ("escape_link", "secret.png"),
            ]
            for parts in unsafe_inputs:
                with self.subTest(parts=parts):
                    with self.assertRaises(HTTPException) as ctx:
                        main.resolve_safe_child_path(root_dir, *parts)
                    self.assertEqual(ctx.exception.status_code, 400)
                    self.assertEqual(ctx.exception.detail, "Invalid or unsafe file path")

            # Verify HTTP traversal rejections & image Cache-Control headers
            sess_dir = root_dir / "sess1"
            (sess_dir / "original").mkdir(parents=True)
            (sess_dir / "colorized").mkdir(parents=True)
            (sess_dir / "original" / "p1.png").write_bytes(b"orig")
            (sess_dir / "colorized" / "p1.png").write_bytes(b"col")
            out_dir = tmp_path / "output"
            out_dir.mkdir()
            exemplar_dir = root_dir / "series_exemplars" / "naruto"
            exemplar_dir.mkdir(parents=True)

            with (
                patch.object(main, "STORAGE_DIR", root_dir),
                patch.object(main, "OUTPUT_DIR", out_dir),
            ):
                orig_resp = self.client.get("/api/session/sess1/image/original/p1.png")
                self.assertEqual(orig_resp.status_code, 200)
                self.assertEqual(orig_resp.headers.get("cache-control"), "public, max-age=3600")

                col_resp = self.client.get("/api/session/sess1/image/colorized/p1.png")
                self.assertEqual(col_resp.status_code, 200)
                self.assertEqual(col_resp.headers.get("cache-control"), "no-cache")

                for bad_url in (
                    "/api/session/%2e%2e/image/original/p1.png",
                    "/api/series-memory/%2e%2e/exemplar-image/p1.png",
                    "/api/download/combined/%2e%2e",
                    "/api/download/%2e%2e/out.pdf",
                ):
                    bad_resp = self.client.get(bad_url)
                    self.assertEqual(bad_resp.status_code, 400, bad_url)

    def test_security_headers_and_loopback_cors(self):
        resp = self.client.get("/api/health", headers={"Origin": "http://127.0.0.1:8000"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(resp.headers.get("x-frame-options"), "SAMEORIGIN")
        self.assertEqual(resp.headers.get("referrer-policy"), "no-referrer")
        self.assertEqual(resp.headers.get("cross-origin-resource-policy"), "same-origin")
        self.assertEqual(resp.headers.get("access-control-allow-origin"), "http://127.0.0.1:8000")

        localhost_resp = self.client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(
            localhost_resp.headers.get("access-control-allow-origin"), "http://localhost:5173"
        )

        evil_resp = self.client.get("/api/health", headers={"Origin": "https://evil.example.com"})
        self.assertIsNone(evil_resp.headers.get("access-control-allow-origin"))

    def test_save_session_meta_atomic_write_and_list_sessions_cache(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_dir = Path(tmp_dir)
            sid = "atomic-session-1"
            sess_payload = {
                "session_id": sid,
                "filename": "vol_01.cbz",
                "ext": ".cbz",
                "total_pages": 1,
                "pages": [{"page_index": 0, "status": "colorized"}],
                "status": "idle",
                "processed_count": 0,
            }
            orig_sessions = dict(main.SESSIONS)
            try:
                main.SESSIONS.clear()
                main.SESSIONS[sid] = sess_payload

                with patch.object(main, "STORAGE_DIR", storage_dir):
                    with patch("main.os.replace", wraps=os.replace) as mock_replace:
                        main.save_session_meta(sid)
                        self.assertEqual(mock_replace.call_count, 1)

                    sess_dir = storage_dir / sid
                    meta_path = sess_dir / "meta.json"
                    self.assertTrue(meta_path.is_file())
                    self.assertEqual(list(sess_dir.glob("*.tmp")), [])
                    saved = json.loads(meta_path.read_text(encoding="utf-8"))
                    self.assertEqual(saved["status"], "completed")
                    self.assertEqual(saved["processed_count"], 1)

                    # Verify failed dump cleans up tmp file and preserves existing meta.json
                    main.SESSIONS[sid]["bad"] = object()
                    main.save_session_meta(sid)
                    self.assertEqual(list(sess_dir.glob("*.tmp")), [])
                    preserved = json.loads(meta_path.read_text(encoding="utf-8"))
                    self.assertEqual(preserved["session_id"], sid)
                    main.SESSIONS[sid].pop("bad", None)

                    # Verify /api/sessions uses in-memory cache without re-parsing meta.json
                    with patch(
                        "main.get_or_restore_session",
                        side_effect=AssertionError("Should not re-parse cached session"),
                    ):
                        resp = self.client.get("/api/sessions")
                        self.assertEqual(resp.status_code, 200)
                        listed = resp.json()["sessions"]
                        self.assertEqual(len(listed), 1)
                        self.assertEqual(listed[0]["session_id"], sid)
            finally:
                main.SESSIONS.clear()
                main.SESSIONS.update(orig_sessions)


if __name__ == "__main__":
    unittest.main()
