import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
import requests

BASE_URL = "http://127.0.0.1:8000"

class TestHistoryUI(unittest.TestCase):
    def test_sessions_api_for_history(self):
        """Test GET /api/sessions returns active sessions with all required history fields."""
        resp = requests.get(f"{BASE_URL}/api/sessions")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("sessions", data)
        self.assertIsInstance(data["sessions"], list)

        if data["sessions"]:
            first = data["sessions"][0]
            self.assertIn("session_id", first)
            self.assertIn("filename", first)
            self.assertIn("ext", first)
            self.assertIn("total_pages", first)
            self.assertIn("processed_count", first)
            self.assertIn("status", first)

    def test_index_html_history_elements(self):
        """Test that index.html contains all History UI triggers and modal markup."""
        resp = requests.get(f"{BASE_URL}/")
        self.assertEqual(resp.status_code, 200)
        html = resp.text

        # Header history trigger
        self.assertIn('id="btn-open-history"', html)
        self.assertIn('id="history-badge-count"', html)
        self.assertIn('openHistoryModal()', html)

        # Modal elements
        self.assertIn('id="history-modal-overlay"', html)
        self.assertIn('id="history-modal-title"', html)
        self.assertIn('id="hist-stat-total"', html)
        self.assertIn('id="hist-stat-completed"', html)
        self.assertIn('id="hist-stat-processing"', html)
        self.assertIn('id="hist-stat-idle"', html)
        self.assertIn('id="history-search-input"', html)
        self.assertIn('id="history-list-container"', html)
        self.assertIn('id="btn-history-batch-export"', html)

    def test_static_assets_contain_history_handlers(self):
        """Test that static JavaScript and CSS contain History styling and logic."""
        # Check app.js
        js_resp = requests.get(f"{BASE_URL}/app.js")
        self.assertEqual(js_resp.status_code, 200)
        js = js_resp.text
        self.assertIn("openHistoryModal", js)
        self.assertIn("closeHistoryModal", js)
        self.assertIn("loadHistoryData", js)
        self.assertIn("renderHistoryList", js)
        self.assertIn("switchFromHistory", js)
        self.assertIn("exportDocumentFromHistory", js)

        # Check styles.css
        css_resp = requests.get(f"{BASE_URL}/styles.css")
        self.assertEqual(css_resp.status_code, 200)
        css = css_resp.text
        self.assertIn(".history-modal-dialog", css)
        self.assertIn(".history-stats-bar", css)
        self.assertIn(".history-item", css)

if __name__ == "__main__":
    unittest.main()
