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

import argparse
import glob
import json
import os
import shutil
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
]

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


def is_authentic_user_manga(name: str = "", title: str = "", sid: str = "") -> bool:
    """Identifies authentic user manga collections (such as Dr. Slump or One Piece)
    that must be preserved by default unless --all is specified."""
    text = f"{name} {title} {sid}".lower()
    # Explicit test markers always take precedence (e.g. api_orig_sync_OnePiece_Vol_01)
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

    # Authentic user manga series
    if "slump" in text:
        return True
    if "one piece" in text or "onepiece" in text or "eiichiro oda" in text:
        return True
    return False


def format_bytes(size_bytes: int) -> str:
    """Formats bytes into human readable string."""
    if size_bytes >= 1024**3:
        return f"{size_bytes / (1024**3):.2f} GB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / (1024**2):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


def get_path_size(path: Path) -> int:
    """Returns size in bytes of a file or directory tree."""
    try:
        if path.is_file() or path.is_symlink():
            return path.stat().st_size
        elif path.is_dir():
            return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
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
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def run_cleanup(
    purge_all: bool = False,
    keep_slump: bool = True,
    clean_tmp: bool = True,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
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
                deleted_sessions.append((Path(sid), 0))
            for _ in range(api_result.get("cleaned_output_files", 0)):
                deleted_outputs.append((Path("api_output"), 0))

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
                    with open(meta_file, encoding="utf-8") as mf:
                        mdata = json.load(mf)
                        fn = (mdata.get("filename") or "").lower()
                        title = (mdata.get("title") or "").lower()
                except Exception:
                    pass

            is_user = is_authentic_user_manga(name=fn, title=title, sid=sid)
            if keep_slump and is_user and not purge_all:
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
            is_user = is_authentic_user_manga(name=name_lower)
            if keep_slump and is_user and not purge_all:
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
            is_user = is_authentic_user_manga(name=name_lower)
            if keep_slump and is_user and not purge_all:
                continue

            prefix = out_file.name.split("_")[0]
            should_delete = purge_all
            if not should_delete:
                if any(kw in name_lower for kw in TEST_KEYWORDS):
                    should_delete = True
                elif name_lower.startswith("combined_") or name_lower.startswith("batch_"):
                    # Delete combined & batch outputs unless they belong to authentic user collections
                    if not is_user:
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
        seen_tmps = set()
        for pat in TMP_TEST_PATTERNS:
            for tmp_path_str in glob.glob(pat):
                if tmp_path_str in seen_tmps:
                    continue
                seen_tmps.add(tmp_path_str)
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
        "deleted_sessions": [str(p[0]) for p in deleted_sessions],
        "deleted_uploads": [str(p[0]) for p in deleted_uploads],
        "deleted_outputs": [str(p[0]) for p in deleted_outputs],
        "deleted_tmps": [str(p[0]) for p in deleted_tmps],
        "api_used": api_result is not None,
    }


def main():
    parser = argparse.ArgumentParser(description="Clean up test data and stale artifacts.")
    parser.add_argument(
        "--all", action="store_true", help="Purge ALL sessions and outputs (full reset)."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would be cleaned without deleting."
    )
    parser.add_argument(
        "--no-tmp", action="store_true", help="Skip cleaning temporary files in /tmp."
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Display individual deleted file paths."
    )
    args = parser.parse_args()

    action = "SIMULATING CLEANUP (DRY-RUN)" if args.dry_run else "CLEANING TEST DATA"
    print(f"=== {action} ===")

    res = run_cleanup(
        purge_all=args.all,
        keep_slump=not args.all,
        clean_tmp=not args.no_tmp,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )

    print(f"Sessions cleaned:   {res['sessions_count']}")
    print(f"Uploads cleaned:    {res['uploads_count']}")
    print(f"Outputs cleaned:    {res['outputs_count']}")
    print(f"Temp files cleaned: {res['tmps_count']}")
    print(f"Total space freed:  {res['freed_formatted']}")
    if res["api_used"]:
        print("Server in-memory state was also synced via API.")

    if args.verbose:
        if res["deleted_sessions"]:
            print("\nCleaned Sessions:")
            for s in res["deleted_sessions"]:
                print(f"  - {s}")
        if res["deleted_uploads"]:
            print("\nCleaned Uploads:")
            for u in res["deleted_uploads"]:
                print(f"  - {u}")
        if res["deleted_outputs"]:
            print("\nCleaned Outputs:")
            for o in res["deleted_outputs"]:
                print(f"  - {o}")
        if res["deleted_tmps"]:
            print("\nCleaned /tmp files:")
            for t in res["deleted_tmps"]:
                print(f"  - {t}")

    print("=== Cleanup Complete ===")


if __name__ == "__main__":
    main()
