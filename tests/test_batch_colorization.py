import unittest

import requests

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


def api_get(path: str):
    if USE_LIVE_SERVER:
        return requests.get(f"{BASE_URL}{path}")
    return test_client.get(path)


def api_post(path: str, **kwargs):
    if USE_LIVE_SERVER:
        return requests.post(f"{BASE_URL}{path}", **kwargs)
    return test_client.post(path, **kwargs)


class TestBatchColorization(unittest.TestCase):
    def test_batch_status_endpoint(self):
        res = api_get("/api/colorize/batch/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("is_running", data)
        self.assertIn("total_docs", data)
        self.assertIn("completed_docs", data)

    def test_sessions_natural_sort_and_counts(self):
        res = api_get("/api/sessions")
        self.assertEqual(res.status_code, 200)
        sessions = res.json().get("sessions", [])
        if not sessions:
            import fitz

            doc = fitz.open()
            doc.new_page(width=400, height=600)
            tmp = "/tmp/batch_test_init.pdf"
            doc.save(tmp)
            doc.close()
            with open(tmp, "rb") as f:
                api_post(
                    "/api/upload",
                    files={"file": ("batch_test_init.pdf", f, "application/pdf")},
                )
            res = api_get("/api/sessions")
            sessions = res.json().get("sessions", [])

        self.assertTrue(len(sessions) > 0)

        # Check that no session has processed_count > total_pages
        for s in sessions:
            if s.get("total_pages", 0) > 0:
                self.assertLessEqual(s.get("processed_count", 0), s.get("total_pages"))

        # Check natural sorting of Dr. Slump volumes
        slump_volumes = [s for s in sessions if "Dr. Slump" in s.get("filename", "")]
        if len(slump_volumes) >= 2:
            filenames = [s["filename"] for s in slump_volumes]
            # Ensure v01 comes before v02, v02 before v03, ... v09 before v10, v10 before v11
            self.assertEqual(filenames, sorted(filenames))

    def test_batch_and_single_page_character_palette_consistency(self):
        """Verifies that single-page preview and batch colorization pass identical palette and recognition parameters."""
        import asyncio
        import shutil
        import uuid
        from pathlib import Path
        from unittest.mock import patch
        from PIL import Image

        from colorizer_engine import CharacterEntry, CharacterPalette, RecognizedCharacter
        from main import (
            SESSIONS,
            SESSION_PALETTES,
            STORAGE_DIR,
            ColorizeRequest,
            _async_colorization_worker,
            save_session_meta,
            app,
        )
        from fastapi.testclient import TestClient

        client = TestClient(app)

        s_prev = "test_prev_" + str(uuid.uuid4())[:8]
        s_batch = "test_batch_" + str(uuid.uuid4())[:8]

        dir_prev = STORAGE_DIR / s_prev
        dir_batch = STORAGE_DIR / s_batch
        (dir_prev / "original").mkdir(parents=True, exist_ok=True)
        (dir_batch / "original").mkdir(parents=True, exist_ok=True)

        img_prev = dir_prev / "original" / "page_0000.jpg"
        img_batch = dir_batch / "original" / "page_0000.jpg"
        Image.new("L", (120, 160), color=240).save(img_prev)
        Image.new("L", (120, 160), color=240).save(img_batch)

        import copy

        chars = [
            CharacterEntry(name="Hanamichi Sakuragi", hair_hex="#D62828", visual_traits=["red_hair", "buzz_cut"]),
            CharacterEntry(name="Kaede Rukawa", hair_hex="#1C2833", visual_traits=["black_hair", "bangs"]),
        ]

        for s_id, p_path in [(s_prev, img_prev), (s_batch, img_batch)]:
            SESSIONS[s_id] = {
                "session_id": s_id,
                "filename": "SlamDunk.cbz",
                "preset_id": "slam_dunk",
                "total_pages": 1,
                "processed_count": 0,
                "status": "ready",
                "pages": [
                    {
                        "page_index": 0,
                        "original_path": str(p_path),
                        "original_filename": "page_0000.jpg",
                        "filename": "page_0000.jpg",
                        "status": "pending",
                    }
                ],
            }
            SESSION_PALETTES[s_id] = CharacterPalette(
                preset_title="Slam Dunk",
                characters=[copy.deepcopy(c) for c in chars],
            )
            save_session_meta(s_id)

        try:
            intercepted_calls = []

            def mock_colorize_page(**kwargs):
                intercepted_calls.append(kwargs)
                out_path = kwargs.get("output_path")
                if out_path:
                    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (120, 160), color=(200, 100, 50)).save(out_path)
                return {
                    "status": "success",
                    "output_path": out_path,
                    "engine": "TestEngine",
                    "recognized_characters": [
                        {"name": "Hanamichi Sakuragi", "confidence": 0.88, "bounding_box": [0.1, 0.1, 0.9, 0.9]}
                    ],
                }

            with patch("main.colorizer_engine.colorize_page", side_effect=mock_colorize_page):
                # 1. Single-page preview execution
                resp = client.post(
                    "/api/colorize/preview",
                    json={
                        "session_id": s_prev,
                        "page_index": 0,
                        "model_provider": "local_smart",
                        "model_name": "smart-engine",
                        "recognition_mode": "auto",
                        "denoise_screentone": True,
                    },
                )
                self.assertEqual(resp.status_code, 200)

                # 2. Batch colorization worker execution
                batch_req = ColorizeRequest(
                    session_id=s_batch,
                    model_provider="local_smart",
                    model_name="smart-engine",
                    recognition_mode="auto",
                    denoise_screentone=True,
                )
                asyncio.run(_async_colorization_worker(s_batch, batch_req))

            self.assertEqual(len(intercepted_calls), 2)
            prev_call = intercepted_calls[0]
            batch_call = intercepted_calls[1]

            # Verify identical recognition_mode and denoise parameters
            self.assertEqual(prev_call["recognition_mode"], "auto")
            self.assertEqual(batch_call["recognition_mode"], "auto")
            self.assertEqual(prev_call["recognition_mode"], batch_call["recognition_mode"])
            self.assertEqual(prev_call["denoise_screentone"], True)
            self.assertEqual(batch_call["denoise_screentone"], True)
            self.assertEqual(prev_call["skip_recognition"], False)
            self.assertEqual(batch_call["skip_recognition"], False)

            # Verify identical character palette structure and visual traits
            pal_prev = prev_call["character_palette"]
            pal_batch = batch_call["character_palette"]
            self.assertIsNotNone(pal_prev)
            self.assertIsNotNone(pal_batch)
            self.assertEqual([c.name for c in pal_prev.characters], [c.name for c in pal_batch.characters])
            self.assertEqual([c.hair_hex for c in pal_prev.characters], [c.hair_hex for c in pal_batch.characters])
            self.assertEqual(
                [c.visual_traits for c in pal_prev.characters],
                [c.visual_traits for c in pal_batch.characters],
            )

        finally:
            shutil.rmtree(dir_prev, ignore_errors=True)
            shutil.rmtree(dir_batch, ignore_errors=True)
            SESSIONS.pop(s_prev, None)
            SESSIONS.pop(s_batch, None)
            SESSION_PALETTES.pop(s_prev, None)
            SESSION_PALETTES.pop(s_batch, None)

    def test_batch_sibling_preset_propagation(self):
        """Verifies that selecting a preset for one session in a batch propagates to siblings sharing batch_id."""
        import shutil
        import uuid
        from main import (
            SESSIONS,
            SESSION_PALETTES,
            STORAGE_DIR,
            _resolve_base_palette,
            save_session_meta,
            app,
        )
        from fastapi.testclient import TestClient

        client = TestClient(app)

        batch_id = "test_batch_group_" + str(uuid.uuid4())[:8]
        s1 = "s1_" + str(uuid.uuid4())[:8]
        s2 = "s2_" + str(uuid.uuid4())[:8]

        d1 = STORAGE_DIR / s1
        d2 = STORAGE_DIR / s2
        d1.mkdir(parents=True, exist_ok=True)
        d2.mkdir(parents=True, exist_ok=True)

        SESSIONS[s1] = {
            "session_id": s1,
            "filename": "SlamDunk_Vol01.cbz",
            "batch_id": batch_id,
            "total_pages": 1,
            "processed_count": 0,
            "status": "ready",
            "pages": [],
        }
        SESSIONS[s2] = {
            "session_id": s2,
            "filename": "SlamDunk_Vol02.cbz",
            "batch_id": batch_id,
            "total_pages": 1,
            "processed_count": 0,
            "status": "ready",
            "pages": [],
        }
        save_session_meta(s1)
        save_session_meta(s2)

        try:
            # Apply preset to s1 with apply_to_batch=True
            resp = client.post(
                "/api/palette/apply-preset",
                json={"session_id": s1, "preset_id": "slam_dunk", "apply_to_batch": True},
            )
            self.assertEqual(resp.status_code, 200)

            # Both sessions must now have the preset applied
            self.assertEqual(SESSIONS[s1].get("preset_id"), "slam_dunk")
            self.assertEqual(SESSIONS[s2].get("preset_id"), "slam_dunk")

            self.assertIn(s1, SESSION_PALETTES)
            self.assertIn(s2, SESSION_PALETTES)

            # Visual traits such as buzz cut on Sakuragi must be preserved
            char1 = next(c for c in SESSION_PALETTES[s1].characters if c.name == "Hanamichi Sakuragi")
            char2 = next(c for c in SESSION_PALETTES[s2].characters if c.name == "Hanamichi Sakuragi")
            self.assertIn("buzz_cut", char1.visual_traits)
            self.assertIn("buzz_cut", char2.visual_traits)

            # Sibling inheritance in _resolve_base_palette
            SESSION_PALETTES.pop(s2, None)
            resolved = _resolve_base_palette(s2)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.preset_title, "Slam Dunk")

        finally:
            shutil.rmtree(d1, ignore_errors=True)
            shutil.rmtree(d2, ignore_errors=True)
            SESSIONS.pop(s1, None)
            SESSIONS.pop(s2, None)
            SESSION_PALETTES.pop(s1, None)
            SESSION_PALETTES.pop(s2, None)

    def test_start_batch_colorization_forwards_recognition_and_screentone(self):
        """Verifies /api/colorize/batch/start forwards recognition_mode and denoise_screentone to workers."""
        import asyncio
        import shutil
        import uuid
        from unittest.mock import AsyncMock, patch
        from PIL import Image
        from main import (
            CURRENT_BATCH,
            SESSIONS,
            SESSION_PALETTES,
            STORAGE_DIR,
            BatchColorizeRequest,
            save_session_meta,
            start_batch_colorization,
        )

        s_id = "test_fwd_" + str(uuid.uuid4())[:8]
        sess_dir = STORAGE_DIR / s_id
        (sess_dir / "original").mkdir(parents=True, exist_ok=True)
        img_p = sess_dir / "original" / "page_0000.jpg"
        Image.new("L", (100, 100), color=255).save(img_p)

        SESSIONS[s_id] = {
            "session_id": s_id,
            "filename": "Doc.pdf",
            "total_pages": 1,
            "processed_count": 0,
            "status": "ready",
            "pages": [
                {
                    "page_index": 0,
                    "original_path": str(img_p),
                    "original_filename": "page_0000.jpg",
                    "filename": "page_0000.jpg",
                    "status": "pending",
                }
            ],
        }
        save_session_meta(s_id)

        try:
            async def _test():
                CURRENT_BATCH["is_running"] = False
                with patch("main._async_colorization_worker", new_callable=AsyncMock) as mock_worker:
                    req = BatchColorizeRequest(
                        session_ids=[s_id],
                        model_provider="local_smart",
                        model_name="smart-engine",
                        recognition_mode="auto",
                        denoise_screentone=True,
                        preset_id="dr_slump",
                    )
                    await start_batch_colorization(req)
                    # Allow spawned _run_batch task to execute
                    await asyncio.sleep(0.05)

                    self.assertTrue(mock_worker.called)
                    call_sid, req_arg = mock_worker.call_args[0]
                    self.assertEqual(call_sid, s_id)
                    self.assertEqual(req_arg.recognition_mode, "auto")
                    self.assertEqual(req_arg.denoise_screentone, True)
                    # Preset was also propagated to session palette
                    self.assertIn(s_id, SESSION_PALETTES)
                    self.assertEqual(SESSION_PALETTES[s_id].preset_id, "dr_slump")

            asyncio.run(_test())

        finally:
            CURRENT_BATCH["is_running"] = False
            shutil.rmtree(sess_dir, ignore_errors=True)
            SESSIONS.pop(s_id, None)
            SESSION_PALETTES.pop(s_id, None)


if __name__ == "__main__":
    unittest.main()
