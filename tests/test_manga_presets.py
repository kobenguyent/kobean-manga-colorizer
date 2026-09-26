"""
tests/test_manga_presets.py - Unit & Integration tests for Manga Color Presets & Auto-Detection.
"""

import json
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image

from colorizer_engine import (
    CharacterEntry,
    CharacterPalette,
    MangaColorizerEngine,
    apply_character_palette_harmonization,
)
from main import (
    EVENT_QUEUES,
    SESSION_PALETTES,
    SESSIONS,
    STORAGE_DIR,
    app,
    save_session_meta,
)
from manga_presets import (
    PRESET_REGISTRY,
    MangaPreset,
    PresetCharacter,
    detect_manga_preset,
    get_all_presets,
    get_preset_by_id,
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
    assert detected.id == expected_preset_id, (
        f"Expected '{expected_preset_id}' but got '{detected.id}' for '{filename}'"
    )


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
        with open(pal_path, encoding="utf-8") as f:
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
    img_rgb[:50, :] = [200, 30, 30]  # red vest
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
    assert np.std(denoised) < np.std(noisy), (
        "Expected standard deviation to decrease after denoising"
    )


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
    assert np.all(bubble_interior >= 210), (
        f"Speech bubble interior was discolored: {bubble_interior}"
    )


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


def test_character_entry_traits_and_serialization():
    """Verifies automatic trait and keyword inference for CharacterEntry."""
    from colorizer_engine import CharacterEntry, RecognizedCharacter

    # Luffy: black hair + straw hat
    c1 = CharacterEntry(
        name="Monkey D. Luffy",
        hair_hex="#111111",
        costume_hex="#D62828",
        notes="Red vest, blue shorts, yellow straw hat",
    )
    assert "black_hair" in c1.visual_traits
    assert "straw_hat" in c1.visual_traits
    assert "luffy" in c1.keywords

    # Arale: screentone hair + round glasses + chibi
    c2 = CharacterEntry(
        name="Arale Norimaki",
        hair_hex="#8B2BE2",
        costume_hex="#E63946",
        notes="Purple hair, large round glasses, winged cap, chibi",
    )
    assert "screentone_hair" in c2.visual_traits
    assert "glasses" in c2.visual_traits
    assert "chibi" in c2.visual_traits
    assert "arale" in c2.keywords

    # Serialization with bounding_box
    c1.bounding_box = (0.1, 0.2, 0.8, 0.9)
    d1 = c1.to_dict()
    assert d1["bounding_box"] == [0.1, 0.2, 0.8, 0.9]
    c1_restored = CharacterEntry.from_dict(d1)
    assert c1_restored.bounding_box == (0.1, 0.2, 0.8, 0.9)

    # RecognizedCharacter serialization
    rc = RecognizedCharacter(
        name="Zoro",
        confidence=0.85,
        bounding_box=(0.15, 0.25, 0.75, 0.85),
        detection_method="visual_heuristic",
        matched_features=["screentone_hair", "standard_body"],
    )
    rc_dict = rc.to_dict()
    assert rc_dict["confidence"] == 0.85
    rc_restored = RecognizedCharacter.from_dict(rc_dict)
    assert rc_restored.name == "Zoro"
    assert rc_restored.bounding_box == (0.15, 0.25, 0.75, 0.85)


def test_character_palette_optimize_for_page():
    """Verifies that CharacterPalette.optimize_for_page isolates the active character."""
    from colorizer_engine import CharacterEntry, CharacterPalette, RecognizedCharacter

    palette = CharacterPalette(
        characters=[
            CharacterEntry(name="Monkey D. Luffy", costume_hex="#D62828"),
            CharacterEntry(name="Roronoa Zoro", costume_hex="#1C4428"),
            CharacterEntry(name="Nami", costume_hex="#264653"),
        ],
        preset_id="one_piece",
        preset_title="One Piece",
    )

    # Zoro is recognized on this specific page
    recognized = [
        RecognizedCharacter(
            name="Roronoa Zoro",
            confidence=0.88,
            bounding_box=(0.1, 0.2, 0.8, 0.9),
            detection_method="visual_heuristic",
        )
    ]

    opt_pal = palette.optimize_for_page(recognized)
    assert len(opt_pal.characters) == 1
    assert opt_pal.characters[0].name == "Roronoa Zoro"
    assert opt_pal.characters[0].bounding_box == (0.1, 0.2, 0.8, 0.9)
    # Luffy and Nami are omitted so their red/orange/blue colors do not bleed onto Zoro
    assert not any(c.name == "Monkey D. Luffy" for c in opt_pal.characters)

    # When recognition is empty, returns empty palette to protect scenery/background pages
    opt_empty = palette.optimize_for_page([])
    assert len(opt_empty.characters) == 0

    # Explicit fallback_to_all preserves all characters
    opt_fallback = palette.optimize_for_page([], fallback_to_all=True)
    assert len(opt_fallback.characters) == 3
    assert opt_fallback.characters[0].name == "Monkey D. Luffy"
    assert opt_fallback.characters[0].bounding_box is None


def test_hint_tensor_with_bounding_box():
    """Verifies that hint seeds are strictly constrained to the character's bounding box."""
    from colorizer_engine import CharacterEntry, CharacterPalette

    # Palette with Zoro constrained to top-left quadrant [0.0, 0.0, 0.5, 0.5]
    palette = CharacterPalette(
        characters=[
            CharacterEntry(
                name="Roronoa Zoro",
                costume_hex="#1C4428",
                bounding_box=(0.0, 0.0, 0.5, 0.5),
            )
        ]
    )

    h, w = 200, 200
    # Sketch with screentone patches in both top-left (Zoro) and bottom-right (other panel)
    sketch = np.ones((h, w), dtype=np.float32)
    sketch[20:60, 20:60] = 0.50  # Candidate in top-left
    sketch[120:160, 120:160] = 0.50  # Candidate in bottom-right

    hint = palette.build_hint_tensor(h, w, device="cpu", sketch_gray=sketch)
    mask = hint[0, 3].numpy()

    # Seeds should exist in top-left quadrant
    top_left_seeds = np.sum(mask[:100, :100] > 0)
    # No seeds should exist in bottom-right quadrant
    bottom_right_seeds = np.sum(mask[100:, 100:] > 0)

    assert top_left_seeds > 0, "Expected seed in top-left region"
    assert bottom_right_seeds == 0, "Seed incorrectly leaked outside bounding box into bottom-right"


def test_harmonization_with_bounding_box():
    """Verifies that color harmonization only snaps hues within the character's bounding box."""
    from colorizer_engine import (
        CharacterEntry,
        CharacterPalette,
        apply_character_palette_harmonization,
    )

    # Zoro: canonical green (#1C4428) constrained to left half of image
    palette = CharacterPalette(
        characters=[
            CharacterEntry(
                name="Roronoa Zoro",
                costume_hex="#1C4428",
                bounding_box=(0.0, 0.0, 1.0, 0.5),  # left half
            )
        ]
    )

    # Create image with muted green-teal pixels everywhere
    img = np.full((100, 100, 3), [40, 110, 50], dtype=np.uint8)

    harmonized = apply_character_palette_harmonization(img, palette)

    # Left half (inside Zoro's box) should be harmonized towards Zoro's hue
    left_sample = harmonized[50, 25]
    # Right half (outside Zoro's box) should remain untouched
    right_sample = harmonized[50, 75]

    assert not np.array_equal(left_sample, [40, 110, 50]), "Expected left half to be harmonized"
    assert np.max(np.abs(right_sample.astype(int) - np.array([40, 110, 50]))) <= 1, (
        "Right half outside bounding box should remain untouched"
    )
    assert not np.array_equal(left_sample, right_sample), (
        "Harmonized left half should differ from unharmonized right half"
    )


def test_manga_character_recognizer_heuristics(tmp_path):
    """Verifies visual heuristic recognition differentiates characters by features."""
    import cv2

    from colorizer_engine import CharacterEntry, CharacterPalette, MangaCharacterRecognizer

    recognizer = MangaCharacterRecognizer()

    palette = CharacterPalette(
        characters=[
            CharacterEntry(
                name="Monkey D. Luffy",
                hair_hex="#111111",
                costume_hex="#D62828",
                notes="Red vest, yellow straw hat",
            ),
            CharacterEntry(
                name="Roronoa Zoro",
                hair_hex="#4E8A3C",
                costume_hex="#1C4428",
                notes="Green haramaki and coat",
            ),
        ]
    )

    # Create a synthetic image of a figure with screentone hair (Zoro's characteristic)
    test_img = np.full((400, 300), 245, dtype=np.uint8)
    # Figure panel
    test_img[50:350, 40:260] = 235
    # Screentone hair in top of figure: gray ~120
    test_img[60:110, 80:220] = 120
    # Lineart body
    cv2.rectangle(test_img, (60, 120), (240, 340), 0, 2)

    img_path = tmp_path / "zoro_test.png"
    cv2.imwrite(str(img_path), test_img)

    results = recognizer.recognize_page_characters(str(img_path), palette)
    assert len(results) >= 1
    # Zoro should be recognized due to screentone hair matching
    names = [r.name for r in results]
    assert "Roronoa Zoro" in names
    top_result = results[0]
    assert top_result.bounding_box is not None


def test_api_recognize_characters_endpoint(tmp_path):
    """Verifies POST /api/session/{session_id}/page/{page_index}/recognize."""
    from colorizer_engine import CharacterEntry, CharacterPalette
    from main import SESSION_PALETTES, SESSIONS, STORAGE_DIR, save_session_meta

    session_id = "test_recog_" + str(uuid.uuid4())[:8]
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)

    img_path = orig_dir / "page_0001.png"
    Image.new("L", (200, 200), color=230).save(img_path)

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "onepiece.cbz",
        "total_pages": 1,
        "processed_count": 0,
        "status": "idle",
        "pages": [
            {
                "page_index": 0,
                "filename": "page_0001.png",
                "original_path": str(img_path),
                "status": "pending",
            }
        ],
    }
    SESSION_PALETTES[session_id] = CharacterPalette(
        characters=[
            CharacterEntry(
                name="Monkey D. Luffy", hair_hex="#111111", costume_hex="#D62828", notes="Straw hat"
            ),
            CharacterEntry(name="Roronoa Zoro", hair_hex="#4E8A3C", costume_hex="#1C4428"),
        ],
        preset_id="one_piece",
    )
    save_session_meta(session_id)

    try:
        resp = client.post(f"/api/session/{session_id}/page/0/recognize")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "recognized" in data
        assert "palette" in data
        assert len(data["recognized"]) >= 1

        # Check that page metadata saved recognized characters
        sess = SESSIONS[session_id]
        page = sess["pages"][0]
        assert "recognized_characters" in page
        assert len(page["recognized_characters"]) >= 1
    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(session_id, None)
        SESSION_PALETTES.pop(session_id, None)


def test_preview_with_active_character_names_override(tmp_path):
    """Verifies that /api/colorize/preview respects active_character_names override."""
    from colorizer_engine import CharacterEntry, CharacterPalette
    from main import SESSION_PALETTES, SESSIONS, STORAGE_DIR, save_session_meta

    session_id = "test_prev_override_" + str(uuid.uuid4())[:8]
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)

    img_path = orig_dir / "page_0001.png"
    Image.new("L", (100, 100), color=230).save(img_path)

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "onepiece.cbz",
        "total_pages": 1,
        "processed_count": 0,
        "status": "idle",
        "pages": [
            {
                "page_index": 0,
                "display_name": "Page 1",
                "filename": "page_0001.png",
                "original_path": str(img_path),
                "status": "pending",
            }
        ],
    }
    SESSION_PALETTES[session_id] = CharacterPalette(
        characters=[
            CharacterEntry(name="Monkey D. Luffy", costume_hex="#D62828"),
            CharacterEntry(name="Roronoa Zoro", costume_hex="#1C4428"),
        ]
    )
    save_session_meta(session_id)

    try:
        # Request preview with only Zoro active
        resp = client.post(
            "/api/colorize/preview",
            json={
                "session_id": session_id,
                "page_index": 0,
                "model_provider": "local_smart",
                "active_character_names": ["Roronoa Zoro"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "recognized_characters" in data
    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(session_id, None)
        SESSION_PALETTES.pop(session_id, None)


def test_offline_clip_character_recognition():
    """Verifies that offline pre-trained CLIP model accurately detects manga characters."""
    pytest.importorskip("transformers")
    from colorizer_engine import CharacterEntry, CharacterPalette, MangaCharacterRecognizer
    from manga_presets import get_preset_by_id

    recognizer = MangaCharacterRecognizer()
    model, processor, _ = recognizer._ensure_clip()
    if model is None or processor is None:
        pytest.skip("Offline CLIP model could not be loaded")

    preset = get_preset_by_id("one_piece")
    assert preset is not None

    palette = CharacterPalette(
        preset_title=preset.title,
        characters=[
            CharacterEntry(name=c.name, hair_hex=c.hair_hex, notes=c.notes)
            for c in preset.characters
        ],
    )

    demo_img = Path("demo/original.png")
    if not demo_img.exists():
        pytest.skip("demo/original.png not available")

    # Run offline CLIP AI recognition
    recs = recognizer.recognize_page_characters(
        image_path=str(demo_img),
        palette=palette,
        recognition_mode="offline_ai",
    )

    assert len(recs) >= 1
    # demo/original.png centers the One Piece cast around Chopper/Luffy; CLIP top-1 can flip
    # between these two across runtime/model builds.
    allowed_top_labels = {"Tony Tony Chopper", "Monkey D. Luffy"}
    top_char = recs[0]
    assert top_char.name in allowed_top_labels
    if len(recs) > 1:
        assert top_char.confidence >= recs[1].confidence
    assert top_char.detection_method == "offline_clip_ai"
    assert any(f.startswith("clip_score:") for f in top_char.matched_features)
    assert any(f.startswith("rel_score:") for f in top_char.matched_features)
    assert top_char.confidence >= 0.40
    assert top_char.bounding_box is not None
    assert len(top_char.bounding_box) == 4


def test_manga_character_recognizer_mode_routing_and_fallbacks(tmp_path):
    """Verifies mode selection routing and error fallback behavior."""
    from colorizer_engine import CharacterEntry, CharacterPalette, MangaCharacterRecognizer

    img_path = tmp_path / "panel.png"
    # Create test image with ink figure
    arr = np.ones((200, 200), dtype=np.uint8) * 255
    arr[40:160, 40:160] = 30
    Image.fromarray(arr).save(img_path)

    palette = CharacterPalette(
        preset_title="Test Manga",
        characters=[
            CharacterEntry(name="Hero", visual_traits=["black_hair"]),
            CharacterEntry(name="Sidekick", visual_traits=["light_hair"]),
        ],
    )
    recognizer = MangaCharacterRecognizer()

    # 1. Fast heuristics mode
    recs_heuristics = recognizer.recognize_page_characters(
        image_path=str(img_path),
        palette=palette,
        recognition_mode="heuristics",
    )
    assert len(recs_heuristics) >= 1
    assert recs_heuristics[0].detection_method == "visual_heuristic"

    # 2. Offline AI fallback when CLIP fails
    with patch.object(recognizer, "_recognize_with_clip", side_effect=RuntimeError("GPU OOM")):
        recs_fallback = recognizer.recognize_page_characters(
            image_path=str(img_path),
            palette=palette,
            recognition_mode="offline_ai",
        )
        assert len(recs_fallback) >= 1
        # Seamlessly falls back to visual heuristics
        assert recs_fallback[0].detection_method == "visual_heuristic"


def test_api_recognize_characters_with_mode_selection(tmp_path):
    """Verifies /api/session/.../recognize endpoint with recognition_mode payload."""
    from colorizer_engine import CharacterEntry, CharacterPalette
    from main import SESSION_PALETTES, SESSIONS, STORAGE_DIR, save_session_meta

    session_id = "test_rec_mode_" + str(uuid.uuid4())[:8]
    sess_dir = STORAGE_DIR / session_id
    orig_dir = sess_dir / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)

    img_path = orig_dir / "page_0001.png"
    arr = np.ones((200, 200), dtype=np.uint8) * 255
    arr[50:150, 50:150] = 20
    Image.fromarray(arr).save(img_path)

    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "onepiece.cbz",
        "total_pages": 1,
        "processed_count": 0,
        "status": "idle",
        "pages": [
            {
                "page_index": 0,
                "display_name": "Page 1",
                "filename": "page_0001.png",
                "original_path": str(img_path),
                "status": "pending",
            }
        ],
    }
    SESSION_PALETTES[session_id] = CharacterPalette(
        preset_title="One Piece",
        characters=[
            CharacterEntry(name="Monkey D. Luffy", visual_traits=["black_hair", "straw_hat"]),
        ],
    )
    save_session_meta(session_id)

    try:
        # 1. Test with explicit heuristics mode
        resp = client.post(
            f"/api/session/{session_id}/page/0/recognize",
            json={"recognition_mode": "heuristics"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["recognized"]) >= 1
        assert data["recognized"][0]["detection_method"] == "visual_heuristic"

        # 2. Test with explicit auto mode
        resp = client.post(
            f"/api/session/{session_id}/page/0/recognize",
            json={"recognition_mode": "auto"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert len(data["recognized"]) >= 1
    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(session_id, None)
        SESSION_PALETTES.pop(session_id, None)


def test_character_eye_hex_support():
    """Verifies eye_hex is correctly stored, serialized, and deserialized."""
    pc = PresetCharacter(
        name="Arale Norimaki",
        hair_hex="#8A2BE2",
        skin_hex="#F4C5A0",
        costume_hex="#2962FF",
        extra_hex="#E53935",
        eye_hex="#3E2723",
    )
    d = pc.to_dict()
    assert d["eye_hex"] == "#3E2723"
    pc2 = PresetCharacter.from_dict(d)
    assert pc2.eye_hex == "#3E2723"

    ce = CharacterEntry(
        name="Arale Norimaki",
        hair_hex="#8A2BE2",
        eye_hex="#3E2723",
    )
    ced = ce.to_dict()
    assert ced["eye_hex"] == "#3E2723"
    ce2 = CharacterEntry.from_dict(ced)
    assert ce2.eye_hex == "#3E2723"


def test_build_hint_tensor_multiseed_adaptive():
    """Verifies build_hint_tensor places seeds across screentone hair, skin, and eye regions."""
    palette = CharacterPalette(
        characters=[
            CharacterEntry(
                name="Midori Yamabuki",
                hair_hex="#4A148C",
                skin_hex="#FFF0E5",
                costume_hex="#E91E63",
                eye_hex="#2E7D32",
                bounding_box=(0.1, 0.1, 0.9, 0.9),
            )
        ]
    )
    h, w = 400, 400
    sketch = np.full((h, w), 0.95, dtype=np.float32)
    # Face skin region (0.75 brightness)
    sketch[120:250, 120:280] = 0.75
    # Hair screentone region (0.35 brightness)
    sketch[40:130, 100:300] = 0.35
    # Eyes dark spots (0.10 brightness)
    sketch[160:175, 150:170] = 0.10
    sketch[160:175, 230:250] = 0.10
    # Costume region (0.45 brightness)
    sketch[260:380, 80:320] = 0.45

    hint = palette.build_hint_tensor(h, w, "cpu", sketch_gray=sketch)
    assert hint.shape == (1, 4, h, w)
    mask = hint[0, 3] > 0
    total_seeds = mask.sum().item()
    assert total_seeds > 0, "Hint tensor must place seeds"

    # Verify colors placed match target canonical colors
    colors = hint[0, :3, mask].numpy()
    unique_colors = np.unique(colors, axis=1).T
    assert len(unique_colors) >= 3, "Should place seeds for multiple features (hair, skin, costume, eye)"


def test_character_palette_hair_and_eye_harmonization():
    """Verifies apply_character_palette_harmonization successfully recolors hair and eyes."""
    palette = CharacterPalette(
        characters=[
            CharacterEntry(
                name="Midori Yamabuki",
                hair_hex="#4A148C",  # violet/indigo hair
                skin_hex="#FFF0E5",
                costume_hex="#E91E63",
                eye_hex="#2E7D32",  # emerald green eyes
                bounding_box=(0.1, 0.1, 0.9, 0.9),
            )
        ]
    )
    # Synthetic image where neural model outputted muddy brown hair (RGB: 90, 70, 80)
    # peach face (RGB: 235, 195, 180), dark eye spots (RGB: 40, 40, 40), magenta dress (RGB: 140, 90, 120)
    img = np.full((300, 300, 3), 245, dtype=np.uint8)
    img[120:220, 90:210] = [235, 195, 180]  # face
    img[40:115, 80:220] = [90, 70, 80]     # hair (muddy)
    img[140:155, 120:135] = [40, 40, 40]   # left eye
    img[140:155, 165:180] = [40, 40, 40]   # right eye
    img[220:290, 70:230] = [140, 90, 120]  # dress

    harmonized = apply_character_palette_harmonization(img, palette)

    # Hair should be violet/indigo (blue > green, red significant)
    hair_pixel = harmonized[70, 150]
    assert hair_pixel[2] > hair_pixel[1], "Violet hair should have blue > green"
    assert hair_pixel[0] > 40, "Violet hair should have visible red component"

    # Eyes should be tinted green (green channel elevated)
    eye_pixel = harmonized[147, 127]
    assert eye_pixel[1] >= eye_pixel[0], "Green eye should have green >= red"


def test_arale_violet_hair_blue_eye_multi_character_harmonization():
    """
    Verifies that in a multi-character two-shot panel:
    1. Arale's bangs and crown hair harmonize to vibrant canonical violet (#8A2BE2).
    2. Arale's eyes harmonize to canonical blue (#1565C0) rather than being hijacked by red cap.
    3. Dr. Senbei on the left retains authentic black hair and is not overwritten by Arale.
    4. optimize_for_page differentiates characters sharing family names ('Norimaki').
    """
    from colorizer_engine import RecognizedCharacter

    palette = CharacterPalette(
        characters=[
            CharacterEntry(
                name="Arale Norimaki",
                hair_hex="#8A2BE2",
                skin_hex="#F4C5A0",
                costume_hex="#2962FF",
                extra_hex="#E53935",
                eye_hex="#1565C0",
            ),
            CharacterEntry(
                name="Dr. Senbei Norimaki",
                hair_hex="#212121",
                skin_hex="#F5C596",
                costume_hex="#7E57C2",
                extra_hex="#FFFFFF",
                eye_hex="#212121",
            ),
        ],
        preset_id="dr_slump",
        preset_title="Dr. Slump",
    )

    # 1. Test optimize_for_page name matching with shared last name "Norimaki"
    recs = [
        RecognizedCharacter(
            name="Dr. Senbei Norimaki",
            confidence=0.88,
            bounding_box=(0.18, 0.02, 0.95, 0.49),
        ),
        RecognizedCharacter(
            name="Arale Norimaki",
            confidence=0.92,
            bounding_box=(0.18, 0.41, 0.95, 0.93),
        ),
    ]
    opt_palette = palette.optimize_for_page(recs)
    assert len(opt_palette.characters) == 2
    assert opt_palette.characters[0].name == "Dr. Senbei Norimaki"
    assert opt_palette.characters[0].hair_hex == "#212121"
    assert opt_palette.characters[1].name == "Arale Norimaki"
    assert opt_palette.characters[1].hair_hex == "#8A2BE2"

    # 2. Test harmonization on two-shot image
    # Senbei on left half (x < 150), Arale on right half (x >= 150)
    H, W = 300, 300
    img = np.full((H, W, 3), 245, dtype=np.uint8)
    orig_gray = np.full((H, W), 0.95, dtype=np.float32)

    # Dr. Senbei on left (x: 20..130): black hair, neutral face
    img[60:120, 20:130] = [30, 30, 30]  # black hair
    orig_gray[60:120, 20:130] = 0.20

    # Arale on right (x: 150..280)
    # Bangs / hair: neural gave orange (RGB: 220, 130, 70)
    img[60:120, 160:270] = [220, 130, 70]
    orig_gray[60:120, 160:270] = 0.60
    # Eye spot: neural gave dark brown (RGB: 70, 35, 20)
    img[140:155, 190:205] = [70, 35, 20]
    orig_gray[140:155, 190:205] = 0.30

    harmonized = apply_character_palette_harmonization(
        img, opt_palette, orig_gray=orig_gray
    )

    # Arale hair (x=210, y=90) must be violet: B > G and R > G
    arale_hair = harmonized[90, 210]
    assert arale_hair[2] > arale_hair[1], f"Arale hair should be violet with B > G: {arale_hair}"
    assert arale_hair[0] > arale_hair[1], f"Arale hair should have prominent red: {arale_hair}"

    # Arale eye (x=197, y=147) must be blue: B > R
    arale_eye = harmonized[147, 197]
    assert arale_eye[2] > arale_eye[0], f"Arale eye should be blue with B > R: {arale_eye}"

    # Dr. Senbei hair (x=70, y=90) must remain authentic dark neutral (not violet)
    senbei_hair = harmonized[90, 70]
    assert abs(int(senbei_hair[0]) - int(senbei_hair[2])) < 25, f"Dr. Senbei hair must stay neutral: {senbei_hair}"


def test_offline_manga109_yolo_detection():
    """Verifies that Manga109 YOLO detector initializes and isolates character faces and bodies."""
    pytest.importorskip("ultralytics")
    from colorizer_engine import CharacterPalette, CharacterEntry, MangaCharacterRecognizer
    from PIL import Image
    from pathlib import Path

    recognizer = MangaCharacterRecognizer()
    yolo_model, device = recognizer._ensure_manga_yolo()
    if yolo_model is None:
        pytest.skip("Manga109 YOLO model weights could not be loaded")

    demo_path = Path("demo/original.png")
    if not demo_path.exists():
        pytest.skip("demo/original.png not available")

    pil_img = Image.open(demo_path).convert("RGB")
    regions = recognizer._detect_manga_yolo_regions(pil_img, conf=0.15)
    assert len(regions) >= 1
    # Check that regions have format (y0, x0, y1, x1, cls_name, conf)
    first_reg = regions[0]
    assert len(first_reg) == 6
    assert first_reg[4] in ("body", "face")
    assert first_reg[5] >= 0.15

    # Test full end-to-end recognize_page_characters with offline_ai
    palette = CharacterPalette(
        preset_title="One Piece",
        characters=[
            CharacterEntry(name="Monkey D. Luffy", notes="Straw hat pirate captain with red vest and black hair"),
            CharacterEntry(name="Tony Tony Chopper", notes="Small reindeer doctor with pink top hat and blue nose"),
        ],
    )
    recs = recognizer.recognize_page_characters(
        image_path=str(demo_path),
        palette=palette,
        recognition_mode="offline_ai",
    )
    assert len(recs) >= 1
    top_char = recs[0]
    assert top_char.bounding_box is not None
    assert len(top_char.bounding_box) == 4
    assert top_char.confidence >= 0.35


def test_preview_preserves_recognized_characters(tmp_path):
    """Verifies that colorization preview preserves previously scanned recognized characters."""
    from main import app, SESSIONS, SESSION_PALETTES, save_session_meta
    from colorizer_engine import CharacterEntry, CharacterPalette
    import uuid
    import shutil
    from fastapi.testclient import TestClient

    client = TestClient(app)
    session_id = f"test-preserve-rec-{uuid.uuid4().hex[:8]}"
    sess_dir = Path("sessions") / session_id
    orig_dir = sess_dir / "original"
    orig_dir.mkdir(parents=True, exist_ok=True)

    img_path = orig_dir / "page_0000.jpg"
    arr = np.ones((100, 100, 3), dtype=np.uint8) * 240
    Image.fromarray(arr).save(img_path)

    scanned_data = [
        {"name": "Arale Norimaki", "confidence": 0.95, "bounding_box": [0.1, 0.1, 0.8, 0.8]}
    ]

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
                "recognized_characters": scanned_data,
            }
        ],
    }
    SESSION_PALETTES[session_id] = CharacterPalette(
        characters=[
            CharacterEntry(name="Arale Norimaki", hair_hex="#8A2BE2"),
        ]
    )
    save_session_meta(session_id)

    try:
        resp = client.post(
            "/api/colorize/preview",
            json={
                "session_id": session_id,
                "page_index": 0,
                "model_provider": "resnext_generator",
                "model_name": "resnext-v2-manga",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        # Must return the preserved recognized characters
        assert len(data.get("recognized_characters", [])) == 1
        assert data["recognized_characters"][0]["name"] == "Arale Norimaki"
        # Must preserve in session page info
        sess = SESSIONS[session_id]
        assert len(sess["pages"][0].get("recognized_characters", [])) == 1
        assert sess["pages"][0]["recognized_characters"][0]["name"] == "Arale Norimaki"
    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
        SESSIONS.pop(session_id, None)
        SESSION_PALETTES.pop(session_id, None)
