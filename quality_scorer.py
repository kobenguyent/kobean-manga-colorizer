"""
quality_scorer.py - Automated Manga Colorization Quality & Confidence Scorer.

Evaluates neural and semantic manga colorization outputs across three core dimensions:
1. Linework & Ink Integrity: Ensures dark ink boundaries remain deep and crisp without chromatic spill.
2. White Paper & Speech Bubble Purity: Guarantees dialogue bubbles and page margins stay clean white.
3. Color Richness & Palette Entropy: Validates vibrant, diverse multi-tone shading over monochromatic washes.

Computes a normalized confidence score (0.00 - 1.00) used for automated active-learning harvesting
and confidence-gated self-training.
"""

from __future__ import annotations

import os
from typing import Optional, Union

import cv2
import numpy as np
from PIL import Image


def _to_rgb_array(img_input: Union[np.ndarray, Image.Image, str], max_dim: int = 512) -> np.ndarray:
    """Helper to convert filepath, PIL Image, or numpy array to a standardized RGB uint8 array."""
    if isinstance(img_input, str):
        if not os.path.exists(img_input):
            raise FileNotFoundError(f"Image not found: {img_input}")
        with Image.open(img_input) as pil_img:
            img = pil_img.convert("RGB")
    elif isinstance(img_input, Image.Image):
        img = img_input.convert("RGB")
    elif isinstance(img_input, np.ndarray):
        if img_input.ndim == 2:
            arr = cv2.cvtColor(img_input, cv2.COLOR_GRAY2RGB)
        elif img_input.shape[2] == 4:
            arr = cv2.cvtColor(img_input, cv2.COLOR_RGBA2RGB)
        else:
            arr = img_input
        if arr.dtype != np.uint8:
            arr = np.clip(arr * 255.0 if arr.max() <= 1.0 else arr, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
    else:
        raise ValueError(f"Unsupported image input type: {type(img_input)}")

    # Downsample for ultra-fast, robust quality metrics (<5ms)
    w, h = img.size
    scale = min(1.0, max_dim / max(w, h))
    if scale < 1.0:
        new_w, new_h = max(16, int(w * scale)), max(16, int(h * scale))
        img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)

    return np.array(img, dtype=np.uint8)


def compute_linework_integrity(orig_gray: np.ndarray, color_hsv: np.ndarray) -> float:
    """
    Measures how cleanly black ink lines and hatching are preserved without chromatic spill.
    Dark ink pixels in original manga (gray < 70) should have near-zero saturation.
    """
    ink_mask = orig_gray < 70
    ink_count = np.count_nonzero(ink_mask)
    if ink_count < 20:
        return 0.90  # Very few ink lines detected

    ink_sat = color_hsv[:, :, 1][ink_mask] / 255.0
    mean_sat = float(np.mean(ink_sat))

    # Saturation > 0.35 in ink indicates heavy color bleeding
    score = 1.0 - min(1.0, mean_sat * 2.0)
    return float(np.clip(score, 0.0, 1.0))


def compute_white_purity(orig_gray: np.ndarray, color_hsv: np.ndarray) -> float:
    """
    Validates that speech bubbles, dialogue backgrounds, and outer page margins
    remain pure, unstained white without rainbow artifacts or tinted color casts.
    Targets:
    1. Speech bubbles (enclosed white contours containing inner text strokes).
    2. Outer page margins (border pixels with gray > 230).
    3. Ultra-bright specular highlights (orig_gray > 248).
    Does NOT penalize normal character skin, hair, or clothing coloring.
    """
    h, w = orig_gray.shape
    bubble_margin_mask = np.zeros((h, w), dtype=bool)

    # 1. Outer margins (dialogue and gutter borders)
    border_y = max(2, int(h * 0.03))
    border_x = max(2, int(w * 0.03))
    margin_zone = np.zeros((h, w), dtype=bool)
    margin_zone[:border_y, :] = True
    margin_zone[-border_y:, :] = True
    margin_zone[:, :border_x] = True
    margin_zone[:, -border_x:] = True
    bubble_margin_mask |= (margin_zone & (orig_gray > 230))

    # 2. Speech bubble contours containing inner text strokes
    try:
        paper_u = (orig_gray >= 210).astype(np.uint8) * 255
        contours, hierarchy = cv2.findContours(paper_u, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        if hierarchy is not None and len(hierarchy[0]) > 0:
            for cnt, hier in zip(contours, hierarchy[0]):
                if hier[2] != -1:  # Contour has inner child strokes (text)
                    area = cv2.contourArea(cnt)
                    if 250 < area < 0.35 * h * w:
                        child_idx = hier[2]
                        child_count = 0
                        while child_idx != -1:
                            child_count += 1
                            child_idx = hierarchy[0][child_idx][0]
                        if child_count >= 2:
                            mask_cnt = np.zeros((h, w), dtype=np.uint8)
                            cv2.drawContours(mask_cnt, [cnt], -1, 255, -1)
                            bubble_margin_mask |= ((mask_cnt > 0) & (orig_gray >= 195))
    except Exception:
        pass

    white_count = np.count_nonzero(bubble_margin_mask)
    if white_count < 20:
        return 0.95

    white_sat = color_hsv[:, :, 1][bubble_margin_mask] / 255.0
    white_val = color_hsv[:, :, 2][bubble_margin_mask] / 255.0

    mean_sat = float(np.mean(white_sat))
    # Penalize if white areas became dirty / darkened
    dark_pen = float(np.mean(np.clip(0.85 - white_val, 0.0, 1.0)))

    penalty = mean_sat * 2.8 + dark_pen * 1.5
    score = 1.0 - min(1.0, penalty)
    return float(np.clip(score, 0.0, 1.0))


def compute_color_richness(color_hsv: np.ndarray) -> float:
    """
    Evaluates chromatic diversity and saturation depth.
    Differentiates vibrant, multi-toned manga coloring from washed-out gray or flat sepia washes.
    """
    sat = color_hsv[:, :, 1] / 255.0
    val = color_hsv[:, :, 2] / 255.0
    hue = color_hsv[:, :, 0].astype(np.float32)  # 0..179 in OpenCV

    # Pixels with perceptible color (not pure black, white, or gray)
    chromatic_mask = (sat > 0.12) & (val > 0.15) & (val < 0.96)
    chromatic_ratio = float(np.count_nonzero(chromatic_mask)) / float(color_hsv.shape[0] * color_hsv.shape[1])

    if chromatic_ratio < 0.03:
        # Nearly completely uncolored / grayscale
        return 0.20

    # 1. Chromatic coverage score (ideal manga range: 15% to 75% colored)
    coverage_score = min(1.0, chromatic_ratio / 0.18)

    # 2. Mean saturation of chromatic regions (ideal: 0.30 to 0.75)
    chroma_sat = sat[chromatic_mask]
    mean_sat = float(np.mean(chroma_sat))
    sat_score = min(1.0, mean_sat / 0.35)

    # 3. Hue diversity / entropy
    chroma_hues = hue[chromatic_mask]
    hue_std = float(np.std(chroma_hues)) if len(chroma_hues) > 10 else 0.0
    hue_diversity_score = min(1.0, max(0.5, hue_std / 25.0))

    richness = 0.35 * coverage_score + 0.35 * sat_score + 0.30 * hue_diversity_score
    return float(np.clip(richness, 0.0, 1.0))


def calculate_quality_score(
    orig_img: Union[np.ndarray, Image.Image, str],
    color_img: Union[np.ndarray, Image.Image, str],
    auto_harvest_threshold: float = 0.82,
    is_skipped_colored: bool = False,
) -> dict:
    """
    Computes comprehensive quality assessment and confidence score for a colorized manga page.

    Returns:
        dict containing:
        - overall_score: float (0.00 to 1.00)
        - grade: "high" | "moderate" | "review_suggested"
        - auto_learn_eligible: bool (True if overall_score >= threshold)
        - metrics:
            - linework_integrity: float
            - white_purity: float
            - color_richness: float
        - threshold: float
    """
    if is_skipped_colored:
        # Original author color page (e.g. cover spread) is 100% ground-truth quality
        return {
            "overall_score": 1.0,
            "grade": "high",
            "auto_learn_eligible": True,
            "metrics": {
                "linework_integrity": 1.0,
                "white_purity": 1.0,
                "color_richness": 1.0,
            },
            "threshold": auto_harvest_threshold,
            "is_author_colored": True,
        }

    orig_rgb = _to_rgb_array(orig_img)
    color_rgb = _to_rgb_array(color_img)

    # Match spatial dimensions if necessary
    if orig_rgb.shape[:2] != color_rgb.shape[:2]:
        orig_rgb = cv2.resize(orig_rgb, (color_rgb.shape[1], color_rgb.shape[0]), interpolation=cv2.INTER_AREA)

    orig_gray = cv2.cvtColor(orig_rgb, cv2.COLOR_RGB2GRAY)
    color_hsv = cv2.cvtColor(color_rgb, cv2.COLOR_RGB2HSV)

    linework_score = compute_linework_integrity(orig_gray, color_hsv)
    white_score = compute_white_purity(orig_gray, color_hsv)
    richness_score = compute_color_richness(color_hsv)

    # Weighted composite score
    overall = 0.35 * linework_score + 0.35 * white_score + 0.30 * richness_score
    overall = float(np.clip(overall, 0.0, 1.0))

    # If the page has essentially no color added (e.g. failed inference or pure grayscale),
    # flag for human review regardless of pure line-art and paper
    if richness_score <= 0.25:
        overall = min(overall, 0.58)

    if overall >= auto_harvest_threshold:
        grade = "high"
    elif overall >= 0.65:
        grade = "moderate"
    else:
        grade = "review_suggested"

    return {
        "overall_score": round(overall, 3),
        "grade": grade,
        "auto_learn_eligible": bool(overall >= auto_harvest_threshold),
        "metrics": {
            "linework_integrity": round(linework_score, 3),
            "white_purity": round(white_score, 3),
            "color_richness": round(richness_score, 3),
        },
        "threshold": auto_harvest_threshold,
    }
