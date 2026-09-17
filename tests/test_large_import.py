import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import io
import time
import shutil
import zipfile
import resource
import unittest
import requests
from PIL import Image

import main
from file_processor import MangaFileProcessor

SERVER_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def create_dummy_png(text="Page"):
    img = Image.new("RGB", (200, 300), color=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_dummy_cbz(path: Path, num_pages: int = 2):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(path), "w") as z:
        for i in range(num_pages):
            z.writestr(f"page_{i+1:03d}.png", create_dummy_png(f"Page {i+1}"))


def create_dummy_zip(path: Path, num_pages: int = 2):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(path), "w") as z:
        for i in range(num_pages):
            z.writestr(f"image_{i+1:03d}.png", create_dummy_png(f"Image {i+1}"))


class TestLargeImport(unittest.TestCase):
    def test_01_nofile_limit_raised(self):
        """Test that the file descriptor limit (RLIMIT_NOFILE) is raised on startup."""
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        self.assertGreaterEqual(soft, 1024, f"RLIMIT_NOFILE soft limit should be >= 1024, got {soft}")

    def test_02_cbz_processor_support(self):
        """Test that .cbz is natively supported by MangaFileProcessor."""
        test_dir = Path("/tmp/import_test_cbz")
        test_dir.mkdir(parents=True, exist_ok=True)
        try:
            cbz_file = test_dir / "sample_test.cbz"
            create_dummy_cbz(cbz_file, num_pages=3)

            processor = MangaFileProcessor(storage_dir=str(test_dir / "sessions"))
            pages = processor.process_input_file(str(cbz_file), "cbz_sess_1")
            self.assertEqual(len(pages), 3, "CBZ extraction should yield 3 pages")
            self.assertTrue(Path(pages[0]["original_path"]).exists(), "Extracted page file should exist on disk")
        finally:
            shutil.rmtree(str(test_dir), ignore_errors=True)

    def test_03_cbz_upload_endpoint(self):
        """Test uploading a .cbz file through POST /api/upload."""
        cbz_buf = io.BytesIO()
        with zipfile.ZipFile(cbz_buf, "w") as z:
            z.writestr("01.png", create_dummy_png("01"))
            z.writestr("02.png", create_dummy_png("02"))
        cbz_bytes = cbz_buf.getvalue()

        resp = requests.post(
            f"{SERVER_URL}/api/upload",
            files=[("files", ("import_test_comic.cbz", cbz_bytes, "application/vnd.comicbook+zip"))],
            timeout=10
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["total_pages"], 2)
        self.assertIn("import_test_comic.cbz", data["filename"])

    def test_04_directory_import_validation(self):
        """Test error validation for POST /api/import/directory."""
        # Non-existent directory returns 400
        resp = requests.post(
            f"{SERVER_URL}/api/import/directory",
            json={"directory_path": "/tmp/non_existent_folder_abc123"},
            timeout=10
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("does not exist", resp.json()["detail"])

        # Empty directory returns 404 (no supported files found)
        empty_dir = Path("/tmp/import_test_empty")
        empty_dir.mkdir(parents=True, exist_ok=True)
        try:
            resp = requests.post(
                f"{SERVER_URL}/api/import/directory",
                json={"directory_path": str(empty_dir)},
                timeout=10
            )
            self.assertEqual(resp.status_code, 404)
            self.assertIn("No supported ebook files", resp.json()["detail"])
        finally:
            shutil.rmtree(str(empty_dir), ignore_errors=True)

    def test_05_directory_import_execution_and_status(self):
        """Test scanning and importing a folder with naturally sorted ebooks."""
        sub_dir = Path("/tmp/import_test_library_05")
        sub_dir.mkdir(parents=True, exist_ok=True)
        try:
            # Create 4 test files with numeric ordering to verify natural sort (Vol 1, Vol 2, Vol 10)
            create_dummy_cbz(sub_dir / "Manga_Vol_1.cbz", num_pages=2)
            create_dummy_cbz(sub_dir / "Manga_Vol_2.cbz", num_pages=2)
            create_dummy_cbz(sub_dir / "Manga_Vol_10.cbz", num_pages=2)
            create_dummy_zip(sub_dir / "Manga_Vol_3.zip", num_pages=1)

            resp = requests.post(
                f"{SERVER_URL}/api/import/directory",
                json={"directory_path": str(sub_dir), "recursive": False, "max_files": 100},
                timeout=10
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn(data["status"], ("started", "running"))
            self.assertEqual(data["total_scanned_files"], 4)
            import_id = data["import_id"]

            # Poll status until completed
            max_wait = 15
            start_t = time.time()
            final_status = None
            while time.time() - start_t < max_wait:
                stat_resp = requests.get(f"{SERVER_URL}/api/import/status/{import_id}", timeout=5)
                self.assertEqual(stat_resp.status_code, 200)
                status_data = stat_resp.json()
                if status_data["status"] in ("completed", "error", "cancelled"):
                    final_status = status_data
                    break
                time.sleep(0.3)

            self.assertIsNotNone(final_status, "Import should complete within timeout")
            self.assertEqual(final_status["status"], "completed")
            self.assertEqual(final_status["processed_files"], 4)
            self.assertEqual(final_status["failed_files"], 0)
            self.assertEqual(len(final_status["created_session_ids"]), 4)

            # Verify created sessions exist on server
            sess_resp = requests.get(f"{SERVER_URL}/api/sessions", timeout=5)
            self.assertEqual(sess_resp.status_code, 200)
            sessions_map = {s["session_id"]: s for s in sess_resp.json().get("sessions", [])}
            for sid in final_status["created_session_ids"]:
                self.assertIn(sid, sessions_map)
                self.assertGreater(sessions_map[sid]["total_pages"], 0)
        finally:
            shutil.rmtree(str(sub_dir), ignore_errors=True)

    def test_06_directory_import_cancel(self):
        """Test cancelling a directory import task via POST /api/import/cancel/{import_id}."""
        cancel_dir = Path("/tmp/import_test_cancel_06")
        cancel_dir.mkdir(parents=True, exist_ok=True)
        try:
            for i in range(5):
                create_dummy_cbz(cancel_dir / f"test_vol_{i+1}.cbz", num_pages=1)

            resp = requests.post(
                f"{SERVER_URL}/api/import/directory",
                json={"directory_path": str(cancel_dir), "recursive": False, "max_files": 100},
                timeout=10
            )
            self.assertEqual(resp.status_code, 200)
            import_id = resp.json()["import_id"]

            cancel_resp = requests.post(f"{SERVER_URL}/api/import/cancel/{import_id}", timeout=5)
            self.assertEqual(cancel_resp.status_code, 200)
            cancel_data = cancel_resp.json()
            self.assertEqual(cancel_data["status"], "success")

            # Verify status is now cancelled
            stat_resp = requests.get(f"{SERVER_URL}/api/import/status/{import_id}", timeout=5)
            self.assertEqual(stat_resp.status_code, 200)
            self.assertEqual(stat_resp.json()["status"], "cancelled")
        finally:
            shutil.rmtree(str(cancel_dir), ignore_errors=True)

    def test_07_frontend_assets_integration(self):
        """Verify that UI HTML contains modal overlays and controls for large imports."""
        index_path = Path(__file__).resolve().parent.parent / "static" / "index.html"
        self.assertTrue(index_path.exists())
        html_content = index_path.read_text(encoding="utf-8")

        self.assertIn('id="import-progress-modal-overlay"', html_content)
        self.assertIn('id="folder-import-modal-overlay"', html_content)
        self.assertIn('id="doc-queue-filter-wrap"', html_content)
        self.assertIn('id="history-pagination-wrap"', html_content)
        self.assertIn('btn-run-folder-import', html_content)
        self.assertIn('openFolderImportModal()', html_content)

        app_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        self.assertTrue(app_path.exists())
        js_content = app_path.read_text(encoding="utf-8")

        self.assertIn("handleBulkChunkedUpload", js_content)
        self.assertIn("openFolderImportModal", js_content)
        self.assertIn("filterDocumentQueue", js_content)
        self.assertIn("changeHistoryPage", js_content)
        self.assertIn("window.handleBulkChunkedUpload", js_content)
        self.assertIn("window.openFolderImportModal", js_content)


if __name__ == "__main__":
    unittest.main()
