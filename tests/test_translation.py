"""
tests/test_translation.py - Unit and Integration Tests for Manga Translation Engine
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import SESSIONS, STORAGE_DIR, app
from manga_translator import (
    MANGA_TRANSLATOR,
    MangaTranslator,
    _gtx_translate,
    is_valid_translation,
    sanitize_japanese_text,
)


@pytest.fixture
def client():
    return TestClient(app)


# ─────────────────────────────────────────────────────────────────────
# 1. Unit Tests: Text Sanitization & Heuristics
# ─────────────────────────────────────────────────────────────────────

def test_sanitize_japanese_text_empty():
    needs_trans, text = sanitize_japanese_text("")
    assert needs_trans is False
    assert text == ""

    needs_trans, text = sanitize_japanese_text("   \n\t  ")
    assert needs_trans is False
    assert text == ""


def test_sanitize_japanese_text_punctuation_normalization():
    # Fullwidth ellipses and exclamations
    needs_trans, text = sanitize_japanese_text("．．．！！")
    assert needs_trans is False
    assert text == "...!!"

    needs_trans, text = sanitize_japanese_text("！？……")
    assert needs_trans is False
    assert "..." in text


def test_sanitize_japanese_text_japanese_characters():
    # Hiragana
    needs_trans, text = sanitize_japanese_text("こんにちは")
    assert needs_trans is True
    assert text == "こんにちは"

    # Katakana
    needs_trans, text = sanitize_japanese_text("エネルギー！")
    assert needs_trans is True
    assert "エネルギー" in text
    assert text.endswith("!")

    # Kanji
    needs_trans, text = sanitize_japanese_text("絶対勝利")
    assert needs_trans is True
    assert text == "絶対勝利"


def test_is_valid_translation():
    # Reject empty or whitespace
    assert is_valid_translation("何", "") is False
    assert is_valid_translation("何", "   ") is False

    # Reject untranslated Japanese text (identical to original)
    assert is_valid_translation("何が起きているんだ", "何が起きているんだ", target_lang="en") is False

    # Reject text containing mostly Japanese characters when target is English
    assert is_valid_translation("何が起きているんだ", "何が起きているんだ?!", target_lang="en") is False
    assert is_valid_translation("く、", "く、", target_lang="en") is False

    # Reject corrupt translation memory markers
    assert is_valid_translation("はい", "metamask wallet provider", target_lang="en") is False
    assert is_valid_translation("はい", "creative commons license", target_lang="en") is False
    assert is_valid_translation("はい", "https://example.com/test", target_lang="en") is False

    # Reject extreme length hallucinations
    assert is_valid_translation("何", "This is an extremely long hallucinated text that has way too many words for a single character input", target_lang="en") is False

    # Accept valid translations
    assert is_valid_translation("何が起きているんだ？！", "What's going on?!", target_lang="en") is True
    assert is_valid_translation("父さん", "Dad", target_lang="en") is True
    assert is_valid_translation("行け！", "Go!", target_lang="en") is True


# ─────────────────────────────────────────────────────────────────────
# 2. Unit Tests: Bubble Inpainting & Typesetting
# ─────────────────────────────────────────────────────────────────────

def test_clean_speech_bubble():
    translator = MangaTranslator()

    # Create a 200x200 image with a white speech bubble and black text inside
    img = np.full((200, 200, 3), 200, dtype=np.uint8)
    cv2.circle(img, (100, 100), 80, (255, 255, 255), -1)  # white bubble
    cv2.putText(img, "TEST", (60, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)  # black text

    box = (30, 30, 170, 170)
    cleaned = translator.clean_speech_bubble(img, box)

    assert cleaned.shape == img.shape
    # Check that dark ink pixels were filled with bubble background
    sample_text_region = cleaned[90:110, 55:145]
    assert np.mean(sample_text_region) > 200  # Inpainted to near white


def test_typeset_bubble():
    translator = MangaTranslator()

    img = Image.new("RGB", (300, 300), color=(255, 255, 255))
    box = (50, 50, 250, 250)

    # Typeset short and long English text
    typeset_img = translator.typeset_bubble(
        pil_img=img,
        text="Hello world! This is a test manga speech bubble translation.",
        box=box,
        uppercase=True,
    )

    assert isinstance(typeset_img, Image.Image)
    assert typeset_img.size == (300, 300)

    # Ensure black text pixels exist within the box
    arr = np.array(typeset_img)
    interior = arr[50:250, 50:250]
    assert np.min(interior) < 50  # Contains dark drawn text


def test_typeset_bubble_empty_text():
    translator = MangaTranslator()
    img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    result = translator.typeset_bubble(img, text="", box=(10, 10, 100, 100))
    assert result == img


# ─────────────────────────────────────────────────────────────────────
# 3. Unit Tests: Translation Pipeline
# ─────────────────────────────────────────────────────────────────────

def test_translate_japanese_text_punctuation_bypass():
    translator = MangaTranslator()
    # Should bypass machine translation and return punctuation directly
    res = translator.translate_japanese_text("．．．！")
    assert res == "...!"


@patch("manga_translator._gtx_translate", return_value="")
@patch("deep_translator.MyMemoryTranslator.translate", return_value="What's going on?!")
def test_translate_japanese_text_mymemory(mock_translate, mock_gtx):
    translator = MangaTranslator()
    translated = translator.translate_japanese_text("何が起きているんだ？！", target_lang="en")
    assert translated == "What's going on?!"


def test_translate_japanese_text_gtx_mocked():
    with patch("requests.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [[["Wait!", "待て", None, None]]]
        mock_get.return_value = mock_resp

        res = _gtx_translate("待て", target_lang="en")
        assert res == "Wait!"


def test_translate_japanese_text_failure_returns_empty_prevents_tofu():
    translator = MangaTranslator()
    with patch("manga_translator._gtx_translate", return_value=""):
        with patch("deep_translator.MyMemoryTranslator.translate", side_effect=Exception("429 TooManyRequests")):
            with patch("deep_translator.GoogleTranslator.translate", side_effect=Exception("Scraping blocked")):
                # When all web translators fail, must return "" (NEVER original Japanese!)
                res = translator.translate_japanese_text("見知らぬ文章サンプルです", target_lang="en")
                assert res == "", "Must return empty string on failure to prevent rendering tofu boxes"


def test_translate_japanese_text_manga_dictionary():
    translator = MangaTranslator()
    # Punctuation reattachment with common manga dialogue expressions
    assert translator.translate_japanese_text("父さん！！") == "Dad!!"
    assert translator.translate_japanese_text("父さん...") == "Dad..."
    assert translator.translate_japanese_text("ダメだ...") == "No..."
    assert translator.translate_japanese_text("先生！") == "Teacher!"


def test_clean_speech_bubble_rejects_oversized_panels():
    translator = MangaTranslator()
    # 1000x1200 page with a large bottom artwork panel (e.g. 800x300)
    img = np.full((1200, 1000, 3), 100, dtype=np.uint8)
    original_copy = img.copy()
    box = (50, 850, 950, 1150)  # Very large panel
    cleaned = translator.clean_speech_bubble(img, box)
    # Must be rejected by safety guard and left completely unchanged
    np.testing.assert_array_equal(cleaned, original_copy)


def test_clean_speech_bubble_rejects_high_ink_artwork():
    translator = MangaTranslator()
    # 600x600 page with a dense character drawing (70% dark ink)
    img = np.zeros((600, 600, 3), dtype=np.uint8)
    original_copy = img.copy()
    box = (50, 50, 200, 200)
    cleaned = translator.clean_speech_bubble(img, box)
    # Must be rejected because dark ink > 0.45
    np.testing.assert_array_equal(cleaned, original_copy)


def test_find_bubble_bounds():
    translator = MangaTranslator()
    # Create white bubble (radius 40 at 100, 100) inside dark background
    gray = np.zeros((200, 200), dtype=np.uint8)
    cv2.circle(gray, (100, 100), 40, 255, -1)
    text_box = (90, 80, 110, 120)  # Narrow text box inside bubble
    bounds = translator.find_bubble_bounds(gray, text_box)
    bx0, by0, bx1, by1 = bounds
    # Bounds should expand outwards into the white bubble
    assert bx0 <= text_box[0]
    assert bx1 >= text_box[2]
    assert by0 <= text_box[1]
    assert by1 >= text_box[3]


def test_translate_page_mocked():
    translator = MangaTranslator()
    img = Image.new("RGB", (400, 500), color=(255, 255, 255))

    mock_boxes = [(50, 50, 200, 200)]
    mock_ocr = MagicMock(return_value="こんにちは")

    with patch.object(translator, "detect_text_regions", return_value=mock_boxes):
        with patch.object(translator, "_ensure_manga_ocr", return_value=mock_ocr):
            with patch.object(translator, "translate_japanese_text", return_value="HELLO"):
                res_img, metadata = translator.translate_page(img, engine="local")
                assert isinstance(res_img, Image.Image)
                assert len(metadata) == 1
                assert metadata[0]["japanese"] == "こんにちは"
                assert metadata[0]["english"] == "HELLO"
                assert metadata[0]["box"] == [50, 50, 200, 200]


def test_translate_page_empty_dialogue_untouched():
    translator = MangaTranslator()
    img = Image.new("RGB", (300, 400), color=(128, 128, 128))
    # When detector finds 0 text boxes, original image must be 100% untouched
    with patch.object(translator, "detect_text_regions", return_value=[]):
        res_img, metadata = translator.translate_page(img, engine="local")
        assert len(metadata) == 0
        diff = np.max(np.abs(np.array(img) - np.array(res_img)))
        assert diff == 0


def test_translate_page_punctuation_only_skipped():
    translator = MangaTranslator()
    img = Image.new("RGB", (300, 400), color=(200, 200, 200))
    # When OCR finds only punctuation like "..." or "!!", it should not be bleached or typeset
    with patch.object(translator, "detect_text_regions", return_value=[(20, 20, 100, 100)]):
        with patch.object(translator, "_ensure_manga_ocr", return_value=MagicMock(return_value="．．．")):
            res_img, metadata = translator.translate_page(img, engine="local")
            assert len(metadata) == 0
            diff = np.max(np.abs(np.array(img) - np.array(res_img)))
            assert diff == 0


def test_translate_page_action_screenshot_6():
    screenshot_path = Path("/Users/kobet/Desktop/Screenshot_ 6.png")
    if not screenshot_path.exists():
        pytest.skip("Screenshot_ 6.png not present on test environment")

    orig_img = Image.open(screenshot_path).convert("RGB")
    res_img, meta = MANGA_TRANSLATOR.translate_page(orig_img, engine="local")

    assert len(meta) == 0, "Action scene should have 0 detected dialogue bubbles"
    diff = np.max(np.abs(np.array(orig_img) - np.array(res_img)))
    assert diff == 0, "Action scene image must be left 100% untouched with 0 pixel difference"


def test_translate_page_dialogue_screenshot_8():
    screenshot_path = Path("/Users/kobet/Desktop/Screenshot_ 8.png")
    if not screenshot_path.exists():
        pytest.skip("Screenshot_ 8.png not present on test environment")

    orig_img = Image.open(screenshot_path).convert("RGB")
    res_img, meta = MANGA_TRANSLATOR.translate_page(orig_img, engine="local")

    assert len(meta) >= 2, "Must detect and translate both dialogue speech bubbles on Screenshot 8"
    english_texts = [m["english"].lower() for m in meta]
    assert any("war" in t or "fight" in t for t in english_texts), "Must translate the war purpose dialogue"
    assert any("bow" in t or "fear" in t for t in english_texts), "Must translate the bow down in fear dialogue"



# ─────────────────────────────────────────────────────────────────────
# 4. API Endpoint Tests: /api/translate/page
# ─────────────────────────────────────────────────────────────────────

def test_api_translate_page_invalid_session(client):
    resp = client.post(
        "/api/translate/page",
        json={
            "session_id": "nonexistent_session_123",
            "page_index": 0,
        },
    )
    assert resp.status_code == 404
    assert "Session not found" in resp.json()["detail"]


def test_api_translate_page_invalid_page_index(client, tmp_path):
    session_id = "test_trans_invalid_page"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)
    orig_path = orig_dir / "page_0000.jpg"
    Image.new("RGB", (100, 100)).save(orig_path)

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "test.pdf",
        "total_pages": 1,
        "processed_count": 0,
        "status": "idle",
        "pages": [{"page_index": 0, "filename": "page_0000.jpg", "original_path": str(orig_path), "status": "pending"}],
    }

    resp = client.post(
        "/api/translate/page",
        json={
            "session_id": session_id,
            "page_index": 999,
        },
    )
    assert resp.status_code == 400
    assert "Invalid page index" in resp.json()["detail"]


def test_api_translate_page_success(client, tmp_path):
    session_id = "test_trans_success_sess"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    color_dir = sess_dir / "colorized"
    orig_dir.mkdir(parents=True, exist_ok=True)
    color_dir.mkdir(parents=True, exist_ok=True)

    # Save a test page image
    test_page = Image.new("RGB", (400, 600), color=(255, 255, 255))
    orig_path = orig_dir / "page_0000.jpg"
    test_page.save(orig_path, format="JPEG")

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "test_manga.pdf",
        "total_pages": 1,
        "processed_count": 0,
        "status": "idle",
        "pages": [
            {
                "page_index": 0,
                "filename": "page_0000.jpg",
                "original_path": str(orig_path),
                "display_name": "Page 1",
                "status": "pending",
                "colorized_url": None,
            }
        ],
    }

    mock_metadata = [
        {
            "box": [50, 50, 180, 180],
            "japanese": "おはよう",
            "english": "GOOD MORNING",
            "confidence": 0.98,
        }
    ]

    with patch.object(
        MANGA_TRANSLATOR,
        "translate_page",
        return_value=(test_page, mock_metadata),
    ):
        resp = client.post(
            "/api/translate/page",
            json={
                "session_id": session_id,
                "page_index": 0,
                "translation_engine": "local",
                "target_language": "en",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["page_index"] == 0
        assert data["bubble_count"] == 1
        assert len(data["translations"]) == 1
        assert data["translations"][0]["english"] == "GOOD MORNING"
        assert "/api/session/" in data["colorized_url"]

        # Check that session page was updated
        page_info = SESSIONS[session_id]["pages"][0]
        assert page_info["translated"] is True
        assert page_info["translations"] == mock_metadata


def test_api_session_page_translations_retrieval(client):
    session_id = "test_trans_retrieval_sess"
    mock_translations = [
        {"box": [20, 20, 100, 100], "japanese": "テスト", "english": "TEST", "confidence": 1.0}
    ]

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "manga.pdf",
        "total_pages": 1,
        "status": "colorized",
        "pages": [
            {
                "page_index": 0,
                "filename": "page_0000.jpg",
                "translated": True,
                "translations": mock_translations,
            }
        ],
    }

    resp = client.get(f"/api/session/{session_id}/page/0/translations")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["page_index"] == 0
    assert data["translated"] is True
    assert data["translations"] == mock_translations


# ─────────────────────────────────────────────────────────────────────
# 5. Integration: Colorize Preview with translate_page=True
# ─────────────────────────────────────────────────────────────────────

def test_api_colorize_preview_with_translation(client, tmp_path):
    session_id = "test_preview_with_trans"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)

    test_page = Image.new("RGB", (300, 400), color=(250, 250, 250))
    orig_path = orig_dir / "page_0000.jpg"
    test_page.save(orig_path, format="JPEG")

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "preview_trans.pdf",
        "total_pages": 1,
        "processed_count": 0,
        "status": "idle",
        "pages": [
            {
                "page_index": 0,
                "filename": "page_0000.jpg",
                "original_path": str(orig_path),
                "display_name": "Page 1",
                "status": "pending",
                "colorized_url": None,
            }
        ],
    }

    mock_metadata = [
        {
            "box": [40, 40, 160, 160],
            "japanese": "すごい！",
            "english": "AMAZING!",
            "confidence": 0.99,
        }
    ]

    with patch.object(
        MANGA_TRANSLATOR,
        "translate_page",
        return_value=(test_page, mock_metadata),
    ):
        resp = client.post(
            "/api/colorize/preview",
            json={
                "session_id": session_id,
                "page_index": 0,
                "model_provider": "local_smart",
                "translate_page": True,
                "translation_engine": "local",
                "target_language": "en",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["translations"][0]["english"] == "AMAZING!"


# ─────────────────────────────────────────────────────────────────────
# 6. Session & Batch Translation Tests
# ─────────────────────────────────────────────────────────────────────

def test_page_needs_translation():
    from main import page_needs_translation

    # Not translated
    assert page_needs_translation({}) is True
    assert page_needs_translation({"translated": False}) is True

    # Clean non-dialogue page
    assert page_needs_translation({"translated": True, "translations": []}) is False

    # Clean translated dialogue page
    valid_page = {
        "translated": True,
        "translations": [{"japanese": "待て", "english": "Wait!"}],
    }
    assert page_needs_translation(valid_page) is False

    # Corrupt / rate-limited page where english is identical to raw Japanese
    corrupt_page = {
        "translated": True,
        "translations": [{"japanese": "操縦者弓さやか", "english": "操縦者弓さやか"}],
    }
    assert page_needs_translation(corrupt_page) is True


def test_api_translate_session_endpoint(client, tmp_path):
    session_id = "test_trans_session_all"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    color_dir = sess_dir / "colorized"
    orig_dir.mkdir(parents=True, exist_ok=True)
    color_dir.mkdir(parents=True, exist_ok=True)

    test_page = Image.new("RGB", (300, 400), color=(250, 250, 250))
    orig_path = orig_dir / "page_0000.jpg"
    color_path = color_dir / "color_0000.jpg"
    test_page.save(orig_path, format="JPEG")
    test_page.save(color_path, format="JPEG")

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "full_trans.pdf",
        "total_pages": 1,
        "processed_count": 1,
        "status": "colorized",
        "pages": [
            {
                "page_index": 0,
                "filename": "page_0000.jpg",
                "original_path": str(orig_path),
                "display_name": "Page 1",
                "status": "colorized",
                "colorized_url": f"/api/session/{session_id}/image/colorized/color_0000.jpg",
                "translated": False,
                "translations": [],
            }
        ],
    }

    mock_metadata = [
        {
            "box": [40, 40, 160, 160],
            "japanese": "おはよう",
            "english": "GOOD MORNING",
            "confidence": 0.99,
        }
    ]

    with patch.object(
        MANGA_TRANSLATOR,
        "translate_page",
        return_value=(test_page, mock_metadata),
    ):
        resp = client.post(
            "/api/translate/session",
            json={
                "session_id": session_id,
                "translation_engine": "local",
                "target_language": "en",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["session_id"] == session_id
        assert data["total_pages"] == 1


def test_translate_batch_endpoint(client, tmp_path):
    session_id = "test_trans_batch_all"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)
    test_page = Image.new("RGB", (100, 100))
    test_page.save(orig_dir / "page_0000.jpg")

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "batch_trans.pdf",
        "total_pages": 1,
        "status": "idle",
        "pages": [{"page_index": 0, "filename": "page_0000.jpg", "status": "pending", "original_path": str(orig_dir / "page_0000.jpg")}],
    }

    resp = client.post(
        "/api/translate/batch",
        json={
            "session_ids": [session_id],
            "translation_engine": "local",
            "target_language": "en",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


def test_retranslate_preserves_pristine_raw_color(client, tmp_path):
    session_id = "test_retranslate_pristine"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    color_dir = sess_dir / "colorized"
    raw_dir = sess_dir / "colorized_raw"
    orig_dir.mkdir(parents=True, exist_ok=True)
    color_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Create pristine raw image (red pixel check) and initial color image
    pristine_raw = Image.new("RGB", (200, 200), color=(255, 0, 0))
    pristine_raw.save(raw_dir / "color_0000.jpg", format="JPEG")
    pristine_raw.save(color_dir / "color_0000.jpg", format="JPEG")
    orig_img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    orig_img.save(orig_dir / "page_0000.jpg", format="JPEG")

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "retrans_test.pdf",
        "total_pages": 1,
        "processed_count": 1,
        "status": "colorized",
        "pages": [
            {
                "page_index": 0,
                "filename": "page_0000.jpg",
                "original_path": str(orig_dir / "page_0000.jpg"),
                "display_name": "Page 1",
                "status": "colorized",
                "colorized_url": f"/api/session/{session_id}/image/colorized/color_0000.jpg",
                "translated": False,
                "translations": [],
            }
        ],
    }

    # First translation: translated image has blue color
    trans_img1 = Image.new("RGB", (200, 200), color=(0, 0, 255))
    mock_meta1 = [{"box": [10, 10, 50, 50], "japanese": "テスト", "english": "TEST 1", "confidence": 0.99}]

    with patch.object(MANGA_TRANSLATOR, "translate_page", return_value=(trans_img1, mock_meta1)):
        resp1 = client.post(
            "/api/translate/page",
            json={
                "session_id": session_id,
                "page_index": 0,
                "target_language": "en",
                "translate_colorized": True,
            },
        )
        assert resp1.status_code == 200
        assert resp1.json()["translated"] is True
        assert len(resp1.json()["translations"]) == 1

    # Verify colorized is updated, but colorized_raw still contains the original red
    assert Image.open(raw_dir / "color_0000.jpg").getpixel((100, 100))[0] > 200

    # Second translation (re-translation into French):
    trans_img2 = Image.new("RGB", (200, 200), color=(0, 255, 0))
    mock_meta2 = [{"box": [10, 10, 50, 50], "japanese": "テスト", "english": "ESSAI", "confidence": 0.99}]

    with patch.object(MANGA_TRANSLATOR, "translate_page") as mock_trans:
        mock_trans.return_value = (trans_img2, mock_meta2)
        resp2 = client.post(
            "/api/translate/page",
            json={
                "session_id": session_id,
                "page_index": 0,
                "target_language": "fr",
                "translate_colorized": True,
                "force": True,
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["translated"] is True
        assert resp2.json()["translations"][0]["english"] == "ESSAI"

        # Verify translate_page was called with colorized_raw as the input!
        called_args, called_kwargs = mock_trans.call_args
        assert called_kwargs["image_input"] == str(raw_dir / "color_0000.jpg")

    # colorized_raw is still untouched red
    assert Image.open(raw_dir / "color_0000.jpg").getpixel((100, 100))[0] > 200


def test_recolorize_resets_translation_when_disabled(client, tmp_path):
    session_id = "test_recolor_reset"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    color_dir = sess_dir / "colorized"
    orig_dir.mkdir(parents=True, exist_ok=True)
    color_dir.mkdir(parents=True, exist_ok=True)

    orig_img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    orig_img.save(orig_dir / "page_0000.jpg", format="JPEG")
    color_img = Image.new("RGB", (200, 200), color=(200, 200, 200))
    color_img.save(color_dir / "color_0000.jpg", format="JPEG")

    # Pre-populate session with an already translated page
    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "recolor_test.pdf",
        "total_pages": 1,
        "processed_count": 1,
        "status": "colorized",
        "pages": [
            {
                "page_index": 0,
                "filename": "page_0000.jpg",
                "original_path": str(orig_dir / "page_0000.jpg"),
                "display_name": "Page 1",
                "status": "colorized",
                "colorized_url": f"/api/session/{session_id}/image/colorized/color_0000.jpg",
                "translated": True,
                "translations": [{"box": [10, 10, 40, 40], "japanese": "はい", "english": "YES"}],
            }
        ],
    }

    # Recolorize page with translate_page = False
    resp = client.post(
        "/api/colorize/preview",
        json={
            "session_id": session_id,
            "page_index": 0,
            "force_recolorize": True,
            "translate_page": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["translated"] is False
    assert data["translations"] == []
    # Verify session in memory was also reset
    assert SESSIONS[session_id]["pages"][0]["translated"] is False
    assert SESSIONS[session_id]["pages"][0]["translations"] == []


def test_retranslate_selected_pages_endpoint(client, tmp_path):
    session_id = "test_retrans_selected"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    color_dir = sess_dir / "colorized"
    orig_dir.mkdir(parents=True, exist_ok=True)
    color_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    for i in range(3):
        fn = f"page_{i:04d}.jpg"
        img = Image.new("RGB", (100, 100), color=(i * 50, i * 50, i * 50))
        img.save(orig_dir / fn)
        img.save(color_dir / f"color_{i:04d}.jpg")
        pages.append(
            {
                "page_index": i,
                "filename": fn,
                "original_path": str(orig_dir / fn),
                "display_name": f"Page {i + 1}",
                "status": "colorized",
                "colorized_url": f"/api/session/{session_id}/image/colorized/color_{i:04d}.jpg",
                "translated": False,
                "translations": [],
            }
        )

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "three_pages.pdf",
        "total_pages": 3,
        "processed_count": 3,
        "status": "colorized",
        "pages": pages,
    }

    mock_meta = [{"box": [10, 10, 50, 50], "japanese": "はい", "english": "YES", "confidence": 0.99}]
    test_img = Image.new("RGB", (100, 100))

    with patch.object(MANGA_TRANSLATOR, "translate_page", return_value=(test_img, mock_meta)):
        resp = client.post(
            "/api/translate/session",
            json={
                "session_id": session_id,
                "target_language": "en",
                "force": True,
                "selected_pages": [0, 2],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "started"
        assert data["target_pages"] == 2


def test_clean_speech_bubble_touching_panel_border():
    """Speech bubbles touching solid black panel frames must be cleaned without aborting."""
    translator = MangaTranslator()
    img = np.full((300, 300, 3), 255, dtype=np.uint8)
    # Solid black panel frame along top and left edges
    img[0:15, :] = 0
    img[:, 0:15] = 0
    # Black text inside speech bubble near border
    cv2.putText(img, "TEXT", (40, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    box = (15, 15, 150, 150)
    cleaned, ok = translator.clean_speech_bubble(img, box, return_status=True)
    assert ok is True
    # The text area must be cleaned to near-white
    assert np.mean(cleaned[60:90, 30:130]) > 200
    # The panel border must NOT be wiped out
    assert np.mean(cleaned[0:10, 0:10]) < 30


def test_clean_speech_bubble_dark_surrounding_background():
    """Irregular or cloud speech bubbles surrounded by black background must be cleaned."""
    translator = MangaTranslator()
    # Dark scenery background
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    # White irregular/cloud bubble
    cv2.circle(img, (150, 150), 70, (255, 255, 255), -1)
    # Dark text inside
    cv2.putText(img, "SPEAK", (105, 160), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)

    box = (80, 80, 220, 220)
    cleaned, ok = translator.clean_speech_bubble(img, box, return_status=True)
    assert ok is True
    # Text strokes inside bubble must be cleaned
    assert np.mean(cleaned[140:170, 100:200]) > 200
    # Outer dark background must remain dark
    assert np.mean(cleaned[10:30, 10:30]) < 10


def test_typeset_bubble_draw_background():
    """When draw_background=True, a clean white backdrop is rendered behind the text."""
    translator = MangaTranslator()
    # Dark patterned image
    img = Image.new("RGB", (300, 300), color=(50, 50, 50))
    box = (50, 50, 250, 250)
    out_img = translator.typeset_bubble(
        pil_img=img,
        text="DIALOGUE",
        box=box,
        draw_background=True,
    )
    arr = np.array(out_img)
    # Interior must contain bright white pixels from the backdrop
    assert np.max(arr[100:200, 100:200]) >= 250


def test_typeset_bubble_font_size_cap_long_dialogue():
    """Long dialogue inside an oversized bounding box must not produce comically giant text."""
    translator = MangaTranslator()
    # 1200x1200 standard manga page size
    img = Image.new("RGB", (1200, 1200), color=(255, 255, 255))
    # Enormous 400x400 box (e.g. from an expanded/bloated bubble detection)
    large_box = (100, 100, 500, 500)
    long_dialogue = (
        "The success of the Japanese army's Burr Harbor raid and Singapore attack "
        "is a sign of an impending defeat for the Allied Forces!"
    )

    out_img = translator.typeset_bubble(
        pil_img=img,
        text=long_dialogue,
        box=large_box,
    )
    assert isinstance(out_img, Image.Image)

    # Verify that text is drawn and stays well within the horizontal and vertical margins
    arr = np.array(out_img)
    # Check that text is not drawn at the top boundary (no vertical overflow)
    top_margin = arr[100:110, 100:500]
    assert np.min(top_margin) == 255  # Clean white, no text drawn in margin


def test_manga_translator_existing_translations_fast_path():
    """Providing existing_translations cleanly typesets text without re-running OCR or translation."""
    translator = MangaTranslator()
    # 200x200 image with a speech bubble
    img = np.full((200, 200, 3), 255, dtype=np.uint8)
    cv2.circle(img, (100, 100), 70, (255, 255, 255), -1)

    existing = [
        {"box": [50, 50, 150, 150], "japanese": "こんにちは", "english": "HELLO", "confidence": 0.95}
    ]

    res_pil, meta = translator.translate_page(img, existing_translations=existing)
    assert isinstance(res_pil, Image.Image)
    assert len(meta) == 1
    assert meta[0]["english"] == "HELLO"
    arr = np.array(res_pil)
    # Interior must have dark text drawn
    assert np.min(arr[50:150, 50:150]) < 50


def test_recolorize_preserves_translation_when_already_translated(client):
    """When a page was already translated, recolorizing it preserves translations on the newly colorized image."""
    session_id = "test_recolor_preserves_trans"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    color_dir = sess_dir / "colorized"
    orig_dir.mkdir(parents=True, exist_ok=True)
    color_dir.mkdir(parents=True, exist_ok=True)

    orig_img = Image.new("RGB", (200, 200), color=(255, 255, 255))
    orig_img.save(orig_dir / "page_0000.jpg", format="JPEG")
    color_img = Image.new("RGB", (200, 200), color=(200, 200, 200))
    color_img.save(color_dir / "page_0000.jpg", format="JPEG")

    existing_trans = [{"box": [20, 20, 100, 100], "japanese": "テスト", "english": "PRESERVED", "confidence": 0.95}]

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "recolor_preserve.pdf",
        "total_pages": 1,
        "processed_count": 1,
        "status": "colorized",
        "pages": [
            {
                "page_index": 0,
                "filename": "page_0000.jpg",
                "original_path": str(orig_dir / "page_0000.jpg"),
                "display_name": "Page 1",
                "status": "colorized",
                "colorized_url": f"/api/session/{session_id}/image/colorized/page_0000.jpg",
                "translated": True,
                "translations": existing_trans,
            }
        ],
    }

    # Recolorize page with translate_page omitted (or translate_page=True as sent by UI when page.translated is true)
    resp = client.post(
        "/api/colorize/preview",
        json={
            "session_id": session_id,
            "page_index": 0,
            "force_recolorize": True,
            "translate_page": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["translated"] is True
    assert len(data["translations"]) == 1
    assert data["translations"][0]["english"] == "PRESERVED"
    assert SESSIONS[session_id]["pages"][0]["translated"] is True


def test_retranslate_without_raw_color_preserves_colorized_image(client):
    """When raw_color_path does not exist on disk, re-translating must source from color_output_path, NOT grayscale original."""
    session_id = "test_retrans_no_raw"
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    color_dir = sess_dir / "colorized"
    raw_dir = sess_dir / "colorized_raw"
    orig_dir.mkdir(parents=True, exist_ok=True)
    color_dir.mkdir(parents=True, exist_ok=True)

    # Grayscale original: pure black (0, 0, 0)
    orig_img = Image.new("RGB", (200, 200), color=(0, 0, 0))
    orig_img.save(orig_dir / "page_0000.jpg", format="JPEG")

    # Vibrant colorized image: bright red (255, 0, 0)
    color_img = Image.new("RGB", (200, 200), color=(255, 0, 0))
    color_img.save(color_dir / "color_0000.jpg", format="JPEG")

    # Ensure raw_dir DOES NOT contain the file
    if (raw_dir / "color_0000.jpg").exists():
        (raw_dir / "color_0000.jpg").unlink()

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "no_raw.pdf",
        "total_pages": 1,
        "processed_count": 1,
        "status": "colorized",
        "pages": [
            {
                "page_index": 0,
                "filename": "page_0000.jpg",
                "original_path": str(orig_dir / "page_0000.jpg"),
                "display_name": "Page 1",
                "status": "colorized",
                "colorized_url": f"/api/session/{session_id}/image/colorized/color_0000.jpg",
                "translated": True,
                "translations": [{"box": [10, 10, 40, 40], "japanese": "はい", "english": "YES"}],
            }
        ],
    }

    mock_res_img = Image.new("RGB", (200, 200), color=(255, 50, 50))
    mock_meta = [{"box": [10, 10, 40, 40], "japanese": "はい", "english": "RETRANSLATED", "confidence": 0.99}]

    with patch.object(MANGA_TRANSLATOR, "translate_page") as mock_trans:
        mock_trans.return_value = (mock_res_img, mock_meta)
        resp = client.post(
            "/api/translate/page",
            json={
                "session_id": session_id,
                "page_index": 0,
                "force": True,
                "translate_colorized": True,
            },
        )
        assert resp.status_code == 200
        called_args, called_kwargs = mock_trans.call_args
        # MUST have used the colorized image as input, NEVER the original grayscale!
        assert called_kwargs["image_input"] == str(color_dir / "color_0000.jpg")




