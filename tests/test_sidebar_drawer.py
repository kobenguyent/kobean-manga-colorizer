"""Automated tests for the Sidebar Drawer Collapse & Expand system.

Validates:
1. HTML markup for the floating edge button with clean '>' chevron icon and the sidebar collapse button with '<' chevron icon.
2. CSS styling for grid-template-columns transitions, off-screen translation, and glassmorphic edge dock button.
3. JavaScript controller functions, keyboard shortcut (Cmd+B/Ctrl+B), localStorage persistence, and lifecycle synchronization.
"""

from pathlib import Path


def test_sidebar_drawer_html_markup():
    index_html = Path("static/index.html").read_text(encoding="utf-8")

    # 1. Floating edge expand button with clean '>' chevron icon
    assert 'id="btn-sidebar-edge-expand"' in index_html
    assert (
        'class="sidebar-edge-tab hidden"' in index_html or 'class="sidebar-edge-tab' in index_html
    )
    assert 'onclick="toggleSidebarDrawer(false)"' in index_html
    assert "ri-arrow-right-s-line" in index_html
    # Ensure confusing count badge is not present on the edge button
    assert 'id="edge-tab-badge-count"' not in index_html

    # 2. Sidebar collapse button with '<' chevron icon and clean button layout
    assert 'id="app-sidebar"' in index_html
    assert 'id="btn-sidebar-collapse"' in index_html
    assert 'onclick="toggleSidebarDrawer(true)"' in index_html
    assert "ri-arrow-left-s-line" in index_html
    assert "Collapse Sidebar" in index_html
    # Ensure old "SIDEBAR" header text and separate "Hide" button are removed
    assert 'class="sidebar-top-bar"' not in index_html
    assert 'class="sidebar-top-label"' not in index_html


def test_sidebar_drawer_css_styling():
    styles_css = Path("static/styles.css").read_text(encoding="utf-8")

    # 1. Dashboard grid transitions & collapsed state
    assert ".dashboard-grid.sidebar-collapsed" in styles_css
    assert "grid-template-columns: 0px minmax(0, 1fr)" in styles_css
    assert "transition: grid-template-columns" in styles_css

    # 2. Sidebar off-screen slide & hidden state
    assert ".dashboard-grid.sidebar-collapsed .sidebar" in styles_css
    assert "transform: translateX(calc(-100% - 2.5rem))" in styles_css
    assert "visibility: hidden" in styles_css

    # 3. Sidebar collapse button styling
    assert ".btn-sidebar-collapse" in styles_css
    assert ".collapse-arrow-icon" in styles_css
    assert ".collapse-shortcut-badge" in styles_css

    # 4. Floating edge tab styling
    assert ".sidebar-edge-tab" in styles_css
    assert "position: fixed" in styles_css
    assert "left: 0" in styles_css
    assert ".edge-tab-icon" in styles_css


def test_sidebar_drawer_javascript_controller():
    app_js = Path("static/app.js").read_text(encoding="utf-8")

    # 1. Storage key & state helpers
    assert 'SIDEBAR_DRAWER_STORAGE_KEY = "kobean_sidebar_drawer_collapsed"' in app_js
    assert "function isSidebarDrawerCollapsed()" in app_js
    assert 'dashboard.classList.contains("sidebar-collapsed")' in app_js

    # 2. Toggle controller
    assert "function toggleSidebarDrawer(forceCollapsed)" in app_js
    assert 'dashboard.classList.add("sidebar-collapsed")' in app_js
    assert 'dashboard.classList.remove("sidebar-collapsed")' in app_js
    assert 'edgeBtn.classList.remove("hidden")' in app_js
    assert 'edgeBtn.classList.add("hidden")' in app_js
    assert "localStorage.setItem(SIDEBAR_DRAWER_STORAGE_KEY" in app_js

    # 3. Initialization & keyboard shortcut
    assert "function initSidebarDrawer()" in app_js
    assert "initSidebarDrawer();" in app_js
    assert (
        'e.key.toLowerCase() === "b"' in app_js
        or 'e.key === "b"' in app_js
        or 'e.key === "B"' in app_js
    )

    # 4. Lifecycle integration (renderDashboard, resetUpload)
    assert "if (isSidebarDrawerCollapsed())" in app_js
