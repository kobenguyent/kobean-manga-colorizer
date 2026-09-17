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


if __name__ == "__main__":
    unittest.main()
