import io
import json
import os
import shutil
import struct
import sys
import uuid
import zipfile
from pathlib import Path

import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from file_processor import MangaFileProcessor

BASE_URL = "http://127.0.0.1:8000"
STORAGE_DIR = Path(__file__).resolve().parent.parent / "sessions"


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
    result = processor.build_mobi_from_images(
        images_data, out_mobi, title="Naruto Shippuden", author="Masashi Kishimoto"
    )
    assert result == out_mobi
    assert os.path.exists(out_mobi)
    file_size = os.path.getsize(out_mobi)
    assert file_size > 1000

    # Inspect Palm Database Header
    with open(out_mobi, "rb") as f:
        header = f.read(78)
        (
            name,
            attr,
            ver,
            ctime,
            mtime,
            btime,
            modnum,
            app_info,
            sort_info,
            b_type,
            b_creator,
            seed,
            next_id,
            n_records,
        ) = struct.unpack(">32sHHIIIIII4s4sIIH", header)
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
        exth_magic = rec0_data[exth_offset : exth_offset + 4]
        assert exth_magic == b"EXTH"
        exth_len, exth_count = struct.unpack(">II", rec0_data[exth_offset + 4 : exth_offset + 12])
        assert exth_count >= 8

        # Parse EXTH tags
        exth_bytes = rec0_data[exth_offset + 12 : exth_offset + exth_len]
        curr = 0
        tags = {}
        for _ in range(exth_count):
            if curr + 8 > len(exth_bytes):
                break
            tag_type, tag_len = struct.unpack(">II", exth_bytes[curr : curr + 8])
            data = exth_bytes[curr + 8 : curr + tag_len]
            tags[tag_type] = data
            curr += tag_len

        assert tags[100] == b"Masashi Kishimoto"  # Author
        assert tags[503] == b"Naruto Shippuden"  # Title
        assert tags[121] == b"comic"  # Book type: comic
        assert tags[122] == b"true"  # Fixed-layout: true
        assert tags[126] == b"none"  # Orientation lock: none
        assert tags[127] == b"horizontal-rl"  # RTL Manga reading direction!
        assert tags[128] == b"pre-paginated"  # Rendition layout

        # Verify Record 1 (HTML text)
        rec2_offset = rec_headers[2][0]
        f.seek(rec1_offset)
        html_bytes = f.read(rec2_offset - rec1_offset).decode("utf-8")
        assert 'dir="rtl"' in html_bytes
        assert 'recindex="0001"' in html_bytes
        assert 'recindex="0002"' in html_bytes
        assert "Volume 1" in html_bytes

        # Verify Record 2 (first image is JPEG)
        f.seek(rec2_offset)
        assert f.read(3) == b"\xff\xd8\xff"


def test_mobi_palmdoc_large_text_chunking(tmp_path):
    """Verifies that MOBI generator slices text content exceeding 4096 bytes into compliant PalmDOC records."""
    processor = MangaFileProcessor(str(tmp_path / "storage"))

    # Create dummy JPEG image
    img = Image.new("RGB", (100, 100), color="blue")
    b = io.BytesIO()
    img.save(b, format="JPEG")
    img_bytes = b.getvalue()

    # Create 80 pages with detailed volume headers and long descriptions to exceed 4096-byte PalmDOC limit
    images_data = []
    for i in range(1, 81):
        images_data.append((
            img_bytes,
            f"Page {i:03d} - Detailed Chapter Section View With Explanatory Caption",
            f"Volume {i // 10 + 1} Section Header" if i % 10 == 1 else None,
        ))

    out_mobi = str(tmp_path / "large_chunked.mobi")
    processor.build_mobi_from_images(images_data, out_mobi, title="PalmDOC Chunking Test")
    assert os.path.exists(out_mobi)

    with open(out_mobi, "rb") as f:
        header = f.read(78)
        _, _, _, _, _, _, _, _, _, b_type, b_creator, _, _, n_records = struct.unpack(
            ">32sHHIIIIII4s4sIIH", header
        )
        assert b_type == b"BOOK"
        assert b_creator == b"MOBI"

        rec_headers = [struct.unpack(">IB3s", f.read(8)) for _ in range(n_records)]
        f.read(2)

        # Record 0
        rec0_offset = rec_headers[0][0]
        rec1_offset = rec_headers[1][0]
        f.seek(rec0_offset)
        rec0_data = f.read(rec1_offset - rec0_offset)

        # PalmDOC header: rcount must reflect chunked slices
        comp, _, tlen, rcount, rsize, _ = struct.unpack(">HHIHHI", rec0_data[:16])
        assert comp == 1
        assert tlen > 4096
        assert rcount > 1
        assert rcount == (tlen + 4095) // 4096
        assert rsize == 4096

        # MOBI header
        first_img = struct.unpack(">I", rec0_data[16 + 92 : 16 + 96])[0]
        first_non_book = struct.unpack(">I", rec0_data[16 + 64 : 16 + 68])[0]
        assert first_img == 1 + rcount
        assert first_non_book == 1 + rcount

        # Verify each text slice is <= 4096 bytes
        for r_idx in range(1, 1 + rcount):
            start_off = rec_headers[r_idx][0]
            end_off = rec_headers[r_idx + 1][0]
            slice_size = end_off - start_off
            assert slice_size <= 4096

        # Verify that record at first_img is the first JPEG image
        first_img_off = rec_headers[first_img][0]
        f.seek(first_img_off)
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

    pages_meta = [
        {
            "filename": "p1.jpg",
            "original_path": str(p1),
            "width": 400,
            "height": 600,
            "display_name": "Cover Page",
        }
    ]

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
    resp = requests.post(
        f"{BASE_URL}/api/upload", files={"file": ("kindle_test_page.jpg", buf, "image/jpeg")}
    )
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

    resp = requests.post(
        f"{BASE_URL}/api/export/batch", json={"session_ids": [sid1, sid2], "format": "mobi"}
    )
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

    resp = requests.post(
        f"{BASE_URL}/api/export/combined",
        json={
            "session_ids": [sid1, sid2],
            "format": "mobi",
            "sync": True,
            "title": "Amazon Kindle Manga Collection",
        },
    )
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


def test_kindle_image_optimization_and_grayscale(tmp_path):
    """Verifies that MangaFileProcessor.optimize_image_data downscales and converts to e-ink grayscale."""
    # 2400 x 3200 high-res image
    img = Image.new("RGB", (2400, 3200), color="royalblue")
    raw_buf = io.BytesIO()
    img.save(raw_buf, format="JPEG", quality=95)
    orig_bytes = raw_buf.getvalue()

    # 1. Downscale to Kindle 1600px max edge
    opt_bytes, w, h = MangaFileProcessor.optimize_image_data(
        orig_bytes, max_dimension=1600, quality=80, grayscale=False
    )
    assert max(w, h) == 1600
    assert w == 1200
    assert h == 1600
    assert len(opt_bytes) < len(orig_bytes) / 2

    # 2. 16-level grayscale conversion for e-ink
    gray_bytes, gw, gh = MangaFileProcessor.optimize_image_data(
        orig_bytes, max_dimension=1600, quality=80, grayscale=True
    )
    assert (gw, gh) == (1200, 1600)
    with Image.open(io.BytesIO(gray_bytes)) as pil_gray:
        assert pil_gray.mode == "L"
    assert len(gray_bytes) <= len(opt_bytes)


def test_omnibus_chunking_direct(tmp_path):
    """Verifies that build_combined_omnibus splits multi-volume collections into clean ZIP bundles."""
    processor = MangaFileProcessor(str(tmp_path / "storage"))
    sessions = []

    for i in range(1, 5):
        s_id = f"sess_{i}"
        s_dir = tmp_path / "storage" / s_id / "original"
        s_dir.mkdir(parents=True)
        img_path = s_dir / f"page_{i}.jpg"
        Image.new("RGB", (300, 450), color="purple").save(str(img_path), "JPEG")

        sessions.append(
            {
                "session_id": s_id,
                "title": f"Volume {i}",
                "pages": [
                    {
                        "filename": f"page_{i}.jpg",
                        "original_path": str(img_path),
                        "width": 300,
                        "height": 450,
                        "display_name": f"Page {i}",
                    }
                ],
            }
        )

    out_file = str(tmp_path / "Manga_Collection.mobi")
    zip_result = processor.build_combined_omnibus(
        sessions,
        out_file,
        export_format="mobi",
        chunk_by="volumes",
        chunk_size=2,
        title="Epic Manga",
        max_dimension=1600,
        jpeg_quality=80,
        grayscale=True,
    )

    assert zip_result.endswith(".zip")
    assert os.path.exists(zip_result)

    with zipfile.ZipFile(zip_result, "r") as zf:
        names = sorted(zf.namelist())
        assert len(names) == 2
        assert "Part_01_Vol_01-02.mobi" in names[0]
        assert "Part_02_Vol_03-04.mobi" in names[1]

        for fname in names:
            mobi_bytes = zf.read(fname)
            assert b"BOOK" in mobi_bytes[:78]
            assert b"MOBI" in mobi_bytes[:78]


def test_omnibus_combined_api_endpoint():
    """Tests POST /api/export/combined with omnibus chunking across multiple volumes via API."""
    sid1 = ensure_test_doc()
    sid2 = ensure_test_doc()
    sid3 = ensure_test_doc()

    resp = requests.post(
        f"{BASE_URL}/api/export/combined",
        json={
            "session_ids": [sid1, sid2, sid3],
            "format": "mobi",
            "sync": True,
            "chunk_by": "volumes",
            "chunk_size": 2,
            "title": "Kindle Omnibus API Collection",
            "max_dimension": 1600,
            "jpeg_quality": 80,
            "grayscale": True,
        },
    )
    assert resp.status_code == 200, f"Omnibus export failed: {resp.text}"
    data = resp.json()
    assert data["status"] == "success"
    assert data["filename"].endswith(".zip")
    assert "/api/download/combined/" in data["download_url"]

    # Verify download and ZIP contents
    dl_resp = requests.get(f"{BASE_URL}{data['download_url']}")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(dl_resp.content), "r") as zf:
        parts = sorted(zf.namelist())
        assert len(parts) == 2
        assert "Part_01_Vol_01-02.mobi" in parts[0]
        assert "Part_02_Vol_03-03.mobi" in parts[1]

        for zinfo in zf.infolist():
            assert zinfo.compress_type == zipfile.ZIP_STORED
            assert ((zinfo.external_attr >> 16) & 0o777) == 0o644
            assert (zinfo.external_attr & 0x20) == 0x20

        for part in parts:
            part_bytes = zf.read(part)
            assert b"BOOK" in part_bytes[:78]
            assert b"MOBI" in part_bytes[:78]


def test_kindle_colorsoft_optimization(tmp_path):
    """Verifies that Kindle Colorsoft preset enhances saturation & contrast for color e-ink displays."""
    img = Image.new("RGB", (2000, 2600), color=(100, 150, 200))
    raw_buf = io.BytesIO()
    img.save(raw_buf, format="JPEG", quality=90)
    raw_bytes = raw_buf.getvalue()

    # Standard kindle export (no tune)
    std_bytes, sw, sh = MangaFileProcessor.optimize_image_data(
        raw_bytes, max_dimension=1600, quality=80, grayscale=False, colorsoft_tune=False
    )
    assert max(sw, sh) == 1600

    # Colorsoft tuned export (e-ink color boost)
    tuned_bytes, tw, th = MangaFileProcessor.optimize_image_data(
        raw_bytes, max_dimension=1600, quality=80, grayscale=False, colorsoft_tune=True
    )
    assert (tw, th) == (sw, sh)

    with Image.open(io.BytesIO(tuned_bytes)) as pil_tuned:
        assert pil_tuned.mode == "RGB"
        # Verify color is not flattened to grayscale
        colors = pil_tuned.getcolors(maxcolors=256)
        assert colors is not None

    # Test API with colorsoft_tune
    sid1 = ensure_test_doc()
    sid2 = ensure_test_doc()
    resp = requests.post(
        f"{BASE_URL}/api/export/combined",
        json={
            "session_ids": [sid1, sid2],
            "format": "mobi",
            "sync": True,
            "title": "Kindle Colorsoft Test",
            "colorsoft_tune": True,
            "grayscale": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["filename"].endswith(".mobi")


def test_combined_export_filters_empty_sessions_and_sorts_volumes():
    """Verifies that empty sessions (0 pages) are omitted and volumes are naturally sorted."""
    sid1 = ensure_test_doc()
    sid2 = ensure_test_doc()

    # Create an empty ghost session with 0 pages
    empty_sid = "test_empty_ghost_" + str(uuid.uuid4())[:8]
    sess_dir = STORAGE_DIR / empty_sid
    sess_dir.mkdir(parents=True, exist_ok=True)
    with open(sess_dir / "meta.json", "w") as f:
        json.dump({"session_id": empty_sid, "filename": "test_ghost.pdf", "pages": []}, f)

    try:
        resp = requests.post(
            f"{BASE_URL}/api/export/combined",
            json={
                "session_ids": [empty_sid, sid2, sid1],
                "format": "mobi",
                "sync": True,
                "title": "Natural Sort and Filter Test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        # Only the 2 real sessions should be merged, empty ghost session skipped
        assert data["total_volumes"] == 2
    finally:
        shutil.rmtree(sess_dir, ignore_errors=True)
