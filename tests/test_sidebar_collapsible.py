"""
Tests for Left Sidebar Collapsible & Expandable Cards Feature
Ensures index.html, styles.css, and app.js contain the required elements,
accessibility attributes, animations, and state persistence logic.
"""

from pathlib import Path


def test_sidebar_cards_markup():
    """Verify that all 4 left sidebar cards have collapsible structures and ARIA attributes."""
    html_path = Path("static/index.html")
    assert html_path.exists(), "index.html must exist"
    html = html_path.read_text(encoding="utf-8")

    expected_cards = [
        ("card-doc-queue", "header-doc-queue", "btn-collapse-doc-queue", "card-body-doc-queue"),
        ("config-card", "header-config", "btn-collapse-config", "card-body-config"),
        ("palette-card", "header-palette", "btn-collapse-palette", "card-body-palette"),
        ("sidebar-export-card", "header-export", "btn-collapse-export", "card-body-export"),
    ]

    for card_id, header_id, btn_id, body_id in expected_cards:
        assert f'id="{card_id}"' in html, f"Card '{card_id}' missing in index.html"
        assert f'id="{header_id}"' in html, f"Header '{header_id}' missing in index.html"
        assert f'id="{btn_id}"' in html, f"Collapse button '{btn_id}' missing in index.html"
        assert f'id="{body_id}"' in html, f"Collapsible body '{body_id}' missing in index.html"
        assert f'aria-controls="{body_id}"' in html, f"aria-controls for '{body_id}' missing"

    # Verify presence of collapsible classes and ARIA roles
    assert "card-collapsible-header" in html
    assert "card-collapsible-body" in html
    assert "card-collapsible-inner" in html
    assert "btn-card-collapse" in html
    assert 'aria-expanded="true"' in html
    assert 'role="button"' in html

    # Verify all 4 card header badges exist and use unified sidebar-card-badge
    for badge_id in [
        "doc-queue-badge",
        "config-card-summary-badge",
        "palette-badge-count",
        "export-badge-count",
    ]:
        assert f'id="{badge_id}"' in html, f"Badge '{badge_id}' missing in index.html"
    assert html.count("sidebar-card-badge") >= 4, (
        "All 4 card header badges must use sidebar-card-badge"
    )


def test_sidebar_cards_styling():
    """Verify CSS styling for smooth GPU-accelerated CSS Grid row transitions and rotating chevrons."""
    css_path = Path("static/styles.css")
    assert css_path.exists(), "styles.css must exist"
    css = css_path.read_text(encoding="utf-8")

    # Verify key selectors, unified badge component, and animation curve
    assert ".card-collapsible-header" in css
    assert ".btn-card-collapse" in css
    assert ".sidebar-card-badge" in css
    assert ".card-collapsible-body" in css
    assert ".card-collapsible-inner" in css
    assert ".card.collapsed" in css
    assert "grid-template-rows: 1fr" in css
    assert "grid-template-rows: 0fr" in css
    assert "cubic-bezier(0.16, 1, 0.3, 1)" in css
    assert "transform: rotate(-90deg)" in css
    assert "prefers-reduced-motion" in css


def test_sidebar_cards_javascript_controller():
    """Verify JavaScript handles event delegation, animation classes, and localStorage persistence."""
    js_path = Path("static/app.js")
    assert js_path.exists(), "app.js must exist"
    js = js_path.read_text(encoding="utf-8")

    assert "initSidebarCollapsibleCards" in js
    assert "toggleSidebarCard" in js
    assert "loadSidebarCollapsedStates" in js
    assert "saveSidebarCollapsedState" in js
    assert "kobean_sidebar_cards_collapsed" in js
    assert "updateSidebarConfigSummary" in js
    assert "is-animating" in js
    assert "initSidebarCollapsibleCards()" in js
