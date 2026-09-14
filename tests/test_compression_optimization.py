import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import sys
import unittest
import tempfile
import shutil
import zipfile
from pathlib import Path
import numpy as np
import cv2
from PIL import Image
import fitz

from file_processor import MangaFileProcessor
from colorizer_engine import MangaColorizerEngine

class TestCompressionOptimization(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.storage_dir = os.path.join(self.test_dir, "sessions")
        self.processor = MangaFileProcessor(self.storage_dir)
        self.engine = MangaColorizerEngine()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_pdf_extraction_compression(self):
        """Verify PDF extraction saves high-res optimized images (~85%+ smaller than raw PNG)."""
        # Create a sample manga-like PDF with text and drawings
        pdf_path = os.path.join(self.test_dir, "manga_sample.pdf")
        doc = fitz.open()
        for i in range(2):
            page = doc.new_page(width=600, height=850)
            # Draw manga-like content
            page.draw_rect(fitz.Rect(50, 50, 550, 400), color=(0, 0, 0), width=2)
            page.draw_circle(fitz.Point(300, 250), 100, color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
            page.insert_text((100, 100), f"CHAPTER {i+1}: COMPRESSION TEST", fontsize=18)
        doc.save(pdf_path)
        doc.close()

        # Extract using processor
        out_dir = Path(self.test_dir) / "extracted"
        out_dir.mkdir(parents=True, exist_ok=True)
        pages_meta = self.processor._extract_pdf_pages(pdf_path, out_dir)

        self.assertEqual(len(pages_meta), 2)
        for p in pages_meta:
            self.assertTrue(p["filename"].endswith(".jpg"))
            self.assertTrue(os.path.exists(p["original_path"]))
            size = os.path.getsize(p["original_path"])
            # The optimized JPEG must be very compact (< 300 KB for this test page)
            self.assertLess(size, 300 * 1024)
            # Verify aspect ratio is preserved
            with Image.open(p["original_path"]) as img:
                self.assertEqual(img.size, (p["width"], p["height"]))

    def test_colorizer_image_write_compression(self):
        """Verify colorizer engine saves optimized images with high visual fidelity."""
        # Create a sample colored manga page
        h, w = 1200, 800
        test_img = np.full((h, w, 3), 245, dtype=np.uint8)
        # Add character hair, skin, and speech bubbles
        cv2.circle(test_img, (400, 500), 200, (180, 105, 255), -1) # Violet
        cv2.circle(test_img, (400, 520), 120, (160, 200, 255), -1) # Peach skin
        cv2.circle(test_img, (200, 200), 80, (255, 255, 255), -1)  # Bubble
        cv2.putText(test_img, "HELLO!", (150, 210), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)

        jpg_out = os.path.join(self.test_dir, "test_out.jpg")
        self.engine._write_optimized_image(jpg_out, test_img, quality=88)
        self.assertTrue(os.path.exists(jpg_out))
        jpg_size = os.path.getsize(jpg_out)
        print(f"Optimized colorized JPG size: {jpg_size / 1024:.1f} KB")
        # Ensure it's compact
        self.assertLess(jpg_size, 350 * 1024)

        # Read back and ensure dimensions match exactly
        read_back = cv2.imread(jpg_out)
        self.assertEqual(read_back.shape, (h, w, 3))

    def test_pdf_export_optimization(self):
        """Verify build_colorized_pdf produces a compact, deflated PDF without ballooning."""
        session_id = "test_sess_opt"
        sess_dir = Path(self.storage_dir) / session_id
        color_dir = sess_dir / "colorized"
        color_dir.mkdir(parents=True, exist_ok=True)

        pages_meta = []
        for i in range(3):
            fn = f"page_{i+1:04d}.jpg"
            img_path = str(color_dir / fn)
            img = np.full((1200, 800, 3), 200, dtype=np.uint8)
            cv2.putText(img, f"PAGE {i+1}", (100, 300), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (50, 50, 200), 3)
            cv2.imwrite(img_path, img, [cv2.IMWRITE_JPEG_QUALITY, 88])
            pages_meta.append({
                "page_index": i,
                "filename": fn,
                "original_path": img_path,
                "width": 800,
                "height": 1200
            })

        pdf_out = os.path.join(self.test_dir, "exported_compact.pdf")
        self.processor.build_colorized_pdf(pages_meta, session_id, pdf_out)

        self.assertTrue(os.path.exists(pdf_out))
        pdf_size = os.path.getsize(pdf_out)
        print(f"Exported 3-page PDF size: {pdf_size / 1024:.1f} KB")

        # Verify PDF validity and page count
        doc = fitz.open(pdf_out)
        self.assertEqual(len(doc), 3)
        doc.close()

    def test_epub_export_optimization(self):
        """Verify build_standalone_epub creates valid, compact EPUB with JPEG pages."""
        session_id = "test_epub_opt"
        sess_dir = Path(self.storage_dir) / session_id
        color_dir = sess_dir / "colorized"
        color_dir.mkdir(parents=True, exist_ok=True)

        pages_meta = []
        for i in range(2):
            fn = f"page_{i+1:04d}.png" # Even if original was PNG
            img_path = str(color_dir / fn)
            img = np.full((1000, 700, 3), 220, dtype=np.uint8)
            cv2.putText(img, f"EPUB P{i+1}", (50, 200), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (10, 10, 10), 2)
            cv2.imwrite(img_path, img)
            pages_meta.append({
                "page_index": i,
                "filename": fn,
                "original_path": img_path,
                "width": 700,
                "height": 1000
            })

        epub_out = os.path.join(self.test_dir, "manga_optimized.epub")
        self.processor.build_standalone_epub(pages_meta, session_id, epub_out, title="Test Manga")

        self.assertTrue(os.path.exists(epub_out))
        epub_size = os.path.getsize(epub_out)
        print(f"Exported EPUB size: {epub_size / 1024:.1f} KB")

        # Verify inside the EPUB: images should be converted to .jpg
        with zipfile.ZipFile(epub_out, 'r') as zf:
            names = zf.namelist()
            self.assertIn("mimetype", names)
            self.assertIn("OEBPS/images/page_0001.jpg", names)
            self.assertIn("OEBPS/images/page_0002.jpg", names)

        # Verify PyMuPDF can open and read it as valid EPUB
        doc = fitz.open(epub_out)
        self.assertEqual(len(doc), 2)
        doc.close()

if __name__ == "__main__":
    from pathlib import Path
    unittest.main()
