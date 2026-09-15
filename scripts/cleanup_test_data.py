#!/usr/bin/env python3
"""
Test Data Cleanup Utility for Kobean Manga Colorizer.

Purges test sessions, uploaded test files, temporary files, and exported test archives.
Preserves authentic user manga collections (such as Dr. Slump) unless --all is specified.

Usage:
  python scripts/cleanup_test_data.py               # Clean test data & stale test artifacts
  python scripts/cleanup_test_data.py --dry-run     # Preview what will be cleaned
  python scripts/cleanup_test_data.py --all         # Clean ALL sessions & outputs (full reset)
"""

import os
import sys
import json
import glob
import shutil
import argparse
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = PROJECT_ROOT / "sessions"
UPLOADS_DIR = PROJECT_ROOT / "uploads"
OUTPUT_DIR = PROJECT_ROOT / "output"
BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")

TEST_KEYWORDS = [
    "test", "sample", "cancel", "switch", "kindle_test", "batch_test",
    "preview_manga", "exp_page", "test_export", "test_vol"
]

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
    "/tmp/progress_test*"
]


def format_bytes(size_bytes: int) -> str:
    """Formats bytes into human readable string."""
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / (1024 ** 3):.2f} GB"
    elif size_bytes >= 1024 ** 2:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


def get_path_size(path: Path) -> int:
    """Returns size in bytes of a file or directory tree."""
    try:
        if path.is_file() or path.is_symlink():
            return path.stat().st_size
        elif path.is_dir():
            return sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
    except Exception:
        pass
    return 0


def cleanup_via_api(purge_all: bool = False, session_ids: list = None) -> dict:
    """Attempts to trigger server-side cleanup if the server is running."""
    if not requests:
        return None
    try:
        resp = requests.post(
            f"{BASE_URL}/api/test/cleanup",
            json={"purge_all": purge_all, "session_ids": session_ids, "clean_orphans": True},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def run_cleanup(purge_all: bool = False, keep_slump: bool = True, clean_tmp: bool = True, dry_run: bool = False) -> dict:
    """Main cleanup routine."""
    total_freed = 0
    deleted_sessions = []
    deleted_uploads = []
    deleted_outputs = []
    deleted_tmps = []

    # Try API cleanup first if server is running and not dry run
    api_result = None
    if not dry_run:
        api_result = cleanup_via_api(purge_all=purge_all)
        if api_result and api_result.get("status") == "success":
            total_freed += api_result.get("freed_bytes", 0)
            for sid in api_result.get("cleaned_sessions", []):
                deleted_sessions.append((sid, 0))
            for _ in range(api_result.get("cleaned_output_files", 0)):
                deleted_outputs.append(("api_output", 0))

    # 1. Scan and clean sessions
    if SESSIONS_DIR.exists():
        for sess_path in SESSIONS_DIR.iterdir():
            if not sess_path.is_dir():
                continue
            sid = sess_path.name
            meta_file = sess_path / "meta.json"
            fn = ""
            title = ""
            if meta_file.exists():
                try:
                    with open(meta_file, "r", encoding="utf-8") as mf:
                        mdata = json.load(mf)
                        fn = (mdata.get("filename") or "").lower()
                        title = (mdata.get("title") or "").lower()
                except Exception:
                    pass

            is_user_slump = ("slump" in fn or "slump" in title or "slump" in sid.lower())
            if keep_slump and is_user_slump and not purge_all:
                continue

            should_delete = purge_all
            if not should_delete:
                for kw in TEST_KEYWORDS:
                    if kw in sid.lower() or kw in fn or kw in title:
                        should_delete = True
                        break

            if should_delete:
                sz = get_path_size(sess_path)
                total_freed += sz
                deleted_sessions.append((sess_path, sz))
                if not dry_run:
                    shutil.rmtree(str(sess_path), ignore_errors=True)

    # Determine remaining active session IDs
    remaining_sids = set()
    if SESSIONS_DIR.exists():
        for s in SESSIONS_DIR.iterdir():
            if s.is_dir():
                remaining_sids.add(s.name)

    # 2. Scan and clean uploads
    if UPLOADS_DIR.exists():
        for up_file in UPLOADS_DIR.iterdir():
            if not up_file.is_file():
                continue
            name_lower = up_file.name.lower()
            is_slump = "slump" in name_lower
            if keep_slump and is_slump and not purge_all:
                continue

            prefix = up_file.name.split("_")[0]
            should_delete = purge_all
            if not should_delete:
                if any(kw in name_lower for kw in TEST_KEYWORDS):
                    should_delete = True
                elif prefix not in remaining_sids:
                    should_delete = True

            if should_delete:
                sz = get_path_size(up_file)
                total_freed += sz
                deleted_uploads.append((up_file, sz))
                if not dry_run:
                    up_file.unlink(missing_ok=True)

    # 3. Scan and clean output archives
    if OUTPUT_DIR.exists():
        for out_file in OUTPUT_DIR.iterdir():
            if not out_file.is_file():
                continue
            name_lower = out_file.name.lower()
            is_slump = "slump" in name_lower
            if keep_slump and is_slump and not purge_all:
                continue

            prefix = out_file.name.split("_")[0]
            should_delete = purge_all
            if not should_delete:
                if any(kw in name_lower for kw in TEST_KEYWORDS):
                    should_delete = True
                elif name_lower.startswith("combined_") or name_lower.startswith("batch_"):
                    # Delete test combined & batch exports
                    if any(kw in name_lower for kw in ["test", "sample", "cancel", "switch", "progress", "kindle"]):
                        should_delete = True
                elif prefix not in remaining_sids:
                    should_delete = True

            if should_delete:
                sz = get_path_size(out_file)
                total_freed += sz
                deleted_outputs.append((out_file, sz))
                if not dry_run:
                    out_file.unlink(missing_ok=True)

    # 4. Clean /tmp test files
    if clean_tmp:
        for pat in TMP_TEST_PATTERNS:
            for tmp_path_str in glob.glob(pat):
                t_path = Path(tmp_path_str)
                sz = get_path_size(t_path)
                total_freed += sz
                deleted_tmps.append((t_path, sz))
                if not dry_run:
                    if t_path.is_dir():
                        shutil.rmtree(str(t_path), ignore_errors=True)
                    else:
                        t_path.unlink(missing_ok=True)

    return {
        "dry_run": dry_run,
        "freed_bytes": total_freed,
        "freed_formatted": format_bytes(total_freed),
        "sessions_count": len(deleted_sessions),
        "uploads_count": len(deleted_uploads),
        "outputs_count": len(deleted_outputs),
        "tmps_count": len(deleted_tmps),
        "api_used": api_result is not None
    }


def main():
    parser = argparse.ArgumentParser(description="Clean up test data and stale artifacts.")
    parser.add_argument("--all", action="store_true", help="Purge ALL sessions and outputs (full reset).")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be cleaned without deleting.")
    parser.add_argument("--no-tmp", action="store_true", help="Skip cleaning temporary files in /tmp.")
    args = parser.parse_args()

    action = "SIMULATING CLEANUP (DRY-RUN)" if args.dry_run else "CLEANING TEST DATA"
    print(f"=== {action} ===")

    res = run_cleanup(
        purge_all=args.all,
        keep_slump=not args.all,
        clean_tmp=not args.no_tmp,
        dry_run=args.dry_run
    )

    print(f"Sessions cleaned:   {res['sessions_count']}")
    print(f"Uploads cleaned:    {res['uploads_count']}")
    print(f"Outputs cleaned:    {res['outputs_count']}")
    print(f"Temp files cleaned: {res['tmps_count']}")
    print(f"Total space freed:  {res['freed_formatted']}")
    if res['api_used']:
        print("Server in-memory state was also synced via API.")
    print("=== Cleanup Complete ===")


if __name__ == "__main__":
    main()
