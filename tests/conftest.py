"""
Pytest configuration and automatic test data cleanup for Kobean Manga Colorizer.

Automatically tracks and purges all test sessions, uploaded files, temporary files,
and exported artifacts generated during test execution.

Pass --keep-test-data to pytest to retain test artifacts for debugging:
  pytest --keep-test-data
"""

import os
import sys
import glob
import shutil
import json
from pathlib import Path
import pytest

try:
    import requests
except ImportError:
    requests = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = PROJECT_ROOT / "sessions"
UPLOADS_DIR = PROJECT_ROOT / "uploads"
OUTPUT_DIR = PROJECT_ROOT / "output"
BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

TMP_TEST_PATTERNS = [
    "/tmp/sample_*",
    "/tmp/*test*.png",
    "/tmp/*test*.pdf",
    "/tmp/*test*.epub",
    "/tmp/*test*.mobi",
    "/tmp/manga_test*",
    "/tmp/cancel_test*",
    "/tmp/switch_test*",
    "/tmp/exp_page*",
    "/tmp/batch_test*",
    "/tmp/kindle_test*",
    "/tmp/test_export*",
    "/tmp/single_image_test*",
    "/tmp/progress_test*",
    "/tmp/import_test*"
]

TEST_KEYWORDS = [
    "test", "sample", "cancel", "switch", "kindle_test", "batch_test",
    "preview_manga", "exp_page", "test_export", "test_vol", "import_test"
]


def pytest_addoption(parser):
    """Add command line flag to optionally preserve test artifacts."""
    parser.addoption(
        "--keep-test-data",
        action="store_true",
        default=False,
        help="Do not clean up test sessions and files after test execution (preserves data for debugging).",
    )


def clean_tmp_files():
    """Removes test files created in /tmp."""
    for pattern in TMP_TEST_PATTERNS:
        for fpath in glob.glob(pattern):
            try:
                p = Path(fpath)
                if p.is_file() or p.is_symlink():
                    p.unlink(missing_ok=True)
                elif p.is_dir():
                    shutil.rmtree(str(p), ignore_errors=True)
            except Exception:
                pass


def purge_test_data():
    """Purges all test sessions, uploaded files, and output archives."""
    # 1. Clean via API if server is alive
    if requests:
        try:
            requests.post(
                f"{BASE_URL}/api/test/cleanup",
                json={"purge_all": False, "clean_orphans": True},
                timeout=5
            )
        except Exception:
            pass

    # 2. Filesystem sweep for test sessions
    if SESSIONS_DIR.exists():
        for sess_dir in SESSIONS_DIR.iterdir():
            if not sess_dir.is_dir():
                continue
            sid = sess_dir.name
            meta_path = sess_dir / "meta.json"
            fn, title = "", ""
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        fn = (data.get("filename") or "").lower()
                        title = (data.get("title") or "").lower()
                except Exception:
                    pass

            # Never delete user manga like Dr. Slump
            if "slump" in fn or "slump" in title or "slump" in sid.lower():
                continue

            is_test = False
            for kw in TEST_KEYWORDS:
                if kw in sid.lower() or kw in fn or kw in title:
                    is_test = True
                    break

            if is_test:
                shutil.rmtree(str(sess_dir), ignore_errors=True)

    # 3. Filesystem sweep for test uploads & outputs
    active_sids = set()
    if SESSIONS_DIR.exists():
        for d in SESSIONS_DIR.iterdir():
            if d.is_dir():
                active_sids.add(d.name)

    if UPLOADS_DIR.exists():
        for f in UPLOADS_DIR.iterdir():
            if not f.is_file():
                continue
            name_lower = f.name.lower()
            if "slump" in name_lower:
                continue
            prefix = f.name.split("_")[0]
            if any(kw in name_lower for kw in TEST_KEYWORDS) or prefix not in active_sids:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    if OUTPUT_DIR.exists():
        for f in OUTPUT_DIR.iterdir():
            if not f.is_file():
                continue
            name_lower = f.name.lower()
            if "slump" in name_lower:
                continue
            prefix = f.name.split("_")[0]
            if any(kw in name_lower for kw in TEST_KEYWORDS) or prefix not in active_sids:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass

    # 4. Clean tmp files
    clean_tmp_files()


@pytest.fixture(autouse=True)
def per_test_cleanup(request):
    """Automatically cleans temporary files after each test."""
    yield
    if not request.config.getoption("--keep-test-data"):
        clean_tmp_files()


def pytest_sessionfinish(session, exitstatus):
    """Hook executed once after all tests in the session complete."""
    if not session.config.getoption("--keep-test-data"):
        purge_test_data()
