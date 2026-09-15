import unittest
import requests

BASE_URL = "http://127.0.0.1:8000"

class TestBatchColorization(unittest.TestCase):
    def test_batch_status_endpoint(self):
        res = requests.get(f"{BASE_URL}/api/colorize/batch/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("is_running", data)
        self.assertIn("total_docs", data)
        self.assertIn("completed_docs", data)

    def test_sessions_natural_sort_and_counts(self):
        res = requests.get(f"{BASE_URL}/api/sessions")
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
                requests.post(f"{BASE_URL}/api/upload", files={"file": ("batch_test_init.pdf", f, "application/pdf")})
            res = requests.get(f"{BASE_URL}/api/sessions")
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
