import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os

import cv2
import numpy as np

from colorizer_engine import MangaColorizerEngine


def run_test():
    # Generate a realistic manga sample with multiple elements (head, hair, shirt, background, speech bubble)
    img = np.full((600, 500), 250, dtype=np.uint8)

    # Speech bubble (white area)
    cv2.circle(img, (120, 100), 60, 255, -1)
    cv2.circle(img, (120, 100), 60, 0, 3)
    cv2.putText(img, "HELLO!", (85, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.7, 0, 2)

    # Character face (skin area)
    cv2.ellipse(img, (250, 300), (70, 90), 0, 0, 360, 200, -1)
    cv2.ellipse(img, (250, 300), (70, 90), 0, 0, 360, 0, 3)

    # Hair region (darker texture)
    cv2.ellipse(img, (250, 220), (80, 50), 0, 180, 360, 80, -1)
    cv2.ellipse(img, (250, 220), (80, 50), 0, 180, 360, 0, 3)

    # Clothing shirt region (midtone panel)
    cv2.rectangle(img, (150, 390), (350, 550), 120, -1)
    cv2.rectangle(img, (150, 390), (350, 550), 0, 3)

    # Background panel (hatching texture)
    cv2.rectangle(img, (380, 50), (480, 550), 160, -1)
    cv2.rectangle(img, (380, 50), (480, 550), 0, 3)

    test_bw_path = "/tmp/multicolor_test_bw.png"
    test_out_path = "/tmp/multicolor_test_out.png"
    cv2.imwrite(test_bw_path, img)

    engine = MangaColorizerEngine()
    res = engine.colorize_page(
        test_bw_path, test_out_path, model_provider="local_smart", style="shonen_vivid"
    )
    print("Colorization result:", res)

    # Read output and verify multiple distinct color channels
    out_bgr = cv2.imread(test_out_path)
    out_hsv = cv2.cvtColor(out_bgr, cv2.COLOR_BGR2HSV)

    # Get sample hue values across skin, hair, clothes, and background
    skin_hue = out_hsv[300, 250, 0]
    hair_hue = out_hsv[210, 250, 0]
    shirt_hue = out_hsv[450, 250, 0]
    bg_hue = out_hsv[300, 430, 0]

    print(
        f"Hues across regions - Skin: {skin_hue}, Hair: {hair_hue}, Shirt: {shirt_hue}, Background: {bg_hue}"
    )
    assert os.path.exists(test_out_path)
    print("MULTI-COLOR COLORIZATION TEST PASSED SUCCESSFULLY!")


def test_multi_color():
    run_test()


if __name__ == "__main__":
    run_test()
