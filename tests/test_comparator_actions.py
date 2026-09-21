from pathlib import Path

from bs4 import BeautifulSoup


def test_comparator_has_one_colorization_action():
    html = Path("static/index.html").read_text()
    controls = BeautifulSoup(html, "html.parser").select(".preview-controls-group button")
    actions = [button for button in controls if "colorize" in button.get_text().lower()]

    assert [button.get("onclick") for button in actions] == [
        "recolorizePage(currentPreviewPageIndex)"
    ]


def test_gallery_has_one_colorization_action():
    html = Path("static/index.html").read_text()
    gallery = BeautifulSoup(html, "html.parser").select_one(".gallery-header-bar")
    actions = [
        button.get("onclick")
        for button in gallery.select("button")
        if button.get("onclick") in {"startColorization()", "recolorizeSelected()"}
    ]

    assert actions == ["recolorizeSelected()"]


def test_comparator_header_chips_uncluttered():
    """Verify that preview-controls-group row is not overcrowded with chips and status badges are organized in comparator-meta-bar."""
    html = Path("static/index.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    # 1. Verify preview-controls-group has no status chips directly on its row
    preview_controls = soup.select_one(".preview-controls-group")
    assert preview_controls is not None
    assert preview_controls.select_one("#preview-quality-chip") is None
    assert preview_controls.select_one("#preview-exemplar-chip") is None
    assert preview_controls.select_one("#series-memory-preview-badge") is None

    # 2. Verify dedicated comparator-meta-bar exists with all metadata chips and learn page button
    meta_bar = soup.select_one("#comparator-meta-bar")
    assert meta_bar is not None
    assert meta_bar.select_one("#preview-quality-chip") is not None
    assert meta_bar.select_one("#preview-exemplar-chip") is not None
    assert meta_bar.select_one("#series-memory-preview-badge") is not None
    assert meta_bar.select_one("#btn-learn-page-memory") is not None

    # 3. Verify JavaScript synchronization functions
    js = Path("static/app.js").read_text(encoding="utf-8")
    assert "function updateComparatorMetaBar" in js
    assert "window.updateComparatorMetaBar = updateComparatorMetaBar" in js

