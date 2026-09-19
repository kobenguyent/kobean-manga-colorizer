"""Automated tests for Kobean Manga Colorizer Multi-Theme Studio System.

Validates:
1. HTML markup: Anti-FOUC bootstrap script, meta tags, and header Theme Switcher container/dropdown.
2. CSS token architecture: 7 complete theme profiles, semantic custom properties, light mode overrides, and glassmorphic styling.
3. JavaScript controller: THEMES metadata registry, init, apply, select, dropdown toggle, persistence, and accessibility.
"""

from pathlib import Path


def test_theme_switcher_html_markup():
    index_html = Path("static/index.html").read_text(encoding="utf-8")

    # 1. Anti-FOUC bootstrap in <head>
    assert "Instant Anti-FOUC Theme Bootstrap" in index_html
    assert "localStorage.getItem('kobean_theme')" in index_html
    assert "document.documentElement.setAttribute('data-theme'" in index_html

    # 2. Dynamic mobile status bar meta tag
    assert 'id="meta-theme-color"' in index_html
    assert 'name="theme-color"' in index_html

    # 3. Theme switcher container and trigger button in header
    assert 'id="theme-switcher-container"' in index_html
    assert 'id="btn-theme-toggle"' in index_html
    assert 'onclick="toggleThemeDropdown(event)"' in index_html
    assert 'aria-haspopup="true"' in index_html
    assert 'aria-expanded="false"' in index_html
    assert 'id="theme-btn-label"' in index_html
    assert 'id="theme-btn-icon"' in index_html

    # 4. Dropdown menu container
    assert 'id="theme-dropdown-menu"' in index_html
    assert 'role="menu"' in index_html
    assert 'id="theme-menu-list"' in index_html
    assert 'id="theme-menu-count"' in index_html


def test_theme_switcher_css_tokens_and_styles():
    styles_css = Path("static/styles.css").read_text(encoding="utf-8")

    # 1. Verify all 7 theme profiles exist
    themes = [
        "cyber-neon",
        "manga-ink",
        "shonen-sunrise",
        "sakura-twilight",
        "emerald-alchemist",
        "nord-frost",
        "paper-studio",
    ]
    for theme_id in themes:
        assert f'[data-theme="{theme_id}"]' in styles_css, (
            f"Missing CSS scope for theme: {theme_id}"
        )

    # 2. Verify essential tokens in flagship cyber-neon
    assert '--theme-id: "cyber-neon"' in styles_css
    assert "--bg-dark: #090d16" in styles_css
    assert "--glow-1-bg: #8b5cf6" in styles_css
    assert "--glow-2-bg: #06b6d4" in styles_css

    # 3. Verify monochrome Manga Ink
    assert '--theme-id: "manga-ink"' in styles_css
    assert "--bg-dark: #0a0b0e" in styles_css
    assert "--accent-primary: #e2e8f0" in styles_css

    # 4. Verify Shonen Sunrise
    assert '--theme-id: "shonen-sunrise"' in styles_css
    assert "--accent-primary: #f59e0b" in styles_css
    assert "--glow-1-bg: #ef4444" in styles_css

    # 5. Verify Sakura Twilight
    assert '--theme-id: "sakura-twilight"' in styles_css
    assert "--accent-primary: #f472b6" in styles_css
    assert "--glow-1-bg: #c084fc" in styles_css

    # 6. Verify Emerald Alchemist
    assert '--theme-id: "emerald-alchemist"' in styles_css
    assert "--accent-primary: #10b981" in styles_css
    assert "--glow-1-bg: #10b981" in styles_css

    # 7. Verify Nord Frost
    assert '--theme-id: "nord-frost"' in styles_css
    assert "--accent-primary: #38bdf8" in styles_css
    assert "--glow-1-bg: #6366f1" in styles_css

    # 8. Verify Paper Studio light mode & overrides
    assert '--theme-id: "paper-studio"' in styles_css
    assert "--bg-dark: #f6f5f0" in styles_css
    assert "--text-primary: #1e293b" in styles_css
    assert '[data-theme="paper-studio"] .history-modal-dialog' in styles_css
    assert '[data-theme="paper-studio"] .modal-overlay' in styles_css

    # 9. Verify Theme Switcher UI classes & micro-interactions
    assert ".theme-switcher-container" in styles_css
    assert ".theme-toggle-btn" in styles_css
    assert ".theme-dropdown-menu" in styles_css
    assert "@keyframes themeMenuEnter" in styles_css
    assert ".theme-option-item" in styles_css
    assert ".theme-option-item.active" in styles_css
    assert ".theme-swatch-strip" in styles_css
    assert ".theme-swatch-dot" in styles_css
    assert ".theme-check-icon" in styles_css


def test_theme_switcher_javascript_controller():
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    # 1. THEMES registry object
    assert "const THEMES = [" in app_js
    themes = [
        "cyber-neon",
        "manga-ink",
        "shonen-sunrise",
        "sakura-twilight",
        "emerald-alchemist",
        "nord-frost",
        "paper-studio",
    ]
    for theme_id in themes:
        assert f'id: "{theme_id}"' in app_js, f"Missing JS theme entry: {theme_id}"

    # 2. Lifecycle and controller functions
    assert "function initThemeSystem()" in app_js
    assert "function renderThemeDropdownMenu()" in app_js
    assert "function applyTheme(" in app_js
    assert "function selectTheme(" in app_js
    assert "function toggleThemeDropdown(" in app_js
    assert "function openThemeDropdown()" in app_js
    assert "function closeThemeDropdown()" in app_js
    assert "function handleThemeOutsideClick(" in app_js
    assert "function handleThemeKeydown(" in app_js

    # 3. Persistence and attribute synchronization
    assert 'localStorage.getItem("kobean_theme")' in app_js
    assert 'localStorage.setItem("kobean_theme"' in app_js
    assert 'document.documentElement.setAttribute("data-theme"' in app_js
    assert 'metaTheme.setAttribute("content", theme.metaColor)' in app_js

    # 4. DOMContentLoaded initialization
    assert "initThemeSystem();" in app_js

    # 5. Window exports
    assert "window.THEMES = THEMES;" in app_js
    assert "window.initThemeSystem = initThemeSystem;" in app_js
    assert "window.applyTheme = applyTheme;" in app_js
    assert "window.selectTheme = selectTheme;" in app_js
    assert "window.toggleThemeDropdown = toggleThemeDropdown;" in app_js
    assert "window.closeThemeDropdown = closeThemeDropdown;" in app_js
