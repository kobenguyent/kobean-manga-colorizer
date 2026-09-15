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
