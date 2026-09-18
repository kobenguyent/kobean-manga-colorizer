"""
tests/test_active_learning.py - Unit & Integration tests for Phase 4: Automated Confidence-Gated Active Learning & Self-Refinement.
"""

import json
import os
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from PIL import Image

import main
from colorizer_engine import MangaColorizerEngine
from main import SERIES_BANK, SESSIONS, app, colorizer_engine
from quality_scorer import (
    calculate_quality_score,
    compute_color_richness,
    compute_linework_integrity,
    compute_white_purity,
)
from series_memory import SeriesMemoryBank, derive_series_key


@pytest.fixture
def client():
    return TestClient(app)


def test_quality_scorer_dimensions_and_metrics():
    """Verifies quality scoring algorithms across linework integrity, white purity, and richness."""
    # 1. Base manga sketch simulation with margin, panel, speech bubble, and character line art
    orig = np.full((300, 300, 3), 255, dtype=np.uint8)
    cv2.rectangle(orig, (30, 30), (270, 270), (0, 0, 0), 3) # panel border
    cv2.circle(orig, (80, 80), 28, (0, 0, 0), 2)             # speech bubble
    cv2.putText(orig, "HELLO", (65, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1) # text
    cv2.rectangle(orig, (120, 100), (240, 240), (0, 0, 0), 2) # character box

    # 2. High-quality colored page: character has vibrant multi-tone color, lines and bubble stay pristine
    colored_high = orig.copy()
    colored_high[122:170, 122:238] = [235, 180, 80]  # vibrant hair
    colored_high[170:238, 122:238] = [240, 195, 170] # vibrant skin

    score_high = calculate_quality_score(orig, colored_high, auto_harvest_threshold=0.82)
    assert score_high["overall_score"] >= 0.82
    assert score_high["grade"] == "high"
    assert score_high["auto_learn_eligible"] is True
    assert score_high["metrics"]["linework_integrity"] >= 0.90
    assert score_high["metrics"]["white_purity"] >= 0.90
    assert score_high["metrics"]["color_richness"] >= 0.65

    # 3. Bleeding & dirty speech bubble page: colors spill over bubble and ink
    colored_poor = colored_high.copy()
    colored_poor[60:100, 60:100] = [180, 140, 100] # stained speech bubble
    colored_poor[30:270, 30:33] = [200, 100, 50]   # stained black ink line
    colored_poor[:15, :] = [210, 150, 120]         # dirty outer margin

    score_poor = calculate_quality_score(orig, colored_poor, auto_harvest_threshold=0.82)
    assert score_poor["overall_score"] < score_high["overall_score"]
    assert score_poor["auto_learn_eligible"] is False
    assert score_poor["metrics"]["white_purity"] < score_high["metrics"]["white_purity"]

    # 4. Desaturated / flat grayscale page: fails color richness check
    score_gray = calculate_quality_score(orig, orig, auto_harvest_threshold=0.82)
    assert score_gray["metrics"]["color_richness"] <= 0.30
    assert score_gray["grade"] == "review_suggested"
    assert score_gray["auto_learn_eligible"] is False

    # 5. Author pre-colored cover spread: returns 1.0 ground-truth score
    score_author = calculate_quality_score(orig, colored_high, is_skipped_colored=True)
    assert score_author["overall_score"] == 1.0
    assert score_author["grade"] == "high"
    assert score_author["auto_learn_eligible"] is True


def test_series_memory_auto_harvest_and_refine_settings(tmp_path):
    """Verifies SeriesMemoryBank confidence-gated auto-harvesting and auto-refinement triggers."""
    store_file = tmp_path / "test_memory.json"
    bank = SeriesMemoryBank(store_file)

    img_path = str(tmp_path / "page_high.png")
    Image.new("RGB", (64, 64), color=(220, 140, 80)).save(img_path)

    # 1. Page with high confidence score (eligible)
    q_high = {
        "overall_score": 0.92,
        "grade": "high",
        "auto_learn_eligible": True,
        "metrics": {"linework_integrity": 0.95, "white_purity": 0.95, "color_richness": 0.85},
    }
    mem, should_refine = bank.record_auto_harvest(
        series_key="dragon_ball",
        title="Dragon Ball",
        session_id="sess_1",
        page_index=0,
        approved_image_path=img_path,
        quality_score=q_high,
    )
    assert mem.auto_learned_count == 1
    assert mem.unrefined_pages_count == 1
    assert len(mem.exemplar_pages) == 1
    assert should_refine is False  # default interval is 5, count is 1

    # 2. Page with poor confidence score (ineligible)
    q_low = {
        "overall_score": 0.55,
        "grade": "review_suggested",
        "auto_learn_eligible": False,
        "metrics": {"linework_integrity": 0.6, "white_purity": 0.5, "color_richness": 0.5},
    }
    mem2, should_refine_low = bank.record_auto_harvest(
        series_key="dragon_ball",
        title="Dragon Ball",
        session_id="sess_1",
        page_index=1,
        approved_image_path=img_path,
        quality_score=q_low,
    )
    # Exemplar pages should NOT have increased
    assert mem2.auto_learned_count == 1
    assert len(mem2.exemplar_pages) == 1
    assert should_refine_low is False

    # 3. Update auto-refine settings
    bank.update_auto_refine_settings("dragon_ball", enabled=True, interval=2, threshold=0.85)
    mem_updated = bank.get_memory("dragon_ball")
    assert mem_updated.auto_refine_interval == 2
    assert mem_updated.auto_harvest_threshold == 0.85

    # 4. Harvest second high-confidence page -> should trigger auto-refine (count >= interval)
    img2_path = str(tmp_path / "page_high_2.png")
    Image.new("RGB", (64, 64), color=(80, 150, 220)).save(img2_path)
    mem3, should_refine_now = bank.record_auto_harvest(
        series_key="dragon_ball",
        title="Dragon Ball",
        session_id="sess_1",
        page_index=2,
        approved_image_path=img2_path,
        quality_score=q_high,
    )
    assert mem3.unrefined_pages_count == 2
    assert should_refine_now is True

    # 5. Reset unrefined counter
    bank.reset_unrefined_counter("dragon_ball")
    assert bank.get_memory("dragon_ball").unrefined_pages_count == 0


def test_colorizer_engine_returns_quality_score(tmp_path):
    """Verifies that colorizer_engine.colorize_page automatically calculates and returns quality_score."""
    sketch_path = str(tmp_path / "engine_sketch.png")
    out_path = str(tmp_path / "engine_out.png")
    Image.new("RGB", (96, 96), color=(245, 245, 245)).save(sketch_path)

    res = colorizer_engine.colorize_page(
        image_path=sketch_path,
        output_path=out_path,
        model_provider="resnext_generator",
    )
    assert res["status"] == "success"
    assert "quality_score" in res
    q = res["quality_score"]
    assert "overall_score" in q
    assert "grade" in q
    assert "metrics" in q
    assert "auto_learn_eligible" in q


def test_active_learning_endpoints(client, tmp_path):
    """Verifies REST endpoints for page quality score, auto-refine settings, and auto-refine trigger."""
    session_id = "test_phase4_api_session"
    sess_dir = tmp_path / session_id
    color_dir = sess_dir / "colorized"
    color_dir.mkdir(parents=True, exist_ok=True)

    dummy_orig = sess_dir / "page_orig_001.png"
    dummy_color = color_dir / "page_001.png"
    Image.new("RGB", (96, 96), color=(240, 240, 240)).save(dummy_orig)
    Image.new("RGB", (96, 96), color=(220, 100, 60)).save(dummy_color)

    with patch("main.STORAGE_DIR", tmp_path):
        # Setup session
        SESSIONS[session_id] = {
            "session_id": session_id,
            "filename": "One Piece - Vol 105.cbz",
            "detected_preset": "one_piece",
            "preset_title": "One Piece",
            "total_pages": 1,
            "processed_count": 1,
            "status": "completed",
            "pages": [
                {
                    "filename": "page_001.png",
                    "path": str(dummy_color),
                    "original_path": str(dummy_orig),
                    "status": "colorized",
                    "colorized_url": f"/api/session/{session_id}/image/colorized/page_001.png",
                }
            ],
        }

        # 1. GET /api/session/{session_id}/page/{page_index}/quality
        res_q = client.get(f"/api/session/{session_id}/page/0/quality")
        assert res_q.status_code == 200
        q_data = res_q.json()
        assert q_data["status"] == "ok"
        assert "quality_score" in q_data
        assert "overall_score" in q_data["quality_score"]

        # 2. GET /api/series-memory/{session_id}/auto-refine
        res_ar = client.get(f"/api/series-memory/{session_id}/auto-refine")
        assert res_ar.status_code == 200
        ar_data = res_ar.json()
        assert ar_data["status"] == "ok"
        assert "auto_refine_enabled" in ar_data
        assert "auto_harvest_threshold" in ar_data
        assert "auto_refine_interval" in ar_data

        # 3. POST /api/series-memory/{session_id}/auto-refine (update settings)
        res_update = client.post(
            f"/api/series-memory/{session_id}/auto-refine",
            json={"enabled": True, "threshold": 0.85, "interval": 4},
        )
        assert res_update.status_code == 200
        up_data = res_update.json()
        assert up_data["auto_harvest_threshold"] == 0.85
        assert up_data["auto_refine_interval"] == 4

        # 4. POST /api/series-memory/{session_id}/trigger-auto-refine
        # Ensure at least 1 exemplar is in series memory
        res_learn = client.post(
            "/api/series-memory/learn-page",
            json={"session_id": session_id, "page_index": 0, "exemplar": True},
        )
        assert res_learn.status_code == 200
        res_trig = client.post(f"/api/series-memory/{session_id}/trigger-auto-refine")
        assert res_trig.status_code == 200
        assert res_trig.json()["status"] == "auto_refine_started"


def test_ui_quality_chip_and_auto_refine_controls():
    """Verifies static/index.html and static/app.js have necessary elements, functions, and conform to rules."""
    html_content = Path("static/index.html").read_text(encoding="utf-8")
    assert 'id="preview-quality-chip"' in html_content
    assert 'id="preview-quality-icon"' in html_content
    assert 'id="preview-quality-label"' in html_content
    assert 'id="adapter-auto-refine-row"' in html_content
    assert 'id="chk-auto-refine-adapter"' in html_content
    assert 'id="auto-refine-counter-text"' in html_content
    assert 'id="auto-harvest-threshold-badge"' in html_content

    # app.js checks
    js_content = Path("static/app.js").read_text(encoding="utf-8")
    assert "updateQualityPreviewChip" in js_content
    assert "fetchSeriesAutoRefineStatus" in js_content
    assert "toggleAutoRefineAdapter" in js_content
    assert "window.updateQualityPreviewChip" in js_content
    assert "window.fetchSeriesAutoRefineStatus" in js_content
    assert "window.toggleAutoRefineAdapter" in js_content

    # Strict rule: NO native confirm() in app.js
    assert "confirm(`" not in js_content
    assert 'confirm("' not in js_content

    # Strict rule: comparator button text constraint
    soup = BeautifulSoup(html_content, "html.parser")
    controls = soup.select(".preview-controls-group button")
    actions = [button for button in controls if "colorize" in button.get_text().lower()]
    assert [button.get("onclick") for button in actions] == [
        "recolorizePage(currentPreviewPageIndex)"
    ]
