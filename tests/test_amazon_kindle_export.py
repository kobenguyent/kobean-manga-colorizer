import os
import sys
import io
import struct
import zipfile
import requests
from pathlib import Path
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from file_processor import MangaFileProcessor

BASE_URL = "http://127.0.0.1:8000"


def test_pure_python_mobi_generator(tmp_path):
    """Verifies that MangaFileProcessor generates a compliant PalmDOC/MOBI e-book with all Amazon comic tags."""
    processor = MangaFileProcessor(str(tmp_path / "storage"))

    # Create two test images
    img1 = Image.new("RGB", (200, 300), color="crimson")
    img2 = Image.new("RGB", (200, 300), color="navy")
    b1, b2 = io.BytesIO(), io.BytesIO()
    img1.save(b1, format="JPEG")
    img2.save(b2, format="JPEG")

    images_data = [
        (b1.getvalue(), "Page 1 - Cover", "Volume 1"),
        (b2.getvalue(), "Page 2", None),
    ]

    out_mobi = str(tmp_path / "manga_test.mobi")
    result = processor.build_mobi_from_images(images_data, out_mobi, title="Naruto Shippuden", author="Masashi Kishimoto")
    assert result == out_mobi
    assert os.path.exists(out_mobi)
    file_size = os.path.getsize(out_mobi)
    assert file_size > 1000

    # Inspect Palm Database Header
    with open(out_mobi, "rb") as f:
        header = f.read(78)
        name, attr, ver, ctime, mtime, btime, modnum, app_info, sort_info, b_type, b_creator, seed, next_id, n_records = struct.unpack(
            ">32sHHIIIIII4s4sIIH", header
        )
        assert b_type == b"BOOK"
        assert b_creator == b"MOBI"
        assert n_records == 7  # rec0, text, img1, img2, FLIS, FCIS, EOF

        # Read record info headers
        rec_headers = [struct.unpack(">IB3s", f.read(8)) for _ in range(n_records)]
        f.read(2)  # padding

        # Verify Record 0
        rec0_offset = rec_headers[0][0]
        rec1_offset = rec_headers[1][0]
        f.seek(rec0_offset)
        rec0_data = f.read(rec1_offset - rec0_offset)

        # PalmDOC header in rec0
        comp, _, tlen, rcount, rsize, cpos = struct.unpack(">HHIHHI", rec0_data[:16])
        assert comp == 1  # uncompressed
        assert rcount == 1
        assert tlen > 0

        # MOBI header in rec0
        mobi_magic = rec0_data[16:20]
        assert mobi_magic == b"MOBI"
        hlen, mtype, enc, uid, file_ver = struct.unpack(">IIIII", rec0_data[20:40])
        assert hlen == 232
        assert mtype == 2  # Book
        assert enc == 65001  # UTF-8
        assert file_ver == 6

        # EXTH header in rec0
        exth_offset = 248
        exth_magic = rec0_data[exth_offset:exth_offset + 4]
        assert exth_magic == b"EXTH"
        exth_len, exth_count = struct.unpack(">II", rec0_data[exth_offset + 4:exth_offset + 12])
        assert exth_count >= 8

        # Parse EXTH tags
        exth_bytes = rec0_data[exth_offset + 12:exth_offset + exth_len]
        curr = 0
        tags = {}
        for _ in range(exth_count):
            if curr + 8 > len(exth_bytes):
                break
            tag_type, tag_len = struct.unpack(">II", exth_bytes[curr:curr + 8])
            data = exth_bytes[curr + 8:curr + tag_len]
            tags[tag_type] = data
            curr += tag_len

        assert tags[100] == b"Masashi Kishimoto"  # Author
        assert tags[503] == b"Naruto Shippuden"    # Title
        assert tags[121] == b"comic"               # Book type: comic
        assert tags[122] == b"true"                # Fixed-layout: true
        assert tags[126] == b"none"                # Orientation lock: none
        assert tags[127] == b"horizontal-rl"       # RTL Manga reading direction!
        assert tags[128] == b"pre-paginated"       # Rendition layout

        # Verify Record 1 (HTML text)
        rec2_offset = rec_headers[2][0]
        f.seek(rec1_offset)
        html_bytes = f.read(rec2_offset - rec1_offset).decode("utf-8")
        assert 'dir="rtl"' in html_bytes
        assert 'recindex="0001"' in html_bytes
        assert 'recindex="0002"' in html_bytes
        assert 'Volume 1' in html_bytes

        # Verify Record 2 (first image is JPEG)
        f.seek(rec2_offset)
        assert f.read(3) == b"\xff\xd8\xff"


def test_kindle_epub_fixed_layout_metadata(tmp_path):
    """Verifies that EPUB archives built by MangaFileProcessor contain full Amazon Kindle comic fixed-layout metadata."""
    processor = MangaFileProcessor(str(tmp_path / "storage"))
    session_id = "test_kindle_sess"
    sess_dir = tmp_path / "storage" / session_id
    orig_dir = sess_dir / "original"
    orig_dir.mkdir(parents=True)

    # Write a test image
    p1 = orig_dir / "p1.jpg"
    Image.new("RGB", (400, 600), "green").save(str(p1), "JPEG")

    pages_meta = [{
        "filename": "p1.jpg",
        "original_path": str(p1),
        "width": 400,
        "height": 600,
        "display_name": "Cover Page"
    }]

    out_epub = str(tmp_path / "manga.epub")
    processor.build_standalone_epub(pages_meta, session_id, out_epub, title="Kindle EPUB Comic")
    assert os.path.exists(out_epub)

    with zipfile.ZipFile(out_epub, "r") as zf:
        assert "OEBPS/content.opf" in zf.namelist()
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert '<meta name="book-type" content="comic"/>' in opf
        assert '<meta name="fixed-layout" content="true"/>' in opf
        assert '<meta name="zero-gutter" content="true"/>' in opf
        assert '<meta name="zero-margin" content="true"/>' in opf
        assert '<meta name="primary-writing-mode" content="horizontal-rl"/>' in opf
        assert '<meta property="rendition:layout">pre-paginated</meta>' in opf
        assert 'page-progression-direction="rtl"' in opf
        assert 'properties="cover-image"' in opf
        assert 'properties="rendition:layout-pre-paginated"' in opf


def ensure_test_doc():
    """Uploads a small test document to local server and returns session_id."""
    img = Image.new("RGB", (300, 400), "orange")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    resp = requests.post(f"{BASE_URL}/api/upload", files={"file": ("kindle_test_page.jpg", buf, "image/jpeg")})
    assert resp.status_code == 200
    return resp.json()["session_id"]


def test_single_document_mobi_export():
    """Tests POST /api/export/{session_id}?format=mobi and GET /api/download/{session_id}/{filename}."""
    session_id = ensure_test_doc()

    resp = requests.post(f"{BASE_URL}/api/export/{session_id}?format=mobi")
    assert resp.status_code == 200, f"Export failed: {resp.text}"
    data = resp.json()
    assert data["status"] == "success"
    assert data["format"] == "mobi"
    assert data["filename"].endswith(".mobi")
    assert f"/api/download/{session_id}/" in data["download_url"]

    # Download file and check MIME type and content
    dl_resp = requests.get(f"{BASE_URL}{data['download_url']}")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/x-mobipocket-ebook"
    assert len(dl_resp.content) > 500
    # PalmDOC/MOBI magic in first 78 bytes
    assert b"BOOK" in dl_resp.content[:78]
    assert b"MOBI" in dl_resp.content[:78]


def test_batch_mobi_export():
    """Tests POST /api/export/batch with format='mobi' packaging MOBI e-books into a zip."""
    sid1 = ensure_test_doc()
    sid2 = ensure_test_doc()

    resp = requests.post(f"{BASE_URL}/api/export/batch", json={
        "session_ids": [sid1, sid2],
        "format": "mobi"
    })
    assert resp.status_code == 200, f"Batch export failed: {resp.text}"
    data = resp.json()
    assert data["status"] == "success"
    assert "kindle" in data["filename"] or "mobi" in data["filename"]

    # Verify batch zip contents
    dl_resp = requests.get(f"{BASE_URL}{data['download_url']}")
    assert dl_resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(dl_resp.content))
    mobi_files = [f for f in zf.namelist() if f.endswith(".mobi")]
    assert len(mobi_files) == 2


def test_combined_mobi_export():
    """Tests POST /api/export/combined with format='mobi' in synchronous mode."""
    sid1 = ensure_test_doc()
    sid2 = ensure_test_doc()

    resp = requests.post(f"{BASE_URL}/api/export/combined", json={
        "session_ids": [sid1, sid2],
        "format": "mobi",
        "sync": True,
        "title": "Amazon Kindle Manga Collection"
    })
    assert resp.status_code == 200, f"Combined export failed: {resp.text}"
    data = resp.json()
    assert data["status"] == "success"
    assert data["filename"].endswith(".mobi")
    assert "/api/download/combined/" in data["download_url"]

    # Verify download and MIME type
    dl_resp = requests.get(f"{BASE_URL}{data['download_url']}")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/x-mobipocket-ebook"
    assert b"BOOK" in dl_resp.content[:78]
    assert b"MOBI" in dl_resp.content[:78]
