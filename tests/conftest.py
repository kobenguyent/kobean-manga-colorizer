"""
Pytest configuration and automatic test data cleanup for Kobean Manga Colorizer.

Automatically tracks and purges all test sessions, uploaded files, temporary files,
and exported artifacts generated during test execution.

Pass --keep-test-data to pytest to retain test artifacts for debugging:
  pytest --keep-test-data
"""

import glob
import json
import os
import shutil
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
    "/tmp/dummy.*",
    "/tmp/dummy_*",
    "/tmp/import_test*",
    "/tmp/manga_test*",
    "/tmp/cancel_test*",
    "/tmp/switch_test*",
    "/tmp/exp_page*",
    "/tmp/batch_test*",
    "/tmp/kindle_test*",
    "/tmp/test_export*",
    "/tmp/single_image_test*",
    "/tmp/progress_test*",
    "/tmp/colorized_manga_output.*",
    "/tmp/colorized_out.*",
    "/tmp/colorized_test_*",
    "/tmp/original_test_*",
    "/tmp/combined_test_*",
    "/tmp/pure_resnext_*",
    "/tmp/resnext_*",
    "/tmp/verified_*",
    "/tmp/multicolor_test*",
    "/tmp/huge_*",
    "/tmp/omnibus_*",
    "/tmp/test_*",
    "/tmp/*bulk_manga_page*",
    "/tmp/bulk_*",
    "/tmp/*test*.png",
    "/tmp/*test*.jpg",
    "/tmp/*test*.jpeg",
    "/tmp/*test*.webp",
    "/tmp/*test*.pdf",
    "/tmp/*test*.epub",
    "/tmp/*test*.mobi",
    "/tmp/*test*.zip",
    "/tmp/*test*.cbz",
]

TEST_KEYWORDS = [
    "test",
    "sample",
    "dummy",
    "cancel",
    "switch",
    "kindle",
    "batch",
    "preview",
    "exp_page",
    "manga_vol",
    "manga_volume",
    "vol_01",
    "vol_02",
    "vol_03",
    "api_split",
    "api_orig_sync",
    "sess_epub",
    "sess_pdf",
    "sess_mobi",
    "import_test",
    "split_test",
    "custom_size",
    "huge_omnibus",
    "omnibus_200mb",
    "huge_manga",
    "single_original",
    "multi_original",
    "epic_manga",
    "amazon_kindle",
    "progress_test",
    "single_image_test",
    "ranma",
    "inuyasha",
    "resnext",
    "multicolor",
    "skip_colored",
    "bulk_manga_page",
    "bulk_manga",
    "bulk",
]


def is_authentic_user_manga(name: str = "", title: str = "", sid: str = "") -> bool:
    """Identifies authentic user manga collections (such as Dr. Slump or One Piece)
    that must be preserved."""
    text = f"{name} {title} {sid}".lower()
    test_markers = [
        "test",
        "sample",
        "dummy",
        "api_orig_sync",
        "api_split",
        "import_test",
        "split_test",
        "custom_size",
    ]
    if any(m in text for m in test_markers):
        return False

    if "slump" in text:
        return True
    if "one piece" in text or "onepiece" in text or "eiichiro oda" in text:
        return True
    return False


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
    seen = set()
    for pattern in TMP_TEST_PATTERNS:
        for fpath in glob.glob(pattern):
            if fpath in seen:
                continue
            seen.add(fpath)
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
                timeout=5,
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
                    with open(meta_path, encoding="utf-8") as f:
                        data = json.load(f)
                        fn = (data.get("filename") or "").lower()
                        title = (data.get("title") or "").lower()
                except Exception:
                    pass

            # Never delete authentic user manga
            if is_authentic_user_manga(name=fn, title=title, sid=sid):
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
            if is_authentic_user_manga(name=name_lower):
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
            if is_authentic_user_manga(name=name_lower):
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
