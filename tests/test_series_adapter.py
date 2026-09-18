"""
tests/test_series_adapter.py - Unit & Integration tests for Phase 3: Series Style LoRA & Residual Adapter.
"""

import json
import os
import shutil
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import torch
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from PIL import Image

import main
from colorizer_engine import MangaColorizerEngine
from main import SERIES_BANK, SESSIONS, app, colorizer_engine
from series_adapter import (
    ResidualBlock,
    SeriesAdapterTrainer,
    SeriesResidualAdapter,
    extract_synthetic_sketch,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_series_residual_adapter_architecture():
    """Verifies adapter model dimensions, parameter size, and zero-init identity behavior."""
    model = SeriesResidualAdapter(hidden_channels=32, num_blocks=2)

    # State dict size should be compact (~100-150KB)
    buf = bytearray()
    torch.save(model.state_dict(), "/tmp/test_adapter_size.pt")
    size = os.path.getsize("/tmp/test_adapter_size.pt")
    os.remove("/tmp/test_adapter_size.pt")
    assert size < 250_000, f"Adapter weights should be compact (<250KB), got {size} bytes"

    # Forward pass with zero-initialized weights should produce zero residual (pure identity)
    base_rgb = torch.rand(1, 3, 128, 128) * 2.0 - 1.0
    sketch_gray = torch.rand(1, 1, 128, 128)
    with torch.no_grad():
        out = model(base_rgb, sketch_gray)

    # Because out = clamp(base_rgb + 0.5 * residual, -1, 1) and residual is initially 0:
    diff = torch.abs(out - base_rgb).max().item()
    assert diff < 1e-6, f"Untrained adapter must be an exact identity function, max diff: {diff}"


def test_extract_synthetic_sketch():
    """Verifies synthetic line-art extraction produces valid 2D grayscale linework."""
    # Create synthetic color image: 128x128 with colorful circles/rectangles
    img_rgb = np.full((128, 128, 3), 255, dtype=np.uint8)
    # Draw dark and colored shapes
    img_rgb[20:60, 20:60] = [220, 50, 50]   # red block
    img_rgb[40:80, 70:110] = [50, 120, 240] # blue block

    sketch = extract_synthetic_sketch(img_rgb)
    assert sketch.shape == (128, 128)
    assert sketch.dtype == np.uint8
    # Linework should not be uniform
    assert sketch.min() < sketch.max()
    # Edges should be darker than white canvas
    assert sketch.min() < 100


def test_series_adapter_training_and_lifecycle(tmp_path):
    """Verifies SeriesAdapterTrainer training loop, checkpoint saving, loading, status, and deletion."""
    trainer = SeriesAdapterTrainer(tmp_path)

    # 1. Status before training
    status_init = trainer.get_status("test_series")
    assert status_init["status"] == "not_trained"
    assert status_init["series_key"] == "test_series"

    # 2. Create sample training images
    img1_path = str(tmp_path / "train_01.png")
    img2_path = str(tmp_path / "train_02.png")
    Image.new("RGB", (96, 96), color=(200, 100, 50)).save(img1_path)
    Image.new("RGB", (96, 96), color=(50, 180, 220)).save(img2_path)

    progress_records = []
    def on_progress(p):
        progress_records.append(p)

    # 3. Train for 8 steps
    meta = trainer.train_series_sync(
        series_key="test_series",
        image_paths=[img1_path, img2_path],
        total_steps=8,
        lr=1e-3,
        on_progress=on_progress,
    )

    assert meta["series_key"] == "test_series"
    assert meta["steps"] == 8
    assert len(progress_records) > 0
    assert progress_records[-1]["status"] == "completed"

    # 4. Check status after training
    status_trained = trainer.get_status("test_series")
    assert status_trained["status"] == "ready"
    assert status_trained["steps"] == 8
    assert status_trained["samples_count"] == 2
    assert "file_size" in status_trained

    # 5. Load adapter
    loaded_model = trainer.load_adapter("test_series", device="cpu")
    assert isinstance(loaded_model, SeriesResidualAdapter)

    # 6. Delete adapter
    deleted = trainer.delete_adapter("test_series")
    assert deleted is True
    assert trainer.get_status("test_series")["status"] == "not_trained"
    assert trainer.load_adapter("test_series") is None


def test_series_adapter_cancellation(tmp_path):
    """Verifies training cancellation stops the training loop early."""
    trainer = SeriesAdapterTrainer(tmp_path)
    img_path = str(tmp_path / "train_cancel.png")
    Image.new("RGB", (96, 96), color=(120, 120, 200)).save(img_path)

    def on_progress(p):
        if p["step"] >= 3:
            trainer.cancel_training("cancel_series")

    meta = trainer.train_series_sync(
        series_key="cancel_series",
        image_paths=[img_path],
        total_steps=50,
        lr=1e-3,
        on_progress=on_progress,
    )
    assert meta.get("cancelled") is True
    assert meta["step"] < 50


def test_series_adapter_endpoints(client, tmp_path):
    """Verifies FastAPI endpoints for adapter status, training trigger, and deletion."""
    session_id = "test_adapter_api_session"
    sess_dir = tmp_path / session_id
    color_dir = sess_dir / "colorized"
    color_dir.mkdir(parents=True, exist_ok=True)

    dummy_color = color_dir / "page_001.png"
    Image.new("RGB", (96, 96), color="orange").save(dummy_color)

    # Setup session
    SESSIONS[session_id] = {
        "session_id": session_id,
        "filename": "My Hero Academia - Vol 01.cbz",
        "detected_preset": "my_hero_academia",
        "preset_title": "My Hero Academia",
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

    # Learn page so Series Memory exemplar is registered
    client.post(
        "/api/series-memory/learn-page",
        json={"session_id": session_id, "page_index": 0, "exemplar": True},
    )

    # 1. GET status (should be not_trained)
    res_status = client.get(f"/api/series-memory/{session_id}/adapter-status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] in ["not_trained", "ready"]

    # 2. POST /train-adapter
    res_train = client.post(
        f"/api/series-memory/{session_id}/train-adapter",
        json={"steps": 5, "lr": 0.001},
    )
    assert res_train.status_code == 200
    train_data = res_train.json()
    assert train_data["status"] == "training_started"
    assert train_data["total_steps"] == 5

    # Wait briefly for background training to finish
    for _ in range(30):
        time.sleep(0.2)
        st = client.get(f"/api/series-memory/{session_id}/adapter-status").json()
        if st.get("status") == "ready":
            break

    # 3. Cancel endpoint
    res_cancel = client.post(f"/api/series-memory/{session_id}/cancel-training")
    assert res_cancel.status_code == 200

    # 4. DELETE /adapter
    res_del = client.delete(f"/api/series-memory/{session_id}/adapter")
    assert res_del.status_code == 200
    assert res_del.json()["status"] == "ok"


def test_ui_adapter_controls_and_scripts():
    """Verifies static/index.html and static/app.js have necessary elements, functions, and conform to rules."""
    html_content = Path("static/index.html").read_text(encoding="utf-8")
    assert 'id="series-adapter-badge"' in html_content
    assert 'id="adapter-control-card"' in html_content
    assert 'id="adapter-status-badge"' in html_content
    assert 'id="adapter-status-subtext"' in html_content
    assert 'id="btn-train-adapter"' in html_content
    assert 'id="btn-delete-adapter"' in html_content
    assert 'id="adapter-training-progress-container"' in html_content
    assert 'id="adapter-training-step-text"' in html_content
    assert 'id="adapter-training-loss-text"' in html_content
    assert 'id="adapter-training-progress-fill"' in html_content

    # app.js checks
    js_content = Path("static/app.js").read_text(encoding="utf-8")
    assert "fetchSeriesAdapterStatus" in js_content
    assert "triggerSeriesAdapterTraining" in js_content
    assert "deleteCurrentSeriesAdapter" in js_content
    assert "updateAdapterTrainingProgressUI" in js_content
    assert "window.fetchSeriesAdapterStatus" in js_content
    assert "window.triggerSeriesAdapterTraining" in js_content
    assert "window.deleteCurrentSeriesAdapter" in js_content
    assert "window.updateAdapterTrainingProgressUI" in js_content

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


def test_series_adapter_engine_integration(tmp_path):
    """Verifies that colorize_page accurately attaches trained adapter weights and sets adapter_used."""
    # 1. Train a dummy adapter under colorizer_engine.adapter_trainer
    series_key = "test_engine_series"
    img_path = str(tmp_path / "engine_train.png")
    Image.new("RGB", (96, 96), color=(180, 80, 40)).save(img_path)

    trainer = colorizer_engine.adapter_trainer
    trainer.train_series_sync(
        series_key=series_key,
        image_paths=[img_path],
        total_steps=5,
        lr=1e-3,
    )

    # 2. Run colorize_page on a grayscale sketch page
    sketch_path = str(tmp_path / "sketch.png")
    out_path = str(tmp_path / "colored_out.png")
    Image.new("RGB", (96, 96), color=(240, 240, 240)).save(sketch_path)

    # Inference with adapter enabled
    ret_with = colorizer_engine.colorize_page(
        image_path=sketch_path,
        output_path=out_path,
        model_provider="resnext_generator",
        series_key=series_key,
        use_series_adapter=True,
    )
    assert ret_with["status"] == "success"
    assert ret_with.get("adapter_used") is True
    assert Path(out_path).exists()

    # Inference with adapter explicitly disabled
    out_no_path = str(tmp_path / "colored_no_adapter.png")
    ret_without = colorizer_engine.colorize_page(
        image_path=sketch_path,
        output_path=out_no_path,
        model_provider="resnext_generator",
        series_key=series_key,
        use_series_adapter=False,
    )
    assert ret_without["status"] == "success"
    assert not ret_without.get("adapter_used")

    # Clean up adapter
    trainer.delete_adapter(series_key)

