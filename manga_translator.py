"""
manga_translator.py - AI-Powered Manga Translation & Typesetting Engine

Provides end-to-end Japanese-to-English translation for manga pages:
1. Speech bubble & text region detection (Manga109 YOLO + contour heuristics)
2. Japanese OCR (offline manga-ocr VisionEncoderDecoder)
3. Context-aware translation (Google Gemini Multimodal or MyMemory/local fallback)
4. Speech bubble cleaning & inpainting (removes Japanese characters seamlessly)
5. Professional typesetting (auto-wrapping, dynamic font sizing, centered text)
"""

import base64
import json
import os
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

import cv2
import numpy as np
import requests
import torch
from PIL import Image, ImageDraw, ImageFont

try:
    from colorizer_engine import gpu_inference_scope
except ImportError:
    import contextlib

    @contextlib.contextmanager
    def gpu_inference_scope(device: Optional[str] = None):
        yield

# ─────────────────────────────────────────────────────────────────────
#  Data Structures
# ─────────────────────────────────────────────────────────────────────

@dataclass
class MangaTranslationItem:
    box: tuple[int, int, int, int]  # (x0, y0, x1, y1) in pixel coordinates
    japanese_text: str
    english_text: str
    confidence: float = 1.0


# Japanese Unicode character ranges: Hiragana, Katakana, Kanji
JAPANESE_WORDS_REGEX = re.compile(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]")

# Hallucination keywords commonly found in public translation memory corruptions
CORRUPT_TRANSLATION_MARKERS = [
    "metamask",
    "blockchain",
    "wallet provider",
    "page <x id=",
    "creative commons",
    "wikipedia",
    "http://",
    "https://",
    "translation memory",
]

# Common manga dialogue phrases, addresses, and exclamations
MANGA_COMMON_DICT: dict[str, str] = {
    "父さん": "Dad",
    "お父さん": "Dad",
    "とうさん": "Dad",
    "オヤジ": "Old man",
    "母さん": "Mom",
    "お母さん": "Mom",
    "かあさん": "Mom",
    "兄さん": "Big brother",
    "お兄さん": "Big brother",
    "姉さん": "Big sister",
    "お姉さん": "Big sister",
    "先生": "Teacher",
    "おい": "Hey",
    "おーい": "Hey",
    "待て": "Wait",
    "待って": "Wait",
    "待ってください": "Please wait",
    "誰だ": "Who's there?",
    "何だ": "What?",
    "何": "What",
    "助けて": "Help me",
    "助けてくれ": "Help me",
    "ダメだ": "No",
    "だめだ": "No",
    "そうだ": "That's right",
    "違う": "No, that's wrong",
    "バカ": "Idiot",
    "ばか": "Idiot",
    "まさか": "It can't be",
    "くそ": "Damn it",
    "くそっ": "Damn it",
    "ちくしょう": "Damn it",
    "ああ": "Ah",
    "うわあ": "Whoa",
    "うわっ": "Whoa",
    "はい": "Yes",
    "いいえ": "No",
    "ありがとう": "Thank you",
    "ありがとうございます": "Thank you very much",
    "おはよう": "Good morning",
    "おはようございます": "Good morning",
    "こんにちは": "Hello",
    "こんばんは": "Good evening",
    "さようなら": "Goodbye",
    "じゃあな": "See ya",
    "またな": "See you later",
    "了解": "Understood",
    "りょうかい": "Understood",
    "わかった": "Got it",
    "分かった": "Got it",
    "わからない": "I don't know",
    "分からない": "I don't know",
    "すまない": "Sorry",
    "ごめん": "Sorry",
    "ごめんなさい": "I'm sorry",
    "逃げろ": "Run!",
    "にげろ": "Run!",
    "危ない": "Watch out!",
    "あぶない": "Watch out!",
    "やめろ": "Stop!",
    "止まれ": "Stop!",
    "行け": "Go!",
    "いけ": "Go!",
    "行くぞ": "Let's go!",
    "いくぞ": "Here I go!",
    "死ね": "Die!",
    "嘘だ": "That's a lie!",
    "うそだ": "That's a lie!",
    "信じられん": "Unbelievable",
    "信じられない": "I can't believe it",
    "やった": "We did it!",
    "やったぞ": "I did it!",
    "勝った": "I won!",
    "頼む": "Please",
    "たのむ": "Please",
    "お前": "You",
    "あんた": "You",
    "貴様": "You bastard",
    "誰": "Who",
    "どこ": "Where",
    "いつ": "When",
    "なぜ": "Why",
    "どうして": "Why",
}


def extract_trailing_punctuation(text: str) -> tuple[str, str]:
    """Extracts trailing punctuation to preserve original emotion during translation."""
    m = re.search(r"([.!?~]+)$", text)
    if m:
        return text[:m.start()].strip(), m.group(1)
    return text.strip(), ""

FONT_CANDIDATES = [
    # macOS standard fonts
    "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    # Linux standard fonts
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    # Windows standard fonts
    "C:/Windows/Fonts/comic.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def sanitize_japanese_text(text: str) -> tuple[bool, str]:
    """
    Sanitizes extracted Japanese text:
    - Normalizes full-width Japanese punctuation (．．． -> ..., ！！ -> !!)
    - Determines if the text contains actual Japanese words/kanji/kana that require machine translation.
    Returns:
        (needs_translation: bool, cleaned_text: str)
    """
    t = (text or "").strip()
    if not t:
        return False, ""

    # Normalize Japanese fullwidth punctuation
    t = (
        t.replace("．", ".")
        .replace("！", "!")
        .replace("？", "?")
        .replace("・", "...")
        .replace("…", "...")
        .replace("－", "-")
        .replace("―", "-")
        .replace("～", "~")
        .replace("，", ", ")
    )
    t = re.sub(r"\.{3,}", "...", t)
    t = re.sub(r"!{2,}", "!!", t)
    t = re.sub(r"\?{2,}", "??", t)

    has_words = bool(JAPANESE_WORDS_REGEX.search(t))
    return has_words, t.strip()


def is_valid_translation(original_ja: str, translated: str, target_lang: str = "en") -> bool:
    """
    Validates that machine translation produced valid text in target language.
    Rejects:
    - Empty or whitespace strings
    - Untranslated Japanese text (identical to original or containing CJK characters when target is English)
    - Hallucinations containing corrupt markers (e.g. metamask, blockchain, http links)
    - Extreme length ratio hallucinations (e.g. <=4 chars yielding > 60 chars)
    """
    if not translated or not translated.strip():
        return False

    t = translated.strip()
    orig = (original_ja or "").strip()

    # If the original text had Japanese words
    if JAPANESE_WORDS_REGEX.search(orig):
        # Translation cannot be identical to the original Japanese text
        if t == orig:
            return False

        # When translating to English (or Latin-based languages), ensure it doesn't still have CJK characters
        if target_lang.lower().startswith("en"):
            cjk_matches = JAPANESE_WORDS_REGEX.findall(t)
            if cjk_matches:
                if len(cjk_matches) / max(1, len(t)) > 0.10:
                    return False
                if len(t) < 6:
                    return False

    # Check for corrupt markers
    t_low = t.lower()
    if any(m in t_low for m in CORRUPT_TRANSLATION_MARKERS):
        return False

    # Reject extreme hallucination ratio
    if len(orig) <= 4 and len(t) > 60:
        return False

    return True


GOOGLE_TRANSLATE_CLIENTS = ["dict-chrome-ex", "at", "it", "p", "gtx"]


def _gtx_translate(text: str, target_lang: str = "en", timeout: float = 6.0) -> str:
    """
    Fast, reliable translation using Google Translate's single web endpoints.
    Rotates through multiple known client endpoints to avoid 429 rate limits.
    """
    if not text or not text.strip():
        return ""
    url = "https://translate.googleapis.com/translate_a/single"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        )
    }
    for client in GOOGLE_TRANSLATE_CLIENTS:
        try:
            params = {
                "client": client,
                "sl": "ja",
                "tl": target_lang,
                "dt": "t",
                "q": text,
            }
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                    translated_parts = [part[0] for part in data[0] if part and len(part) > 0 and part[0]]
                    res = "".join(translated_parts).strip()
                    if res:
                        return res
        except Exception:
            continue
    return ""


class MangaTranslator:
    """
    Modular translation engine for Japanese manga pages.
    Supports Google Gemini multimodal AI as well as local offline AI (Manga109 YOLO + manga-ocr).
    """

    _manga_ocr_instance: Optional[Any] = None
    _font_path: Optional[str] = None

    def __init__(self, device: Optional[str] = None):
        if device is None:
            if torch.backends.mps.is_available():
                self.device = "mps"
            elif torch.cuda.is_available():
                self.device = "cuda"
            else:
                self.device = "cpu"
        else:
            self.device = device

    @classmethod
    def _get_font_path(cls) -> Optional[str]:
        if cls._font_path is not None:
            return cls._font_path
        for p in FONT_CANDIDATES:
            if os.path.exists(p):
                cls._font_path = p
                return p
        return None

    @classmethod
    def _ensure_manga_ocr(cls):
        """Lazy-loads offline manga-ocr model for Japanese text recognition."""
        if cls._manga_ocr_instance is not None:
            return cls._manga_ocr_instance
        try:
            from manga_ocr import MangaOcr

            with gpu_inference_scope():
                print("[MangaTranslator] Initializing offline manga-ocr VisionEncoderDecoder...")
                cls._manga_ocr_instance = MangaOcr()
                return cls._manga_ocr_instance
        except Exception as e:
            print(f"[MangaTranslator WARNING] Failed to load manga-ocr: {e}")
            return None

    def _ensure_yolo(self):
        """Retrieves lazy-loaded Manga109 YOLO model from colorizer_engine."""
        try:
            from colorizer_engine import MangaCharacterRecognizer

            return MangaCharacterRecognizer._ensure_manga_yolo()
        except Exception as e:
            print(f"[MangaTranslator WARNING] Could not access YOLO model: {e}")
            return None, "cpu"

    # ─────────────────────────────────────────────────────────────────
    #  1. Detection: Text Boxes & Speech Bubbles
    # ─────────────────────────────────────────────────────────────────

    def detect_text_regions(
        self,
        pil_img: Image.Image,
        cv_img: Optional[np.ndarray] = None,
        conf: float = 0.10,
    ) -> list[tuple[int, int, int, int]]:
        """
        Detects bounding boxes of speech bubbles and text regions on the manga page.
        Returns list of (x0, y0, x1, y1) in pixel coordinates.
        """
        w, h = pil_img.size
        if cv_img is None:
            cv_img = np.array(pil_img.convert("RGB"))
            cv_img = cv2.cvtColor(cv_img, cv2.COLOR_RGB2BGR)

        detected_boxes: list[tuple[int, int, int, int]] = []

        # 1. Primary: YOLO Manga109 text detections
        yolo_model, dev = self._ensure_yolo()
        if yolo_model is not None:
            try:
                with gpu_inference_scope(dev):
                    preds = yolo_model.predict(
                        pil_img, device=dev, conf=conf, imgsz=1280, verbose=False
                    )[0]
                raw_boxes: list[tuple[float, tuple[int, int, int, int]]] = []
                for b in preds.boxes:
                    cls_id = int(b.cls[0])
                    cls_name = yolo_model.names.get(cls_id, "")
                    if cls_name == "text":
                        conf_val = float(b.conf[0])
                        bx0, by0, bx1, by1 = b.xyxy[0].tolist()
                        pw = (bx1 - bx0) * 0.04
                        ph = (by1 - by0) * 0.04
                        raw_boxes.append(
                            (
                                conf_val,
                                (
                                    max(0, int(bx0 - pw)),
                                    max(0, int(by0 - ph)),
                                    min(w, int(bx1 + pw)),
                                    min(h, int(by1 + ph)),
                                ),
                            )
                        )

                # Confidence-ranked NMS suppression: higher confidence boxes are prioritized
                raw_boxes.sort(key=lambda item: item[0], reverse=True)
                filtered_boxes: list[tuple[int, int, int, int]] = []

                for conf_val, b in raw_boxes:
                    x0, y0, x1, y1 = b
                    b_area = (x1 - x0) * (y1 - y0)
                    roi = cv_img[y0:y1, x0:x1]
                    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi

                    # Discard boxes that are dominated by dark artwork/hair rather than text
                    dark_r = float(np.mean(gray < 160))
                    if dark_r > 0.45:
                        continue

                    suppress = False
                    for k in filtered_boxes:
                        kx0, ky0, kx1, ky1 = k
                        k_area = (kx1 - kx0) * (ky1 - ky0)
                        ix0, iy0 = max(x0, kx0), max(y0, ky0)
                        ix1, iy1 = min(x1, kx1), min(y1, ky1)
                        if ix1 > ix0 and iy1 > iy0:
                            inter = (ix1 - ix0) * (iy1 - iy0)
                            iou = inter / float(b_area + k_area - inter)
                            containment = inter / float(min(b_area, k_area))
                            # Suppress lower-confidence overlapping boxes (prevents bloated ghost expansions)
                            if iou >= 0.28 or containment >= 0.50:
                                suppress = True
                                break

                    if not suppress:
                        filtered_boxes.append(b)

                detected_boxes = filtered_boxes
            except Exception as e:
                print(f"[MangaTranslator WARNING] YOLO text detection error: {e}")

            # When the offline YOLO detector is active, its prediction is authoritative.
            # If YOLO detected 0 text boxes, there are NO speech bubbles on this page.
            # Never run noisy contour fallback on pages where YOLO found 0 text boxes.
            if not detected_boxes:
                return []
            return sorted(detected_boxes, key=lambda b: (b[1] // 100, -b[0]))

        # 2. Strict contour fallback ONLY if YOLO model failed to load entirely (yolo_model is None)
        if yolo_model is None and not detected_boxes:
            try:
                gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY) if cv_img.ndim == 3 else cv_img
                # Speech bubbles are almost pure white paper: threshold at >= 235
                paper = (gray >= 235).astype(np.uint8) * 255
                contours, hierarchy = cv2.findContours(paper, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                if hierarchy is not None and len(hierarchy[0]) > 0:
                    max_area = int(0.08 * h * w)  # Never allow large panels
                    min_area = int(0.002 * h * w)
                    max_dim_w = int(0.30 * w)
                    max_dim_h = int(0.30 * h)
                    for cnt, hier in zip(contours, hierarchy[0]):
                        if hier[2] != -1:  # Has child contours (inner text)
                            area = cv2.contourArea(cnt)
                            if min_area < area < max_area:
                                bx, by, bw, bh = cv2.boundingRect(cnt)
                                if bw <= max_dim_w and bh <= max_dim_h:
                                    aspect = bw / float(max(1, bh))
                                    if 0.30 <= aspect <= 2.8:
                                        roi_gray = gray[by : by + bh, bx : bx + bw]
                                        if roi_gray.size > 0:
                                            # Speech bubble interior must be predominantly white
                                            if np.median(roi_gray) >= 225:
                                                dark_ratio = float(np.mean(roi_gray < 160))
                                                if 0.02 <= dark_ratio <= 0.28:
                                                    detected_boxes.append((bx, by, bx + bw, by + bh))
            except Exception as e:
                print(f"[MangaTranslator WARNING] Contour bubble detection error: {e}")

        if not detected_boxes:
            return []

        # 3. Non-Maximum Suppression / Merging overlapping boxes
        merged = self._merge_overlapping_boxes(detected_boxes, w, h)
        return merged

    @staticmethod
    def _merge_overlapping_boxes(
        boxes: list[tuple[int, int, int, int]], w_max: int, h_max: int, iou_thresh: float = 0.35
    ) -> list[tuple[int, int, int, int]]:
        """Merges heavily overlapping bounding boxes to group multi-column Japanese dialogue."""
        if not boxes:
            return []

        # Sort reading order: Top-to-bottom, Right-to-left
        sorted_boxes = sorted(boxes, key=lambda b: (b[1] // 100, -b[0]))
        keep: list[tuple[int, int, int, int]] = []

        for b in sorted_boxes:
            x0, y0, x1, y1 = b
            b_area = (x1 - x0) * (y1 - y0)
            merged = False
            for idx, k in enumerate(keep):
                kx0, ky0, kx1, ky1 = k
                k_area = (kx1 - kx0) * (ky1 - ky0)
                ix0, iy0 = max(x0, kx0), max(y0, ky0)
                ix1, iy1 = min(x1, kx1), min(y1, ky1)
                if ix1 > ix0 and iy1 > iy0:
                    inter = (ix1 - ix0) * (iy1 - iy0)
                    union = b_area + k_area - inter
                    iou = inter / float(max(1, union))
                    containment = inter / float(min(b_area, k_area))
                    if iou >= iou_thresh or containment >= 0.70:
                        keep[idx] = (
                            min(x0, kx0),
                            min(y0, ky0),
                            max(x1, kx1),
                            max(y1, ky1),
                        )
                        merged = True
                        break
            if not merged:
                keep.append(b)

        return sorted(keep, key=lambda b: (b[1] // 100, -b[0]))

    # ─────────────────────────────────────────────────────────────────
    #  2. Text Cleaning & Inpainting
    # ─────────────────────────────────────────────────────────────────

    def clean_speech_bubble(
        self,
        img: np.ndarray,
        box: tuple[int, int, int, int],
        return_status: bool = False,
    ) -> Union[np.ndarray, tuple[np.ndarray, bool]]:
        """
        Cleans the Japanese text strokes out of the speech bubble area,
        leaving a clean canvas for English typesetting while preserving bubble outlines.
        Guarded against accidentally wiping out character artwork or panels.
        """
        H, W = img.shape[:2]
        x0, y0, x1, y1 = box
        bw = x1 - x0
        bh = y1 - y0

        def _ret(result_img: np.ndarray, success: bool):
            return (result_img, success) if return_status else result_img

        # Safety Guard 1: Never clean oversized boxes on manga pages (panels or multi-panel regions)
        if W >= 500 and H >= 500:
            if bw > int(0.48 * W) or bh > int(0.48 * H) or (bw * bh) > int(0.16 * W * H):
                return _ret(img, False)

        pad = 6
        cx0 = max(0, x0 - pad)
        cy0 = max(0, y0 - pad)
        cx1 = min(W, x1 + pad)
        cy1 = min(H, y1 + pad)

        roi = img[cy0:cy1, cx0:cx1]
        if roi.size == 0 or roi.shape[0] < 8 or roi.shape[1] < 8:
            return _ret(img, False)

        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
        roi_area = gray.shape[0] * gray.shape[1]

        # Safety Guard 2: Adaptive paper luminance detection
        # Handles pure white paper, warm vintage scans, colorized page tints, and light screentones
        p75 = float(np.percentile(gray, 75))
        p90 = float(np.percentile(gray, 90))

        if p90 < 150:
            # Entire region is too dark to be a speech bubble (character artwork or dark panel)
            return _ret(img, False)

        paper_thresh = max(150, min(215, int(p75 - 15))) if p90 >= 160 else max(130, int(p90 - 20))
        white_paper = (gray >= paper_thresh).astype(np.uint8) * 255
        if np.mean(white_paper > 0) < 0.10:
            return _ret(img, False)

        # Close gaps between text strokes to form the continuous bubble interior
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (19, 19))
        closed = cv2.morphologyEx(white_paper, cv2.MORPH_CLOSE, kernel)

        # Retain substantial white paper components (the speech bubble)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(closed)
        bubble_mask = np.zeros_like(gray, dtype=np.uint8)

        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            if area >= max(180, int(0.025 * roi_area)):
                bubble_mask[labels == i] = 255

        cleaned_text = False
        if np.sum(bubble_mask > 0) >= max(180, int(0.05 * roi_area)):
            # Erode bubble body so we NEVER touch border lines, spikes, or exterior artwork
            eroded_body = cv2.erode(bubble_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
            ink_cutoff = min(int(paper_thresh - 15), 185)
            text_mask = ((gray <= ink_cutoff) & (eroded_body > 0)).astype(np.uint8) * 255
            text_mask = cv2.dilate(text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        else:
            # Fallback for borderless speech bubbles or bubbles touching the panel frame:
            # Clean dark text strokes strictly inside the inner text bounding box margins
            inner_body = np.zeros_like(gray, dtype=np.uint8)
            bx0 = max(2, x0 - cx0)
            by0 = max(2, y0 - cy0)
            bx1 = min(gray.shape[1] - 2, x1 - cx0)
            by1 = min(gray.shape[0] - 2, y1 - cy0)
            inner_body[by0:by1, bx0:bx1] = 255

            ink_cutoff = min(int(p75 - 20), 175)
            text_mask = ((gray <= ink_cutoff) & (inner_body > 0)).astype(np.uint8) * 255
            text_mask = cv2.dilate(text_mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
            bubble_mask = inner_body

        if np.any(text_mask > 0):
            # Sample dominant bubble paper color
            paper_pixels = roi[bubble_mask > 0]
            if paper_pixels.size > 0:
                bg_color = np.median(paper_pixels, axis=0)
                if isinstance(bg_color, (list, tuple, np.ndarray)):
                    fill_val = [min(255, max(225, int(c))) for c in bg_color]
                else:
                    c_int = min(255, max(225, int(bg_color)))
                    fill_val = [c_int, c_int, c_int]
            else:
                fill_val = [255, 255, 255]

            if roi.ndim == 3:
                for c in range(roi.shape[2]):
                    roi[text_mask > 0, c] = fill_val[c] if c < len(fill_val) else 255
            else:
                roi[text_mask > 0] = fill_val[0]

            img[cy0:cy1, cx0:cx1] = roi
            cleaned_text = True

        return _ret(img, cleaned_text)

    def find_bubble_bounds(
        self,
        cleaned_gray: np.ndarray,
        text_box: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int]:
        """
        Expands a detected text box into the enclosing speech bubble boundary
        for natural English typesetting. Raycasts outward into the cleaned white space.
        """
        H, W = cleaned_gray.shape[:2]
        bx0, by0, bx1, by1 = text_box
        cx = (bx0 + bx1) // 2
        cy = (by0 + by1) // 2
        bh = by1 - by0

        max_pad_x = min(int(max(20, bh * 0.30)), int(0.18 * W))
        max_pad_y = min(int(max(10, bh * 0.18)), int(0.12 * H))

        # Sample horizontal extent at 3 vertical points around center
        l_candidates = []
        r_candidates = []
        sample_ys = [max(0, cy - 15), cy, min(H - 1, cy + 15)]

        for y in sample_ys:
            lx = cx
            while lx > max(0, cx - max_pad_x) and cleaned_gray[y, lx] >= 180:
                lx -= 1
            l_candidates.append(lx)

            rx = cx
            while rx < min(W - 1, cx + max_pad_x) and cleaned_gray[y, rx] >= 180:
                rx += 1
            r_candidates.append(rx)

        uy = cy
        while uy > max(0, cy - max_pad_y) and cleaned_gray[uy, cx] >= 180:
            uy -= 1

        dy = cy
        while dy < min(H - 1, cy + max_pad_y) and cleaned_gray[dy, cx] >= 180:
            dy += 1

        # Use median of candidate limits to resist single-point notches/spikes
        cand_lx = int(np.median(l_candidates)) if l_candidates else bx0
        cand_rx = int(np.median(r_candidates)) if r_candidates else bx1

        # Apply safe inner margin (4px)
        bubble_x0 = min(bx0, cand_lx + 4)
        bubble_x1 = max(bx1, cand_rx - 4) if cleaned_gray[cy, min(W - 1, bx1)] >= 180 else min(bx1, cand_rx - 4)
        bubble_y0 = min(by0, uy + 4)
        bubble_y1 = max(by1, dy - 4) if cleaned_gray[min(H - 1, by1), cx] >= 180 else min(by1, dy - 4)

        return (max(0, bubble_x0), max(0, bubble_y0), min(W, bubble_x1), min(H, bubble_y1))

    # ─────────────────────────────────────────────────────────────────
    #  3. Typesetting & Text Rendering
    # ─────────────────────────────────────────────────────────────────

    def typeset_bubble(
        self,
        pil_img: Image.Image,
        text: str,
        box: tuple[int, int, int, int],
        uppercase: bool = True,
        text_color: tuple[int, int, int] = (15, 15, 15),
        draw_background: bool = False,
    ) -> Image.Image:
        """
        Typesets English translated text into the speech bubble box with:
        - Word-count-aware manga lettering size caps (prevents comically oversized text)
        - Elliptical speech bubble safe inner margins
        - Dynamic auto-scaling font size with intelligent word wrapping
        - Perfect horizontal and vertical centering without top/bottom overflow
        - Optional fail-safe white backdrop for uncleaned/difficult bubbles
        """
        clean_text = (text or "").strip()
        if not clean_text:
            return pil_img

        if uppercase:
            clean_text = clean_text.upper()

        draw = ImageDraw.Draw(pil_img)
        x0, y0, x1, y1 = box
        bw = x1 - x0
        bh = y1 - y0

        if bw < 15 or bh < 15:
            return pil_img

        words = clean_text.split()
        word_count = len(words)
        scale = (pil_img.height / 1200.0) if getattr(pil_img, "height", None) else 1.0

        # Manga-authentic dialogue lettering size caps based on word count
        if word_count <= 2:
            fs_cap = int(26 * scale)
        elif word_count <= 5:
            fs_cap = int(21 * scale)
        elif word_count <= 10:
            fs_cap = int(17 * scale)
        elif word_count <= 16:
            fs_cap = int(15 * scale)
        else:
            fs_cap = int(13 * scale)

        # Elliptical bubble safe inner margins (22% margin so text stays within curved bubble body)
        target_w = max(12, int(bw * 0.78))
        target_h = max(12, int(bh * 0.78))

        bw_factor = 0.45 if word_count <= 2 else 0.34
        max_fs = max(10, min(fs_cap, int(bh * 0.30), int(bw * bw_factor)))
        min_fs = 9

        best_font = None
        best_lines: list[str] = []

        font_path = self._get_font_path()

        for fs in range(max_fs, min_fs - 1, -1):
            try:
                if font_path:
                    font = ImageFont.truetype(font_path, fs)
                else:
                    font = ImageFont.load_default(fs)
            except Exception:
                font = ImageFont.load_default()

            lines: list[str] = []
            cur_line: list[str] = []
            fit_failed = False

            for w in words:
                test_str = " ".join(cur_line + [w])
                bbox = font.getbbox(test_str)
                line_w = bbox[2] - bbox[0]
                if line_w <= target_w:
                    cur_line.append(w)
                else:
                    if not cur_line:
                        fit_failed = True
                        break
                    lines.append(" ".join(cur_line))
                    cur_line = [w]
                    w_bbox = font.getbbox(w)
                    if (w_bbox[2] - w_bbox[0]) > target_w:
                        fit_failed = True
                        break

            if cur_line:
                lines.append(" ".join(cur_line))

            if fit_failed:
                continue

            line_heights = [font.getbbox(ln)[3] - font.getbbox(ln)[1] for ln in lines]
            line_spacing = max(1, int(fs * 0.20))
            total_h = sum(line_heights) + (len(lines) - 1) * line_spacing

            if total_h <= target_h:
                best_font = font
                best_lines = lines
                break

        if not best_lines or best_font is None:
            try:
                best_font = (
                    ImageFont.truetype(font_path, min_fs)
                    if font_path
                    else ImageFont.load_default(min_fs)
                )
            except Exception:
                best_font = ImageFont.load_default()
            chars_per_line = max(6, int(target_w / (min_fs * 0.6)))
            best_lines = textwrap.wrap(clean_text, width=chars_per_line) or [clean_text]

        line_heights = [best_font.getbbox(ln)[3] - best_font.getbbox(ln)[1] for ln in best_lines]
        line_widths = [best_font.getbbox(ln)[2] - best_font.getbbox(ln)[0] for ln in best_lines]
        max_lw = max(line_widths) if line_widths else 0

        font_size = getattr(best_font, "size", 12)
        line_spacing = max(1, int(font_size * 0.20))
        total_h = sum(line_heights) + (len(best_lines) - 1) * line_spacing

        # Prevent text from overflowing above the bubble top or below the bottom
        start_y = max(y0 + 2, y0 + (bh - total_h) // 2)

        if draw_background:
            pad_x = max(6, int(font_size * 0.45))
            pad_y = max(4, int(font_size * 0.35))
            bg_box = [
                max(x0, x0 + (bw - max_lw) // 2 - pad_x),
                max(y0, start_y - pad_y),
                min(x1, x0 + (bw + max_lw) // 2 + pad_x),
                min(y1, start_y + total_h + pad_y),
            ]
            draw.rounded_rectangle(bg_box, radius=max(6, int(font_size * 0.5)), fill=(255, 255, 255, 252))

        cur_y = start_y
        for line in best_lines:
            bbox = best_font.getbbox(line)
            lw = bbox[2] - bbox[0]
            lh = bbox[3] - bbox[1]
            cur_x = x0 + (bw - lw) // 2

            # Subtle white halo around text to guarantee readability
            for ox, oy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                draw.text((cur_x + ox, cur_y + oy), line, fill=(255, 255, 255), font=best_font)

            draw.text((cur_x, cur_y), line, fill=text_color, font=best_font)
            cur_y += lh + line_spacing

        return pil_img

    # ─────────────────────────────────────────────────────────────────
    #  4. Translation Service (Gemini Multimodal / Local OCR + Free Web)
    # ─────────────────────────────────────────────────────────────────

    def translate_japanese_text(
        self,
        text: str,
        target_lang: str = "en",
        api_key: str = "",
    ) -> str:
        """
        Translates a single extracted Japanese string into the target language.
        Normalizes punctuation and sanitizes against hallucinated translations.
        Returns empty string if translation fails to prevent rendering tofu boxes.
        """
        needs_trans, clean = sanitize_japanese_text(text)
        if not clean:
            return ""

        # If text doesn't contain Japanese characters, return sanitized punctuation/text as is
        if not needs_trans:
            return clean

        stem, punct = extract_trailing_punctuation(clean)

        # 1. Manga dialogue dictionary for authentic character addresses and expressions
        if stem in MANGA_COMMON_DICT:
            return MANGA_COMMON_DICT[stem] + punct

        # 2. Fast & reliable Google GTX endpoint
        gtx_res = _gtx_translate(clean, target_lang=target_lang)
        if gtx_res and is_valid_translation(clean, gtx_res, target_lang=target_lang):
            return gtx_res

        # 3. Free high-quality MyMemory translation
        try:
            from deep_translator import MyMemoryTranslator

            translator = MyMemoryTranslator(source="ja-JP", target=f"{target_lang}-US")
            translated = translator.translate(clean)
            if translated and translated.strip():
                t_clean = translated.strip().strip('"').strip("'")
                if t_clean.startswith("- "):
                    t_clean = t_clean[2:].strip()
                if is_valid_translation(clean, t_clean, target_lang=target_lang):
                    return t_clean
        except Exception as e:
            print(f"[MangaTranslator] MyMemory translation fallback: {e}")

        # 4. Google Translate Web fallback
        try:
            from deep_translator import GoogleTranslator

            g_trans = GoogleTranslator(source="ja", target=target_lang)
            res = g_trans.translate(clean)
            if res and res.strip():
                t_clean = res.strip().strip('"').strip("'")
                if t_clean.startswith("- "):
                    t_clean = t_clean[2:].strip()
                if is_valid_translation(clean, t_clean, target_lang=target_lang):
                    return t_clean
        except Exception:
            pass

        # NEVER return raw Japanese text when translation fails to prevent rendering tofu boxes □□□□
        return ""

    def _translate_page_with_gemini(
        self,
        pil_img: Image.Image,
        api_key: str,
        target_lang: str = "en",
        model_name: str = "gemini-2.5-flash",
    ) -> list[MangaTranslationItem]:
        """
        Translates an entire manga page using Google Gemini's multimodal vision API.
        Extracts speech bubble coordinates and natural context-aware English translation.
        """
        import io

        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=88)
        b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")

        prompt = (
            "You are a professional manga localization expert and typesetter.\n"
            f"Detect all Japanese dialogue, speech bubbles, sound effects, and narration boxes on this manga page.\n"
            f"Translate each text into natural, idiomatic {target_lang.upper()} dialogue suitable for manga speech bubbles.\n"
            "Return ONLY a valid JSON array of objects with the exact following schema and no extra markdown wrapping:\n"
            "[\n"
            "  {\n"
            '    "box_2d": [ymin, xmin, ymax, xmax],\n'
            '    "japanese": "Original Japanese text",\n'
            '    "english": "Natural English translation"\n'
            "  }\n"
            "]\n"
            "Note: box_2d coordinates must be normalized integers from 0 to 1000 representing [ymin, xmin, ymax, xmax].\n"
            "If no Japanese text is found, return []."
        )

        target_model = model_name or "gemini-2.5-flash"
        if "nano" in target_model.lower():
            target_model = "gemini-2.5-flash"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:generateContent?key={api_key}"
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg",
                                "data": b64_img,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        resp = requests.post(url, json=body, headers={"Content-Type": "application/json"}, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"Gemini API error ({resp.status_code}): {resp.text[:140]}")

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return []

        text_content = ""
        for p in candidates[0].get("content", {}).get("parts", []):
            if "text" in p:
                text_content += p["text"]

        text_content = text_content.strip()
        if text_content.startswith("```"):
            text_content = re.sub(r"^```(?:json)?\n?", "", text_content)
            text_content = re.sub(r"\n?```$", "", text_content)

        parsed = json.loads(text_content)
        w, h = pil_img.size
        items: list[MangaTranslationItem] = []

        for entry in parsed:
            box_2d = entry.get("box_2d") or entry.get("box")
            if not box_2d or len(box_2d) != 4:
                continue

            ymin, xmin, ymax, xmax = box_2d
            if ymax <= 1000 and xmax <= 1000 and (ymax > 1.0 or xmax > 1.0):
                px0 = max(0, int((xmin / 1000.0) * w))
                py0 = max(0, int((ymin / 1000.0) * h))
                px1 = min(w, int((xmax / 1000.0) * w))
                py1 = min(h, int((ymax / 1000.0) * h))
            elif ymax <= 1.01 and xmax <= 1.01:
                px0 = max(0, int(xmin * w))
                py0 = max(0, int(ymin * h))
                px1 = min(w, int(xmax * w))
                py1 = min(h, int(ymax * h))
            else:
                px0, py0, px1, py1 = int(xmin), int(ymin), int(xmax), int(ymax)

            ja = entry.get("japanese") or ""
            en = entry.get("english") or entry.get("translation") or ""

            if en and is_valid_translation(ja, en, target_lang=target_lang):
                items.append(
                    MangaTranslationItem(
                        box=(px0, py0, px1, py1),
                        japanese_text=ja,
                        english_text=en,
                        confidence=0.98,
                    )
                )

        return items

    # ─────────────────────────────────────────────────────────────────
    #  5. Complete Page Translation Pipeline
    # ─────────────────────────────────────────────────────────────────

    def translate_page(
        self,
        image_input: Union[str, Path, Image.Image, np.ndarray],
        target_lang: str = "en",
        engine: str = "auto",
        api_key: str = "",
        uppercase: bool = True,
        existing_translations: Optional[list[dict[str, Any]]] = None,
    ) -> tuple[Image.Image, list[dict[str, Any]]]:
        """
        Executes the full translation and typesetting pipeline on a manga page.
        If existing_translations are supplied (e.g. during page recolorization),
        instantly cleans and typesets them onto the new image without calling OCR or external APIs.
        Returns:
            (translated_pil_image, list_of_translation_metadata_dicts)
        """
        if isinstance(image_input, (str, Path)):
            pil_img = Image.open(str(image_input)).convert("RGB")
        elif isinstance(image_input, np.ndarray):
            if image_input.ndim == 2:
                pil_img = Image.fromarray(image_input).convert("RGB")
            else:
                pil_img = Image.fromarray(cv2.cvtColor(image_input, cv2.COLOR_BGR2RGB))
        else:
            pil_img = image_input.copy().convert("RGB")

        w, h = pil_img.size
        cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        mode = (engine or "auto").lower()
        gemini_key = api_key or os.environ.get("GOOGLE_API_KEY", "") or os.environ.get("GEMINI_API_KEY", "")

        translation_items: list[MangaTranslationItem] = []

        # 0. Reuse existing translations if available (e.g. preserving translations when recolorizing)
        if existing_translations:
            for it in existing_translations:
                b = it.get("box")
                if b and len(b) == 4 and (it.get("english") or it.get("japanese")):
                    translation_items.append(
                        MangaTranslationItem(
                            box=tuple(int(v) for v in b),
                            japanese_text=it.get("japanese", ""),
                            english_text=it.get("english") or it.get("japanese", ""),
                            confidence=float(it.get("confidence", 0.88)),
                        )
                    )

        # 1. Cloud Multimodal Vision (Google Gemini)
        if not translation_items and (mode in ("gemini", "cloud", "google_nano") or (mode == "auto" and gemini_key)):
            if gemini_key:
                try:
                    gemini_items = self._translate_page_with_gemini(
                        pil_img=pil_img,
                        api_key=gemini_key,
                        target_lang=target_lang,
                    )
                    if gemini_items:
                        translation_items = gemini_items
                except Exception as e:
                    print(f"[MangaTranslator WARNING] Gemini page translation fallback: {e}")

        # 2. Local AI Pipeline (Manga109 YOLO + manga-ocr + free translation)
        if not translation_items:
            # Step A: Detect speech bubbles & text regions
            text_boxes = self.detect_text_regions(pil_img, cv_img=cv_img)

            # Step B: OCR with manga-ocr
            mocr = self._ensure_manga_ocr()

            for box in text_boxes:
                x0, y0, x1, y1 = box
                if (x1 - x0) < 14 or (y1 - y0) < 14:
                    continue

                crop_pil = pil_img.crop((x0, y0, x1, y1))
                raw_ja = ""
                if mocr is not None:
                    try:
                        with gpu_inference_scope(self.device):
                            raw_ja = mocr(crop_pil)
                    except Exception as e:
                        print(f"[MangaTranslator WARNING] OCR error on box {box}: {e}")

                if raw_ja and raw_ja.strip():
                    needs_trans, clean_ja = sanitize_japanese_text(raw_ja)
                    # Only process speech bubbles containing actual Japanese words/kanji/kana
                    # Punctuation-only boxes (... or !!) should NOT be bleached or typeset
                    if clean_ja and needs_trans:
                        en_text = self.translate_japanese_text(
                            clean_ja, target_lang=target_lang, api_key=gemini_key
                        )
                        if en_text and is_valid_translation(clean_ja, en_text, target_lang=target_lang):
                            translation_items.append(
                                MangaTranslationItem(
                                    box=box,
                                    japanese_text=clean_ja,
                                    english_text=en_text,
                                    confidence=0.88,
                                )
                            )

        # Safety Guard: If no valid translations were obtained, leave image 100% untouched!
        if not translation_items:
            return pil_img.copy(), []

        # 3. Clean speech bubbles on the image
        working_img = cv_img.copy()
        cleaning_status: list[bool] = []
        for item in translation_items:
            pad = 6
            padded_box = (
                max(0, item.box[0] - pad),
                max(0, item.box[1] - pad),
                min(w, item.box[2] + pad),
                min(h, item.box[3] + pad),
            )
            working_img, was_cleaned = self.clean_speech_bubble(working_img, padded_box, return_status=True)
            cleaning_status.append(was_cleaned)

        # Convert back to PIL for high-fidelity typesetting
        translated_pil = Image.fromarray(cv2.cvtColor(working_img, cv2.COLOR_BGR2RGB))
        cleaned_gray = cv2.cvtColor(working_img, cv2.COLOR_BGR2GRAY)

        # 4. Typeset English dialogue into speech bubbles
        for i, item in enumerate(translation_items):
            was_cleaned = cleaning_status[i] if i < len(cleaning_status) else True
            typeset_box = self.find_bubble_bounds(cleaned_gray, item.box)
            translated_pil = self.typeset_bubble(
                pil_img=translated_pil,
                text=item.english_text,
                box=typeset_box,
                uppercase=uppercase,
                draw_background=(not was_cleaned),
            )

        metadata = [
            {
                "box": list(it.box),
                "japanese": it.japanese_text,
                "english": it.english_text,
                "confidence": it.confidence,
            }
            for it in translation_items
        ]

        return translated_pil, metadata


# Global singleton instance
MANGA_TRANSLATOR = MangaTranslator()
