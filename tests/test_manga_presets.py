"""
tests/test_manga_presets.py - Unit & Integration tests for Manga Color Presets & Auto-Detection.
"""

import io
import json
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image

from colorizer_engine import CharacterEntry, CharacterPalette, MangaColorizerEngine
from main import (
    EVENT_QUEUES,
    SESSION_PALETTES,
    SESSIONS,
    STORAGE_DIR,
    app,
    get_or_restore_session,
    save_session_meta,
)
from manga_presets import (
    BUILTIN_PRESETS,
    PRESET_REGISTRY,
    MangaPreset,
    PresetCharacter,
    detect_manga_preset,
    get_all_presets,
    get_preset_by_id,
    normalize_text_for_matching,
    search_online_manga_preset,
)

client = TestClient(app)


# ─────────────────────────────────────────────────────────────────────
# 1. Built-in Presets Structure & Model Tests
# ─────────────────────────────────────────────────────────────────────


def test_builtin_presets_coverage():
    """Verifies all required popular manga presets exist with complete canonical palettes."""
    presets = get_all_presets()
    assert len(presets) >= 18

    preset_ids = {p.id for p in presets}
    required_ids = [
        "one_piece",
        "doraemon",
        "slam_dunk",
        "dr_slump",
        "dragon_ball",
        "naruto",
        "bleach",
        "detective_conan",
        "demon_slayer",
        "attack_on_titan",
        "jujutsu_kaisen",
        "my_hero_academia",
        "chainsaw_man",
        "spy_x_family",
        "death_note",
        "fullmetal_alchemist",
        "hunter_x_hunter",
        "jojo",
    ]
    for req_id in required_ids:
        assert req_id in preset_ids, f"Required preset '{req_id}' missing from registry!"

    # Detailed check on One Piece
    op = get_preset_by_id("one_piece")
    assert op is not None
    assert op.title == "One Piece"
    char_names = {c.name for c in op.characters}
    assert "Monkey D. Luffy" in char_names
    assert "Roronoa Zoro" in char_names
    assert "Nami" in char_names

    # Check Luffy's signature colors
    luffy = next(c for c in op.characters if c.name == "Monkey D. Luffy")
    assert luffy.costume_hex == "#E62C39"  # signature red vest
    assert luffy.extra_hex == "#FBC920"  # straw hat

    # Detailed check on Doraemon
    dora = get_preset_by_id("doraemon")
    assert dora is not None
    assert dora.characters[0].name == "Doraemon"
    assert dora.characters[0].hair_hex == "#0095D9"  # sky blue body

    # Detailed check on Slam Dunk
    sd = get_preset_by_id("slam_dunk")
    assert sd is not None
    assert any("Sakuragi" in c.name for c in sd.characters)
    sakuragi = next(c for c in sd.characters if "Sakuragi" in c.name)
    assert sakuragi.hair_hex == "#E30016"  # bright red hair
    assert sakuragi.costume_hex == "#C62828"  # Shohoku red jersey


def test_preset_serialization_and_prompt_guidance():
    """Tests serialization round-trip and AI prompt guidance builder."""
    op = get_preset_by_id("one_piece")
    assert op is not None

    d = op.to_dict()
    assert d["id"] == "one_piece"
    assert isinstance(d["characters"], list)
    assert len(d["characters"]) > 0

    reconstructed = MangaPreset.from_dict(d)
    assert reconstructed.id == op.id
    assert reconstructed.title == op.title
    assert len(reconstructed.characters) == len(op.characters)
    assert reconstructed.characters[0].name == op.characters[0].name

    # Test dynamic prompt guidance generator
    custom_p = MangaPreset(
        id="test_custom",
        title="Test Custom Manga",
        aliases=["test"],
        description="Testing prompt generator",
        characters=[
            PresetCharacter(
                name="Hero",
                hair_hex="#112233",
                skin_hex="#FFEEDD",
                costume_hex="#445566",
                extra_hex="#778899",
            )
        ],
    )
    guidance = custom_p.build_prompt_guidance()
    assert "Canonical anime palette for Test Custom Manga" in guidance
    assert "Hero" in guidance
    assert "hair #112233" in guidance
    assert "costume #445566" in guidance


# ─────────────────────────────────────────────────────────────────────
# 2. Filename Auto-Detection Engine Tests
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "filename,expected_preset_id",
    [
        ("One Piece Colored - Eiichiro Oda - Volume 0001.epub", "one_piece"),
        ("onepiece_ch1000.cbz", "one_piece"),
        ("Straw Hat Luffy Adventure.pdf", "one_piece"),
        ("Colorized_DrSlump_full_Omnibus_a2ebb137.zip", "dr_slump"),
        ("Dr. Slump - Arale-chan Vol 01.cbr", "dr_slump"),
        ("Toriyama Dr Slump Omnibus.epub", "dr_slump"),
        ("Slam Dunk - 01.pdf", "slam_dunk"),
        ("SlamDunk Takehiko Inoue Vol 10.zip", "slam_dunk"),
        ("Shohoku Basketball Team Ch 25.cbz", "slam_dunk"),
        ("Doraemon Vol 05.cbz", "doraemon"),
        ("Fujiko F Fujio Nobita and Doraemon.pdf", "doraemon"),
        ("Dragon Ball Super Ch 10.cbr", "dragon_ball"),
        ("DBZ Goku Saiyan Saga Vol 03.cbz", "dragon_ball"),
        ("Naruto Shippuden Vol 12.zip", "naruto"),
        ("Bleach - Thousand-Year Blood War.cbz", "bleach"),
        ("Detective Conan Case Closed 01.pdf", "detective_conan"),
        ("Demon Slayer Kimetsu no Yaiba 01.epub", "demon_slayer"),
        ("Attack on Titan Vol 34.zip", "attack_on_titan"),
        ("Jujutsu Kaisen 01.zip", "jujutsu_kaisen"),
        ("My Hero Academia 10.pdf", "my_hero_academia"),
        ("Chainsaw Man 05.cbz", "chainsaw_man"),
        ("Spy x Family 03.epub", "spy_x_family"),
        ("Death Note 01.zip", "death_note"),
        ("Fullmetal Alchemist 01.cbz", "fullmetal_alchemist"),
        ("Hunter x Hunter 36.pdf", "hunter_x_hunter"),
        ("JoJos Bizarre Adventure Stardust Crusaders.zip", "jojo"),
    ],
)
def test_detect_manga_preset_matches(filename, expected_preset_id):
    """Verifies that all popular manga titles and variations match their canonical preset."""
    detected = detect_manga_preset(filename)
    assert detected is not None, f"Failed to detect preset for '{filename}'"
    assert (
        detected.id == expected_preset_id
    ), f"Expected '{expected_preset_id}' but got '{detected.id}' for '{filename}'"


def test_detect_manga_preset_unknown_and_edge_cases():
    """Verifies unknown titles and boundary strings return None gracefully."""
    assert detect_manga_preset("") is None
    assert detect_manga_preset("    ") is None
    assert detect_manga_preset("Unknown_Manga_Book_12345.pdf") is None
    assert detect_manga_preset("generic_comic_scan_001.zip") is None
    assert detect_manga_preset("My Mathematics Textbook 2026.pdf") is None


# ─────────────────────────────────────────────────────────────────────
# 3. FastAPI REST Endpoints for Presets
# ─────────────────────────────────────────────────────────────────────


def test_api_list_presets():
    """Verifies GET /api/palette/presets returns all presets with full character data."""
    response = client.get("/api/palette/presets")
    assert response.status_code == 200
    data = response.json()
    assert "presets" in data
    assert "count" in data
    assert data["count"] >= 18
    assert any(p["id"] == "one_piece" for p in data["presets"])
    assert any(p["id"] == "doraemon" for p in data["presets"])
    assert any(p["id"] == "slam_dunk" for p in data["presets"])
    assert any(p["id"] == "dr_slump" for p in data["presets"])


def test_api_get_preset_by_id():
    """Verifies GET /api/palette/preset/{preset_id} returns preset details or 404."""
    # Valid preset
    response = client.get("/api/palette/preset/one_piece")
    assert response.status_code == 200
    data = response.json()
    assert "preset" in data
    assert data["preset"]["id"] == "one_piece"
    assert data["preset"]["title"] == "One Piece"
    assert len(data["preset"]["characters"]) > 0

    # Non-existent preset
    response_404 = client.get("/api/palette/preset/non_existent_preset_xyz")
    assert response_404.status_code == 404


def test_api_apply_preset(tmp_path):
    """Verifies POST /api/palette/apply-preset injects preset characters into active session."""
    session_id = f"test_preset_apply_{uuid.uuid4().hex[:8]}"
    sess_dir = STORAGE_DIR / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "generic_basketball_manga.pdf",
        "total_pages": 10,
        "processed_count": 0,
        "status": "idle",
        "pages": [],
    }
    EVENT_QUEUES[session_id] = []
    save_session_meta(session_id)

    try:
        # Apply Slam Dunk preset
        resp = client.post(
            "/api/palette/apply-preset",
            json={"session_id": session_id, "preset_id": "slam_dunk"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["preset_id"] == "slam_dunk"
        assert data["preset_title"] == "Slam Dunk"
        assert len(data["palette"]["characters"]) >= 5

        # Check in-memory session palette
        pal = SESSION_PALETTES.get(session_id)
        assert pal is not None
        assert pal.preset_id == "slam_dunk"
        assert any("Sakuragi" in c.name for c in pal.characters)

        # Check session metadata
        sess = SESSIONS[session_id]
        assert sess.get("detected_preset") == "slam_dunk"
        assert sess.get("preset_title") == "Slam Dunk"

        # Check on-disk persistence
        pal_path = sess_dir / "palette.json"
        assert pal_path.exists()
        with open(pal_path, "r", encoding="utf-8") as f:
            disk_pal = json.load(f)
            assert disk_pal["preset_id"] == "slam_dunk"

    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(session_id, None)
        SESSION_PALETTES.pop(session_id, None)
        EVENT_QUEUES.pop(session_id, None)


def test_api_apply_preset_invalid_cases():
    """Verifies error handling when applying invalid presets or non-existent sessions."""
    # Invalid session
    resp1 = client.post(
        "/api/palette/apply-preset",
        json={"session_id": "ghost_session_xyz", "preset_id": "one_piece"},
    )
    assert resp1.status_code == 404

    # Valid session, invalid preset
    session_id = f"test_err_{uuid.uuid4().hex[:8]}"
    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "sample.pdf",
        "pages": [],
    }
    try:
        resp2 = client.post(
            "/api/palette/apply-preset",
            json={"session_id": session_id, "preset_id": "invalid_unknown_preset_123"},
        )
        assert resp2.status_code == 404
    finally:
        SESSIONS.pop(session_id, None)


# ─────────────────────────────────────────────────────────────────────
# 4. Online Search & Dynamic Preset Generator Tests
# ─────────────────────────────────────────────────────────────────────


def test_search_online_preset_existing_registry():
    """Verifies that online search for an indexed manga returns the built-in preset immediately."""
    preset = search_online_manga_preset("One Piece")
    assert preset is not None
    assert preset.id == "one_piece"
    assert preset.title == "One Piece"


def test_search_online_preset_mock_wikipedia(tmp_path):
    """Verifies online preset generator parses Wikipedia character extracts correctly."""
    mock_search_json = {
        "query": {
            "search": [
                {"title": "List of Inuyasha characters"},
                {"title": "Inuyasha (manga)"},
            ]
        }
    }
    mock_extract_json = {
        "query": {
            "pages": {
                "12345": {
                    "extract": (
                        "== Main characters ==\n"
                        "=== Inuyasha ===\n"
                        "Inuyasha has long silver hair and wears a vibrant red robe made of fire-rat fur.\n"
                        "=== Kagome Higurashi ===\n"
                        "Kagome has black hair and wears a green school uniform and white shirt.\n"
                        "=== Miroku ===\n"
                        "Miroku has black ponytail hair and wears a purple buddhist robe.\n"
                        "== Media =="
                    )
                }
            }
        }
    }

    def mock_urlopen(req, timeout=6):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "action=query&list=search" in url:
            data = json.dumps(mock_search_json).encode("utf-8")
        else:
            data = json.dumps(mock_extract_json).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = data
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    try:
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            preset = search_online_manga_preset("Inuyasha Series")
            assert preset is not None
            assert preset.id == "inuyasha_series"
            assert len(preset.characters) >= 2

            char_names = [c.name for c in preset.characters]
            assert "Inuyasha" in char_names
            inuyasha = next(c for c in preset.characters if c.name == "Inuyasha")
            assert inuyasha.hair_hex == "#ECEFF1"  # silver hair
            assert inuyasha.costume_hex == "#D32F2F"  # red robe

            kagome = next((c for c in preset.characters if c.name == "Kagome Higurashi"), None)
            if kagome:
                assert kagome.costume_hex == "#388E3C"  # green uniform
    finally:
        PRESET_REGISTRY.pop("inuyasha_series", None)


def test_api_search_online_endpoint(tmp_path):
    """Verifies POST /api/palette/search-online endpoint with session binding."""
    session_id = f"test_online_sess_{uuid.uuid4().hex[:8]}"
    sess_dir = STORAGE_DIR / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "inuyasha_vol01.cbz",
        "total_pages": 5,
        "processed_count": 0,
        "status": "idle",
        "pages": [],
    }
    EVENT_QUEUES[session_id] = []
    save_session_meta(session_id)

    mock_search_json = {
        "query": {
            "search": [
                {"title": "List of Ranma characters"},
            ]
        }
    }
    mock_extract_json = {
        "query": {
            "pages": {
                "9999": {
                    "extract": (
                        "=== Ranma Saotome ===\n"
                        "Ranma has black hair with a pigtail and wears a red chinese shirt.\n"
                        "=== Akane Tendo ===\n"
                        "Akane has short blue hair and wears a blue school dress.\n"
                    )
                }
            }
        }
    }

    def mock_urlopen(req, timeout=6):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "action=query&list=search" in url:
            data = json.dumps(mock_search_json).encode("utf-8")
        else:
            data = json.dumps(mock_extract_json).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = data
        mock_resp.__enter__.return_value = mock_resp
        return mock_resp

    try:
        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            resp = client.post(
                "/api/palette/search-online",
                json={"query": "Ranma Half", "session_id": session_id},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["preset"]["title"] == "Ranma Half"
            assert data["applied_to_session"] == session_id

            # Check that session palette was updated
            pal = SESSION_PALETTES.get(session_id)
            assert pal is not None
            assert pal.preset_id == "ranma_half"
            assert any(c.name == "Ranma Saotome" for c in pal.characters)
    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(session_id, None)
        SESSION_PALETTES.pop(session_id, None)
        EVENT_QUEUES.pop(session_id, None)
        PRESET_REGISTRY.pop("ranma_half", None)


# ─────────────────────────────────────────────────────────────────────
# 5. Colorizer Engine Integration with Character Presets
# ─────────────────────────────────────────────────────────────────────


def test_character_palette_hint_tensor():
    """Verifies CharacterPalette generates clean (1, 4, H, W) hint tensor for neural colorizer."""
    palette = CharacterPalette(
        characters=[
            CharacterEntry(
                name="Luffy",
                hair_hex="#1C1B1F",
                skin_hex="#FCD0A1",
                costume_hex="#E62C39",
            ),
            CharacterEntry(
                name="Zoro",
                hair_hex="#4E8752",
                skin_hex="#F5C596",
                costume_hex="#1B4332",
            ),
        ],
        preset_id="one_piece",
        preset_title="One Piece",
    )

    tensor = palette.build_hint_tensor(h=256, w=256, device="cpu")
    assert isinstance(tensor, torch.Tensor)
    assert tensor.shape == (1, 4, 256, 256)
    assert (tensor == 0).all()

    # Empty palette should also return all-zeros
    empty_pal = CharacterPalette()
    empty_tensor = empty_pal.build_hint_tensor(h=128, w=128, device="cpu")
    assert (empty_tensor == 0).all()


def test_character_palette_harmonization():
    """Verifies apply_character_palette_harmonization aligns character colors without flat-washing backgrounds."""
    from colorizer_engine import apply_character_palette_harmonization

    palette = CharacterPalette(
        characters=[
            CharacterEntry(
                name="Luffy",
                hair_hex="#1C1B1F",
                skin_hex="#FCD0A1",
                costume_hex="#E62C39",
            ),
        ],
        preset_id="one_piece",
        preset_title="One Piece",
    )

    # Test image with red vest area (RGB: 200, 30, 30) and blue sky (RGB: 100, 150, 240)
    img_rgb = np.zeros((100, 100, 3), dtype=np.uint8)
    img_rgb[:50, :] = [200, 30, 30]    # red vest
    img_rgb[50:, :] = [100, 150, 240]  # blue sky

    harmonized = apply_character_palette_harmonization(img_rgb, palette)

    # Blue sky should remain blue (dominant B channel, not contaminated by red vest palette)
    assert harmonized[75, 50, 2] > harmonized[75, 50, 0]
    assert harmonized[75, 50, 2] > 200

    # Red vest should remain vibrant red (dominant R channel)
    assert harmonized[25, 50, 0] > 200
    assert harmonized[25, 50, 1] < 100


def test_colorizer_engine_local_smart_with_preset(tmp_path):
    """Verifies local_smart engine colorizes an image with preset chromatic bias."""
    engine = MangaColorizerEngine()

    in_img_path = tmp_path / "test_manga_in.png"
    out_img_path = tmp_path / "test_manga_out.jpg"

    # Create synthetic manga panel
    img = Image.new("L", (200, 200), color=255)
    for y in range(50, 150):
        for x in range(50, 150):
            img.putpixel((x, y), 128)
    img.save(in_img_path)

    palette = CharacterPalette(
        characters=[
            CharacterEntry(name="Doraemon", costume_hex="#0095D9", skin_hex="#FFFFFF"),
        ],
        preset_id="doraemon",
        preset_title="Doraemon",
    )

    result = engine.colorize_page(
        image_path=str(in_img_path),
        output_path=str(out_img_path),
        model_provider="local_smart",
        model_name="smart-local-vibrant",
        style="shonen_vivid",
        saturation=1.0,
        contrast=1.0,
        line_preserve=0.85,
        character_palette=palette,
    )

    assert result["status"] == "success"
    assert Path(out_img_path).exists()
    assert Path(out_img_path).stat().st_size > 0

    # Read output and verify it's a valid 3-channel color image
    out_pil = Image.open(out_img_path)
    assert out_pil.mode == "RGB"
    assert out_pil.size == (200, 200)


def test_colorizer_engine_neural_with_preset(tmp_path):
    """Verifies neural ResNeXt colorizer runs with hint tensor derived from preset."""
    engine = MangaColorizerEngine()

    in_img_path = tmp_path / "test_neural_in.png"
    out_img_path = tmp_path / "test_neural_out.jpg"

    img = Image.new("L", (128, 128), color=240)
    img.save(in_img_path)

    palette = CharacterPalette(
        characters=[
            CharacterEntry(name="Arale", hair_hex="#8B2BE2", costume_hex="#E62C39"),
        ],
        preset_id="dr_slump",
        preset_title="Dr. Slump",
    )

    result = engine.colorize_page(
        image_path=str(in_img_path),
        output_path=str(out_img_path),
        model_provider="resnext_generator",
        model_name="resnext-generator-anime-v1",
        style="gemini_anime",
        saturation=1.0,
        contrast=1.0,
        line_preserve=0.85,
        character_palette=palette,
    )

    assert result["status"] == "success"
    assert Path(out_img_path).exists()


def test_character_palette_sparse_seed_hint_tensor():
    """Verifies sparse seed hints are injected into candidate midtone regions."""
    palette = CharacterPalette(
        characters=[
            CharacterEntry(
                name="Luffy",
                hair_hex="#1C1B1F",
                skin_hex="#FEDBC5",
                costume_hex="#D62828",
            )
        ],
        preset_id="one_piece",
        preset_title="One Piece",
    )
    sketch = np.ones((256, 256), dtype=np.float32)
    # Synthetic costume screentone area
    sketch[60:120, 60:120] = 0.50

    tensor = palette.build_hint_tensor(h=256, w=256, device="cpu", sketch_gray=sketch)
    assert isinstance(tensor, torch.Tensor)
    assert tensor.shape == (1, 4, 256, 256)

    mask = tensor[0, 3] > 0
    assert torch.any(mask), "Expected sparse seed hint to place at least one localized mask point"

    # Verify scaled color in seeded region: (214/255 - 0.5) / 0.5 ~ 0.678
    r_val = tensor[0, 0, mask][0].item()
    assert 0.55 < r_val < 0.80, f"Expected red channel to be scaled in [-1, 1], got {r_val}"


def test_denoiser_screentone_filtering():
    """Verifies FFDNetDenoiser removes halftone dot screentone noise from image."""
    engine = MangaColorizerEngine()
    if engine.denoiser is None:
        pytest.skip("FFDNetDenoiser weights not available in environment")

    noisy = np.full((128, 128, 3), 200, dtype=np.uint8)
    noisy[::2, ::2] = 40  # Regular screentone dot pattern

    denoised = engine.denoiser.get_denoised_image(noisy, sigma=25)
    assert denoised.shape == (128, 128, 3)
    assert np.std(denoised) < np.std(noisy), "Expected standard deviation to decrease after denoising"


def test_speech_bubble_and_margin_protection(tmp_path):
    """Verifies enclosed speech bubble with text stays clean white and resists color wash."""
    import cv2

    engine = MangaColorizerEngine()

    in_img_path = tmp_path / "bubble_in.png"
    out_img_path = tmp_path / "bubble_out.jpg"

    img_u = np.full((300, 300, 3), 250, dtype=np.uint8)
    cv2.ellipse(img_u, (150, 100), (50, 35), 0, 0, 360, (0, 0, 0), 2)
    cv2.putText(img_u, "HEY!", (130, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    cv2.imwrite(str(in_img_path), img_u)

    res = engine.colorize_page(
        image_path=str(in_img_path),
        output_path=str(out_img_path),
        denoise_screentone=True,
    )
    assert res["status"] == "success"
    assert Path(out_img_path).exists()

    out_img = cv2.imread(str(out_img_path))
    # Interior of speech bubble away from text strokes should remain near white
    bubble_interior = out_img[80, 150]
    assert np.all(bubble_interior >= 210), f"Speech bubble interior was discolored: {bubble_interior}"


def test_colorize_page_denoise_screentone_flags(tmp_path):
    """Verifies colorize_page accepts denoise_screentone flag toggles cleanly."""
    engine = MangaColorizerEngine()

    in_img_path = tmp_path / "flag_test_in.png"
    out_img_path = tmp_path / "flag_test_out.jpg"

    img = Image.new("L", (128, 128), color=230)
    img.save(in_img_path)

    # Test with denoise_screentone=True
    res1 = engine.colorize_page(
        image_path=str(in_img_path),
        output_path=str(out_img_path),
        denoise_screentone=True,
        denoise_sigma=25,
    )
    assert res1["status"] == "success"

    # Test with denoise_screentone=False
    res2 = engine.colorize_page(
        image_path=str(in_img_path),
        output_path=str(out_img_path),
        denoise_screentone=False,
    )
    assert res2["status"] == "success"

