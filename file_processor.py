import os
import zipfile
import shutil
import io
import struct
import time
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any
from PIL import Image, ImageOps
try:
    import pymupdf as fitz
except ImportError:
    import fitz  # Fallback for older PyMuPDF versions
from bs4 import BeautifulSoup
import re

def natural_sort_key(s: str):
    """Sorts strings with embedded numbers naturally (e.g., page 2 before page 10)."""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

class MangaFileProcessor:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def process_input_file(self, file_path: str, session_id: str):
        """
        Extracts images from .pdf or .epub file into a session folder.
        Returns a list of dicts with page metadata.
        """
        session_dir = self.storage_dir / session_id
        orig_dir = session_dir / "original"
        colorized_dir = session_dir / "colorized"
        
        orig_dir.mkdir(parents=True, exist_ok=True)
        colorized_dir.mkdir(parents=True, exist_ok=True)

        IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tiff')
        ext = Path(file_path).suffix.lower()

        if ext == ".pdf":
            return self._extract_pdf_pages(file_path, orig_dir)
        elif ext == ".epub":
            return self._extract_epub_images(file_path, orig_dir)
        elif ext in IMAGE_EXTENSIONS:
            return self._extract_single_image(file_path, orig_dir)
        elif ext == ".zip":
            return self._extract_epub_images(file_path, orig_dir)  # reuse zip extraction
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def _extract_single_image(self, file_path: str, output_dir: Path):
        """Processes a single image file (.png, .jpg, .webp, etc.) preserving exact aspect ratio and orientation."""
        with Image.open(file_path) as orig_img:
            transposed = ImageOps.exif_transpose(orig_img) or orig_img
            ext = Path(file_path).suffix.lower() or ".png"
            img_filename = f"page_0001{ext}"
            out_path = output_dir / img_filename
            transposed.save(out_path)
            w, h = transposed.size

        return [{
            "page_index": 0,
            "display_name": f"Image 1 ({Path(file_path).name})",
            "filename": img_filename,
            "original_path": str(out_path),
            "width": w,
            "height": h,
            "type": "single_image"
        }]

    def _extract_pdf_pages(self, pdf_path: str, output_dir: Path):
        """Renders each page of PDF to high-res optimized JPEG image strictly maintaining physical aspect ratio."""
        doc = fitz.open(pdf_path)
        pages_meta = []

        for page_num in range(len(doc)):
            page = doc[page_num]
            # Uniform 2.0x zoom strictly maintains the native page aspect ratio
            zoom = 2.0
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            
            output_dir.mkdir(parents=True, exist_ok=True)
            img_filename = f"page_{page_num + 1:04d}.jpg"
            img_path = output_dir / img_filename
            try:
                pix.pil_save(str(img_path), format="JPEG", quality=90, optimize=True)
            except Exception:
                pix.save(str(img_path), jpg_quality=90)

            pages_meta.append({
                "page_index": page_num,
                "display_name": f"Page {page_num + 1}",
                "filename": img_filename,
                "original_path": str(img_path),
                "width": pix.width,
                "height": pix.height,
                "type": "pdf_page"
            })

        doc.close()
        return pages_meta

    def _extract_epub_images(self, epub_path: str, output_dir: Path):
        """Extracts images from EPUB archive in reading order with exact aspect ratio preservation."""
        pages_meta = []
        
        with zipfile.ZipFile(epub_path, 'r') as zf:
            namelist = zf.namelist()
            img_extensions = ('.png', '.jpg', '.jpeg', '.webp')
            
            # Natural sort all images
            all_imgs = [f for f in namelist if f.lower().endswith(img_extensions) and not f.startswith('__MACOSX')]
            all_imgs.sort(key=natural_sort_key)

            for idx, zip_img_path in enumerate(all_imgs):
                img_data = zf.read(zip_img_path)
                try:
                    ext = Path(zip_img_path).suffix.lower() or ".png"
                    img_filename = f"image_{idx + 1:04d}{ext}"
                    out_path = output_dir / img_filename

                    # Write raw image bytes directly to preserve 100% pixel fidelity without recompression
                    with open(out_path, 'wb') as f:
                        f.write(img_data)

                    # Accurately detect dimensions & handle any EXIF orientation
                    with Image.open(out_path) as im:
                        im_trans = ImageOps.exif_transpose(im)
                        if im_trans is not None and im_trans != im:
                            im_trans.save(out_path)
                            width, height = im_trans.size
                        else:
                            width, height = im.size

                    pages_meta.append({
                        "page_index": idx,
                        "display_name": f"Image {idx + 1} ({Path(zip_img_path).name})",
                        "filename": img_filename,
                        "zip_internal_path": zip_img_path,
                        "original_path": str(out_path),
                        "width": width,
                        "height": height,
                        "type": "epub_image"
                    })
                except Exception as e:
                    print(f"Skipping non-image zip entry {zip_img_path}: {e}")

        return pages_meta

    def build_colorized_pdf(self, pages_meta: list, session_id: str, output_filepath: str):
        """Assembles colorized images into a new, compact, optimized PDF document."""
        session_dir = self.storage_dir / session_id
        colorized_dir = session_dir / "colorized"
        
        pdf_doc = fitz.open()

        for page_info in pages_meta:
            color_filename = page_info["filename"]
            color_path = colorized_dir / color_filename
            
            # Fallback to original image if colorized version is missing
            if not color_path.exists():
                color_path = Path(page_info["original_path"])

            ext = color_path.suffix.lower()
            with Image.open(str(color_path)) as pil_img:
                width, height = pil_img.size
                pdf_page = pdf_doc.new_page(width=width, height=height)
                rect = fitz.Rect(0, 0, width, height)

                # If already JPEG, insert directly; if PNG or uncompressed, convert to high-quality JPEG stream
                if ext in ('.jpg', '.jpeg'):
                    pdf_page.insert_image(rect, filename=str(color_path))
                else:
                    rgb_img = pil_img.convert("RGB")
                    buf = io.BytesIO()
                    rgb_img.save(buf, format="JPEG", quality=90, optimize=True)
                    pdf_page.insert_image(rect, stream=buf.getvalue())

        pdf_doc.save(output_filepath, garbage=4, deflate=True, clean=True)
        pdf_doc.close()
        return output_filepath

    def build_colorized_epub(self, original_epub_path: str, pages_meta: list, session_id: str, output_filepath: str, title: str = "Colorized Manga"):
        """
        Clones original EPUB zip archive and replaces images with colorized versions.
        If original file is not an EPUB (e.g. was PDF or image), generates a standalone EPUB.
        """
        if original_epub_path and os.path.exists(original_epub_path) and original_epub_path.lower().endswith(".epub") and zipfile.is_zipfile(original_epub_path):
            session_dir = self.storage_dir / session_id
            colorized_dir = session_dir / "colorized"

            temp_epub = output_filepath + ".tmp"

            with zipfile.ZipFile(original_epub_path, 'r') as zin:
                with zipfile.ZipFile(temp_epub, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
                    # Map zip_internal_path -> colorized file path
                    color_map = {}
                    for p in pages_meta:
                        zip_path = p.get("zip_internal_path")
                        if zip_path:
                            c_path = colorized_dir / p["filename"]
                            if c_path.exists():
                                color_map[zip_path] = str(c_path)

                    for item in zin.infolist():
                        if item.filename in color_map:
                            # Write the colorized replacement image
                            with open(color_map[item.filename], 'rb') as f:
                                zout.writestr(item.filename, f.read())
                        else:
                            # Copy original file unchanged
                            zout.writestr(item.filename, zin.read(item.filename))

            if os.path.exists(output_filepath):
                os.remove(output_filepath)
            os.rename(temp_epub, output_filepath)
            return output_filepath
        else:
            return self.build_standalone_epub(pages_meta, session_id, output_filepath, title=title)

    def build_standalone_epub(self, pages_meta: list, session_id: str, output_filepath: str, title: str = "Colorized Manga"):
        """
        Builds a compliant EPUB3 comic/manga e-book from colorized page images.
        Compatible with Apple Books, Kindle, Kobo, and all EPUB3 readers.
        """
        session_dir = self.storage_dir / session_id
        colorized_dir = session_dir / "colorized"

        temp_epub = output_filepath + ".tmp"
        if os.path.exists(temp_epub):
            os.remove(temp_epub)

        with zipfile.ZipFile(temp_epub, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
            # 1. mimetype (MUST be uncompressed and the first entry in zip)
            zout.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)

            # 2. META-INF/container.xml
            container_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''
            zout.writestr('META-INF/container.xml', container_xml, compress_type=zipfile.ZIP_DEFLATED)

            manifest_items = [
                '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            ]
            spine_items = []
            nav_items = []

            # 3. Add images and create XHTML pages
            for idx, page_info in enumerate(pages_meta):
                color_filename = page_info["filename"]
                color_path = colorized_dir / color_filename
                if not color_path.exists():
                    color_path = Path(page_info["original_path"])

                ext = color_path.suffix.lower()
                # Optimize page image to JPEG to drastically reduce EPUB package size while retaining high visual quality
                if ext in ('.jpg', '.jpeg'):
                    with open(color_path, 'rb') as f:
                        img_bytes = f.read()
                    safe_img_name = f"page_{idx+1:04d}.jpg"
                    media_type = "image/jpeg"
                else:
                    with Image.open(str(color_path)) as pil_img:
                        rgb_img = pil_img.convert("RGB")
                        buf = io.BytesIO()
                        rgb_img.save(buf, format="JPEG", quality=90, optimize=True)
                        img_bytes = buf.getvalue()
                    safe_img_name = f"page_{idx+1:04d}.jpg"
                    media_type = "image/jpeg"

                zout.writestr(f"OEBPS/images/{safe_img_name}", img_bytes, compress_type=zipfile.ZIP_DEFLATED)

                page_id = f"page_{idx+1}"
                img_id = f"img_{idx+1}"
                xhtml_name = f"page_{idx+1:04d}.xhtml"

                cover_attr = ' properties="cover-image"' if idx == 0 else ""
                manifest_items.append(f'<item id="{img_id}" href="images/{safe_img_name}" media-type="{media_type}"{cover_attr}/>')
                manifest_items.append(f'<item id="{page_id}" href="{xhtml_name}" media-type="application/xhtml+xml"/>')
                spine_items.append(f'<itemref idref="{page_id}" properties="rendition:layout-pre-paginated"/>')
                nav_items.append(f'<li><a href="{xhtml_name}">{page_info.get("display_name", f"Page {idx+1}")}</a></li>')

                w = page_info.get("width", 1200)
                h = page_info.get("height", 1600)
                page_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8"/>
  <title>Page {idx+1}</title>
  <meta name="viewport" content="width={w}, height={h}"/>
  <style>
    @page {{ margin: 0; }}
    body {{ margin: 0; padding: 0; background-color: #000; text-align: center; }}
    img {{ max-width: 100%; max-height: 100vh; width: auto; height: auto; display: block; margin: auto; }}
  </style>
</head>
<body>
  <img src="images/{safe_img_name}" alt="Page {idx+1}"/>
</body>
</html>'''
                zout.writestr(f"OEBPS/{xhtml_name}", page_xhtml, compress_type=zipfile.ZIP_DEFLATED)

            # 4. Navigation TOC
            nav_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><meta charset="utf-8"/><title>Table of Contents</title></head>
<body>
  <nav epub:type="toc">
    <h2>Table of Contents</h2>
    <ol>
      {"".join(nav_items)}
    </ol>
  </nav>
</body>
</html>'''
            zout.writestr('OEBPS/nav.xhtml', nav_xhtml, compress_type=zipfile.ZIP_DEFLATED)

            # 5. content.opf
            clean_title = (title or "Colorized Manga").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:{session_id}</dc:identifier>
    <dc:title>{clean_title}</dc:title>
    <dc:language>en</dc:language>
    <meta property="dcterms:modified">2026-09-14T00:00:00Z</meta>
    <!-- Amazon Kindle & EPUB3 Manga Fixed-Layout Metadata -->
    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:orientation">auto</meta>
    <meta property="rendition:spread">auto</meta>
    <meta name="book-type" content="comic"/>
    <meta name="fixed-layout" content="true"/>
    <meta name="zero-gutter" content="true"/>
    <meta name="zero-margin" content="true"/>
    <meta name="ke-border-color" content="#000000"/>
    <meta name="orientation-lock" content="none"/>
    <meta name="primary-writing-mode" content="horizontal-rl"/>
    <meta name="RegionMagnification" content="false"/>
    <meta name="cover" content="img_1"/>
  </metadata>
  <manifest>
    {"".join(manifest_items)}
  </manifest>
  <spine page-progression-direction="rtl">
    {"".join(spine_items)}
  </spine>
</package>'''
            zout.writestr('OEBPS/content.opf', opf, compress_type=zipfile.ZIP_DEFLATED)

        if os.path.exists(output_filepath):
            os.remove(output_filepath)
        os.rename(temp_epub, output_filepath)
        return output_filepath

    def build_colorized_single_image(self, pages_meta: list, session_id: str, output_filepath: str):
        """Exports colorized single image file."""
        session_dir = self.storage_dir / session_id
        colorized_dir = session_dir / "colorized"
        
        if len(pages_meta) > 0:
            color_filename = pages_meta[0]["filename"]
            color_path = colorized_dir / color_filename
            if not color_path.exists():
                color_path = Path(pages_meta[0]["original_path"])
            
            shutil.copyfile(str(color_path), output_filepath)
            return output_filepath
        raise ValueError("No page metadata found for single image export")

    def build_colorized_zip(self, pages_meta: list, session_id: str, output_filepath: str):
        """Packs all colorized images into a zip archive with maximum compression."""
        session_dir = self.storage_dir / session_id
        colorized_dir = session_dir / "colorized"

        with zipfile.ZipFile(output_filepath, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
            for p in pages_meta:
                c_path = colorized_dir / p["filename"]
                if not c_path.exists():
                    c_path = Path(p["original_path"])
                zout.write(str(c_path), arcname=p["filename"])

        return output_filepath

    @staticmethod
    def _convert_epub_to_mobi(epub_path: str, mobi_path: str) -> bool:
        """Attempts conversion via ebook-convert (Calibre) or kindlegen if installed."""
        ebook_convert = shutil.which("ebook-convert")
        if ebook_convert:
            try:
                res = subprocess.run([
                    ebook_convert, epub_path, mobi_path,
                    "--output-profile", "kindle",
                    "--mobi-file-type", "both"
                ], capture_output=True, timeout=180)
                if res.returncode == 0 and os.path.exists(mobi_path) and os.path.getsize(mobi_path) > 0:
                    return True
            except Exception:
                pass

        kindlegen = shutil.which("kindlegen")
        if kindlegen:
            try:
                out_name = Path(mobi_path).name
                out_dir = str(Path(mobi_path).parent)
                res = subprocess.run([
                    kindlegen, epub_path, "-c2", "-o", out_name
                ], cwd=out_dir, capture_output=True, timeout=180)
                if res.returncode in (0, 1) and os.path.exists(mobi_path) and os.path.getsize(mobi_path) > 0:
                    return True
            except Exception:
                pass
        return False

    def build_mobi_from_images(
        self,
        images_data: list,
        output_filepath: str,
        title: str = "Colorized Manga",
        author: str = "Kobean Manga Colorizer"
    ) -> str:
        """
        Builds a compliant PalmDOC / MOBI 6 e-book container in pure Python.
        Compatible with Amazon Kindle (sideloading into /documents), Kindle apps,
        KOReader, Moon+ Reader, and Calibre.
        """
        if not images_data:
            raise ValueError("No images provided for MOBI generation")

        clean_title = (title or "Colorized Manga").strip()
        num_images = len(images_data)

        # 1. Generate text record (HTML)
        html_lines = [
            "<!DOCTYPE html>",
            "<html>",
            "<head>",
            '<meta http-equiv="content-type" content="text/html; charset=utf-8" />',
            f"<title>{clean_title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</title>",
            "<style>",
            "@page { margin: 0; }",
            "body { margin: 0; padding: 0; background-color: #000; text-align: center; }",
            "div.page { page-break-after: always; text-align: center; margin: 0; padding: 0; }",
            "div.vol-heading { color: #fff; padding: 40px 10px; page-break-after: always; text-align: center; }",
            "h2 { font-size: 1.8em; color: #fff; margin: 0; }",
            "img { max-width: 100%; height: auto; display: block; margin: 0 auto; }",
            "</style>",
            "</head>",
            '<body dir="rtl">',
        ]

        image_bytes_list = []
        for i, item in enumerate(images_data, start=1):
            if isinstance(item, (tuple, list)):
                raw_bytes = item[0]
                label = item[1] if len(item) > 1 else f"Page {i}"
                vol_header = item[2] if len(item) > 2 else None
            else:
                raw_bytes = item
                label = f"Page {i}"
                vol_header = None

            image_bytes_list.append(raw_bytes)

            if vol_header:
                clean_vol = str(vol_header).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_lines.append(f'<div class="vol-heading"><h2>{clean_vol}</h2></div>')

            clean_lbl = str(label).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_lines.append(f'<div class="page"><img recindex="{i:04d}" alt="{clean_lbl}"/></div>')

        html_lines.append("</body></html>")
        text_content = "\n".join(html_lines).encode("utf-8")
        text_len = len(text_content)

        first_image_index = 2
        last_image_index = first_image_index + num_images - 1
        flis_index = last_image_index + 1
        fcis_index = flis_index + 1
        eof_index = fcis_index + 1
        total_records = eof_index + 1

        def exth_record(tag, data):
            return struct.pack(">II", tag, 8 + len(data)) + data

        title_bytes = clean_title.encode("utf-8")
        author_bytes = (author or "Kobean Manga Colorizer").encode("utf-8")

        exth_records = [
            exth_record(100, author_bytes),                      # Author
            exth_record(503, title_bytes),                       # Title
            exth_record(121, b"comic"),                           # Book type: comic
            exth_record(122, b"true"),                            # Fixed-layout: true
            exth_record(125, struct.pack(">I", num_images)),     # Image count
            exth_record(126, b"none"),                            # Orientation lock: none
            exth_record(127, b"horizontal-rl"),                   # Primary writing mode: RTL
            exth_record(128, b"pre-paginated"),                   # Rendition layout
            exth_record(201, struct.pack(">I", 0)),               # Cover offset (1st image)
        ]
        exth_data = b"".join(exth_records)
        exth_header_len = 12 + len(exth_data)
        pad_len = (4 - (exth_header_len % 4)) % 4
        exth_header_len += pad_len
        exth_block = struct.pack(">4sII", b"EXTH", exth_header_len, len(exth_records)) + exth_data + (b"\x00" * pad_len)

        # PalmDOC Header (16 bytes)
        palmdoc_header = struct.pack(
            ">HHIHHI",
            1,          # compression: 1 (none)
            0,          # unused
            text_len,   # text length
            1,          # record count (1 text record)
            4096,       # record size
            0           # current position
        )

        title_offset = 248 + len(exth_block)
        title_len = len(title_bytes)

        # MOBI Header (232 bytes, starts at offset 16)
        mobi_fields = [
            ("identifier", "4s", b"MOBI"),
            ("header_length", "I", 232),
            ("mobi_type", "I", 2),                  # Mobipocket book
            ("text_encoding", "I", 65001),          # UTF-8
            ("unique_id", "I", int(time.time()) & 0xFFFFFFFF),
            ("file_version", "I", 6),
            ("orthographic_index", "I", 0xFFFFFFFF),
            ("inflection_index", "I", 0xFFFFFFFF),
            ("index_names", "I", 0xFFFFFFFF),
            ("index_keys", "I", 0xFFFFFFFF),
            ("extra_index_0", "I", 0xFFFFFFFF),
            ("extra_index_1", "I", 0xFFFFFFFF),
            ("extra_index_2", "I", 0xFFFFFFFF),
            ("extra_index_3", "I", 0xFFFFFFFF),
            ("extra_index_4", "I", 0xFFFFFFFF),
            ("extra_index_5", "I", 0xFFFFFFFF),
            ("first_non_book_index", "I", 2),
            ("full_name_offset", "I", title_offset),
            ("full_name_length", "I", title_len),
            ("locale", "I", 1033),
            ("input_language", "I", 0),
            ("output_language", "I", 0),
            ("min_version", "I", 6),
            ("first_image_index", "I", first_image_index),
            ("huffman_record_offset", "I", 0),
            ("huffman_record_count", "I", 0),
            ("huffman_table_offset", "I", 0),
            ("huffman_table_length", "I", 0),
            ("exth_flags", "I", 0x50),               # Bit 6 set for EXTH
            ("reserved", "32s", b"\x00" * 32),
            ("drm_offset", "I", 0xFFFFFFFF),
            ("drm_count", "I", 0),
            ("drm_size", "I", 0),
            ("drm_flags", "I", 0),
        ]
        fmt = ">" + "".join(f[1] for f in mobi_fields)
        mobi_header = struct.pack(fmt, *[f[2] for f in mobi_fields])
        if len(mobi_header) < 232:
            mobi_header += b"\x00" * (232 - len(mobi_header))

        record_0 = palmdoc_header + mobi_header + exth_block + title_bytes + b"\x00\x00"
        if len(record_0) % 4 != 0:
            record_0 += b"\x00" * (4 - (len(record_0) % 4))

        flis_record = b"FLIS\x00\x00\x00\x08\x00\x41\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\x00\x01\x00\x03\x00\x00\x00\x00\x00\x00\x00\x00"
        fcis_record = b"FCIS\x00\x00\x00\x14\x00\x00\x00\x10\x00\x00\x00\x01\x00\x00\x00\x00" + struct.pack(">I", text_len) + b"\x00\x00\x00\x00\x00\x00\x00\x20\x00\x00\x00\x08\x00\x01\x00\x01\x00\x00\x00\x00"
        eof_record = b"\xe9\x8e\r\n"

        records = [record_0, text_content] + image_bytes_list + [flis_record, fcis_record, eof_record]

        header_size = 78 + (8 * total_records) + 2
        record_offsets = []
        curr_offset = header_size
        for rec in records:
            record_offsets.append(curr_offset)
            curr_offset += len(rec)

        now = int(time.time()) + 2082844800  # seconds since 1904-01-01
        name_field = clean_title.encode("ascii", errors="replace")[:31].ljust(32, b"\x00")
        pdb_header = struct.pack(
            ">32sHHIIIIII4s4sIIH",
            name_field,
            0, 0,
            now, now, 0, 0, 0, 0,
            b"BOOK", b"MOBI",
            2 * total_records + 1,
            0,
            total_records
        )

        rec_headers = []
        for i, offset in enumerate(record_offsets):
            unique_id = struct.pack(">I", 2 * i)[1:]
            rec_headers.append(struct.pack(">IB3s", offset, 0, unique_id))

        rec_list = b"".join(rec_headers) + b"\x00\x00"

        temp_mobi = output_filepath + ".tmp"
        if os.path.exists(temp_mobi):
            os.remove(temp_mobi)

        with open(temp_mobi, "wb") as f:
            f.write(pdb_header)
            f.write(rec_list)
            for rec in records:
                f.write(rec)

        if os.path.exists(output_filepath):
            os.remove(output_filepath)
        os.rename(temp_mobi, output_filepath)
        return output_filepath

    def build_colorized_mobi(self, pages_meta: list, session_id: str, output_filepath: str, title: str = "Colorized Manga"):
        """
        Builds an Amazon Kindle-compatible MOBI comic/manga e-book from colorized page images.
        """
        import tempfile

        if shutil.which("ebook-convert") or shutil.which("kindlegen"):
            with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp_epub:
                tmp_epub_path = tmp_epub.name
            try:
                self.build_standalone_epub(pages_meta, session_id, tmp_epub_path, title=title)
                if self._convert_epub_to_mobi(tmp_epub_path, output_filepath):
                    return output_filepath
            finally:
                if os.path.exists(tmp_epub_path):
                    try:
                        os.remove(tmp_epub_path)
                    except Exception:
                        pass

        session_dir = self.storage_dir / session_id
        colorized_dir = session_dir / "colorized"

        images_data = []
        for idx, page_info in enumerate(pages_meta):
            color_filename = page_info["filename"]
            color_path = colorized_dir / color_filename
            if not color_path.exists():
                color_path = Path(page_info["original_path"])
            if not color_path.exists():
                continue

            ext = color_path.suffix.lower()
            if ext in ('.jpg', '.jpeg'):
                with open(color_path, 'rb') as f:
                    img_bytes = f.read()
            else:
                with Image.open(str(color_path)) as pil_img:
                    rgb = pil_img.convert("RGB")
                    buf = io.BytesIO()
                    rgb.save(buf, format="JPEG", quality=90, optimize=True)
                    img_bytes = buf.getvalue()

            page_label = page_info.get("display_name", f"Page {idx+1}")
            images_data.append((img_bytes, page_label))

        return self.build_mobi_from_images(images_data, output_filepath, title=title)

    def build_batch_export(self, sessions_data: list, output_filepath: str, format_override: Optional[str] = None) -> str:
        """
        Builds and packages multiple colorized documents into a single archive.
        Preserves original document formats (e.g. EPUBs as EPUB, PDFs as PDF) or applies format_override.
        """
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            created_files = []

            for sess in sessions_data:
                session_id = sess["session_id"]
                stem = Path(sess["filename"]).stem
                ext = sess.get("ext", "").lower()
                pages_meta = sess.get("pages", [])
                original_path = sess.get("file_path", "")

                target_fmt = (format_override or "auto").lower().strip()
                if target_fmt == "auto":
                    if ext == ".epub":
                        target_fmt = "epub"
                    elif ext == ".pdf":
                        target_fmt = "pdf"
                    else:
                        target_fmt = "pdf"

                if target_fmt in ["mobi", "azw3", "kindle"]:
                    doc_filename = f"colorized_{stem}.mobi"
                    doc_path = str(temp_path / doc_filename)
                    self.build_colorized_mobi(pages_meta, session_id, doc_path, title=f"Colorized - {stem}")
                    created_files.append((doc_path, doc_filename))
                elif target_fmt == "epub":
                    doc_filename = f"colorized_{stem}.epub"
                    doc_path = str(temp_path / doc_filename)
                    self.build_colorized_epub(original_path, pages_meta, session_id, doc_path, title=f"Colorized - {stem}")
                    created_files.append((doc_path, doc_filename))
                elif target_fmt == "pdf":
                    doc_filename = f"colorized_{stem}.pdf"
                    doc_path = str(temp_path / doc_filename)
                    self.build_colorized_pdf(pages_meta, session_id, doc_path)
                    created_files.append((doc_path, doc_filename))
                elif target_fmt == "zip":
                    doc_filename = f"colorized_{stem}_images.zip"
                    doc_path = str(temp_path / doc_filename)
                    self.build_colorized_zip(pages_meta, session_id, doc_path)
                    created_files.append((doc_path, doc_filename))

            # Package all generated colorized books/files into output zip
            with zipfile.ZipFile(output_filepath, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
                for file_path, arcname in created_files:
                    zout.write(file_path, arcname=arcname)

        return output_filepath

    # ── Combined single-file export (all volumes → one EPUB / PDF) ───

    def build_combined_epub(
        self,
        sessions_data: list,
        output_filepath: str,
        title: str = "Colorized Manga Collection",
        progress_callback: Optional[Any] = None,
        cancel_check: Optional[Any] = None,
    ) -> str:
        """
        Merges all queued volumes into one continuous EPUB3 file optimised for e-readers.

        Structure:
          OEBPS/
            images/vol_{v:02d}_page_{p:04d}.jpg   — all page images, namespaced per volume
            vol_{v:02d}_page_{p:04d}.xhtml        — one XHTML wrapper per page
            nav.xhtml                              — table of contents with volume chapter headings
            content.opf                            — manifest + spine

        Supports real-time progress callbacks and cancellation checks.
        """
        import tempfile, uuid as _uuid

        temp_epub = output_filepath + ".tmp"
        if os.path.exists(temp_epub):
            os.remove(temp_epub)

        manifest_items: List[str] = [
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        ]
        spine_items: List[str] = []
        toc_volumes: List[dict] = []

        total_pages = sum(len(s.get("pages", [])) for s in sessions_data)
        processed_pages = 0
        global_page_idx = 0

        try:
            with zipfile.ZipFile(temp_epub, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
                zout.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)

                container_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>'''
                zout.writestr('META-INF/container.xml', container_xml)

                for vol_idx, sess in enumerate(sessions_data):
                    if cancel_check and cancel_check():
                        raise InterruptedError("Combined EPUB export cancelled")

                    session_id = sess["session_id"]
                    vol_stem   = Path(sess.get("filename", f"Volume {vol_idx+1}")).stem
                    pages_meta = sess.get("pages", [])
                    colorized_dir = self.storage_dir / session_id / "colorized"

                    vol_toc = {"label": f"Vol. {vol_idx+1} — {vol_stem}", "pages": []}

                    for page_info in pages_meta:
                        if cancel_check and cancel_check():
                            raise InterruptedError("Combined EPUB export cancelled")

                        color_filename = page_info["filename"]
                        color_path = colorized_dir / color_filename
                        if not color_path.exists():
                            color_path = Path(page_info["original_path"])
                        if not color_path.exists():
                            continue

                        gidx = global_page_idx
                        global_page_idx += 1

                        # Image
                        ext = color_path.suffix.lower()
                        img_arc_name = f"images/vol_{vol_idx+1:02d}_page_{gidx+1:04d}.jpg"
                        if ext in ('.jpg', '.jpeg'):
                            with open(color_path, 'rb') as f:
                                img_bytes = f.read()
                        else:
                            with Image.open(str(color_path)) as pil_img:
                                rgb = pil_img.convert("RGB")
                                buf = io.BytesIO()
                                rgb.save(buf, format="JPEG", quality=90, optimize=True)
                                img_bytes = buf.getvalue()

                        zout.writestr(f"OEBPS/{img_arc_name}", img_bytes)

                        # XHTML page wrapper
                        xhtml_name = f"vol_{vol_idx+1:02d}_page_{gidx+1:04d}.xhtml"
                        img_id  = f"img_v{vol_idx+1}p{gidx+1}"
                        page_id = f"page_v{vol_idx+1}p{gidx+1}"
                        w = page_info.get("width", 1200)
                        h = page_info.get("height", 1600)
                        page_label = page_info.get("display_name", f"Page {gidx+1}")

                        page_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8"/>
  <title>{page_label}</title>
  <meta name="viewport" content="width={w}, height={h}"/>
  <style>
    @page {{ margin: 0; }}
    body {{ margin: 0; padding: 0; background-color: #000; text-align: center; }}
    img {{ max-width: 100%; max-height: 100vh; width: auto; height: auto; display: block; margin: auto; }}
  </style>
</head>
<body>
  <img src="{img_arc_name}" alt="{page_label}"/>
</body>
</html>'''
                        zout.writestr(f"OEBPS/{xhtml_name}", page_xhtml)

                        cover_attr = ' properties="cover-image"' if gidx == 0 else ""
                        manifest_items.append(
                            f'<item id="{img_id}" href="{img_arc_name}" media-type="image/jpeg"{cover_attr}/>'
                        )
                        manifest_items.append(
                            f'<item id="{page_id}" href="{xhtml_name}" media-type="application/xhtml+xml"/>'
                        )
                        spine_items.append(f'<itemref idref="{page_id}" properties="rendition:layout-pre-paginated"/>')
                        vol_toc["pages"].append({"xhtml": xhtml_name, "title": page_label})

                        processed_pages += 1
                        if progress_callback:
                            progress_callback({
                                "vol_num": vol_idx + 1,
                                "total_vols": len(sessions_data),
                                "vol_title": vol_stem,
                                "processed_pages": processed_pages,
                                "total_pages": total_pages,
                                "percent": int((processed_pages / max(total_pages, 1)) * 100),
                                "status": f"Volume {vol_idx + 1}/{len(sessions_data)}: {page_label}"
                            })

                    if vol_toc["pages"]:
                        toc_volumes.append(vol_toc)

                # Navigation TOC — volume-level chapter headers
                nav_ol_parts: List[str] = []
                for vol in toc_volumes:
                    first_xhtml = vol["pages"][0]["xhtml"] if vol["pages"] else "#"
                    clean_vol_label = vol["label"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    page_lis = "".join(
                        f'<li><a href="{p["xhtml"]}">{p["title"].replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")}</a></li>'
                        for p in vol["pages"]
                    )
                    nav_ol_parts.append(
                        f'<li><a href="{first_xhtml}">{clean_vol_label}</a>'
                        f'<ol>{page_lis}</ol></li>'
                    )

                nav_xhtml = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><meta charset="utf-8"/><title>Table of Contents</title></head>
<body>
  <nav epub:type="toc">
    <h2>Table of Contents</h2>
    <ol>{"".join(nav_ol_parts)}</ol>
  </nav>
</body>
</html>'''
                zout.writestr('OEBPS/nav.xhtml', nav_xhtml)

                # content.opf
                safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                book_uuid  = str(_uuid.uuid4())
                opf = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="pub-id">urn:uuid:{book_uuid}</dc:identifier>
    <dc:title>{safe_title}</dc:title>
    <dc:language>en</dc:language>
    <meta property="dcterms:modified">2026-09-15T00:00:00Z</meta>
    <!-- Amazon Kindle & EPUB3 Manga Fixed-Layout Metadata -->
    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:orientation">auto</meta>
    <meta property="rendition:spread">auto</meta>
    <meta name="book-type" content="comic"/>
    <meta name="fixed-layout" content="true"/>
    <meta name="zero-gutter" content="true"/>
    <meta name="zero-margin" content="true"/>
    <meta name="ke-border-color" content="#000000"/>
    <meta name="orientation-lock" content="none"/>
    <meta name="primary-writing-mode" content="horizontal-rl"/>
    <meta name="RegionMagnification" content="false"/>
    <meta name="cover" content="img_v1p1"/>
  </metadata>
  <manifest>
    {"".join(manifest_items)}
  </manifest>
  <spine page-progression-direction="rtl">
    {"".join(spine_items)}
  </spine>
</package>'''
                zout.writestr('OEBPS/content.opf', opf)

            if cancel_check and cancel_check():
                raise InterruptedError("Combined EPUB export cancelled")

            if os.path.exists(output_filepath):
                os.remove(output_filepath)
            os.rename(temp_epub, output_filepath)
            return output_filepath
        except Exception:
            if os.path.exists(temp_epub):
                try:
                    os.remove(temp_epub)
                except Exception:
                    pass
            raise

    def build_combined_pdf(
        self,
        sessions_data: list,
        output_filepath: str,
        title: str = "Colorized Manga Collection",
        progress_callback: Optional[Any] = None,
        cancel_check: Optional[Any] = None,
    ) -> str:
        """
        Concatenates all volumes into a single PDF with PDF bookmarks (outlines)
        at the volume level for easy navigation on e-readers and PDF viewers.

        Supports real-time progress callbacks and cancellation checks.
        """
        pdf_doc = fitz.open()
        total_pages = sum(len(s.get("pages", [])) for s in sessions_data)
        processed_pages = 0

        try:
            for vol_idx, sess in enumerate(sessions_data):
                if cancel_check and cancel_check():
                    raise InterruptedError("Combined PDF export cancelled")

                session_id   = sess["session_id"]
                vol_stem     = Path(sess.get("filename", f"Volume {vol_idx+1}")).stem
                pages_meta   = sess.get("pages", [])
                colorized_dir = self.storage_dir / session_id / "colorized"

                vol_start_page = len(pdf_doc)  # page index before adding this volume

                for page_info in pages_meta:
                    if cancel_check and cancel_check():
                        raise InterruptedError("Combined PDF export cancelled")

                    color_filename = page_info["filename"]
                    color_path = colorized_dir / color_filename
                    if not color_path.exists():
                        color_path = Path(page_info["original_path"])
                    if not color_path.exists():
                        continue

                    ext = color_path.suffix.lower()
                    with Image.open(str(color_path)) as pil_img:
                        width, height = pil_img.size
                        pdf_page = pdf_doc.new_page(width=width, height=height)
                        rect = fitz.Rect(0, 0, width, height)
                        if ext in ('.jpg', '.jpeg'):
                            pdf_page.insert_image(rect, filename=str(color_path))
                        else:
                            rgb_img = pil_img.convert("RGB")
                            buf = io.BytesIO()
                            rgb_img.save(buf, format="JPEG", quality=90, optimize=True)
                            pdf_page.insert_image(rect, stream=buf.getvalue())

                    processed_pages += 1
                    if progress_callback:
                        progress_callback({
                            "vol_num": vol_idx + 1,
                            "total_vols": len(sessions_data),
                            "vol_title": vol_stem,
                            "processed_pages": processed_pages,
                            "total_pages": total_pages,
                            "percent": int((processed_pages / max(total_pages, 1)) * 100),
                            "status": f"Volume {vol_idx + 1}/{len(sessions_data)}: {page_info.get('display_name', f'Page {processed_pages}')}"
                        })

                # Add a bookmark (outline entry) pointing to the first page of this volume
                if len(pdf_doc) > vol_start_page:
                    pdf_doc.set_toc(
                        pdf_doc.get_toc() + [[1, f"Vol. {vol_idx+1} — {vol_stem}", vol_start_page + 1]]
                    )

            if cancel_check and cancel_check():
                raise InterruptedError("Combined PDF export cancelled")

            pdf_doc.set_metadata({"title": title, "creator": "Kobean Manga Colorizer"})
            pdf_doc.save(output_filepath, garbage=4, deflate=True, clean=True)
            pdf_doc.close()
            return output_filepath
        except Exception:
            pdf_doc.close()
            if os.path.exists(output_filepath):
                try:
                    os.remove(output_filepath)
                except Exception:
                    pass
            raise

    def build_combined_mobi(
        self,
        sessions_data: list,
        output_filepath: str,
        title: str = "Colorized Manga Collection",
        progress_callback: Optional[Any] = None,
        cancel_check: Optional[Any] = None,
    ) -> str:
        """
        Merges all queued volumes into a single Amazon Kindle MOBI file.
        Supports real-time progress callbacks and cancellation checks.
        """
        import tempfile

        if cancel_check and cancel_check():
            raise InterruptedError("Combined MOBI export cancelled")

        total_pages = sum(len(s.get("pages", [])) for s in sessions_data)
        processed_pages = 0
        global_page_idx = 0

        # Check if external converter is available
        if shutil.which("ebook-convert") or shutil.which("kindlegen"):
            with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp_epub:
                tmp_epub_path = tmp_epub.name
            try:
                self.build_combined_epub(
                    sessions_data, tmp_epub_path, title=title,
                    progress_callback=progress_callback,
                    cancel_check=cancel_check
                )
                if cancel_check and cancel_check():
                    raise InterruptedError("Combined MOBI export cancelled")
                if self._convert_epub_to_mobi(tmp_epub_path, output_filepath):
                    return output_filepath
            finally:
                if os.path.exists(tmp_epub_path):
                    try:
                        os.remove(tmp_epub_path)
                    except Exception:
                        pass

        # Pure-Python MOBI assembly with volume chapter headers
        images_data = []
        for vol_idx, sess in enumerate(sessions_data):
            if cancel_check and cancel_check():
                raise InterruptedError("Combined MOBI export cancelled")

            session_id = sess["session_id"]
            vol_stem = Path(sess.get("filename", f"Volume {vol_idx+1}")).stem
            vol_label = f"Vol. {vol_idx+1} — {vol_stem}"
            pages_meta = sess.get("pages", [])
            colorized_dir = self.storage_dir / session_id / "colorized"

            for p_idx, page_info in enumerate(pages_meta):
                if cancel_check and cancel_check():
                    raise InterruptedError("Combined MOBI export cancelled")

                color_filename = page_info["filename"]
                color_path = colorized_dir / color_filename
                if not color_path.exists():
                    color_path = Path(page_info["original_path"])
                if not color_path.exists():
                    continue

                gidx = global_page_idx
                global_page_idx += 1

                ext = color_path.suffix.lower()
                if ext in ('.jpg', '.jpeg'):
                    with open(color_path, 'rb') as f:
                        img_bytes = f.read()
                else:
                    with Image.open(str(color_path)) as pil_img:
                        rgb = pil_img.convert("RGB")
                        buf = io.BytesIO()
                        rgb.save(buf, format="JPEG", quality=90, optimize=True)
                        img_bytes = buf.getvalue()

                page_label = page_info.get("display_name", f"Page {gidx+1}")
                vol_header = vol_label if p_idx == 0 else None
                images_data.append((img_bytes, page_label, vol_header))

                processed_pages += 1
                if progress_callback:
                    progress_callback({
                        "vol_num": vol_idx + 1,
                        "total_vols": len(sessions_data),
                        "vol_title": vol_stem,
                        "processed_pages": processed_pages,
                        "total_pages": total_pages,
                        "percent": int((processed_pages / max(total_pages, 1)) * 100),
                        "status": f"Volume {vol_idx + 1}/{len(sessions_data)}: {page_label}"
                    })

        if cancel_check and cancel_check():
            raise InterruptedError("Combined MOBI export cancelled")

        return self.build_mobi_from_images(images_data, output_filepath, title=title)


