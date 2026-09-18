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
    exemplar = bank.get_exemplar_image("dr_slump", exclude_path=str(img2))
    assert exemplar == str(img1)

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
