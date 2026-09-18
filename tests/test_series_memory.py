"""
tests/test_series_memory.py - Test suite for Series Memory Bank & Cross-Page Active Learning.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from colorizer_engine import CharacterEntry, CharacterPalette
from main import SERIES_BANK, SESSIONS, app, save_session_meta
from series_memory import (
    LearnedCharacterTrait,
    SeriesMemory,
    SeriesMemoryBank,
    derive_series_key,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_derive_series_key():
    """Verifies series key derivation from presets and arbitrary filenames."""
    # Presets
    key, title = derive_series_key("Dr. Slump - Arale-chan Vol 01.cbr")
    assert key == "dr_slump"
    assert "Dr. Slump" in title

    key, title = derive_series_key("[MangaStream] One Piece - Ch. 1050 [1080p].cbz")
    assert key == "one_piece"
    assert "One Piece" in title

    # Explicit preset_id
    key, title = derive_series_key("random_file.zip", preset_id="naruto")
    assert key == "naruto"
    assert "Naruto" in title

    # Non-preset arbitrary title sanitization
    key, title = derive_series_key("[ScanGroup] Spy x Family - Vol 02 Ch 10 [Digital].cbz")
    assert "spy" in key and "family" in key


def test_series_memory_persistence(tmp_path):
    """Verifies SeriesMemoryBank persistence, reload, confidence tracking, and exemplar caps."""
    store_file = tmp_path / "memory.json"
    bank = SeriesMemoryBank(store_file)

    # Create dummy exemplar images
    img1 = tmp_path / "page_1.png"
    img2 = tmp_path / "page_2.png"
    Image.new("RGB", (64, 64), color="red").save(img1)
    Image.new("RGB", (64, 64), color="blue").save(img2)

    chars = [
        {"name": "Arale", "hair_hex": "#6b21a8", "skin_hex": "#ffdfba", "eye_hex": "#2563eb"}
    ]

    # First confirmation
    bank.record_learning(
        series_key="dr_slump",
        title="Dr. Slump",
        characters=chars,
        session_id="sess_1",
        page_index=0,
        approved_image_path=str(img1),
        style="shonen_vivid",
    )

    mem = bank.get_memory("dr_slump")
    assert mem is not None
    assert mem.series_key == "dr_slump"
    assert "arale" in mem.characters
    assert mem.characters["arale"].hair_hex == "#6b21a8"
    assert mem.characters["arale"].confirmation_count == 1
    assert len(mem.exemplar_pages) == 1

    # Second confirmation: confidence should increase
    bank.record_learning(
        series_key="dr_slump",
        title="Dr. Slump",
        characters=[{"name": "Arale", "hair_hex": "#6b21a8", "skin_hex": "#ffdfba"}],
        session_id="sess_2",
        page_index=1,
        approved_image_path=str(img2),
    )

    mem2 = bank.get_memory("dr_slump")
    assert mem2.characters["arale"].confirmation_count == 2
    assert mem2.characters["arale"].confidence > 1.5
    assert len(mem2.exemplar_pages) == 2

    # Exemplar resolution with exclude
    exemplar = bank.get_exemplar_image("dr_slump", exclude_path=mem2.exemplar_pages[1]["image_path"])
    assert exemplar is not None
    assert "page_1" in Path(exemplar).name
    assert Path(exemplar).exists()

    # Persistence verification: reload from disk in new instance
    bank_reloaded = SeriesMemoryBank(store_file)
    mem_reloaded = bank_reloaded.get_memory("dr_slump")
    assert mem_reloaded is not None
    assert mem_reloaded.characters["arale"].hair_hex == "#6b21a8"
    assert len(mem_reloaded.exemplar_pages) == 2

    # Reset
    assert bank_reloaded.reset_series_memory("dr_slump") is True
    assert bank_reloaded.get_memory("dr_slump") is None


def test_character_palette_apply_series_memory():
    """Verifies that apply_series_memory updates existing character entries and adds new ones."""
    base_palette = CharacterPalette(
        characters=[
            CharacterEntry(name="Arale Norimaki", hair_hex="#2e1065", skin_hex="#fcd34d"),
            CharacterEntry(name="Senbei Norimaki", hair_hex="#1f2937", skin_hex="#fde047"),
        ],
        preset_id="dr_slump",
        preset_title="Dr. Slump",
    )

    memory = SeriesMemory(
        series_key="dr_slump",
        title="Dr. Slump",
        characters={
            "arale norimaki": LearnedCharacterTrait(
                name="Arale Norimaki",
                hair_hex="#7e22ce",  # updated purple
                eye_hex="#3b82f6",   # learned blue eyes
            ),
            "gatchan": LearnedCharacterTrait(
                name="Gatchan",
                hair_hex="#22c55e",  # learned green hair
                skin_hex="#fef08a",
            ),
        },
    )

    updated_palette = base_palette.apply_series_memory(memory)
    char_map = {c.name.lower(): c for c in updated_palette.characters}

    # Existing Arale updated
    assert char_map["arale norimaki"].hair_hex == "#7e22ce"
    assert char_map["arale norimaki"].eye_hex == "#3b82f6"
    assert char_map["arale norimaki"].skin_hex == "#fcd34d"  # preserved original skin

    # Preserved Senbei
    assert char_map["senbei norimaki"].hair_hex == "#1f2937"

    # Newly discovered Gatchan added
    assert "gatchan" in char_map
    assert char_map["gatchan"].hair_hex == "#22c55e"


def test_series_memory_api_endpoints(client, tmp_path):
    """Verifies GET /api/series-memory/{id}, POST /api/series-memory/learn-page, and reset."""
    session_id = "test_memory_session_1"
    sess_dir = tmp_path / session_id
    color_dir = sess_dir / "colorized"
    color_dir.mkdir(parents=True, exist_ok=True)

    dummy_color = color_dir / "page_001.png"
    Image.new("RGB", (100, 100), color="green").save(dummy_color)

    with patch("main.STORAGE_DIR", tmp_path):
        SESSIONS[session_id] = {
            "session_id": session_id,
            "filename": "Dr. Slump - Vol 01.cbz",
            "detected_preset": "dr_slump",
            "preset_title": "Dr. Slump",
            "total_pages": 1,
            "processed_count": 1,
            "status": "completed",
            "pages": [
                {
                    "filename": "page_001.png",
                    "path": str(dummy_color),
                    "original_path": str(dummy_color),
                    "status": "colorized",
                    "colorized_url": f"/api/session/{session_id}/image/colorized/page_001.png",
                }
            ],
        }

        # 1. GET series memory before learning
        res_get = client.get(f"/api/series-memory/{session_id}")
        assert res_get.status_code == 200
        data_get = res_get.json()
        assert data_get["series_key"] == "dr_slump"

        # 2. Learn page
        res_learn = client.post(
            "/api/series-memory/learn-page",
            json={
                "session_id": session_id,
                "page_index": 0,
                "exemplar": True,
            },
        )
        assert res_learn.status_code == 200
        data_learn = res_learn.json()
        assert data_learn["status"] == "ok"
        assert "memory" in data_learn
        assert len(data_learn["memory"]["exemplar_pages"]) >= 1

        # Verify page marked as learned
        assert SESSIONS[session_id]["pages"][0]["learned_to_memory"] is True

        # 3. GET series memory after learning
        res_get2 = client.get(f"/api/series-memory/{session_id}")
        assert res_get2.status_code == 200
        mem_data = res_get2.json()["memory"]
        assert mem_data is not None
        assert mem_data["approved_pages_count"] >= 1

        # 4. Reset series memory
        res_reset = client.post(f"/api/series-memory/reset/{data_learn['series_key']}")
        assert res_reset.status_code == 200
        assert res_reset.json()["reset"] is True


def test_find_best_exemplars_ranking(tmp_path):
    """Verifies that find_best_exemplars ranks exemplars by character overlap, pinned status, and luminance."""
    bank = SeriesMemoryBank(tmp_path / "memory.json")
    series_key = "one_piece"

    # Create 3 dummy pages
    img0 = tmp_path / "p0.png"
    img1 = tmp_path / "p1.png"
    img2 = tmp_path / "p2.png"
    Image.new("RGB", (64, 64), color=(200, 200, 200)).save(img0)
    Image.new("RGB", (64, 64), color=(30, 30, 30)).save(img1)
    Image.new("RGB", (64, 64), color=(120, 120, 120)).save(img2)

    # Page 0: Luffy
    bank.record_learning(
        series_key=series_key,
        title="One Piece",
        characters=[{"name": "Luffy", "hair_hex": "#000000"}],
        session_id="s1",
        page_index=0,
        approved_image_path=str(img0),
        pinned=False,
    )
    # Page 1: Zoro (pinned)
    bank.record_learning(
        series_key=series_key,
        title="One Piece",
        characters=[{"name": "Zoro", "hair_hex": "#15803d"}],
        session_id="s1",
        page_index=1,
        approved_image_path=str(img1),
        pinned=True,
    )
    # Page 2: Luffy & Nami
    bank.record_learning(
        series_key=series_key,
        title="One Piece",
        characters=[
            {"name": "Luffy", "hair_hex": "#000000"},
            {"name": "Nami", "hair_hex": "#ea580c"},
        ],
        session_id="s1",
        page_index=2,
        approved_image_path=str(img2),
        pinned=False,
    )

    # 1. Query for Luffy: Page 1 is pinned (+50), Page 2 has Luffy (+20), Page 0 has Luffy (+20)
    best = bank.find_best_exemplars(
        series_key=series_key,
        active_character_names=["Luffy"],
        max_count=2,
    )
    assert len(best) == 2
    # Pinned page 1 should be ranked #1
    assert best[0]["page_index"] == 1
    assert best[0]["pinned"] is True

    # 2. Unpin Page 1 and query for Luffy & Nami
    bank.pin_exemplar(series_key, 1, pinned=False)
    best_unpinned = bank.find_best_exemplars(
        series_key=series_key,
        active_character_names=["Luffy", "Nami"],
        max_count=2,
    )
    assert len(best_unpinned) == 2
    # Page 2 has 2 matching characters (overlap score 40) -> should be #1
    assert best_unpinned[0]["page_index"] == 2
    # Page 0 has 1 matching character (overlap score 20) -> should be #2
    assert best_unpinned[1]["page_index"] == 0

    # 3. Test remove_exemplar
    assert bank.remove_exemplar(series_key, 2) is True
    remaining = bank.find_best_exemplars(series_key, max_count=5)
    remaining_indices = [ex["page_index"] for ex in remaining]
    assert 2 not in remaining_indices
    assert len(remaining) == 2


def test_transfer_exemplar_palette(tmp_path):
    """Verifies statistical Reinhard Lab color transfer with line art and speech bubble protection."""
    import numpy as np
    from colorizer_engine import transfer_exemplar_palette

    # Create target RGB image (neutral flat color)
    target = np.full((100, 100, 3), 128, dtype=np.uint8)
    # Add a pure white speech bubble in top-left
    target[0:20, 0:20] = 255
    # Add deep black line art ink in bottom-left
    target[80:100, 0:20] = 10

    # Normalized original grayscale
    orig_gray = np.mean(target.astype(np.float32) / 255.0, axis=2)

    # Create exemplar image with warm red/gold tint
    exemplar_file = tmp_path / "exemplar_tint.png"
    exemplar_img = Image.new("RGB", (100, 100), color=(220, 90, 40))
    exemplar_img.save(exemplar_file)

    transferred = transfer_exemplar_palette(
        target_rgb=target,
        exemplar_img_path=str(exemplar_file),
        blend_weight=0.5,
        preserve_line_art=True,
        orig_gray=orig_gray,
    )

    assert transferred.shape == (100, 100, 3)
    assert transferred.dtype == np.uint8

    # The neutral gray body (center) should have shifted towards the warm exemplar
    center_pixel = transferred[50, 50]
    # Red channel should be higher than blue channel due to the warm exemplar
    assert center_pixel[0] > center_pixel[2]

    # Bubble area (white) should be protected and remain bright
    bubble_pixel = transferred[5, 5]
    assert bubble_pixel[0] >= 240 and bubble_pixel[1] >= 240 and bubble_pixel[2] >= 240

    # Ink line area should be protected and remain dark
    ink_pixel = transferred[90, 5]
    assert ink_pixel[0] <= 30 and ink_pixel[1] <= 30 and ink_pixel[2] <= 30


def test_series_memory_exemplar_endpoints(client, tmp_path):
    """Verifies GET /exemplars, GET /exemplar-image, POST /pin-exemplar, and DELETE /exemplar."""
    session_id = "test_exemplar_api_session"
    sess_dir = tmp_path / session_id
    color_dir = sess_dir / "colorized"
    color_dir.mkdir(parents=True, exist_ok=True)

    dummy_color = color_dir / "page_001.png"
    Image.new("RGB", (64, 64), color="purple").save(dummy_color)

    with patch("main.STORAGE_DIR", tmp_path):
        SESSIONS[session_id] = {
            "session_id": session_id,
            "filename": "Chainsaw Man - Ch 01.cbz",
            "detected_preset": "chainsaw_man",
            "preset_title": "Chainsaw Man",
            "total_pages": 1,
            "processed_count": 1,
            "status": "completed",
            "pages": [
                {
                    "filename": "page_001.png",
                    "path": str(dummy_color),
                    "original_path": str(dummy_color),
                    "status": "colorized",
                    "colorized_url": f"/api/session/{session_id}/image/colorized/page_001.png",
                }
            ],
        }

        # 1. Learn page with exemplar
        res_learn = client.post(
            "/api/series-memory/learn-page",
            json={
                "session_id": session_id,
                "page_index": 0,
                "character_names": ["Denji"],
                "exemplar": True,
            },
        )
        assert res_learn.status_code == 200
        series_key = res_learn.json()["series_key"]

        # 2. GET /api/series-memory/{session_id}/exemplars
        res_exs = client.get(f"/api/series-memory/{session_id}/exemplars")
        assert res_exs.status_code == 200
        data_exs = res_exs.json()
        assert data_exs["status"] == "ok"
        assert len(data_exs["exemplars"]) == 1
        ex0 = data_exs["exemplars"][0]
        assert ex0["page_index"] == 0
        assert ex0["pinned"] is False
        assert ex0["image_url"] is not None

        # 3. Fetch exemplar image via image_url
        img_resp = client.get(ex0["image_url"])
        assert img_resp.status_code == 200
        assert "image" in img_resp.headers.get("content-type", "")

        # 4. Pin exemplar
        pin_resp = client.post(
            "/api/series-memory/pin-exemplar",
            json={"series_key": series_key, "page_index": 0, "pinned": True},
        )
        assert pin_resp.status_code == 200
        assert pin_resp.json()["pinned"] is True

        # Check it's pinned
        res_exs2 = client.get(f"/api/series-memory/{session_id}/exemplars")
        assert res_exs2.json()["exemplars"][0]["pinned"] is True

        # 5. Delete exemplar
        del_resp = client.delete(f"/api/series-memory/{series_key}/exemplar/0")
        assert del_resp.status_code == 200
        assert del_resp.json()["removed"] is True

        # Check it's gone
        res_exs3 = client.get(f"/api/series-memory/{session_id}/exemplars")
        assert len(res_exs3.json()["exemplars"]) == 0

