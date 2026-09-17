import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from colorizer_engine import MangaColorizerEngine, resize_pad_manga
from file_processor import MangaFileProcessor


class TestAspectRatioPreservation(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.storage_dir = os.path.join(self.test_dir, "sessions")
        self.processor = MangaFileProcessor(self.storage_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_single_image_aspect_ratios(self):
        """Verify arbitrary single image aspect ratios (portrait, landscape, banner) are 100% preserved."""
        test_cases = [
            (800, 1200),  # Standard portrait (2:3)
            (1200, 800),  # Standard landscape (3:2)
            (1482, 2196),  # Real manga cover ratio
            (982, 763),  # Real manga credits landscape
            (1272, 486),  # Real manga wide banner
        ]

        for w, h in test_cases:
            img_path = os.path.join(self.test_dir, f"test_{w}x{h}.png")
            test_img = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
            cv2.imwrite(img_path, test_img)

            pages = self.processor._extract_single_image(img_path, Path(self.test_dir))
            self.assertEqual(len(pages), 1)
            p = pages[0]
            self.assertEqual(p["width"], w, f"Expected width {w} got {p['width']}")
            self.assertEqual(p["height"], h, f"Expected height {h} got {p['height']}")

            # Verify file on disk
            with Image.open(p["original_path"]) as disk_im:
                self.assertEqual(disk_im.size, (w, h))

    def test_epub_image_extraction_aspect_ratios(self):
        """Verify EPUB extraction maintains exact dimensions and natural order for multi-ratio manga."""
        epub_path = os.path.join(self.test_dir, "test_manga.epub")
        pages_specs = [
            ("image_0001.jpg", 1482, 2196),
            ("image_0002.jpg", 982, 763),
            ("image_0003.jpg", 1500, 2250),
            ("image_0010.jpg", 1272, 486),
        ]

        with zipfile.ZipFile(epub_path, "w") as zf:
            for name, w, h in pages_specs:
                buf = cv2.imencode(".jpg", np.ones((h, w, 3), dtype=np.uint8) * 128)[1].tobytes()
                zf.writestr(f"OEBPS/images/{name}", buf)

        out_dir = Path(self.test_dir) / "extracted"
        out_dir.mkdir(parents=True, exist_ok=True)
        pages_meta = self.processor._extract_epub_images(epub_path, out_dir)

        self.assertEqual(len(pages_meta), len(pages_specs))
        # Verify natural sorting: image_0003 must precede image_0010
        filenames = [p["filename"] for p in pages_meta]
        self.assertEqual(
            filenames, ["image_0001.jpg", "image_0002.jpg", "image_0003.jpg", "image_0004.jpg"]
        )

        # Check dimensions
        expected_dims = [(1482, 2196), (982, 763), (1500, 2250), (1272, 486)]
        for i, (exp_w, exp_h) in enumerate(expected_dims):
            self.assertEqual(pages_meta[i]["width"], exp_w)
            self.assertEqual(pages_meta[i]["height"], exp_h)

            with Image.open(pages_meta[i]["original_path"]) as im:
                self.assertEqual(im.size, (exp_w, exp_h))

    def test_neural_colorizer_aspect_ratio_preservation(self):
        """Verify resize_pad_manga and neural colorization strictly preserve original resolution and ratios."""
        engine = MangaColorizerEngine()

        test_sizes = [
            (600, 900),  # 2:3
            (900, 600),  # 3:2
            (1024, 768),  # 4:3
            (700, 1100),  # non-multiple of 32
        ]

        for w, h in test_sizes:
            dummy = np.zeros((h, w, 3), dtype=np.float32)
            padded, pad = resize_pad_manga(dummy, size=768)
            # Padded dimensions must be multiples of 32
            self.assertEqual(padded.shape[0] % 32, 0)
            self.assertEqual(padded.shape[1] % 32, 0)

            # Test full inference pipeline
            in_path = os.path.join(self.test_dir, f"in_{w}x{h}.png")
            out_path = os.path.join(self.test_dir, f"out_{w}x{h}.png")
            cv2.imwrite(in_path, (np.random.rand(h, w, 3) * 255).astype(np.uint8))

            res = engine.colorize_page(
                image_path=in_path,
                output_path=out_path,
                model_provider="resnext_generator",
                model_name="resnext_deep_gen",
                style="shonen_vivid",
            )
            self.assertEqual(res["status"], "success")

            # Check output image exact dimensions
            out_img = cv2.imread(out_path)
            self.assertEqual(
                out_img.shape[1], w, f"Width mismatch: expected {w}, got {out_img.shape[1]}"
            )
            self.assertEqual(
                out_img.shape[0], h, f"Height mismatch: expected {h}, got {out_img.shape[0]}"
            )


if __name__ == "__main__":
    unittest.main()
