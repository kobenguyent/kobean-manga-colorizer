from pathlib import Path

from bs4 import BeautifulSoup


def test_app_shell_uses_the_kobean_brand_mark_and_favicon():
    html = Path("static/index.html").read_text()
    page = BeautifulSoup(html, "html.parser")

    assert page.title.string == "Kobean Manga Colorizer"
    assert page.select_one('.logo-icon img[src="brand-icon.png"]')
    assert page.select_one('link[rel="icon"][href="favicon.png"]')
    assert Path("static/brand-icon.png").is_file()
