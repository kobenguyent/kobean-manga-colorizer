"""Automated tests for the Interactive Before / After Comparator Navigation system.

Validates:
1. HTML markup for the left thumbnail panel, toggle button, and editable page counter input.
2. CSS styling for flex layout, thumbnails, active states, counter input, error shake, and fullscreen mode.
3. JavaScript controller functions, keyboard navigation, input validation, and lifecycle synchronization.
"""

from pathlib import Path


def test_comparator_navigation_html_markup():
    index_html = Path("static/index.html").read_text(encoding="utf-8")

    # 1. Left thumbnail toggle button in header
    assert 'id="btn-toggle-comparator-thumbs"' in index_html
    assert 'onclick="toggleComparatorThumbPanel()"' in index_html
    assert "ri-side-bar-line" in index_html

    # 2. Editable page counter in header
    assert 'id="comparator-page-counter"' in index_html
    assert 'id="comparator-page-input"' in index_html
    assert 'id="comparator-page-total"' in index_html
    assert 'class="page-counter-box"' in index_html
    assert 'class="page-counter-sep"' in index_html
    assert 'inputmode="numeric"' in index_html

    # 3. Comparator workspace wrapping navigation panel & slider
    assert 'id="comparator-workspace"' in index_html
    assert 'class="comparator-workspace"' in index_html
    assert 'id="comparator-nav-panel"' in index_html
    assert 'class="comparator-nav-panel"' in index_html
    assert 'id="comparator-nav-list"' in index_html
    assert 'id="comparator-nav-count"' in index_html


def test_comparator_navigation_css_styling():
    styles_css = Path("static/styles.css").read_text(encoding="utf-8")

    # 1. Comparator workspace flex layout
    assert ".comparator-workspace" in styles_css
    assert "display: flex" in styles_css

    # 2. Left thumbnail navigation panel & collapsed state
    assert ".comparator-nav-panel" in styles_css
    assert ".comparator-nav-panel.collapsed" in styles_css
    assert "width: 0 !important" in styles_css

    # 3. Thumbnail items, badges, and active state
    assert ".comparator-nav-list" in styles_css
    assert ".comparator-thumb-item" in styles_css
    assert ".comp-thumb-badge" in styles_css
    assert ".comparator-thumb-item.active" in styles_css
    assert "border-color: var(--accent-cyan)" in styles_css

    # 4. Page counter input & error shake animation
    assert ".comparator-page-counter" in styles_css
    assert ".page-counter-box" in styles_css
    assert ".comparator-page-input" in styles_css
    assert ".comparator-page-input.input-error" in styles_css
    assert "@keyframes compInputShake" in styles_css

    # 5. Fullscreen layout support
    assert "#split-preview-card.is-fullscreen .comparator-workspace" in styles_css
    assert "#split-preview-card.is-fullscreen .comparator-nav-panel" in styles_css


def test_comparator_navigation_javascript_controller():
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    # 1. Page counter input initialization & handlers
    assert "function initComparatorPageCounter()" in app_js
    assert "function commitPageCounterJump()" in app_js
    assert "function revertPageCounterInput()" in app_js
    assert "function updateComparatorPageCounter(pageIdx, totalPages)" in app_js
    assert "initComparatorPageCounter();" in app_js

    # 2. Thumbnail panel rendering & synchronization
    assert "function renderComparatorNavPanel()" in app_js
    assert "function updateComparatorNavActive(pageIdx)" in app_js
    assert "function toggleComparatorThumbPanel(forceState)" in app_js
    assert 'localStorage.setItem("kobean_comparator_nav_collapsed"' in app_js

    # 3. Lifecycle integration in openSplitPreview, renderDashboard, recolorizePage
    assert "updateComparatorPageCounter(pageIdx, totalPages);" in app_js
    assert "updateComparatorNavActive(pageIdx);" in app_js
    assert "renderComparatorNavPanel();" in app_js
    assert "comp-thumb-img-${pageIdx}" in app_js

    # 4. Keyboard shortcuts for toggle
    assert 'e.key === "t" || e.key === "T"' in app_js
    assert "toggleComparatorThumbPanel();" in app_js
