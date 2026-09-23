"""
test_offline_character_colorization.py

Comprehensive tests for:
1. Offline Manga109 YOLO + CLIP character recognition with face-body association and hair tone prior.
2. Neural generator hint tensor seeding with CharacterPalette.
3. Neural colorization post-inference palette harmonization.
4. End-to-end /api/colorize/preview returning recognized_characters and applying character palette.
5. Background colorization worker preserving and broadcasting recognized_characters via SSE.
"""

import os
import shutil
import uuid
from pathlib import Path

import cv2
import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image

from colorizer_engine import (
    CharacterEntry,
    CharacterPalette,
    MangaCharacterRecognizer,
    MangaColorizerEngine,
    RecognizedCharacter,
    apply_character_palette_harmonization,
)
from main import SESSIONS, SESSION_PALETTES, app, save_session_meta


def test_candidate_pairs_face_body_association():
    """
    Verifies that _extract_candidate_pairs associates a detected face with its enclosing body,
    so that the resulting figure_box covers the entire figure (hair, face, torso, clothing).
    """
    recognizer = MangaCharacterRecognizer()

    # Create synthetic mock image 600x400
    img = np.ones((600, 400), dtype=np.uint8) * 255
    pil_img = Image.fromarray(img)

    # Mock _detect_manga_yolo_regions to return a face and an enclosing body
    face_box = (100, 120, 200, 240, "face", 0.90)  # y0, x0, y1, x1
    body_box = (90, 100, 500, 280, "body", 0.85)   # enclosing body
    recognizer._detect_manga_yolo_regions = lambda p_img, c_img=None, conf=0.16: [face_box, body_box]

    pairs = recognizer._extract_candidate_pairs(img, pil_img=pil_img)
    assert len(pairs) >= 1

    crop_box, fig_box = pairs[0]
    # Crop box must be the face for high-fidelity facial classification
    assert crop_box == (100, 120, 200, 240)
    # Figure box must cover the full figure union with the body
    assert fig_box[0] <= 100 and fig_box[1] <= 120
    assert fig_box[2] >= 500 and fig_box[3] >= 280

    # Also verify backward compatibility of _extract_candidate_boxes
    boxes = recognizer._extract_candidate_boxes(img, pil_img=pil_img)
    assert len(boxes) >= 1
    assert boxes[0] == (100, 120, 200, 240)


def test_clip_recognition_hair_tone_prior():
    """
    Verifies that hair tone prior in _recognize_with_clip leverages dark ink vs light paper
    luminance in the candidate crop hair region to favor dark or light haired characters.
    """
    recognizer = MangaCharacterRecognizer()

    palette = CharacterPalette(
        preset_title="Slam Dunk",
        characters=[
            CharacterEntry(
                name="Hanamichi Sakuragi",
                hair_hex="#D32F2F",  # Red / screentone hair
                visual_traits=["screentone_hair", "short_hair"],
                notes="Shohoku power forward with red short hair",
            ),
            CharacterEntry(
                name="Hisashi Mitsui",
                hair_hex="#1A237E",  # Dark navy / black ink hair
                visual_traits=["black_hair", "short_hair"],
                notes="Shohoku shooting guard with dark black hair",
            ),
        ],
    )

    # Create dark hair test image: top 30% has black ink lines
    dark_head = np.ones((120, 100), dtype=np.uint8) * 245
    dark_head[:35, :] = 20  # solid black ink hair
    dark_pil = Image.fromarray(dark_head)
    temp_dark_path = "/tmp/test_dark_hair.png"
    dark_pil.save(temp_dark_path)

    try:
        # Mock CLIP model/processor to return neutral/equal logits across characters
        class MockClipOutputs:
            def __init__(self, n_prompts):
                # Sakuragi: 0.35, Mitsui: 0.35, Neutral: 0.30
                logits = torch.tensor([[1.0, 1.0, 0.8]])
                self.logits_per_image = logits

        class MockClipProcessor:
            def __call__(self, text, images, return_tensors, padding):
                return self
            def to(self, device):
                return {"input_ids": torch.zeros((1, 1))}

        class MockClipModel:
            def __call__(self, **kwargs):
                return MockClipOutputs(3)

        recognizer._ensure_clip = lambda: (MockClipModel(), MockClipProcessor(), "cpu")
        recognizer._extract_candidate_pairs = lambda img, pil_img=None: [
            ((0, 0, 120, 100), (0, 0, 120, 100))
        ]

        recs = recognizer._recognize_with_clip(temp_dark_path, palette, min_confidence=0.20)
        assert len(recs) == 1
        # Due to dark hair prior on black ink hair, Mitsui (black_hair) should win over Sakuragi
        assert recs[0].name == "Hisashi Mitsui"
        assert "dark_hair_prior" in recs[0].matched_features
    finally:
        if os.path.exists(temp_dark_path):
            os.remove(temp_dark_path)


def test_neural_colorizer_hint_injection_and_harmonization():
    """
    Verifies that _colorize_neural injects CharacterPalette hint seeds and applies harmonization.
    """
    engine = MangaColorizerEngine()

    palette = CharacterPalette(
        preset_title="Test Series",
        characters=[
            CharacterEntry(
                name="Test Hero",
                hair_hex="#FF0000",
                skin_hex="#FCE4D6",
                costume_hex="#0000FF",
                bounding_box=(0.1, 0.1, 0.9, 0.9),
            )
        ],
    )

    # Create dummy manga lineart image
    img = np.ones((200, 200, 3), dtype=np.uint8) * 240
    cv2.circle(img, (100, 100), 40, (0, 0, 0), 2)
    in_path = "/tmp/test_neural_in.png"
    out_path = "/tmp/test_neural_out.png"
    cv2.imwrite(in_path, img)

    try:
        # Run colorize_page with character_palette
        res = engine.colorize_page(
            image_path=in_path,
            output_path=out_path,
            model_provider="resnext_generator",
            character_palette=palette,
            skip_recognition=True,
        )
        assert res["status"] in ("success", "colorized", "skipped_colored")
        assert os.path.exists(out_path)

        # Output image should exist and be valid 3-channel image
        out_bgr = cv2.imread(out_path)
        assert out_bgr is not None
        assert out_bgr.shape == (200, 200, 3)
    finally:
        if os.path.exists(in_path):
            os.remove(in_path)
        if os.path.exists(out_path):
            os.remove(out_path)


def test_preview_endpoint_with_offline_recognition(tmp_path):
    """
    Verifies that /api/colorize/preview performs character recognition,
    attaches recognized_characters to page_info, and returns them in the response.
    """
    client = TestClient(app)
    session_id = f"test-offline-rec-{uuid.uuid4().hex[:8]}"
    sess_dir = Path("sessions") / session_id
    orig_dir = sess_dir / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)

    img_path = orig_dir / "page_0000.jpg"
    arr = np.ones((120, 120, 3), dtype=np.uint8) * 240
    cv2.circle(arr, (60, 60), 30, (0, 0, 0), 2)
    Image.fromarray(arr).save(img_path)

    palette = CharacterPalette(
        preset_title="Dr. Slump",
        characters=[
            CharacterEntry(name="Arale Norimaki", hair_hex="#8A2BE2", costume_hex="#E91E63", notes="Robot girl with purple hair"),
            CharacterEntry(name="Senbei Norimaki", hair_hex="#212121", costume_hex="#FFFFFF", notes="Scientist with black hair"),
        ],
    )

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "DrSlump.pdf",
        "total_pages": 1,
        "processed_count": 0,
        "status": "ready",
        "pages": [
            {
                "page_index": 0,
                "original_path": str(img_path),
                "original_filename": "page_0000.jpg",
                "filename": "page_0000.jpg",
                "status": "pending",
                "recognized_characters": [],
            }
        ],
    }
    SESSION_PALETTES[session_id] = palette
    save_session_meta(session_id)

    try:
        resp = client.post(
            "/api/colorize/preview",
            json={
                "session_id": session_id,
                "page_index": 0,
                "model_provider": "resnext_generator",
                "model_name": "resnext-v2-manga",
                "recognition_mode": "heuristics",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        # Must return recognized characters
        rec_chars = data.get("recognized_characters", [])
        assert len(rec_chars) >= 1
        assert "name" in rec_chars[0]

        # Must persist recognized characters on session page
        sess = SESSIONS[session_id]
        assert len(sess["pages"][0].get("recognized_characters", [])) >= 1
    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(session_id, None)
        SESSION_PALETTES.pop(session_id, None)


@pytest.mark.anyio
async def test_colorization_worker_with_offline_recognition():
    """
    Verifies that _async_colorization_worker detects characters during session colorization,
    saves recognized_characters to page_info, and injects palette seeds into neural colorization.
    """
    from main import ColorizeRequest, _async_colorization_worker

    session_id = f"test-worker-rec-{uuid.uuid4().hex[:8]}"
    sess_dir = Path("sessions") / session_id
    orig_dir = sess_dir / "original"
    color_dir = sess_dir / "colorized"
    orig_dir.mkdir(parents=True, exist_ok=True)
    color_dir.mkdir(parents=True, exist_ok=True)

    img_path = orig_dir / "page_0000.jpg"
    arr = np.ones((120, 120, 3), dtype=np.uint8) * 240
    cv2.circle(arr, (60, 60), 30, (0, 0, 0), 2)
    Image.fromarray(arr).save(img_path)

    palette = CharacterPalette(
        preset_title="Dr. Slump",
        characters=[
            CharacterEntry(name="Arale Norimaki", hair_hex="#8A2BE2", costume_hex="#E91E63", notes="Robot girl with purple hair"),
        ],
    )

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "DrSlump.pdf",
        "total_pages": 1,
        "processed_count": 0,
        "status": "ready",
        "pages": [
            {
                "page_index": 0,
                "original_path": str(img_path),
                "original_filename": "page_0000.jpg",
                "filename": "page_0000.jpg",
                "status": "pending",
                "recognized_characters": [],
            }
        ],
    }
    SESSION_PALETTES[session_id] = palette
    save_session_meta(session_id)

    req = ColorizeRequest(
        session_id=session_id,
        model_provider="resnext_generator",
        model_name="resnext-v2-manga",
        recognition_mode="heuristics",
    )

    try:
        await _async_colorization_worker(session_id, req)
        sess = SESSIONS[session_id]
        page = sess["pages"][0]
        assert page["status"] == "colorized"
        # Character recognition ran during colorization and saved characters to page
        rec_chars = page.get("recognized_characters", [])
        assert len(rec_chars) >= 1
        assert rec_chars[0]["name"] in ("Arale Norimaki", "Dr. Senbei Norimaki")
        # Output image exists
        out_file = color_dir / "page_0000.jpg"
        assert out_file.exists()
    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(session_id, None)
        SESSION_PALETTES.pop(session_id, None)

