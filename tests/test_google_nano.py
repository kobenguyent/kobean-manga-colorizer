import unittest
from unittest.mock import patch, MagicMock
import base64
import os
import io
import cv2
import numpy as np
from PIL import Image

from colorizer_engine import MangaColorizerEngine

class TestGoogleNanoBananaAPI(unittest.TestCase):
    def setUp(self):
        self.engine = MangaColorizerEngine()
        self.test_img_path = "/tmp/test_google_manga.png"
        self.test_out_path = "/tmp/test_google_manga_out.png"

        # Create a simple black & white test image
        img = np.full((300, 200, 3), 255, dtype=np.uint8)
        cv2.rectangle(img, (20, 20), (180, 280), (0, 0, 0), 2)
        cv2.imwrite(self.test_img_path, img)

    def tearDown(self):
        for p in [self.test_img_path, self.test_out_path]:
            if os.path.exists(p):
                os.remove(p)

    @patch("requests.post")
    def test_google_api_key_used_when_provided(self, mock_post):
        """Verifies that Google Gemini API is called with mapped model when api_key is provided."""
        # Create a fake 100x100 RGB image response from Gemini
        fake_color = Image.new("RGB", (200, 300), color=(100, 150, 200))
        buf = io.BytesIO()
        fake_color.save(buf, format="PNG")
        fake_b64 = base64.b64encode(buf.getvalue()).decode()

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{
                "content": {
                    "parts": [{
                        "inlineData": {
                            "mimeType": "image/png",
                            "data": fake_b64
                        }
                    }]
                }
            }]
        }
        mock_post.return_value = mock_resp

        res = self.engine.colorize_page(
            image_path=self.test_img_path,
            output_path=self.test_out_path,
            model_provider="google_nano",
            model_name="nano-banana",
            api_key="AIzaSyValidTestKey123"
        )

        # 1. Verify requests.post was called to Google Generative Language API
        self.assertTrue(mock_post.called)
        called_url = mock_post.call_args[0][0]
        self.assertIn("generativelanguage.googleapis.com", called_url)
        self.assertIn("gemini-2.0-flash-exp", called_url)
        self.assertIn("key=AIzaSyValidTestKey123", called_url)

        # 2. Verify returned engine name indicates real Google Gemini API was used
        self.assertIn("Google Gemini Nano Banana (gemini-2.0-flash-exp)", res.get("engine"))
        self.assertEqual(res.get("status"), "success")
        self.assertTrue(os.path.exists(self.test_out_path))

    def test_google_nano_fallback_without_key(self):
        """Verifies that when no API key is provided, engine gracefully uses vibrant anime neural fallback."""
        res = self.engine.colorize_page(
            image_path=self.test_img_path,
            output_path=self.test_out_path,
            model_provider="google_nano",
            model_name="nano-banana",
            api_key=""
        )
        self.assertEqual(res.get("status"), "success")
        self.assertTrue(os.path.exists(self.test_out_path))

def test_google_nano():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestGoogleNanoBananaAPI)
    runner = unittest.TextTestRunner()
    result = runner.run(suite)
    assert result.wasSuccessful()

if __name__ == "__main__":
    unittest.main()
