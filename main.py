#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Auto-respawn in local venv if executed by system python lacking dependencies
if __name__ == "__main__":
    _curr_dir = Path(__file__).resolve().parent
    _venv_py = _curr_dir / ".venv" / "bin" / "python3"
    if not _venv_py.exists():
        _venv_py = _curr_dir / "venv" / "bin" / "python3"
    if _venv_py.exists() and sys.executable != str(_venv_py):
        try:
            import fastapi  # noqa: F401
            import uvicorn  # noqa: F401
        except ImportError:
            os.execv(str(_venv_py), [str(_venv_py)] + sys.argv)


import asyncio
import copy
import json
import re
import shutil
import uuid
from typing import Any, Optional

from fastapi import (
    BackgroundTasks,
    Body,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from colorizer_engine import (
    CharacterEntry,
    CharacterPalette,
    MangaColorizerEngine,
    is_colored_page,
)
from file_processor import MangaFileProcessor
from manga_presets import (
    detect_manga_preset,
    get_all_presets,
    get_preset_by_id,
    search_online_manga_preset,
)
from series_memory import (
    LearnedCharacterTrait,
    SeriesMemory,
    SeriesMemoryBank,
    derive_series_key,
)

app = FastAPI(title="Manga Colorizer Pro", version="1.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent.resolve()
UPLOAD_DIR = BASE_DIR / "uploads"
STORAGE_DIR = BASE_DIR / "sessions"
OUTPUT_DIR = BASE_DIR / "output"
STATIC_DIR = BASE_DIR / "static"

for d in [UPLOAD_DIR, STORAGE_DIR, OUTPUT_DIR, STATIC_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Increase open file descriptors limit for handling +1076 ebook files simultaneously
try:
    import resource

    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = min(hard, 65536) if hard > 0 else 65536
    resource.setrlimit(resource.RLIMIT_NOFILE, (target, hard))
except Exception as e:
    print(f"[Resource Note] RLIMIT_NOFILE could not be raised: {e}")

# Instantiate core engines
file_processor = MangaFileProcessor(storage_dir=str(STORAGE_DIR))
colorizer_engine = MangaColorizerEngine()
SERIES_BANK = SeriesMemoryBank(STORAGE_DIR / "series_memory.json")

# Session state store
# session_id -> { "file_path": str, "filename": str, "ext": str, "pages": [...], "status": "idle"|"processing"|"completed", "progress": {...} }
SESSIONS: dict[str, dict] = {}
# session_id -> asyncio.Queue for SSE events
EVENT_QUEUES: dict[str, list[asyncio.Queue]] = {}

# Active Colorization Tasks tracker
# session_id -> asyncio.Task
ACTIVE_COLORIZATION_TASKS: dict[str, asyncio.Task] = {}


def is_task_active(session_id: str) -> bool:
    """Returns True if an asyncio background task is currently running for session_id."""
    task = ACTIVE_COLORIZATION_TASKS.get(session_id)
    return task is not None and not task.done()

# Background Directory Import Tasks tracker
# import_id -> { "import_id": str, "status": "running"|"completed"|"cancelled"|"failed", ... }
IMPORT_TASKS: dict[str, Any] = {}

# Global Active Batch Tracking
CURRENT_BATCH: dict[str, Any] = {
    "is_running": False,
    "total_docs": 0,
    "completed_docs": 0,
    "current_index": 0,
    "current_session_id": None,
    "session_ids": [],
}


def save_session_meta(session_id: str):
    """Persists session state to meta.json on disk to survive server restarts."""
    sess = SESSIONS.get(session_id)
    if not sess:
        return
    if "pages" in sess:
        actual_count = sum(1 for p in sess["pages"] if p.get("status") == "colorized")
        sess["processed_count"] = actual_count
        if sess.get("total_pages") and actual_count >= sess["total_pages"]:
            sess["status"] = "completed"
    sess_dir = STORAGE_DIR / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    meta_path = sess_dir / "meta.json"
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(sess, f, indent=2)
    except Exception as e:
        print(f"[Session Warning] Failed to write meta.json: {e}")


def get_or_restore_session(session_id: str) -> Optional[dict]:
    """Retrieves session from memory, or restores from disk if server restarted."""
    sess = None
    if session_id in SESSIONS:
        sess = SESSIONS[session_id]
    else:
        sess_dir = STORAGE_DIR / session_id
        if not sess_dir.exists():
            return None

        meta_path = sess_dir / "meta.json"
        if meta_path.exists():
            try:
                with open(meta_path, encoding="utf-8") as f:
                    sess = json.load(f)
                    if "pages" in sess:
                        sess["processed_count"] = sum(
                            1 for p in sess["pages"] if p.get("status") == "colorized"
                        )
                    if not sess.get("detected_preset") and sess.get("filename"):
                        detected = detect_manga_preset(sess["filename"])
                        if detected:
                            sess["detected_preset"] = detected.id
                            sess["preset_title"] = detected.title
                            if not sess.get("recommended_style") and detected.recommended_style:
                                sess["recommended_style"] = detected.recommended_style
                    if session_id not in SESSION_PALETTES:
                        _get_palette(session_id)
                    SESSIONS[session_id] = sess
                    if session_id not in EVENT_QUEUES:
                        EVENT_QUEUES[session_id] = []
            except Exception as e:
                print(f"[Session Warning] Error loading meta.json for {session_id}: {e}")

        # Fallback auto-recovery from disk session folders
        if not sess:
            orig_dir = sess_dir / "original"
            if orig_dir.exists():
                orig_files = sorted(orig_dir.glob("*.*"))
                if orig_files:
                    pages = []
                    colorized_dir = sess_dir / "colorized"
                    for idx, p_path in enumerate(orig_files):
                        c_path = colorized_dir / p_path.name
                        is_colored = c_path.exists()
                        pages.append(
                            {
                                "page_index": idx,
                                "display_name": f"Page {idx + 1}",
                                "filename": p_path.name,
                                "original_path": str(p_path),
                                "status": "colorized" if is_colored else "pending",
                                "colorized_url": f"/api/session/{session_id}/image/colorized/{p_path.name}"
                                if is_colored
                                else None,
                                "engine_used": "ResNeXt-50/101 Generator + Vibrant Chroma (MPS)"
                                if is_colored
                                else None,
                            }
                        )
                    recovered = {
                        "session_id": session_id,
                        "filename": orig_files[0].name,
                        "file_path": str(orig_files[0]),
                        "ext": orig_files[0].suffix.lower(),
                        "total_pages": len(pages),
                        "pages": pages,
                        "status": "completed" if all(p["status"] == "colorized" for p in pages) else "idle",
                        "processed_count": sum(1 for p in pages if p["status"] == "colorized"),
                        "model_provider": "resnext_generator",
                        "model_name": "resnext-v2-manga",
                    }
                    SESSIONS[session_id] = recovered
                    if session_id not in EVENT_QUEUES:
                        EVENT_QUEUES[session_id] = []
                    save_session_meta(session_id)
                    sess = recovered

    if sess:
        # Sanitize dangling processing status if no task is actually running
        if sess.get("status") == "processing" and not is_task_active(session_id):
            pages = sess.get("pages", [])
            actual_count = sum(1 for p in pages if p.get("status") == "colorized")
            sess["processed_count"] = actual_count
            total = sess.get("total_pages", len(pages))
            if total > 0 and actual_count >= total:
                sess["status"] = "completed"
            elif actual_count > 0:
                sess["status"] = "pending"
            else:
                sess["status"] = "idle"

            # Reset any page that was mid-flight back to pending
            for p in pages:
                if p.get("status") == "processing":
                    p["status"] = "pending"
            save_session_meta(session_id)

        return sess

    return None


class ColorizeRequest(BaseModel):
    session_id: str
    model_provider: str = "google_nano"  # "google_nano", "apple_foundation", "local_smart"
    model_name: str = "nano-banana"
    api_key: Optional[str] = ""
    style: str = "gemini_anime"
    saturation: float = 1.2
    contrast: float = 1.1
    line_preserve: float = 0.85
    selected_pages: Optional[list[int]] = None
    skip_if_colored: bool = False
    force_recolorize: bool = False  # when True, re-run even if page already has a colorized file
    denoise_screentone: bool = True
    denoise_sigma: int = 25
    recognition_mode: Optional[str] = "auto"


class BatchColorizeRequest(BaseModel):
    session_ids: list[str]
    model_provider: str = "google_nano"
    model_name: str = "nano-banana"
    api_key: Optional[str] = ""
    style: str = "gemini_anime"
    saturation: float = 1.2
    contrast: float = 1.1
    line_preserve: float = 0.85
    skip_if_colored: bool = False
    denoise_screentone: bool = True
    denoise_sigma: int = 25
    recognition_mode: Optional[str] = "auto"


class BatchExportRequest(BaseModel):
    session_ids: list[str]
    format: Optional[str] = "auto"


class CombinedExportRequest(BaseModel):
    session_ids: Optional[list[str]] = None
    format: str = "epub"  # "epub", "mobi", "pdf"
    title: Optional[str] = "Colorized Manga Collection"
    sync: Optional[bool] = False
    chunk_by: Optional[str] = "none"  # "none", "volumes", "size_mb"
    chunk_size: Optional[int] = 3  # e.g. 3 volumes or 400 MB
    max_dimension: Optional[int] = 1600  # 1600 (Kindle optimal), 1920 (Tablet), 0 (Original)
    jpeg_quality: Optional[int] = 80  # 80 (E-reader recommended), 85, 90
    grayscale: Optional[bool] = False  # true for 16-level e-ink optimization
    colorsoft_tune: Optional[bool] = (
        False  # true for Kindle Colorsoft / Color E-Ink vibrancy & contrast boost
    )
    export_original: Optional[bool] = (
        False  # true to export original manga pages directly without colorization
    )


class TestCleanupRequest(BaseModel):
    session_ids: Optional[list[str]] = None
    purge_all: Optional[bool] = False
    clean_orphans: Optional[bool] = True


class BulkDeleteSessionsRequest(BaseModel):
    session_ids: Optional[list[str]] = None
    delete_all: Optional[bool] = False


class DirectoryImportRequest(BaseModel):
    directory_path: str
    recursive: Optional[bool] = False
    batch_id: Optional[str] = None
    max_files: Optional[int] = 5000
    run_async: Optional[bool] = True


class PreviewRequest(BaseModel):
    session_id: str
    page_index: int = 0
    model_provider: str = "google_nano"
    model_name: str = "nano-banana"
    api_key: Optional[str] = ""
    style: str = "gemini_anime"
    saturation: float = 1.2
    contrast: float = 1.1
    line_preserve: float = 0.85
    skip_if_colored: bool = False
    force_recolorize: bool = False
    denoise_screentone: bool = True
    denoise_sigma: int = 25
    active_character_names: Optional[list[str]] = None
    recognition_mode: Optional[str] = "auto"


# ── Character Palette models ─────────────────────────────────────────


class CharacterEntryModel(BaseModel):
    name: str
    hair_hex: str = ""
    skin_hex: str = ""
    costume_hex: str = ""
    extra_hex: str = ""
    eye_hex: str = ""
    notes: str = ""
    visual_traits: Optional[list[str]] = None
    keywords: Optional[list[str]] = None
    bounding_box: Optional[list[float]] = None



class CharacterRecognizeRequest(BaseModel):
    api_key: Optional[str] = ""
    model_name: Optional[str] = ""
    recognition_mode: Optional[str] = "auto"


class PaletteUpsertRequest(BaseModel):
    session_id: str
    character: CharacterEntryModel


class PaletteDeleteRequest(BaseModel):
    session_id: str
    character_name: str


class PaletteApplyPresetRequest(BaseModel):
    session_id: str
    preset_id: str


class PaletteOnlineSearchRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class LearnPageRequest(BaseModel):
    session_id: str
    page_index: int
    character_names: Optional[list[str]] = None
    exemplar: bool = True


class PinExemplarRequest(BaseModel):
    series_key: str
    page_index: int
    pinned: bool = True


class TrainSeriesAdapterRequest(BaseModel):
    series_key: Optional[str] = None
    steps: int = 100
    lr: float = 2e-4


class AutoRefineSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    threshold: Optional[float] = None
    interval: Optional[int] = None




# In-memory palette store: session_id -> CharacterPalette
SESSION_PALETTES: dict[str, CharacterPalette] = {}


def save_session_palette(session_id: str, palette: CharacterPalette):
    """Saves the palette to palette.json in the session directory."""
    sess_dir = STORAGE_DIR / session_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    pal_path = sess_dir / "palette.json"
    try:
        with open(pal_path, "w", encoding="utf-8") as f:
            json.dump(palette.to_dict(), f, indent=2)
    except Exception as e:
        print(f"[Palette Warning] Failed to write palette.json for {session_id}: {e}")


def _resolve_base_palette(session_id: str) -> CharacterPalette:
    """Resolves the raw base palette for a session from memory or disk."""
    if session_id in SESSION_PALETTES:
        pal = SESSION_PALETTES[session_id]
        sess = SESSIONS.get(session_id)
        if pal.characters:
            # Backfill eye_hex if missing from older sessions
            preset_ref = None
            if pal.preset_id:
                preset_ref = get_preset_by_id(pal.preset_id)
            elif sess and sess.get("detected_preset"):
                preset_ref = get_preset_by_id(sess["detected_preset"])
            if preset_ref:
                preset_map = {pc.name.lower().strip(): pc for pc in preset_ref.characters}
                need_save = False
                for c in pal.characters:
                    if not getattr(c, "eye_hex", ""):
                        match = preset_map.get(c.name.lower().strip())
                        if match and getattr(match, "eye_hex", ""):
                            c.eye_hex = match.eye_hex
                            need_save = True
                if need_save:
                    save_session_palette(session_id, pal)
            return pal
        detected = None
        if pal.preset_id:
            detected = get_preset_by_id(pal.preset_id)
        elif sess and sess.get("detected_preset"):
            detected = get_preset_by_id(sess["detected_preset"])
        elif sess and sess.get("filename"):
            detected = detect_manga_preset(sess["filename"])
        if detected:
            pal = CharacterPalette(
                characters=[
                    CharacterEntry(
                        name=c.name,
                        hair_hex=c.hair_hex,
                        skin_hex=c.skin_hex,
                        costume_hex=c.costume_hex,
                        extra_hex=c.extra_hex,
                        eye_hex=getattr(c, "eye_hex", ""),
                    )
                    for c in detected.characters
                ],
                preset_id=detected.id,
                preset_title=detected.title,
            )
            SESSION_PALETTES[session_id] = pal
            save_session_palette(session_id, pal)
            return pal
        return pal

    # Try loading from disk
    pal_path = STORAGE_DIR / session_id / "palette.json"
    if pal_path.exists():
        try:
            with open(pal_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                pal = CharacterPalette.from_dict(d)
                sess = SESSIONS.get(session_id)
                if not pal.characters:
                    detected = None
                    if pal.preset_id:
                        detected = get_preset_by_id(pal.preset_id)
                    elif sess and sess.get("detected_preset"):
                        detected = get_preset_by_id(sess["detected_preset"])
                    elif sess and sess.get("filename"):
                        detected = detect_manga_preset(sess["filename"])
                    if detected:
                        pal = CharacterPalette(
                            characters=[
                                CharacterEntry(
                                    name=c.name,
                                    hair_hex=c.hair_hex,
                                    skin_hex=c.skin_hex,
                                    costume_hex=c.costume_hex,
                                    extra_hex=c.extra_hex,
                                    eye_hex=getattr(c, "eye_hex", ""),
                                )
                                for c in detected.characters
                            ],
                            preset_id=detected.id,
                            preset_title=detected.title,
                        )
                        save_session_palette(session_id, pal)
                else:
                    # Backfill eye_hex if missing from existing palette.json
                    preset_ref = None
                    if pal.preset_id:
                        preset_ref = get_preset_by_id(pal.preset_id)
                    elif sess and sess.get("detected_preset"):
                        preset_ref = get_preset_by_id(sess["detected_preset"])
                    if preset_ref:
                        preset_map = {pc.name.lower().strip(): pc for pc in preset_ref.characters}
                        need_save = False
                        for c in pal.characters:
                            if not getattr(c, "eye_hex", ""):
                                match = preset_map.get(c.name.lower().strip())
                                if match and getattr(match, "eye_hex", ""):
                                    c.eye_hex = match.eye_hex
                                    need_save = True
                        if need_save:
                            save_session_palette(session_id, pal)
                SESSION_PALETTES[session_id] = pal
                return pal
        except Exception as e:
            print(f"[Palette Warning] Failed to read palette.json for {session_id}: {e}")

    # Fallback: check if session has a filename and auto-detect
    sess = SESSIONS.get(session_id)
    if sess and sess.get("filename"):
        detected = detect_manga_preset(sess["filename"])
        if detected:
            pal = CharacterPalette(
                characters=[
                    CharacterEntry(
                        name=c.name,
                        hair_hex=c.hair_hex,
                        skin_hex=c.skin_hex,
                        costume_hex=c.costume_hex,
                        extra_hex=c.extra_hex,
                        eye_hex=getattr(c, "eye_hex", ""),
                    )
                    for c in detected.characters
                ],
                preset_id=detected.id,
                preset_title=detected.title,
            )
            SESSION_PALETTES[session_id] = pal
            save_session_palette(session_id, pal)
            sess["detected_preset"] = detected.id
            sess["preset_title"] = detected.title
            return pal

    new_pal = CharacterPalette()
    SESSION_PALETTES[session_id] = new_pal
    return new_pal


def _apply_series_memory_to_palette(session_id: str, pal: CharacterPalette) -> CharacterPalette:
    """Merges learned traits from SeriesMemory into the session's active palette."""
    sess = SESSIONS.get(session_id)
    fn = ""
    pid = pal.preset_id
    if sess:
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = pid or sess.get("detected_preset")
    if fn or pid:
        s_key, _ = derive_series_key(fn, pid)
        mem = SERIES_BANK.get_memory(s_key)
        if mem and mem.characters:
            return pal.apply_series_memory(mem)
    return pal


def _get_palette(session_id: str) -> CharacterPalette:
    """Returns the palette for a session, dynamically enhanced with learned series memory."""
    pal = _resolve_base_palette(session_id)
    return _apply_series_memory_to_palette(session_id, pal)


@app.post("/api/upload")
async def upload_files(
    file: Optional[UploadFile] = File(None),
    files: Optional[list[UploadFile]] = File(None),
    batch_id: Optional[str] = Form(None),
):
    upload_list = []
    if files:
        upload_list.extend(files)
    if file:
        upload_list.append(file)

    if not upload_list:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    ALLOWED_EXTENSIONS = [
        ".pdf",
        ".epub",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".gif",
        ".tiff",
        ".zip",
        ".cbz",
    ]
    effective_batch_id = batch_id or str(uuid.uuid4())
    created_sessions = []

    for uploaded_file in upload_list:
        ext = Path(uploaded_file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue

        session_id = str(uuid.uuid4())
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        upload_path = UPLOAD_DIR / f"{session_id}_{uploaded_file.filename}"

        with open(upload_path, "wb") as buffer:
            while chunk := await uploaded_file.read(1024 * 1024):
                buffer.write(chunk)

        try:
            pages_meta = file_processor.process_input_file(str(upload_path), session_id)
        except Exception as e:
            if upload_path.exists():
                upload_path.unlink(missing_ok=True)
            print(f"[Upload Parse Error] {uploaded_file.filename}: {e}")
            continue

        if not pages_meta:
            if upload_path.exists():
                upload_path.unlink(missing_ok=True)
            print(f"[Upload Warning] No readable pages found in {uploaded_file.filename}")
            continue

        for page in pages_meta:
            page["status"] = "pending"
            page["colorized_url"] = None

        detected = detect_manga_preset(uploaded_file.filename)
        detected_preset_id = detected.id if detected else None
        preset_title = detected.title if detected else None

        sess_obj = {
            "session_id": session_id,
            "batch_id": effective_batch_id,
            "filename": uploaded_file.filename,
            "file_path": str(upload_path),
            "ext": ext,
            "total_pages": len(pages_meta),
            "pages": pages_meta,
            "status": "idle",
            "processed_count": 0,
            "model_provider": "google_nano",
            "model_name": "nano-banana",
            "detected_preset": detected_preset_id,
            "preset_title": preset_title,
        }
        if detected:
            if detected.recommended_style:
                sess_obj["recommended_style"] = detected.recommended_style
            pal = CharacterPalette(
                characters=[
                    CharacterEntry(
                        name=c.name,
                        hair_hex=c.hair_hex,
                        skin_hex=c.skin_hex,
                        costume_hex=c.costume_hex,
                        extra_hex=c.extra_hex,
                        eye_hex=getattr(c, "eye_hex", ""),
                    )
                    for c in detected.characters
                ],
                preset_id=detected.id,
                preset_title=detected.title,
            )
            SESSION_PALETTES[session_id] = pal
            save_session_palette(session_id, pal)

        SESSIONS[session_id] = sess_obj
        EVENT_QUEUES[session_id] = []
        save_session_meta(session_id)
        created_sessions.append(sess_obj)

    if not created_sessions:
        raise HTTPException(status_code=400, detail="Failed to parse any of the uploaded files.")

    session_summaries = []
    for s in created_sessions:
        session_summaries.append(
            {
                "session_id": s["session_id"],
                "batch_id": effective_batch_id,
                "filename": s["filename"],
                "ext": s["ext"],
                "total_pages": s["total_pages"],
                "status": s["status"],
                "processed_count": s["processed_count"],
                "detected_preset": s.get("detected_preset"),
                "preset_title": s.get("preset_title"),
            }
        )

    primary = created_sessions[0]
    return JSONResponse(
        {
            "status": "success",
            "batch_id": effective_batch_id,
            "total_files": len(created_sessions),
            "sessions": session_summaries,
            # backward compatibility fields:
            "session_id": primary["session_id"],
            "filename": primary["filename"],
            "total_pages": primary["total_pages"],
            "pages": primary["pages"],
        }
    )


def normalize_directory_path(raw_path: str) -> Path:
    """
    Normalizes a user-supplied directory path from various browser/OS formats:
    - Strips surrounding quotes ("..." or '...')
    - Strips file:// or file: URL schemes
    - Unquotes URL encoded characters (e.g. %20 -> space)
    - Unescapes terminal escaped spaces (e.g. \  -> space)
    - Expands user home directories (~)
    - If a user selected or pointed to a file inside the folder, resolves to its parent folder.
    """
    import urllib.parse
    p = raw_path.strip()
    if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
        p = p[1:-1].strip()
    if p.startswith("file://"):
        p = urllib.parse.unquote(urllib.parse.urlparse(p).path)
    elif p.startswith("file:"):
        p = urllib.parse.unquote(p[5:])
    if "%" in p:
        p = urllib.parse.unquote(p)
    p = p.replace(r"\ ", " ")
    resolved = Path(p).expanduser().resolve()
    if resolved.exists() and resolved.is_file():
        resolved = resolved.parent
    return resolved


@app.post("/api/import/directory")
async def import_directory_endpoint(req: DirectoryImportRequest, background_tasks: BackgroundTasks):
    """
    Imports all supported ebook files (.epub, .pdf, .cbz, .zip, etc.) directly from a local directory path.
    Supports +1076 files, recursive scanning, natural sorting, and asynchronous background progress tracking.
    """
    try:
        dir_path = normalize_directory_path(req.directory_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid directory path format: {req.directory_path} ({e})")

    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Directory does not exist or is not a directory: {req.directory_path} (resolved: {dir_path})",
        )

    ALLOWED_EXTENSIONS = {".pdf", ".epub", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".zip", ".cbz"}

    discovered_files = []
    if req.recursive:
        for root, _, files in os.walk(str(dir_path)):
            for f in files:
                if f.startswith(".") or f.startswith("__MACOSX"):
                    continue
                p = Path(root) / f
                if p.suffix.lower() in ALLOWED_EXTENSIONS:
                    discovered_files.append(p)
    else:
        for item in dir_path.iterdir():
            if item.is_file() and not item.name.startswith("."):
                if item.suffix.lower() in ALLOWED_EXTENSIONS:
                    discovered_files.append(item)

    def _sort_key(p: Path):
        fn = p.name.lower()
        parts = [int(text) if text.isdigit() else text for text in re.split(r'(\d+)', fn)]
        return parts

    discovered_files.sort(key=_sort_key)

    if req.max_files and len(discovered_files) > req.max_files:
        discovered_files = discovered_files[:req.max_files]

    if not discovered_files:
        raise HTTPException(status_code=404, detail=f"No supported ebook files found in {dir_path}")

    import_id = str(uuid.uuid4())
    effective_batch_id = req.batch_id or str(uuid.uuid4())

    task_state = {
        "import_id": import_id,
        "batch_id": effective_batch_id,
        "directory": str(dir_path),
        "status": "running",
        "total_files": len(discovered_files),
        "imported_files": 0,
        "failed_files": 0,
        "current_file": None,
        "created_sessions": [],
        "error": None,
        "cancel_requested": False
    }
    IMPORT_TASKS[import_id] = task_state

    def _process_import():
        for file_p in discovered_files:
            if task_state.get("cancel_requested"):
                task_state["status"] = "cancelled"
                break

            task_state["current_file"] = file_p.name
            ext = file_p.suffix.lower()
            session_id = str(uuid.uuid4())
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            upload_path = UPLOAD_DIR / f"{session_id}_{file_p.name}"

            try:
                shutil.copy2(str(file_p), str(upload_path))
                pages_meta = file_processor.process_input_file(str(upload_path), session_id)
                if not pages_meta:
                    if upload_path.exists():
                        upload_path.unlink(missing_ok=True)
                    task_state["failed_files"] += 1
                    continue

                for page in pages_meta:
                    page["status"] = "pending"
                    page["colorized_url"] = None

                detected = detect_manga_preset(file_p.name)
                detected_preset_id = detected.id if detected else None
                preset_title = detected.title if detected else None

                sess_obj = {
                    "session_id": session_id,
                    "batch_id": effective_batch_id,
                    "filename": file_p.name,
                    "file_path": str(upload_path),
                    "ext": ext,
                    "total_pages": len(pages_meta),
                    "pages": pages_meta,
                    "status": "idle",
                    "processed_count": 0,
                    "model_provider": "google_nano",
                    "model_name": "nano-banana",
                    "detected_preset": detected_preset_id,
                    "preset_title": preset_title,
                }
                if detected:
                    if detected.recommended_style:
                        sess_obj["recommended_style"] = detected.recommended_style
                    pal = CharacterPalette(
                        characters=[
                            CharacterEntry(
                                name=c.name,
                                hair_hex=c.hair_hex,
                                skin_hex=c.skin_hex,
                                costume_hex=c.costume_hex,
                                extra_hex=c.extra_hex,
                                eye_hex=getattr(c, "eye_hex", ""),
                            )
                            for c in detected.characters
                        ],
                        preset_id=detected.id,
                        preset_title=detected.title,
                    )
                    SESSION_PALETTES[session_id] = pal
                    save_session_palette(session_id, pal)

                SESSIONS[session_id] = sess_obj
                EVENT_QUEUES[session_id] = []
                save_session_meta(session_id)
                task_state["imported_files"] += 1
                task_state["created_sessions"].append({
                    "session_id": session_id,
                    "batch_id": effective_batch_id,
                    "filename": file_p.name,
                    "ext": ext,
                    "total_pages": len(pages_meta),
                    "status": "idle",
                    "processed_count": 0,
                    "detected_preset": detected_preset_id,
                    "preset_title": preset_title,
                })
            except Exception as e:
                task_state["failed_files"] += 1
                print(f"[Directory Import Error] {file_p.name}: {e}")
                if upload_path.exists():
                    upload_path.unlink(missing_ok=True)

        if task_state["status"] != "cancelled":
            task_state["status"] = "completed"
        task_state["current_file"] = None

    if req.run_async:
        background_tasks.add_task(_process_import)
        return JSONResponse({
            "status": "started",
            "import_id": import_id,
            "batch_id": effective_batch_id,
            "total_files": len(discovered_files),
            "total_scanned_files": len(discovered_files),
            "message": f"Started background import of {len(discovered_files)} files from {dir_path.name}"
        })
    else:
        _process_import()
        return JSONResponse({
            "status": "completed",
            "import_id": import_id,
            "batch_id": effective_batch_id,
            "total_files": len(discovered_files),
            "total_scanned_files": len(discovered_files),
            "imported_files": task_state["imported_files"],
            "processed_files": task_state["imported_files"] + task_state["failed_files"],
            "failed_files": task_state["failed_files"],
            "created_sessions": task_state["created_sessions"],
            "created_session_ids": [s["session_id"] for s in task_state["created_sessions"]]
        })


@app.get("/api/import/status/{import_id}")
async def get_import_status(import_id: str):
    task = IMPORT_TASKS.get(import_id)
    if not task:
        raise HTTPException(status_code=404, detail="Import task not found")
    total = task.get("total_files", 0)
    imported = task.get("imported_files", 0)
    failed = task.get("failed_files", 0)
    percent = round(((imported + failed) / total * 100), 1) if total > 0 else 0
    return JSONResponse({
        **task,
        "percent": percent,
        "progress_percent": percent,
        "total_scanned_files": total,
        "processed_files": imported + failed,
        "created_session_ids": [s["session_id"] for s in task.get("created_sessions", [])]
    })


@app.post("/api/import/cancel/{import_id}")
async def cancel_import_task(import_id: str):
    task = IMPORT_TASKS.get(import_id)
    if not task:
        raise HTTPException(status_code=404, detail="Import task not found")
    task["cancel_requested"] = True
    task["status"] = "cancelled"
    return JSONResponse({
        "status": "success",
        "message": f"Import task {import_id} cancelled"
    })


@app.get("/api/import/validate-directory")
async def validate_directory_endpoint(path: str = Query(...)):
    """
    Validates a directory path, normalizes it, and counts supported ebook files.
    Used for instant live UI feedback when choosing or pasting a folder path.
    """
    if not path or not path.strip():
        return JSONResponse({"valid": False, "error": "Path is empty"})

    try:
        dir_path = normalize_directory_path(path)
    except Exception as e:
        return JSONResponse({"valid": False, "error": f"Invalid format: {e}"})

    if not dir_path.exists():
        return JSONResponse({
            "valid": False,
            "error": "Directory does not exist",
            "resolved_path": str(dir_path),
        })

    if not dir_path.is_dir():
        return JSONResponse({
            "valid": False,
            "error": "Path is not a directory",
            "resolved_path": str(dir_path),
        })

    ALLOWED_EXTENSIONS = {".pdf", ".epub", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".zip", ".cbz"}
    sample_files = []
    file_count = 0

    try:
        for item in dir_path.iterdir():
            if item.is_file() and not item.name.startswith(".") and item.suffix.lower() in ALLOWED_EXTENSIONS:
                file_count += 1
                if len(sample_files) < 5:
                    sample_files.append(item.name)
    except Exception as e:
        return JSONResponse({"valid": False, "error": str(e), "resolved_path": str(dir_path)})

    return JSONResponse({
        "valid": True,
        "resolved_path": str(dir_path),
        "name": dir_path.name or str(dir_path),
        "total_files": file_count,
        "sample_files": sample_files,
    })


@app.get("/api/import/suggest-directories")
async def suggest_directories_endpoint(query: Optional[str] = None):
    """
    Returns quick accessible folders and autocompletions for the folder path input.
    """
    home = Path.home()
    quick_roots = [
        {"name": "Desktop", "path": str(home / "Desktop")},
        {"name": "Downloads", "path": str(home / "Downloads")},
        {"name": "Documents", "path": str(home / "Documents")},
        {"name": "Home (~)", "path": str(home)},
        {"name": "Current Project", "path": str(BASE_DIR)},
    ]
    accessible = [r for r in quick_roots if Path(r["path"]).exists()]

    if query and query.strip():
        try:
            q_path = normalize_directory_path(query)
            parent = q_path if (q_path.exists() and q_path.is_dir()) else q_path.parent
            if parent.exists() and parent.is_dir():
                subdirs = []
                q_name = q_path.name.lower() if not (q_path.exists() and q_path.is_dir()) else ""
                for child in sorted(parent.iterdir()):
                    if child.is_dir() and not child.name.startswith("."):
                        if not q_name or q_name in child.name.lower():
                            subdirs.append({"name": child.name, "path": str(child)})
                            if len(subdirs) >= 10:
                                break
                return JSONResponse({"suggestions": subdirs, "quick_roots": accessible})
        except Exception:
            pass

    return JSONResponse({"suggestions": [], "quick_roots": accessible})


@app.get("/api/import/browse-directory")
async def browse_directory_endpoint(path: Optional[str] = None):
    """
    Returns directory contents for browsing folders inside the custom web modal.
    Includes breadcrumbs, parent path, quick navigation roots, and child folders with ebook file counts.
    """
    home = Path.home()

    quick_roots = [
        {"name": "Home (~)", "path": str(home), "icon": "ri-home-4-line"},
        {"name": "Desktop", "path": str(home / "Desktop"), "icon": "ri-macbook-line"},
        {"name": "Downloads", "path": str(home / "Downloads"), "icon": "ri-download-line"},
        {"name": "Documents", "path": str(home / "Documents"), "icon": "ri-file-text-line"},
        {"name": "Current Project", "path": str(BASE_DIR), "icon": "ri-folder-settings-line"},
    ]
    if Path("/Volumes").exists():
        quick_roots.append({"name": "Volumes (Disks)", "path": "/Volumes", "icon": "ri-hard-drive-2-line"})
    accessible_roots = [r for r in quick_roots if Path(r["path"]).exists()]

    target_path = None
    if path and path.strip():
        try:
            target_path = normalize_directory_path(path)
        except Exception:
            target_path = None

    if not target_path or not target_path.exists() or not target_path.is_dir():
        target_path = (home / "Desktop") if (home / "Desktop").exists() else home

    ALLOWED_EXTENSIONS = {".pdf", ".epub", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".zip", ".cbz"}

    # Calculate breadcrumbs
    parts = []
    curr = target_path
    while curr != curr.parent:
        parts.append({"name": curr.name or str(curr), "path": str(curr)})
        curr = curr.parent
    parts.append({"name": "Root (/)", "path": str(curr)})
    parts.reverse()

    subdirs = []
    ebooks_here = 0
    sample_ebooks = []

    try:
        for item in sorted(target_path.iterdir(), key=lambda x: x.name.lower()):
            if item.name.startswith(".") or item.name.startswith("__MACOSX"):
                continue
            if item.is_dir():
                ebook_cnt = 0
                has_child_dir = False
                try:
                    for child in item.iterdir():
                        if child.name.startswith("."):
                            continue
                        if child.is_file() and child.suffix.lower() in ALLOWED_EXTENSIONS:
                            ebook_cnt += 1
                        elif child.is_dir():
                            has_child_dir = True
                except Exception:
                    pass

                subdirs.append({
                    "name": item.name,
                    "path": str(item),
                    "ebook_count": ebook_cnt,
                    "has_subfolders": has_child_dir,
                })
            elif item.is_file() and item.suffix.lower() in ALLOWED_EXTENSIONS:
                ebooks_here += 1
                if len(sample_ebooks) < 5:
                    sample_ebooks.append(item.name)
    except PermissionError:
        return JSONResponse({
            "error": f"Permission denied accessing {target_path}",
            "current_path": str(target_path),
            "parent_path": str(target_path.parent) if target_path != target_path.parent else None,
            "breadcrumbs": parts,
            "quick_roots": accessible_roots,
            "directories": [],
            "ebooks_here_count": 0,
            "sample_ebooks": [],
        })
    except Exception as e:
        return JSONResponse({
            "error": str(e),
            "current_path": str(target_path),
            "parent_path": str(target_path.parent) if target_path != target_path.parent else None,
            "breadcrumbs": parts,
            "quick_roots": accessible_roots,
            "directories": [],
            "ebooks_here_count": 0,
            "sample_ebooks": [],
        })

    return JSONResponse({
        "current_path": str(target_path),
        "name": target_path.name or str(target_path),
        "parent_path": str(target_path.parent) if target_path != target_path.parent else None,
        "breadcrumbs": parts,
        "quick_roots": accessible_roots,
        "directories": subdirs,
        "ebooks_here_count": ebooks_here,
        "sample_ebooks": sample_ebooks,
    })


@app.get("/api/session/latest")
async def get_latest_session():
    """Returns the session with the highest progress / colorized pages, or most recent."""
    candidates = []
    if SESSIONS:
        for sess in SESSIONS.values():
            if sess.get("pages"):
                candidates.append(sess)

    # Also scan disk sessions
    dirs = [d for d in STORAGE_DIR.iterdir() if d.is_dir()]
    for d in dirs:
        sess = get_or_restore_session(d.name)
        if sess and sess.get("pages"):
            if not any(c.get("session_id") == sess.get("session_id") for c in candidates):
                candidates.append(sess)

    if candidates:
        # Prioritize processed_count > 0, then highest processed_count, then total_pages
        candidates.sort(
            key=lambda s: (
                1 if s.get("processed_count", 0) > 0 else 0,
                s.get("processed_count", 0),
                s.get("total_pages", 0),
            ),
            reverse=True,
        )
        return JSONResponse(candidates[0])

    raise HTTPException(status_code=404, detail="No active session found")


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found.")
    return JSONResponse(sess)


@app.get("/api/session/{session_id}/image/{img_type}/{filename}")
async def get_session_image(session_id: str, img_type: str, filename: str):
    if img_type not in ["original", "colorized"]:
        raise HTTPException(status_code=400, detail="Invalid image type")

    img_path = STORAGE_DIR / session_id / img_type / filename
    if not img_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(str(img_path))


async def notify_sse_listeners(session_id: str, event_data: dict):
    if session_id in EVENT_QUEUES:
        for q in EVENT_QUEUES[session_id]:
            await q.put(event_data)


@app.get("/api/colorize/stream/{session_id}")
async def stream_progress(session_id: str, auto_resume: bool = Query(False)):
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    pages = sess.get("pages", [])
    colorized_dir = STORAGE_DIR / session_id / "colorized"
    uncolorized_indices = [
        idx
        for idx, p in enumerate(pages)
        if p.get("status") != "colorized"
        or not (colorized_dir / p.get("filename", "")).exists()
        or (colorized_dir / p.get("filename", "")).stat().st_size == 0
    ]

    # Auto-resume interrupted session if requested or if status was left in processing without an active task
    if (auto_resume or sess.get("status") == "processing") and not is_task_active(session_id):
        if uncolorized_indices:
            req = ColorizeRequest(
                session_id=session_id,
                model_provider=sess.get("model_provider") or "google_nano",
                model_name=sess.get("model_name") or "nano-banana",
                style=sess.get("style") or sess.get("recommended_style") or "gemini_anime",
                saturation=sess.get("saturation", 1.2),
                contrast=sess.get("contrast", 1.1),
                line_preserve=sess.get("line_preserve", 0.85),
                selected_pages=uncolorized_indices,
                skip_if_colored=sess.get("skip_if_colored", False),
                force_recolorize=False,
                denoise_screentone=sess.get("denoise_screentone", True),
                denoise_sigma=sess.get("denoise_sigma", 25),
                recognition_mode=sess.get("recognition_mode", "auto"),
            )
            sess["status"] = "processing"
            sess["cancel_requested"] = False
            save_session_meta(session_id)
            task = asyncio.create_task(_async_colorization_worker(session_id, req))
            ACTIVE_COLORIZATION_TASKS[session_id] = task
        elif len(pages) > 0:
            sess["status"] = "completed"
            sess["processed_count"] = len(pages)
            save_session_meta(session_id)

    q = asyncio.Queue()
    if session_id not in EVENT_QUEUES:
        EVENT_QUEUES[session_id] = []
    EVENT_QUEUES[session_id].append(q)

    async def event_generator():
        try:
            # Yield initial status
            init_data = {
                "type": "init",
                "session": sess,
                "is_active": is_task_active(session_id),
                "uncolorized_count": len(uncolorized_indices),
            }
            yield f"data: {json.dumps(init_data)}\n\n"

            # If the session is already finished and no task is active, emit terminal event
            if (
                sess.get("status") in ["completed", "cancelled", "error"]
                and not is_task_active(session_id)
            ):
                yield f"data: {json.dumps({'type': sess.get('status'), 'total_processed': sess.get('processed_count', 0)})}\n\n"
                return

            # If no task is active and session is idle/pending (not auto-resumed), emit idle event
            if not is_task_active(session_id) and sess.get("status") in ["idle", "pending"]:
                yield f"data: {json.dumps({'type': 'idle', 'total_processed': sess.get('processed_count', 0), 'total': sess.get('total_pages', 0)})}\n\n"
                return

            while True:
                data = await q.get()
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("type") in ["completed", "error", "cancelled"]:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            if session_id in EVENT_QUEUES and q in EVENT_QUEUES[session_id]:
                EVENT_QUEUES[session_id].remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


def _launch_auto_adapter_refine(series_key: str, title: str, session_id: str):
    """
    Asynchronously fine-tunes the SeriesResidualAdapter when enough high-confidence
    pages are harvested through the active learning loop.
    """
    trainer = colorizer_engine.adapter_trainer
    if trainer is None or series_key in trainer.active_trainers:
        return

    mem = SERIES_BANK.get_memory(series_key)
    if not mem or len(mem.exemplar_pages) < 1:
        return

    train_images = []
    for ex in mem.exemplar_pages:
        p = ex.get("image_path")
        if p and os.path.exists(p) and p not in train_images:
            train_images.append(p)

    if not train_images:
        return

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    def _worker():
        try:
            def _on_progress(progress_info):
                for sid, s in SESSIONS.items():
                    fn = s.get("filename") or s.get("folder_name") or ""
                    pid = s.get("detected_preset")
                    k, _ = derive_series_key(fn, pid)
                    if k == series_key:
                        asyncio.run_coroutine_threadsafe(
                            notify_sse_listeners(sid, {
                                "type": "adapter_training_progress",
                                "auto_refine": True,
                                **progress_info,
                            }),
                            loop,
                        )

            trainer.train_series_sync(
                series_key=series_key,
                image_paths=train_images,
                total_steps=40,
                lr=2e-4,
                on_progress=_on_progress,
            )
            SERIES_BANK.reset_unrefined_counter(series_key)
        except Exception as e:
            print(f"[Auto-Refine Error] {e}")

    asyncio.create_task(asyncio.to_thread(_worker))


def run_colorization_worker(session_id: str, req: ColorizeRequest):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_async_colorization_worker(session_id, req))


async def _async_colorization_worker(session_id: str, req: ColorizeRequest):
    sess = SESSIONS.get(session_id)
    if not sess:
        return

    sess["status"] = "processing"
    sess["cancel_requested"] = False
    sess["model_provider"] = req.model_provider
    sess["model_name"] = req.model_name
    sess["style"] = req.style
    sess["saturation"] = req.saturation
    sess["contrast"] = req.contrast
    sess["line_preserve"] = req.line_preserve
    sess["skip_if_colored"] = req.skip_if_colored
    sess["denoise_screentone"] = getattr(req, "denoise_screentone", True)
    sess["denoise_sigma"] = getattr(req, "denoise_sigma", 25)
    sess["recognition_mode"] = getattr(req, "recognition_mode", "auto")

    await notify_sse_listeners(
        session_id,
        {
            "type": "start",
            "total": sess["total_pages"],
            "model_provider": req.model_provider,
            "model_name": req.model_name,
        },
    )

    pages = sess["pages"]
    target_pages = req.selected_pages if req.selected_pages is not None else list(range(len(pages)))

    session_dir = STORAGE_DIR / session_id
    colorized_dir = session_dir / "colorized"
    colorized_dir.mkdir(parents=True, exist_ok=True)

    # Ensure processed_count strictly reflects actual colorized pages
    sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")

    try:
        for idx in target_pages:
            # Check if cancellation was requested before processing next page
            if sess.get("cancel_requested"):
                sess["status"] = "cancelled"
                for p in pages:
                    if p.get("status") == "processing":
                        p["status"] = "pending"
                await notify_sse_listeners(
                    session_id,
                    {
                        "type": "cancelled",
                        "processed_count": sess["processed_count"],
                        "total": sess["total_pages"],
                    },
                )
                return

            if idx >= len(pages):
                continue

            page_info = pages[idx]
            orig_path = page_info["original_path"]
            color_filename = page_info["filename"]
            output_path = str(colorized_dir / color_filename)

            # Skip if page is already colorized and output file exists on disk,
            # UNLESS the caller explicitly requested a force recolorize.
            if (
                not req.force_recolorize
                and page_info.get("status") == "colorized"
                and Path(output_path).exists()
                and Path(output_path).stat().st_size > 0
            ):
                if not page_info.get("colorized_url"):
                    page_info["colorized_url"] = (
                        f"/api/session/{session_id}/image/colorized/{color_filename}"
                    )
                continue

            # When forcing recolorize, reset page status so the UI shows it as in-flight
            if req.force_recolorize:
                page_info["status"] = "pending"
                page_info.pop("skipped_colored", None)

            # Fast pre-flight check: if page already has color and user wants to skip colored pages,
            # copy original immediately and NEVER show as "processing" in-flight
            if req.skip_if_colored and is_colored_page(orig_path):
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                shutil.copy2(orig_path, output_path)
                page_info["status"] = "colorized"
                page_info["skipped_colored"] = True
                page_info["colorized_url"] = (
                    f"/api/session/{session_id}/image/colorized/{color_filename}"
                )
                page_info["engine_used"] = "original (already colored)"
                sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")
                save_session_meta(session_id)

                await notify_sse_listeners(
                    session_id,
                    {
                        "type": "page_update",
                        "page_index": idx,
                        "status": "colorized",
                        "skipped_colored": True,
                        "colorized_url": page_info["colorized_url"],
                        "engine": page_info["engine_used"],
                        "processed_count": sess["processed_count"],
                        "total": sess["total_pages"],
                        "message": f"Page {idx + 1}: Preserved original color (skipped)",
                    },
                )
                continue
            page_info["status"] = "processing"

            await notify_sse_listeners(
                session_id,
                {
                    "type": "page_update",
                    "page_index": idx,
                    "status": "processing",
                    "progress": f"{idx + 1}/{len(pages)}",
                },
            )

            try:
                # Resolve palette for this session (if any characters are defined)
                palette = _get_palette(session_id)
                if palette and not palette.characters:
                    palette = None

                # Visual few-shot exemplar from series memory
                s_fn = sess.get("filename") or sess.get("folder_name") or ""
                s_pid = (palette.preset_id if palette else None) or sess.get("detected_preset")
                s_key, s_title = derive_series_key(s_fn, s_pid)
                active_char_names = [c.name for c in palette.characters] if palette else []
                best_exs = SERIES_BANK.find_best_exemplars(
                    s_key,
                    target_image_path=orig_path,
                    active_character_names=active_char_names,
                    exclude_path=output_path,
                    max_count=2,
                )
                exemplar_paths = [
                    e["image_path"] for e in best_exs
                    if e.get("image_path") and os.path.exists(e["image_path"])
                ]
                exemplar_path = exemplar_paths[0] if exemplar_paths else None

                # Run CPU-bound colorization in a thread without blocking main asyncio loop
                res = await asyncio.to_thread(
                    colorizer_engine.colorize_page,
                    image_path=orig_path,
                    output_path=output_path,
                    model_provider=req.model_provider,
                    model_name=req.model_name,
                    api_key=req.api_key or "",
                    style=req.style,
                    saturation=req.saturation,
                    contrast=req.contrast,
                    line_preserve=req.line_preserve,
                    skip_if_colored=req.skip_if_colored,
                    character_palette=palette,
                    denoise_screentone=getattr(req, "denoise_screentone", True),
                    denoise_sigma=getattr(req, "denoise_sigma", 25),
                    recognition_mode=getattr(req, "recognition_mode", "auto"),
                    exemplar_image_path=exemplar_path,
                    exemplar_image_paths=exemplar_paths,
                    series_key=s_key,
                    use_series_adapter=True,
                )

                # Check again immediately after colorizing in case cancel was pressed mid-task
                if sess.get("cancel_requested"):
                    sess["status"] = "cancelled"
                    page_info["status"] = "colorized"
                    page_info["colorized_url"] = (
                        f"/api/session/{session_id}/image/colorized/{color_filename}"
                    )
                    sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")
                    await notify_sse_listeners(
                        session_id,
                        {
                            "type": "cancelled",
                            "processed_count": sess["processed_count"],
                            "total": sess["total_pages"],
                        },
                    )
                    return

                # "skipped_colored" counts as colorized — output was copied as-is
                eff_status = "colorized"
                page_info["status"] = eff_status
                page_info["colorized_url"] = (
                    f"/api/session/{session_id}/image/colorized/{color_filename}"
                )
                page_info["engine_used"] = res.get("engine", req.model_provider)
                if res.get("status") == "skipped_colored":
                    page_info["skipped_colored"] = True
                if res.get("exemplar_used"):
                    page_info["exemplar_used"] = res["exemplar_used"]
                if res.get("exemplars_used"):
                    page_info["exemplars_used"] = res["exemplars_used"]
                if res.get("adapter_used"):
                    page_info["adapter_used"] = True

                # Phase 4: Automated Quality & Confidence-Gated Auto-Harvesting
                q_score = res.get("quality_score")
                if q_score:
                    page_info["quality_score"] = q_score

                if res.get("status") != "failed" and os.path.exists(output_path):
                    if q_score:
                        mem, should_refine = SERIES_BANK.record_auto_harvest(
                            series_key=s_key,
                            title=s_title,
                            session_id=session_id,
                            page_index=idx,
                            approved_image_path=output_path,
                            quality_score=q_score,
                            characters=[c.to_dict() for c in palette.characters] if palette else [],
                            style=req.style,
                        )
                        if q_score.get("auto_learn_eligible"):
                            page_info["auto_harvested"] = True

                        if should_refine:
                            _launch_auto_adapter_refine(s_key, s_title, session_id)
                    else:
                        mem = SERIES_BANK.get_memory(s_key)
                        if not mem or not mem.exemplar_pages:
                            SERIES_BANK.record_learning(
                                series_key=s_key,
                                title=s_title,
                                characters=[c.to_dict() for c in palette.characters] if palette else [],
                                session_id=session_id,
                                page_index=idx,
                                approved_image_path=output_path,
                                style=req.style,
                                saturation=req.saturation,
                                contrast=req.contrast,
                                line_preserve=req.line_preserve,
                            )

                sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")
                save_session_meta(session_id)

                await notify_sse_listeners(
                    session_id,
                    {
                        "type": "page_update",
                        "page_index": idx,
                        "status": "colorized",
                        "skipped_colored": bool(page_info.get("skipped_colored")),
                        "colorized_url": page_info["colorized_url"],
                        "engine": page_info["engine_used"],
                        "exemplar_used": page_info.get("exemplar_used"),
                        "exemplars_used": page_info.get("exemplars_used", []),
                        "adapter_used": bool(page_info.get("adapter_used")),
                        "quality_score": page_info.get("quality_score"),
                        "auto_harvested": bool(page_info.get("auto_harvested")),
                        "processed_count": sess["processed_count"],
                        "total": sess["total_pages"],
                    },
                )

            except Exception as e:
                print(f"Error colorizing page {idx}: {e}")
                page_info["status"] = "error"
                page_info["error_msg"] = str(e)
                save_session_meta(session_id)

                await notify_sse_listeners(
                    session_id,
                    {"type": "page_update", "page_index": idx, "status": "error", "error": str(e)},
                )

        actual_count = sum(1 for p in pages if p.get("status") == "colorized")
        sess["processed_count"] = actual_count
        total_p = sess.get("total_pages", len(pages))
        if total_p > 0 and actual_count >= total_p:
            sess["status"] = "completed"
        else:
            sess["status"] = "pending"
        save_session_meta(session_id)

        if sess["status"] == "completed":
            await notify_sse_listeners(
                session_id, {"type": "completed", "total_processed": actual_count}
            )
        else:
            await notify_sse_listeners(
                session_id, {"type": "idle", "total_processed": actual_count}
            )
    finally:
        ACTIVE_COLORIZATION_TASKS.pop(session_id, None)
        # Ensure if task was terminated/cancelled unexpectedly while in processing, status is updated
        if sess.get("status") == "processing":
            actual_count = sum(1 for p in pages if p.get("status") == "colorized")
            sess["processed_count"] = actual_count
            total_p = sess.get("total_pages", len(pages))
            if total_p > 0 and actual_count >= total_p:
                sess["status"] = "completed"
            else:
                sess["status"] = "pending" if actual_count > 0 else "idle"
            for p in pages:
                if p.get("status") == "processing":
                    p["status"] = "pending"
            save_session_meta(session_id)


@app.post("/api/colorize/start")
async def start_colorization(req: ColorizeRequest):
    session_id = req.session_id
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if is_task_active(session_id):
        raise HTTPException(status_code=400, detail="Colorization already in progress")

    sess["cancel_requested"] = False
    sess["status"] = "processing"
    save_session_meta(session_id)

    # Launch worker directly on main event loop using asyncio.create_task and track
    task = asyncio.create_task(_async_colorization_worker(session_id, req))
    ACTIVE_COLORIZATION_TASKS[session_id] = task
    return JSONResponse({"status": "started", "session_id": session_id})


@app.post("/api/colorize/resume/{session_id}")
async def resume_colorization(session_id: str, req: Optional[ColorizeRequest] = None):
    """
    Resumes an interrupted or pending colorization session from the first uncolored page.
    Skips already colorized pages unless force_recolorize is requested.
    """
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if is_task_active(session_id):
        return JSONResponse(
            {
                "status": "already_running",
                "message": "Colorization is already actively in progress",
                "session_id": session_id,
                "processed_count": sess.get("processed_count", 0),
                "total_pages": sess.get("total_pages", 0),
            }
        )

    pages = sess.get("pages", [])
    colorized_dir = STORAGE_DIR / session_id / "colorized"
    uncolorized_indices = [
        idx
        for idx, p in enumerate(pages)
        if p.get("status") != "colorized"
        or not (colorized_dir / p.get("filename", "")).exists()
        or (colorized_dir / p.get("filename", "")).stat().st_size == 0
    ]

    if not uncolorized_indices and len(pages) > 0:
        sess["status"] = "completed"
        sess["processed_count"] = len(pages)
        save_session_meta(session_id)
        return JSONResponse(
            {
                "status": "already_completed",
                "message": "All pages are already colorized",
                "session_id": session_id,
                "processed_count": len(pages),
                "total_pages": len(pages),
            }
        )

    if req is None:
        req = ColorizeRequest(
            session_id=session_id,
            model_provider=sess.get("model_provider") or "google_nano",
            model_name=sess.get("model_name") or "nano-banana",
            style=sess.get("style") or sess.get("recommended_style") or "gemini_anime",
            saturation=sess.get("saturation", 1.2),
            contrast=sess.get("contrast", 1.1),
            line_preserve=sess.get("line_preserve", 0.85),
            selected_pages=uncolorized_indices,
            skip_if_colored=sess.get("skip_if_colored", False),
            force_recolorize=False,
            denoise_screentone=sess.get("denoise_screentone", True),
            denoise_sigma=sess.get("denoise_sigma", 25),
            recognition_mode=sess.get("recognition_mode", "auto"),
        )
    else:
        req.session_id = session_id
        req.force_recolorize = False
        if req.selected_pages is None:
            req.selected_pages = uncolorized_indices

    sess["cancel_requested"] = False
    sess["status"] = "processing"
    save_session_meta(session_id)

    task = asyncio.create_task(_async_colorization_worker(session_id, req))
    ACTIVE_COLORIZATION_TASKS[session_id] = task

    return JSONResponse(
        {
            "status": "resumed",
            "message": f"Resumed colorization for {len(uncolorized_indices)} pending pages",
            "session_id": session_id,
            "processed_count": sess.get("processed_count", 0),
            "total_pages": sess.get("total_pages", len(pages)),
            "remaining_pages": len(uncolorized_indices),
        }
    )


@app.post("/api/colorize/cancel/{session_id}")
async def cancel_colorization(session_id: str):
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    sess["cancel_requested"] = True
    sess["status"] = "cancelled"

    for p in sess["pages"]:
        if p.get("status") == "processing":
            p["status"] = "pending"

    save_session_meta(session_id)

    ACTIVE_COLORIZATION_TASKS.pop(session_id, None)

    await notify_sse_listeners(
        session_id,
        {
            "type": "cancelled",
            "processed_count": sess["processed_count"],
            "total": sess["total_pages"],
        },
    )

    return JSONResponse({"status": "cancelled", "session_id": session_id})


@app.post("/api/colorize/preview")
async def preview_single_page(req: PreviewRequest):
    session_id = req.session_id
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    pages = sess["pages"]
    if req.page_index < 0 or req.page_index >= len(pages):
        raise HTTPException(status_code=400, detail="Invalid page index")

    page_info = pages[req.page_index]
    orig_path = page_info["original_path"]
    color_filename = page_info["filename"]

    session_dir = STORAGE_DIR / session_id
    colorized_dir = session_dir / "colorized"
    colorized_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(colorized_dir / color_filename)

    try:
        palette = _get_palette(session_id)
        if palette and not palette.characters:
            palette = None

        # Track whether the caller has already declared active characters,
        has_active_names = bool(getattr(req, "active_character_names", None))

        if palette and has_active_names:
            palette = copy.deepcopy(palette)
            palette.characters = [
                c for c in palette.characters if c.name in req.active_character_names
            ]

        # Resolve exemplar for preview
        s_fn = sess.get("filename") or sess.get("folder_name") or ""
        s_pid = (palette.preset_id if palette else None) or sess.get("detected_preset")
        s_key, s_title = derive_series_key(s_fn, s_pid)
        active_char_names = list(req.active_character_names) if getattr(req, "active_character_names", None) else (
            [c.name for c in palette.characters] if palette else []
        )
        best_exs = SERIES_BANK.find_best_exemplars(
            s_key,
            target_image_path=orig_path,
            active_character_names=active_char_names,
            exclude_path=output_path,
            max_count=2,
        )
        exemplar_paths = [
            e["image_path"] for e in best_exs
            if e.get("image_path") and os.path.exists(e["image_path"])
        ]
        exemplar_path = exemplar_paths[0] if exemplar_paths else None

        res = await asyncio.to_thread(
            colorizer_engine.colorize_page,
            image_path=orig_path,
            output_path=output_path,
            model_provider=req.model_provider,
            model_name=req.model_name,
            api_key=req.api_key or "",
            style=req.style,
            saturation=req.saturation,
            contrast=req.contrast,
            line_preserve=req.line_preserve,
            skip_if_colored=req.skip_if_colored,
            character_palette=palette,
            denoise_screentone=getattr(req, "denoise_screentone", True),
            denoise_sigma=getattr(req, "denoise_sigma", 25),
            recognition_mode=getattr(req, "recognition_mode", "auto"),
            skip_recognition=bool(getattr(req, "skip_recognition", False)),
            exemplar_image_path=exemplar_path,
            exemplar_image_paths=exemplar_paths,
            series_key=s_key,
            use_series_adapter=True,
        )

        page_info["status"] = "colorized"
        page_info["colorized_url"] = f"/api/session/{session_id}/image/colorized/{color_filename}"
        page_info["engine_used"] = res.get("engine", req.model_provider)
        if res.get("status") == "skipped_colored":
            page_info["skipped_colored"] = True
        if res.get("exemplar_used"):
            page_info["exemplar_used"] = res["exemplar_used"]
        if res.get("exemplars_used"):
            page_info["exemplars_used"] = res["exemplars_used"]
        if res.get("adapter_used"):
            page_info["adapter_used"] = True
        if res.get("quality_score"):
            page_info["quality_score"] = res["quality_score"]
        if "recognized_characters" in res:
            page_info["recognized_characters"] = res["recognized_characters"]

        # Update processed_count and status
        sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")
        if sess["processed_count"] == sess.get("total_pages", len(pages)):
            sess["status"] = "completed"

        save_session_meta(session_id)

        await notify_sse_listeners(
            session_id,
            {
                "type": "page_update",
                "page_index": req.page_index,
                "status": "colorized",
                "colorized_url": page_info["colorized_url"],
                "engine": page_info["engine_used"],
                "exemplar_used": page_info.get("exemplar_used"),
                "exemplars_used": page_info.get("exemplars_used", []),
                "adapter_used": bool(page_info.get("adapter_used")),
                "quality_score": page_info.get("quality_score"),
                "processed_count": sess["processed_count"],
                "total": sess.get("total_pages", len(pages)),
            },
        )

        return JSONResponse(
            {
                "status": "success",
                "page_index": req.page_index,
                "colorized_url": page_info["colorized_url"],
                "engine": page_info["engine_used"],
                "page_info": page_info,
                "quality_score": page_info.get("quality_score"),
                "recognized_characters": res.get("recognized_characters", []),
                "exemplar_used": res.get("exemplar_used"),
                "exemplars_used": res.get("exemplars_used", []),
                "adapter_used": bool(res.get("adapter_used")),
                "series_key": s_key,
                "processed_count": sess["processed_count"],
                "total_pages": sess.get("total_pages", len(pages)),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@app.get("/api/palette/presets")
async def list_manga_presets():
    """Returns all registered manga presets with canonical character colors."""
    presets = get_all_presets()
    return JSONResponse({
        "presets": [p.to_dict() for p in presets],
        "count": len(presets),
    })


@app.get("/api/palette/preset/{preset_id}")
async def get_manga_preset(preset_id: str):
    """Returns a specific manga preset by its ID."""
    preset = get_preset_by_id(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return JSONResponse({"preset": preset.to_dict()})


@app.post("/api/palette/apply-preset")
async def apply_preset_to_session(req: PaletteApplyPresetRequest):
    """Applies all characters from a manga preset to the session palette."""
    sess = get_or_restore_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    preset = get_preset_by_id(req.preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{req.preset_id}' not found")

    palette = CharacterPalette(
        characters=[
            CharacterEntry(
                name=c.name,
                hair_hex=c.hair_hex,
                skin_hex=c.skin_hex,
                costume_hex=c.costume_hex,
                extra_hex=c.extra_hex,
                eye_hex=getattr(c, "eye_hex", ""),
            )
            for c in preset.characters
        ],
        preset_id=preset.id,
        preset_title=preset.title,
    )
    SESSION_PALETTES[req.session_id] = palette
    save_session_palette(req.session_id, palette)

    sess["detected_preset"] = preset.id
    sess["preset_title"] = preset.title
    if preset.recommended_style:
        sess["recommended_style"] = preset.recommended_style
    save_session_meta(req.session_id)

    return JSONResponse({
        "status": "ok",
        "session_id": req.session_id,
        "preset_id": preset.id,
        "preset_title": preset.title,
        "palette": palette.to_dict(),
    })


@app.post("/api/palette/search-online")
async def search_online_preset_endpoint(req: PaletteOnlineSearchRequest):
    """Searches online sources for character color palettes and generates a preset."""
    preset = search_online_manga_preset(req.query)
    if not preset:
        raise HTTPException(status_code=404, detail=f"No color palette found online for '{req.query}'")

    if req.session_id:
        sess = get_or_restore_session(req.session_id)
        if sess:
            palette = CharacterPalette(
                characters=[
                    CharacterEntry(
                        name=c.name,
                        hair_hex=c.hair_hex,
                        skin_hex=c.skin_hex,
                        costume_hex=c.costume_hex,
                        extra_hex=c.extra_hex,
                        eye_hex=getattr(c, "eye_hex", ""),
                    )
                    for c in preset.characters
                ],
                preset_id=preset.id,
                preset_title=preset.title,
            )
            SESSION_PALETTES[req.session_id] = palette
            save_session_palette(req.session_id, palette)
            sess["detected_preset"] = preset.id
            sess["preset_title"] = preset.title
            save_session_meta(req.session_id)

    return JSONResponse({
        "status": "ok",
        "preset": preset.to_dict(),
        "applied_to_session": req.session_id if req.session_id else None,
    })


@app.get("/api/palette/{session_id}")
async def get_palette(session_id: str):
    """Returns the character color palette for the given session."""
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    palette = _get_palette(session_id)
    return JSONResponse({
        "session_id": session_id,
        "preset_id": palette.preset_id or sess.get("detected_preset", ""),
        "preset_title": palette.preset_title or sess.get("preset_title", ""),
        "palette": palette.to_dict(),
    })


@app.post("/api/palette/upsert")
async def upsert_palette_character(req: PaletteUpsertRequest):
    """
    Adds or updates a character entry in the session's palette.
    If a character with the same name already exists it is replaced.
    """
    sess = get_or_restore_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    palette = _get_palette(req.session_id)
    new_entry = CharacterEntry(
        name=req.character.name,
        hair_hex=req.character.hair_hex,
        skin_hex=req.character.skin_hex,
        costume_hex=req.character.costume_hex,
        extra_hex=req.character.extra_hex,
        eye_hex=req.character.eye_hex or "",
        notes=req.character.notes or "",
        visual_traits=req.character.visual_traits or [],
        keywords=req.character.keywords or [],
        bounding_box=tuple(req.character.bounding_box) if req.character.bounding_box else None,
    )
    # Replace existing entry by name, or append
    palette.characters = [c for c in palette.characters if c.name.lower() != new_entry.name.lower()]
    palette.characters.append(new_entry)
    save_session_palette(req.session_id, palette)

    # Automatically persist learned character trait into series memory
    try:
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = palette.preset_id or sess.get("detected_preset")
        s_key, s_title = derive_series_key(fn, pid)
        SERIES_BANK.record_learning(
            series_key=s_key,
            title=s_title,
            characters=[new_entry.to_dict()],
            session_id=req.session_id,
            page_index=0,
        )
    except Exception as e:
        print(f"[SeriesMemory Learn Error] {e}")

    return JSONResponse(
        {"status": "ok", "session_id": req.session_id, "palette": palette.to_dict()}
    )


@app.delete("/api/palette/{session_id}/{character_name}")
async def delete_palette_character(session_id: str, character_name: str):
    """Removes a single character from the session palette."""
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    palette = _get_palette(session_id)
    before = len(palette.characters)
    palette.characters = [c for c in palette.characters if c.name.lower() != character_name.lower()]
    removed = before - len(palette.characters)
    save_session_palette(session_id, palette)

    return JSONResponse(
        {"status": "ok", "removed": removed, "session_id": session_id, "palette": palette.to_dict()}
    )


@app.delete("/api/palette/{session_id}")
async def clear_palette(session_id: str):
    """Clears all characters from the session palette."""
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    empty_pal = CharacterPalette()
    SESSION_PALETTES[session_id] = empty_pal
    save_session_palette(session_id, empty_pal)
    sess["detected_preset"] = None
    sess["preset_title"] = None
    save_session_meta(session_id)

    return JSONResponse({"status": "ok", "session_id": session_id, "palette": {"characters": []}})


# ── Series Memory Endpoints ─────────────────────────────────────────

@app.get("/api/series-memory/{session_id}")
async def get_series_memory_endpoint(session_id: str):
    """Retrieves learned character traits and exemplars for this session's manga series."""
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    pal = _get_palette(session_id)
    fn = sess.get("filename") or sess.get("folder_name") or ""
    pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
    s_key, s_title = derive_series_key(fn, pid)
    mem = SERIES_BANK.get_memory(s_key)
    return JSONResponse({
        "status": "ok",
        "session_id": session_id,
        "series_key": s_key,
        "title": s_title,
        "memory": mem.to_dict() if mem else None,
    })


@app.post("/api/series-memory/learn-page")
async def learn_page_endpoint(req: LearnPageRequest):
    """
    Explicitly saves a user-approved or corrected colorized page into Series Memory:
    - Learns active character traits for this page.
    - Saves the page's colorized rendering as a visual exemplar for future pages.
    """
    sess = get_or_restore_session(req.session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    pages = sess.get("pages", [])
    if req.page_index < 0 or req.page_index >= len(pages):
        raise HTTPException(status_code=400, detail=f"Page index {req.page_index} out of range")

    page_info = pages[req.page_index]
    if page_info.get("status") != "colorized":
        raise HTTPException(status_code=400, detail="Page is not yet colorized")

    sess_dir = STORAGE_DIR / req.session_id
    color_filename = (
        page_info.get("filename")
        or (Path(page_info["original_path"]).name if page_info.get("original_path") else None)
        or (Path(page_info["path"]).name if page_info.get("path") else None)
    )
    if not color_filename and page_info.get("colorized_url"):
        color_filename = Path(page_info["colorized_url"].split("?")[0]).name
    if not color_filename:
        color_filename = f"page_{req.page_index + 1:04d}.jpg"

    colorized_path = sess_dir / "colorized" / color_filename
    if not colorized_path.exists():
        stem = Path(color_filename).stem
        alt_png = sess_dir / "colorized" / f"{stem}.png"
        alt_jpg = sess_dir / "colorized" / f"{stem}.jpg"
        alt_idx_jpg = sess_dir / "colorized" / f"page_{req.page_index + 1:04d}.jpg"
        alt_idx_png = sess_dir / "colorized" / f"page_{req.page_index + 1:04d}.png"
        if alt_png.exists():
            colorized_path = alt_png
        elif alt_jpg.exists():
            colorized_path = alt_jpg
        elif alt_idx_jpg.exists():
            colorized_path = alt_idx_jpg
        elif alt_idx_png.exists():
            colorized_path = alt_idx_png
        elif page_info.get("path") and Path(page_info["path"]).exists():
            colorized_path = Path(page_info["path"])
        elif page_info.get("original_path") and page_info.get("skipped_colored") and Path(page_info["original_path"]).exists():
            colorized_path = Path(page_info["original_path"])
        else:
            raise HTTPException(status_code=404, detail="Colorized image file not found")

    palette = _get_palette(req.session_id)
    fn = sess.get("filename") or sess.get("folder_name") or ""
    pid = (palette.preset_id if palette else None) or sess.get("detected_preset")
    s_key, s_title = derive_series_key(fn, pid)

    chars_to_learn = []
    if palette and palette.characters:
        if req.character_names:
            names_set = {n.lower().strip() for n in req.character_names}
            chars_to_learn = [c.to_dict() for c in palette.characters if c.name.lower().strip() in names_set]
        else:
            rec = page_info.get("recognized_characters", [])
            if rec:
                rec_names = {r["name"].lower().strip() for r in rec if isinstance(r, dict) and "name" in r}
                chars_to_learn = [c.to_dict() for c in palette.characters if c.name.lower().strip() in rec_names]
            if not chars_to_learn:
                chars_to_learn = [c.to_dict() for c in palette.characters]

    mem = SERIES_BANK.record_learning(
        series_key=s_key,
        title=s_title,
        characters=chars_to_learn,
        session_id=req.session_id,
        page_index=req.page_index,
        approved_image_path=str(colorized_path) if req.exemplar else None,
        style=sess.get("style"),
        saturation=sess.get("saturation"),
        contrast=sess.get("contrast"),
        line_preserve=sess.get("line_preserve"),
    )

    page_info["learned_to_memory"] = True
    save_session_meta(req.session_id)

    return JSONResponse({
        "status": "ok",
        "series_key": s_key,
        "title": s_title,
        "message": f"Saved page {req.page_index + 1} into Series Memory for {s_title}",
        "memory": mem.to_dict(),
    })


@app.post("/api/series-memory/reset/{series_key}")
async def reset_series_memory_endpoint(series_key: str):
    """Resets learned traits and exemplars for a given manga series key."""
    success = SERIES_BANK.reset_series_memory(series_key)
    return JSONResponse({
        "status": "ok",
        "series_key": series_key,
        "reset": success,
    })


@app.get("/api/series-memory/{session_id}/exemplars")
async def get_series_exemplars_endpoint(session_id: str):
    """Retrieves all visual few-shot exemplars stored in Series Memory for a session or series."""
    sess = get_or_restore_session(session_id)
    if sess:
        pal = _get_palette(session_id)
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
        s_key, s_title = derive_series_key(fn, pid)
    else:
        # Check if session_id is directly a series_key
        mem = SERIES_BANK.get_memory(session_id)
        if mem:
            s_key = session_id
            s_title = mem.title or session_id
        else:
            raise HTTPException(status_code=404, detail="Session or series not found")

    mem = SERIES_BANK.get_memory(s_key)
    exemplars = []
    if mem and mem.exemplar_pages:
        for ex in mem.exemplar_pages:
            img_p = ex.get("image_path")
            fn_img = Path(img_p).name if img_p else ""
            exemplars.append({
                "page_index": ex.get("page_index"),
                "session_id": ex.get("session_id"),
                "character_names": ex.get("character_names", []),
                "mean_l": ex.get("mean_l"),
                "style": ex.get("style", "manga"),
                "pinned": bool(ex.get("pinned", False)),
                "created_at": ex.get("created_at"),
                "image_url": f"/api/series-memory/{s_key}/exemplar-image/{fn_img}" if fn_img else None,
                "exists": os.path.exists(img_p) if img_p else False,
            })

    return JSONResponse({
        "status": "ok",
        "session_id": session_id,
        "series_key": s_key,
        "title": s_title,
        "exemplars": exemplars,
    })


@app.get("/api/series-memory/{series_key}/exemplar-image/{filename}")
async def get_series_exemplar_image(series_key: str, filename: str):
    """Serves a stored exemplar image for a given series."""
    img_path = STORAGE_DIR / "series_exemplars" / series_key / filename
    if not img_path.exists():
        bank_path = SERIES_BANK.storage_path.parent / "series_exemplars" / series_key / filename
        if bank_path.exists():
            img_path = bank_path
        else:
            raise HTTPException(status_code=404, detail="Exemplar image not found")
    return FileResponse(str(img_path))


@app.delete("/api/series-memory/{series_key}/exemplar/{page_index}")
async def delete_series_exemplar_endpoint(series_key: str, page_index: int, session_id: Optional[str] = None):
    """Removes a page exemplar from Series Memory and deletes its stored image file."""
    effective_key = series_key
    sess = get_or_restore_session(series_key)
    if sess:
        pal = _get_palette(series_key)
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
        effective_key, _ = derive_series_key(fn, pid)

    success = SERIES_BANK.remove_exemplar(effective_key, page_index, session_id=session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Exemplar not found")
    return JSONResponse({
        "status": "ok",
        "series_key": effective_key,
        "page_index": page_index,
        "removed": True,
    })


@app.post("/api/series-memory/pin-exemplar")
async def pin_series_exemplar_endpoint(req: PinExemplarRequest):
    """Pins or unpins a visual exemplar in Series Memory to prioritize it in rankings."""
    effective_key = req.series_key
    sess = get_or_restore_session(req.series_key)
    if sess:
        pal = _get_palette(req.series_key)
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
        effective_key, _ = derive_series_key(fn, pid)

    success = SERIES_BANK.pin_exemplar(effective_key, req.page_index, req.pinned)
    if not success:
        raise HTTPException(status_code=404, detail="Exemplar not found")
    return JSONResponse({
        "status": "ok",
        "series_key": effective_key,
        "page_index": req.page_index,
        "pinned": req.pinned,
    })


# ── Series Style Adapter (LoRA Fine-Tuning) Endpoints ───────────────

@app.post("/api/series-memory/{series_key}/train-adapter")
async def train_series_adapter_endpoint(
    series_key: str,
    req: Optional[TrainSeriesAdapterRequest] = None,
):
    """
    Launches background fine-tuning of a lightweight Series Style Adapter (~140 KB)
    for this series using user-approved exemplar pages and color spreads.
    """
    effective_key = series_key
    sess = get_or_restore_session(series_key)
    if sess:
        pal = _get_palette(series_key)
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
        effective_key, _ = derive_series_key(fn, pid)

    trainer = colorizer_engine.adapter_trainer
    if trainer is None:
        raise HTTPException(status_code=500, detail="SeriesAdapterTrainer not initialized")

    status = trainer.get_status(effective_key)
    if status.get("status") == "training":
        raise HTTPException(status_code=409, detail="Adapter training already in progress")

    # Collect training images from Series Memory exemplars and colored session pages
    train_images: list[str] = []
    mem = SERIES_BANK.get_memory(effective_key)
    if mem and mem.exemplar_pages:
        for ex in mem.exemplar_pages:
            p = ex.get("image_path")
            if p and os.path.exists(p) and p not in train_images:
                train_images.append(p)

    # Also search SESSIONS for colorized/color pages matching this series
    for sid, s in SESSIONS.items():
        fn = s.get("filename") or s.get("folder_name") or ""
        pid = s.get("detected_preset")
        k, _ = derive_series_key(fn, pid)
        if k == effective_key:
            for page in s.get("pages", []):
                if page.get("status") == "colorized" or page.get("skipped_colored"):
                    color_p = page.get("path")
                    if not color_p and page.get("status") == "colorized":
                        fn = page.get("filename")
                        if fn:
                            cand = STORAGE_DIR / sid / "colorized" / fn
                            if cand.exists():
                                color_p = str(cand)
                    if not color_p and page.get("skipped_colored"):
                        color_p = page.get("original_path")
                    if color_p and os.path.exists(color_p) and color_p not in train_images:
                        train_images.append(color_p)

    if not train_images:
        raise HTTPException(
            status_code=400,
            detail="No training images available for this series. Please learn/approve at least one page or import a volume with color pages.",
        )

    steps = req.steps if req and req.steps else 100
    lr = req.lr if req and req.lr else 2e-4

    loop = asyncio.get_running_loop()

    def _train_worker():
        def _on_progress(progress_info):
            for sid, s in SESSIONS.items():
                fn = s.get("filename") or s.get("folder_name") or ""
                pid = s.get("detected_preset")
                k, _ = derive_series_key(fn, pid)
                if k == effective_key:
                    asyncio.run_coroutine_threadsafe(
                        notify_sse_listeners(sid, {
                            "type": "adapter_training_progress",
                            **progress_info,
                        }),
                        loop,
                    )

        return trainer.train_series_sync(
            series_key=effective_key,
            image_paths=train_images,
            total_steps=steps,
            lr=lr,
            on_progress=_on_progress,
        )

    # Launch in background thread without blocking FastAPI event loop
    asyncio.create_task(asyncio.to_thread(_train_worker))

    return JSONResponse({
        "status": "training_started",
        "series_key": effective_key,
        "total_steps": steps,
        "samples_count": len(train_images),
    })


@app.get("/api/series-memory/{series_key}/adapter-status")
async def get_series_adapter_status_endpoint(series_key: str):
    """Returns training progress or current checkpoint metadata for a series adapter."""
    effective_key = series_key
    sess = get_or_restore_session(series_key)
    if sess:
        pal = _get_palette(series_key)
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
        effective_key, _ = derive_series_key(fn, pid)

    trainer = colorizer_engine.adapter_trainer
    if trainer is None:
        return JSONResponse({"status": "unavailable", "series_key": effective_key})

    status_data = trainer.get_status(effective_key)
    return JSONResponse(status_data)


@app.post("/api/series-memory/{series_key}/cancel-training")
async def cancel_series_adapter_training_endpoint(series_key: str):
    """Cancels ongoing fine-tuning of a series style adapter."""
    effective_key = series_key
    sess = get_or_restore_session(series_key)
    if sess:
        pal = _get_palette(series_key)
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
        effective_key, _ = derive_series_key(fn, pid)

    trainer = colorizer_engine.adapter_trainer
    cancelled = trainer.cancel_training(effective_key) if trainer else False
    return JSONResponse({
        "status": "ok",
        "series_key": effective_key,
        "cancelled": cancelled,
    })


@app.delete("/api/series-memory/{series_key}/adapter")
async def delete_series_adapter_endpoint(series_key: str):
    """Deletes a trained series style adapter checkpoint and frees in-memory weights."""
    effective_key = series_key
    sess = get_or_restore_session(series_key)
    if sess:
        pal = _get_palette(series_key)
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
        effective_key, _ = derive_series_key(fn, pid)

    trainer = colorizer_engine.adapter_trainer
    deleted = trainer.delete_adapter(effective_key) if trainer else False
    return JSONResponse({
        "status": "ok",
        "series_key": effective_key,
        "deleted": deleted,
    })


@app.get("/api/session/{session_id}/page/{page_index}/quality")
async def get_page_quality_score_endpoint(session_id: str, page_index: int):
    """Returns detailed quality metrics and confidence breakdown for a colorized page."""
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    pages = sess.get("pages", [])
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(status_code=404, detail="Page index out of range")

    page = pages[page_index]
    if page.get("quality_score"):
        return JSONResponse({"status": "ok", "page_index": page_index, "quality_score": page["quality_score"]})

    # If not already stored but colorized page exists, compute on the fly
    orig_path = page.get("original_path")
    color_path = page.get("path")
    if not color_path and orig_path:
        fn = page.get("filename") or Path(orig_path).name
        cand = STORAGE_DIR / session_id / "colorized" / fn
        if cand.exists():
            color_path = str(cand)
    if orig_path and color_path and os.path.exists(orig_path) and os.path.exists(color_path):
        from quality_scorer import calculate_quality_score
        is_skipped = bool(page.get("skipped_colored"))
        q = calculate_quality_score(orig_path, color_path, is_skipped_colored=is_skipped)
        page["quality_score"] = q
        save_session_meta(session_id)
        return JSONResponse({"status": "ok", "page_index": page_index, "quality_score": q})

    raise HTTPException(status_code=400, detail="Page is not yet colorized")


@app.get("/api/series-memory/{series_key}/auto-refine")
async def get_series_auto_refine_endpoint(series_key: str):
    """Returns auto-refinement and confidence-gated active learning settings for a series."""
    effective_key = series_key
    sess = get_or_restore_session(series_key)
    if sess:
        pal = _get_palette(series_key)
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
        effective_key, _ = derive_series_key(fn, pid)

    mem = SERIES_BANK.get_memory(effective_key)
    return JSONResponse({
        "status": "ok",
        "series_key": effective_key,
        "auto_refine_enabled": mem.auto_refine_enabled if mem else True,
        "auto_harvest_threshold": mem.auto_harvest_threshold if mem else 0.82,
        "auto_refine_interval": mem.auto_refine_interval if mem else 5,
        "unrefined_pages_count": mem.unrefined_pages_count if mem else 0,
        "auto_learned_count": mem.auto_learned_count if mem else 0,
        "total_exemplars": len(mem.exemplar_pages) if mem else 0,
    })


@app.post("/api/series-memory/{series_key}/auto-refine")
async def update_series_auto_refine_endpoint(
    series_key: str,
    req: AutoRefineSettingsRequest,
):
    """Updates auto-refinement and confidence thresholds for a series."""
    effective_key = series_key
    sess = get_or_restore_session(series_key)
    if sess:
        pal = _get_palette(series_key)
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
        effective_key, _ = derive_series_key(fn, pid)

    mem = SERIES_BANK.update_auto_refine_settings(
        series_key=effective_key,
        enabled=req.enabled,
        threshold=req.threshold,
        interval=req.interval,
    )
    return JSONResponse({
        "status": "ok",
        "series_key": effective_key,
        "auto_refine_enabled": mem.auto_refine_enabled,
        "auto_harvest_threshold": mem.auto_harvest_threshold,
        "auto_refine_interval": mem.auto_refine_interval,
        "unrefined_pages_count": mem.unrefined_pages_count,
        "auto_learned_count": mem.auto_learned_count,
    })


@app.post("/api/series-memory/{series_key}/trigger-auto-refine")
async def trigger_series_auto_refine_endpoint(series_key: str):
    """Forces an immediate LoRA adapter refinement pass using harvested high-confidence pages."""
    effective_key = series_key
    effective_title = series_key
    sess = get_or_restore_session(series_key)
    session_id = series_key
    if sess:
        pal = _get_palette(series_key)
        fn = sess.get("filename") or sess.get("folder_name") or ""
        pid = (pal.preset_id if pal else None) or sess.get("detected_preset")
        effective_key, effective_title = derive_series_key(fn, pid)
        session_id = sess.get("session_id", series_key)

    trainer = colorizer_engine.adapter_trainer
    if trainer is None:
        raise HTTPException(status_code=500, detail="Adapter trainer not initialized")
    if effective_key in trainer.active_trainers:
        raise HTTPException(status_code=409, detail="Adapter training already in progress")

    mem = SERIES_BANK.get_memory(effective_key)
    if not mem or not mem.exemplar_pages:
        raise HTTPException(status_code=400, detail="No harvested exemplar pages found for this series")

    _launch_auto_adapter_refine(effective_key, effective_title, session_id)
    return JSONResponse({
        "status": "auto_refine_started",
        "series_key": effective_key,
        "samples_count": len(mem.exemplar_pages),
    })


@app.post("/api/session/{session_id}/page/{page_index}/recognize")
async def recognize_characters_for_page(
    session_id: str,
    page_index: int,
    req: Optional[CharacterRecognizeRequest] = None,
):
    """
    Analyzes the specified manga page against the session's active character palette
    and returns detected characters with confidences and bounding boxes.
    """
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    pages = sess.get("pages", [])
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(status_code=400, detail="Invalid page index")

    page_info = pages[page_index]
    orig_path = page_info.get("original_path", "")
    if not orig_path or not os.path.exists(orig_path):
        raise HTTPException(status_code=404, detail="Original page image not found")

    palette = _get_palette(session_id)
    if not palette or not palette.characters:
        return JSONResponse({
            "status": "no_palette",
            "message": "No active character palette for this session",
            "recognized": [],
            "palette": palette.to_dict() if palette else {"characters": []},
        })

    api_key = req.api_key if req else ""
    model_name = req.model_name if req else ""
    recognition_mode = req.recognition_mode if (req and req.recognition_mode) else "auto"

    recognized = await asyncio.to_thread(
        colorizer_engine.recognizer.recognize_page_characters,
        image_path=orig_path,
        palette=palette,
        api_key=api_key,
        model_name=model_name,
        recognition_mode=recognition_mode,
    )

    rec_dicts = [rc.to_dict() for rc in recognized]
    page_info["recognized_characters"] = rec_dicts
    save_session_meta(session_id)

    return JSONResponse({
        "status": "ok",
        "session_id": session_id,
        "page_index": page_index,
        "recognized": rec_dicts,
        "palette": palette.to_dict(),
    })


@app.post("/api/export/batch")
async def export_batch_documents(req: BatchExportRequest):
    """Builds and packages multiple colorized documents into a single archive."""
    sessions_data = []
    for sid in req.session_ids:
        sess = SESSIONS.get(sid) or get_or_restore_session(sid)
        if sess:
            sessions_data.append(sess)

    if not sessions_data:
        raise HTTPException(status_code=404, detail="No valid documents found for batch export")

    format_override = (req.format or "auto").lower().strip()
    batch_token = str(uuid.uuid4())[:8]

    if format_override in ["mobi", "azw3", "kindle"]:
        out_filename = f"colorized_manga_kindle_{batch_token}.zip"
    elif format_override == "epub":
        out_filename = f"colorized_manga_epubs_{batch_token}.zip"
    elif format_override == "pdf":
        out_filename = f"colorized_manga_pdfs_{batch_token}.zip"
    else:
        out_filename = f"colorized_manga_collection_{batch_token}.zip"

    output_filepath = str(OUTPUT_DIR / f"batch_{out_filename}")

    try:
        file_processor.build_batch_export(
            sessions_data, output_filepath, format_override=format_override
        )
        download_url = f"/api/download/batch/{out_filename}"
        return JSONResponse(
            {
                "status": "success",
                "format": format_override,
                "download_url": download_url,
                "filename": out_filename,
                "total_documents": len(sessions_data),
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch export failed: {str(e)}")


# ── Combined Export Background State ──────────────────────────────────
COMBINED_EXPORTS: dict[str, dict] = {}
COMBINED_EXPORT_QUEUES: dict[str, list[asyncio.Queue]] = {}


async def notify_combined_sse(job_id: str, event_data: dict):
    if job_id in COMBINED_EXPORT_QUEUES:
        for q in list(COMBINED_EXPORT_QUEUES[job_id]):
            await q.put(event_data)


async def _async_combined_export_worker(
    job_id: str,
    sessions_data: list,
    output_filepath: str,
    out_filename: str,
    fmt: str,
    title: str,
    chunk_by: str = "none",
    chunk_size: int = 3,
    max_dimension: Optional[int] = 1600,
    jpeg_quality: int = 80,
    grayscale: bool = False,
    colorsoft_tune: bool = False,
    export_original: bool = False,
):
    job = COMBINED_EXPORTS.get(job_id)
    if not job:
        return

    def on_progress(p_data: dict):
        job["progress"] = p_data
        if job_id in COMBINED_EXPORT_QUEUES:
            for q in list(COMBINED_EXPORT_QUEUES[job_id]):
                q.put_nowait({"type": "progress", "job_id": job_id, **p_data})

    def check_cancelled() -> bool:
        return bool(job.get("cancel_requested", False))

    try:
        await asyncio.to_thread(
            file_processor.build_combined_omnibus,
            sessions_data=sessions_data,
            output_filepath=output_filepath,
            export_format=fmt,
            title=title,
            chunk_by=chunk_by,
            chunk_size=chunk_size,
            max_dimension=max_dimension,
            jpeg_quality=jpeg_quality,
            grayscale=grayscale,
            colorsoft_tune=colorsoft_tune,
            export_original=export_original,
            progress_callback=on_progress,
            cancel_check=check_cancelled,
        )

        if job.get("cancel_requested"):
            job["status"] = "cancelled"
            if os.path.exists(output_filepath):
                try:
                    os.remove(output_filepath)
                except Exception:
                    pass
            await notify_combined_sse(
                job_id,
                {"type": "cancelled", "job_id": job_id, "message": "Combined export cancelled."},
            )
            return

        job["status"] = "completed"
        if "progress" not in job or not job["progress"]:
            job["progress"] = {}
        job["progress"]["percent"] = 100
        download_url = f"/api/download/combined/{out_filename}"
        job["download_url"] = download_url
        await notify_combined_sse(
            job_id,
            {
                "type": "completed",
                "job_id": job_id,
                "download_url": download_url,
                "filename": out_filename,
                "total_volumes": len(sessions_data),
                "title": title,
            },
        )

    except InterruptedError:
        job["status"] = "cancelled"
        if os.path.exists(output_filepath):
            try:
                os.remove(output_filepath)
            except Exception:
                pass
        await notify_combined_sse(
            job_id, {"type": "cancelled", "job_id": job_id, "message": "Combined export cancelled."}
        )
    except Exception as e:
        print(f"[Combined Export Error] Job {job_id} failed: {e}")
        job["status"] = "error"
        job["error"] = str(e)
        if os.path.exists(output_filepath):
            try:
                os.remove(output_filepath)
            except Exception:
                pass
        await notify_combined_sse(job_id, {"type": "error", "job_id": job_id, "error": str(e)})


@app.post("/api/export/combined")
async def export_combined_volume(req: CombinedExportRequest):
    """
    Merges all queued volumes into an e-reader optimized file or omnibus package.

    - format='epub'  → EPUB3 with chapter-level TOC per volume (Kindle Send-to-Kindle, Kobo, Apple Books)
    - format='mobi'  → Amazon Kindle MOBI fixed-layout manga
    - format='pdf'   → PDF with bookmarks per volume
    - chunk_by='volumes' / 'size_mb' → creates multi-part omnibus ZIP for huge collections
    """
    sessions_data = []
    if req.session_ids:
        for sid in req.session_ids:
            sess = SESSIONS.get(sid) or get_or_restore_session(sid)
            if sess:
                sessions_data.append(sess)

    # Fallback to all sessions in memory / on disk if none matched or none supplied
    if not sessions_data:
        for sess in list(SESSIONS.values()):
            if sess and sess not in sessions_data:
                sessions_data.append(sess)
        for d in sorted(STORAGE_DIR.iterdir()):
            if d.is_dir():
                sess = get_or_restore_session(d.name)
                if sess and sess not in sessions_data:
                    sessions_data.append(sess)

    # Filter out empty or unextracted sessions that have 0 pages
    sessions_data = [s for s in sessions_data if len(s.get("pages", [])) > 0]

    if not sessions_data:
        raise HTTPException(status_code=404, detail="No valid sessions with pages found to export")

    # Naturally sort sessions by filename so volumes appear in correct reading order (v01, v02, ...)
    def _natural_volume_key(s):
        fn = s.get("filename", "").lower()
        return [int(text) if text.isdigit() else text for text in re.split(r"(\d+)", fn)]

    sessions_data.sort(key=_natural_volume_key)

    # Pre-flight check: ensure at least 1 GB of free disk space is available
    try:
        _, _, free_bytes = shutil.disk_usage(str(OUTPUT_DIR))
        if free_bytes < 1024 * 1024 * 1024:
            raise HTTPException(
                status_code=507,
                detail=f"Low disk space: only {free_bytes // (1024 * 1024)} MB available. Free up disk space before exporting.",
            )
    except HTTPException:
        raise
    except Exception:
        pass

    fmt = (req.format or "epub").lower().strip()
    export_original = bool(req.export_original)
    default_title = "Manga Collection" if export_original else "Colorized Manga Collection"
    title = (req.title or default_title).strip() or default_title
    if title == "Colorized Manga Collection" and export_original:
        title = "Manga Collection"

    # Sanitize title for filename
    clean_title = re.sub(r"[^a-zA-Z0-9_\- ]", "", title).strip().replace(" ", "_")
    if not clean_title:
        clean_title = "manga_collection"
    if export_original and not clean_title.lower().startswith("original"):
        clean_title = f"Original_{clean_title}"

    token = str(uuid.uuid4())[:8]
    n = len(sessions_data)
    total_pages = sum(len(s.get("pages", [])) for s in sessions_data)

    chunk_by = (req.chunk_by or "none").lower().strip()
    chunk_size = req.chunk_size if (req.chunk_size is not None and req.chunk_size > 0) else 3
    max_dim = (
        req.max_dimension if (req.max_dimension is not None and req.max_dimension > 0) else None
    )
    jpeg_qual = req.jpeg_quality if (req.jpeg_quality is not None and req.jpeg_quality > 0) else 80
    is_gray = bool(req.grayscale)
    colorsoft_tune = bool(req.colorsoft_tune)

    will_chunk = False
    if chunk_by == "volumes" and n > chunk_size:
        will_chunk = True
    elif chunk_by in ["size_mb", "size"]:
        budget_mb = max(20, chunk_size)
        avg_kb = 160 if is_gray else (480 if (max_dim and max_dim <= 1600) else 750)
        total_est_mb = (total_pages * avg_kb) / 1024
        max_safe_pages = min(450, max(80, int((budget_mb * 1024) / avg_kb)))
        if total_est_mb > budget_mb or total_pages > max_safe_pages or (n > 1 and total_pages > 220):
            will_chunk = True

    if will_chunk:
        out_ext = ".zip"
        out_filename = f"{clean_title}_Omnibus_{token}.zip"
    else:
        if fmt == "pdf":
            out_ext = ".pdf"
        elif fmt in ["mobi", "azw3", "kindle"]:
            out_ext = ".mobi"
        else:
            out_ext = ".epub"
        out_filename = f"{clean_title}_{token}{out_ext}"

    output_filepath = str(OUTPUT_DIR / f"combined_{out_filename}")

    # Synchronous execution mode (for automated tests or simple scripts)
    if req.sync:
        try:
            await asyncio.to_thread(
                file_processor.build_combined_omnibus,
                sessions_data=sessions_data,
                output_filepath=output_filepath,
                export_format=fmt,
                title=title,
                chunk_by=chunk_by,
                chunk_size=chunk_size,
                max_dimension=max_dim,
                jpeg_quality=jpeg_qual,
                grayscale=is_gray,
                colorsoft_tune=colorsoft_tune,
                export_original=export_original,
            )
            return JSONResponse(
                {
                    "status": "success",
                    "format": fmt,
                    "download_url": f"/api/download/combined/{out_filename}",
                    "filename": out_filename,
                    "total_volumes": n,
                    "title": title,
                    "is_omnibus": will_chunk,
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Combined export failed: {str(e)}")

    # Asynchronous job mode with SSE streaming and cancellation support
    job_id = token
    job_info = {
        "job_id": job_id,
        "status": "processing",
        "cancel_requested": False,
        "format": fmt,
        "title": title,
        "out_filename": out_filename,
        "total_volumes": n,
        "total_pages": total_pages,
        "is_omnibus": will_chunk,
        "progress": {
            "percent": 0,
            "processed_pages": 0,
            "total_pages": total_pages,
            "status": "Starting export...",
        },
    }
    COMBINED_EXPORTS[job_id] = job_info

    asyncio.create_task(
        _async_combined_export_worker(
            job_id,
            sessions_data,
            output_filepath,
            out_filename,
            fmt,
            title,
            chunk_by=chunk_by,
            chunk_size=chunk_size,
            max_dimension=max_dim,
            jpeg_quality=jpeg_qual,
            grayscale=is_gray,
            colorsoft_tune=colorsoft_tune,
            export_original=export_original,
        )
    )

    return JSONResponse(
        {
            "status": "started",
            "job_id": job_id,
            "format": fmt,
            "total_volumes": n,
            "total_pages": total_pages,
            "title": title,
            "is_omnibus": will_chunk,
            "stream_url": f"/api/export/combined/stream/{job_id}",
            "cancel_url": f"/api/export/combined/cancel/{job_id}",
        }
    )


@app.get("/api/export/combined/stream/{job_id}")
async def stream_combined_export_progress(job_id: str):
    """Streams real-time progress and completion events for a combined export job."""
    job = COMBINED_EXPORTS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Combined export job not found")

    q = asyncio.Queue()
    if job_id not in COMBINED_EXPORT_QUEUES:
        COMBINED_EXPORT_QUEUES[job_id] = []
    COMBINED_EXPORT_QUEUES[job_id].append(q)

    async def event_generator():
        try:
            init_data = {
                "type": "init",
                "job_id": job_id,
                "status": job.get("status", "processing"),
                "progress": job.get("progress", {}),
            }
            yield f"data: {json.dumps(init_data)}\n\n"

            if job.get("status") == "completed":
                download_url = f"/api/download/combined/{job.get('out_filename', '')}"
                yield f"data: {json.dumps({'type': 'completed', 'job_id': job_id, 'download_url': download_url, 'filename': job.get('out_filename', '')})}\n\n"
                return
            elif job.get("status") == "cancelled":
                yield f"data: {json.dumps({'type': 'cancelled', 'job_id': job_id})}\n\n"
                return
            elif job.get("status") == "error":
                yield f"data: {json.dumps({'type': 'error', 'job_id': job_id, 'error': job.get('error', 'Export failed')})}\n\n"
                return

            while True:
                data = await q.get()
                yield f"data: {json.dumps(data)}\n\n"
                if data.get("type") in ["completed", "error", "cancelled"]:
                    break
        except asyncio.CancelledError:
            pass
        finally:
            if job_id in COMBINED_EXPORT_QUEUES and q in COMBINED_EXPORT_QUEUES[job_id]:
                COMBINED_EXPORT_QUEUES[job_id].remove(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/export/combined/cancel/{job_id}")
async def cancel_combined_export(job_id: str):
    """Cancels an active combined export job immediately and deletes partial files."""
    job = COMBINED_EXPORTS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Combined export job not found")

    job["cancel_requested"] = True
    job["status"] = "cancelled"
    await notify_combined_sse(
        job_id,
        {
            "type": "cancelled",
            "job_id": job_id,
            "message": "Combined export cancellation requested.",
        },
    )
    return JSONResponse({"status": "cancelled", "job_id": job_id})


@app.get("/api/export/combined/status/{job_id}")
async def get_combined_export_status(job_id: str):
    """Returns the current progress status of a combined export job."""
    job = COMBINED_EXPORTS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Combined export job not found")
    return JSONResponse(
        {
            "job_id": job_id,
            "status": job.get("status"),
            "progress": job.get("progress", {}),
            "cancel_requested": job.get("cancel_requested", False),
        }
    )


@app.get("/api/download/combined/{filename}")
async def download_combined_file(filename: str):
    """Serves a combined single-volume export file."""
    out_filepath = str(OUTPUT_DIR / f"combined_{filename}")
    if not os.path.exists(out_filepath):
        raise HTTPException(status_code=404, detail="Combined export not found or expired")
    ext = Path(filename).suffix.lower()
    if ext == ".epub":
        media_type = "application/epub+zip"
    elif ext == ".pdf":
        media_type = "application/pdf"
    elif ext == ".mobi":
        media_type = "application/x-mobipocket-ebook"
    elif ext == ".azw3":
        media_type = "application/vnd.amazon.mobi8-ebook"
    elif ext == ".zip":
        media_type = "application/zip"
    else:
        media_type = "application/octet-stream"
    return FileResponse(
        out_filepath, filename=filename, media_type=media_type, headers={"Accept-Ranges": "bytes"}
    )


@app.post("/api/export/{session_id}")
async def export_document(session_id: str, format: Optional[str] = None):
    if session_id in ("combined", "batch"):
        raise HTTPException(
            status_code=400, detail=f"'{session_id}' is a reserved route, not a session ID."
        )
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    ext = sess["ext"]
    original_path = sess["file_path"]
    pages_meta = sess["pages"]
    stem = Path(sess["filename"]).stem
    IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff"]

    target_format = (format or "auto").lower().strip()
    if target_format == "auto":
        if ext == ".pdf":
            target_format = "pdf"
        elif ext == ".epub":
            target_format = "epub"
        elif ext in IMAGE_EXTENSIONS:
            target_format = "image"
        elif ext == ".zip":
            target_format = "zip"
        else:
            target_format = "pdf"

    try:
        if target_format == "pdf":
            out_filename = f"colorized_{stem}.pdf"
            output_filepath = str(OUTPUT_DIR / f"{session_id}_{out_filename}")
            file_processor.build_colorized_pdf(pages_meta, session_id, output_filepath)

        elif target_format in ["mobi", "azw3", "kindle"]:
            out_filename = f"colorized_{stem}.mobi"
            output_filepath = str(OUTPUT_DIR / f"{session_id}_{out_filename}")
            file_processor.build_colorized_mobi(
                pages_meta, session_id, output_filepath, title=f"Colorized - {stem}"
            )

        elif target_format == "epub":
            out_filename = f"colorized_{stem}.epub"
            output_filepath = str(OUTPUT_DIR / f"{session_id}_{out_filename}")
            file_processor.build_colorized_epub(
                original_path, pages_meta, session_id, output_filepath, title=f"Colorized - {stem}"
            )

        elif target_format == "zip":
            out_filename = f"colorized_{stem}_images.zip"
            output_filepath = str(OUTPUT_DIR / f"{session_id}_{out_filename}")
            file_processor.build_colorized_zip(pages_meta, session_id, output_filepath)

        elif target_format in ["image", "single_image"]:
            if len(pages_meta) == 1:
                img_ext = ext if ext in IMAGE_EXTENSIONS else ".png"
                out_filename = f"colorized_{stem}{img_ext}"
                output_filepath = str(OUTPUT_DIR / f"{session_id}_{out_filename}")
                file_processor.build_colorized_single_image(pages_meta, session_id, output_filepath)
            else:
                out_filename = f"colorized_{stem}_images.zip"
                output_filepath = str(OUTPUT_DIR / f"{session_id}_{out_filename}")
                file_processor.build_colorized_zip(pages_meta, session_id, output_filepath)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported export format: {target_format}. Supported: pdf, epub, mobi, azw3, zip, image",
            )

        download_url = f"/api/download/{session_id}/{out_filename}"
        return JSONResponse(
            {
                "status": "success",
                "format": target_format,
                "download_url": download_url,
                "filename": out_filename,
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@app.get("/api/download/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    out_filepath = str(OUTPUT_DIR / f"{session_id}_{filename}")
    if not os.path.exists(out_filepath):
        raise HTTPException(status_code=404, detail="File not found or export expired")

    ext = Path(filename).suffix.lower()
    media_map = {
        ".epub": "application/epub+zip",
        ".pdf": "application/pdf",
        ".mobi": "application/x-mobipocket-ebook",
        ".azw3": "application/vnd.amazon.mobi8-ebook",
        ".zip": "application/zip",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    media_type = media_map.get(ext, "application/octet-stream")

    return FileResponse(out_filepath, filename=filename, media_type=media_type)


@app.get("/api/sessions")
async def list_sessions(batch_id: Optional[str] = None):
    """Returns list of active/cached sessions, optionally filtered by batch_id, naturally sorted by filename."""
    existing_dirs = {d.name for d in STORAGE_DIR.iterdir() if d.is_dir()}
    for sid in list(SESSIONS.keys()):
        if sid not in existing_dirs:
            SESSIONS.pop(sid, None)
            EVENT_QUEUES.pop(sid, None)

    for d_name in existing_dirs:
        if d_name not in SESSIONS:
            get_or_restore_session(d_name)

    results = []
    for sess in SESSIONS.values():
        if batch_id and sess.get("batch_id") != batch_id:
            continue
        sid = sess["session_id"]
        pages = sess.get("pages", [])
        if pages:
            actual_count = sum(1 for p in pages if p.get("status") == "colorized")
            sess["processed_count"] = actual_count
            total_p = sess.get("total_pages", len(pages))
            if total_p > 0 and actual_count >= total_p:
                sess["status"] = "completed"
            elif sess.get("status") == "processing" and not is_task_active(sid):
                sess["status"] = "pending" if actual_count > 0 else "idle"
                for p in pages:
                    if p.get("status") == "processing":
                        p["status"] = "pending"
                save_session_meta(sid)

        results.append(
            {
                "session_id": sess["session_id"],
                "batch_id": sess.get("batch_id"),
                "filename": sess["filename"],
                "ext": sess.get("ext", ""),
                "total_pages": sess.get("total_pages", 0),
                "processed_count": sess.get("processed_count", 0),
                "status": sess.get("status", "idle"),
                "is_active": is_task_active(sess["session_id"]),
            }
        )

    def _sort_key(s):
        fn = s.get("filename", "").lower()
        parts = [int(text) if text.isdigit() else text for text in re.split(r"(\d+)", fn)]
        return parts

    results.sort(key=_sort_key)
    return JSONResponse({"sessions": results})


@app.get("/api/colorize/batch/status")
async def get_batch_status():
    """Returns current active batch colorization status."""
    return JSONResponse(CURRENT_BATCH)


@app.post("/api/colorize/batch/start")
async def start_batch_colorization(req: BatchColorizeRequest):
    """Starts sequential colorization for a batch of documents."""
    global CURRENT_BATCH
    if CURRENT_BATCH.get("is_running"):
        return JSONResponse(
            {
                "status": "already_running",
                "message": "Batch colorization is already running",
                "batch": CURRENT_BATCH,
            }
        )

    valid_sessions = []
    for sid in req.session_ids:
        sess = SESSIONS.get(sid) or get_or_restore_session(sid)
        if sess:
            valid_sessions.append(sid)

    if not valid_sessions:
        raise HTTPException(
            status_code=404, detail="No valid sessions found for batch colorization"
        )

    CURRENT_BATCH = {
        "is_running": True,
        "total_docs": len(valid_sessions),
        "completed_docs": 0,
        "current_index": 0,
        "current_session_id": valid_sessions[0] if valid_sessions else None,
        "session_ids": valid_sessions,
    }

    async def _run_batch():
        global CURRENT_BATCH
        try:
            for idx, sid in enumerate(valid_sessions):
                if not CURRENT_BATCH.get("is_running"):
                    break
                CURRENT_BATCH["current_index"] = idx
                CURRENT_BATCH["current_session_id"] = sid

                sess = SESSIONS.get(sid) or get_or_restore_session(sid)
                if not sess:
                    continue

                pages = sess.get("pages", [])
                colorized_dir = STORAGE_DIR / sid / "colorized"
                uncolorized = [
                    p
                    for p in pages
                    if p.get("status") != "colorized"
                    or not (colorized_dir / p.get("filename", "")).exists()
                ]

                if not uncolorized and len(pages) > 0:
                    sess["status"] = "completed"
                    sess["processed_count"] = len(pages)
                    save_session_meta(sid)
                    CURRENT_BATCH["completed_docs"] += 1
                    await notify_sse_listeners(
                        sid,
                        {
                            "type": "completed",
                            "total_processed": len(pages),
                            "batch_info": {
                                "current_doc_idx": idx + 1,
                                "total_docs": len(valid_sessions),
                                "completed_docs": CURRENT_BATCH["completed_docs"],
                            },
                        },
                    )
                    continue

                single_req = ColorizeRequest(
                    session_id=sid,
                    model_provider=req.model_provider,
                    model_name=req.model_name,
                    api_key=req.api_key,
                    style=req.style,
                    saturation=req.saturation,
                    contrast=req.contrast,
                    line_preserve=req.line_preserve,
                    skip_if_colored=req.skip_if_colored,
                )
                task = asyncio.current_task()
                if task:
                    ACTIVE_COLORIZATION_TASKS[sid] = task
                try:
                    await _async_colorization_worker(sid, single_req)
                finally:
                    ACTIVE_COLORIZATION_TASKS.pop(sid, None)
                CURRENT_BATCH["completed_docs"] += 1
        finally:
            CURRENT_BATCH["is_running"] = False
            CURRENT_BATCH["current_session_id"] = None

    asyncio.create_task(_run_batch())
    return JSONResponse(
        {
            "status": "started",
            "message": f"Batch colorization started for {len(valid_sessions)} documents",
            "session_ids": valid_sessions,
        }
    )


@app.post("/api/colorize/batch/resume")
async def resume_batch_colorization(req: Optional[BatchColorizeRequest] = None):
    """
    Resumes batch colorization for pending sessions (where processed_count < total_pages).
    """
    global CURRENT_BATCH
    if CURRENT_BATCH.get("is_running"):
        return JSONResponse(
            {
                "status": "already_running",
                "message": "Batch colorization is already running",
                "batch": CURRENT_BATCH,
            }
        )

    target_sessions = []
    if req and req.session_ids:
        candidate_ids = req.session_ids
    elif CURRENT_BATCH.get("session_ids"):
        candidate_ids = CURRENT_BATCH.get("session_ids")
    else:
        existing_dirs = {d.name for d in STORAGE_DIR.iterdir() if d.is_dir()}
        for d_name in existing_dirs:
            if d_name not in SESSIONS:
                get_or_restore_session(d_name)
        candidate_ids = list(SESSIONS.keys())

    for sid in candidate_ids:
        sess = SESSIONS.get(sid) or get_or_restore_session(sid)
        if sess and sess.get("pages"):
            colorized_dir = STORAGE_DIR / sid / "colorized"
            has_pending = any(
                p.get("status") != "colorized"
                or not (colorized_dir / p.get("filename", "")).exists()
                or (colorized_dir / p.get("filename", "")).stat().st_size == 0
                for p in sess.get("pages", [])
            )
            if has_pending:
                target_sessions.append(sid)

    if not target_sessions:
        return JSONResponse(
            {
                "status": "completed",
                "message": "No pending sessions to resume",
                "batch": CURRENT_BATCH,
            }
        )

    batch_req = req or BatchColorizeRequest(session_ids=target_sessions)
    batch_req.session_ids = target_sessions
    return await start_batch_colorization(batch_req)


def remove_single_session_artifacts(session_id: str) -> bool:
    """
    Deletes all files and memory state for a single session ID.
    Returns True if session was found/deleted, False if already absent.
    """
    sess = SESSIONS.get(session_id) or get_or_restore_session(session_id)
    sess_dir = STORAGE_DIR / session_id

    # Stop any running process
    if sess:
        sess["cancel_requested"] = True

    # Pop from memory
    SESSIONS.pop(session_id, None)
    EVENT_QUEUES.pop(session_id, None)
    SESSION_PALETTES.pop(session_id, None)

    deleted = False

    # Delete storage directory
    if sess_dir.exists():
        shutil.rmtree(str(sess_dir), ignore_errors=True)
        deleted = True

    # Delete original uploaded file
    if sess and sess.get("file_path"):
        try:
            up_path = Path(sess["file_path"])
            if up_path.exists() and "uploads" in str(up_path.resolve()):
                up_path.unlink(missing_ok=True)
                deleted = True
        except Exception as e:
            print(f"Error removing upload file: {e}")

    for f in UPLOAD_DIR.glob(f"{session_id}_*"):
        f.unlink(missing_ok=True)
        deleted = True

    # Delete output archives
    for out_f in OUTPUT_DIR.glob(f"{session_id}_*"):
        try:
            out_f.unlink(missing_ok=True)
            deleted = True
        except Exception:
            pass

    return deleted or (sess is not None)


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Deletes a document session and its extracted/colorized files from disk and memory."""
    sess = SESSIONS.get(session_id) or get_or_restore_session(session_id)
    sess_dir = STORAGE_DIR / session_id
    if not sess and not sess_dir.exists():
        for f in UPLOAD_DIR.glob(f"{session_id}_*"):
            f.unlink(missing_ok=True)
        for out_f in OUTPUT_DIR.glob(f"{session_id}_*"):
            out_f.unlink(missing_ok=True)
        return JSONResponse(
            {
                "status": "success",
                "message": f"Document session {session_id} already deleted",
                "deleted_session_id": session_id,
            }
        )

    remove_single_session_artifacts(session_id)

    return JSONResponse(
        {
            "status": "success",
            "message": f"Document session {session_id} deleted successfully",
            "deleted_session_id": session_id,
        }
    )


@app.post("/api/sessions/bulk-delete")
async def bulk_delete_sessions(req: BulkDeleteSessionsRequest):
    """
    Bulk deletes specified document sessions and their files.
    If delete_all=True or session_ids is empty with delete_all, deletes all sessions.
    """
    deleted_ids = []
    failed_ids = []

    if req.delete_all:
        all_sids = set(SESSIONS.keys())
        for d in STORAGE_DIR.iterdir():
            if d.is_dir():
                all_sids.add(d.name)
        for sid in all_sids:
            try:
                remove_single_session_artifacts(sid)
                deleted_ids.append(sid)
            except Exception:
                failed_ids.append(sid)
        return JSONResponse(
            {
                "status": "success",
                "message": f"All {len(deleted_ids)} document sessions deleted successfully",
                "deleted_session_ids": deleted_ids,
                "failed_session_ids": failed_ids,
                "count": len(deleted_ids),
            }
        )

    if not req.session_ids:
        raise HTTPException(status_code=400, detail="No session_ids provided for bulk deletion.")

    for sid in req.session_ids:
        try:
            remove_single_session_artifacts(sid)
            deleted_ids.append(sid)
        except Exception:
            failed_ids.append(sid)

    return JSONResponse(
        {
            "status": "success",
            "message": f"Successfully deleted {len(deleted_ids)} document session(s)",
            "deleted_session_ids": deleted_ids,
            "failed_session_ids": failed_ids,
            "count": len(deleted_ids),
        }
    )


def is_authentic_user_manga(name: str = "", title: str = "", sid: str = "") -> bool:
    """Identifies authentic user manga collections (such as Dr. Slump or One Piece)
    that must be preserved unless purge_all is explicitly specified."""
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


@app.post("/api/test/cleanup")
async def cleanup_test_data_endpoint(req: Optional[TestCleanupRequest] = None):
    """
    Cleans up sessions, uploaded files, and exported archives generated during testing.
    Can clean specific session IDs, all test-pattern sessions, or all sessions.
    """
    session_ids = req.session_ids if req else None
    purge_all = req.purge_all if req else False
    clean_orphans = req.clean_orphans if req else True

    cleaned_sids = []
    freed_bytes = 0

    def calc_size(p: Path) -> int:
        try:
            if p.is_file():
                return p.stat().st_size
            elif p.is_dir():
                return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        except Exception:
            pass
        return 0

    test_keywords = [
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

    # 1. Determine target session IDs
    target_sids = set()
    if session_ids:
        target_sids.update(session_ids)
    elif purge_all:
        target_sids.update(SESSIONS.keys())
        for d in STORAGE_DIR.iterdir():
            if d.is_dir():
                target_sids.add(d.name)
    else:
        all_sids = set(SESSIONS.keys())
        for d in STORAGE_DIR.iterdir():
            if d.is_dir():
                all_sids.add(d.name)

        for sid in all_sids:
            sess = SESSIONS.get(sid) or get_or_restore_session(sid)
            fn = (sess.get("filename") or "").lower() if sess else ""
            title = (sess.get("title") or "").lower() if sess else ""
            # Preserve authentic user volumes unless purge_all is explicitly requested
            if is_authentic_user_manga(name=fn, title=title, sid=sid):
                continue
            is_test = False
            for kw in test_keywords:
                if kw in sid.lower() or kw in fn or kw in title:
                    is_test = True
                    break
            if is_test:
                target_sids.add(sid)

    # 2. Purge target sessions
    for sid in target_sids:
        sess_dir = STORAGE_DIR / sid
        freed_bytes += calc_size(sess_dir)
        for f in UPLOAD_DIR.glob(f"{sid}_*"):
            freed_bytes += calc_size(f)
            f.unlink(missing_ok=True)
        for out_f in OUTPUT_DIR.glob(f"{sid}_*"):
            freed_bytes += calc_size(out_f)
            out_f.unlink(missing_ok=True)
        if sess_dir.exists():
            shutil.rmtree(str(sess_dir), ignore_errors=True)
        SESSIONS.pop(sid, None)
        EVENT_QUEUES.pop(sid, None)
        cleaned_sids.append(sid)

    # 3. Clean orphan or test output files if requested
    cleaned_output_files = 0
    if clean_orphans or purge_all:
        disk_sids = {d.name for d in STORAGE_DIR.iterdir() if d.is_dir()}
        for sid in list(SESSIONS.keys()):
            if sid not in disk_sids:
                SESSIONS.pop(sid, None)
                EVENT_QUEUES.pop(sid, None)
        active_sids = set(SESSIONS.keys()) | disk_sids

        for f in OUTPUT_DIR.iterdir():
            if not f.is_file():
                continue
            name_lower = f.name.lower()
            is_user = is_authentic_user_manga(name=name_lower)
            if is_user and not purge_all:
                continue

            should_delete = False
            if purge_all:
                should_delete = True
            elif any(k in name_lower for k in test_keywords):
                should_delete = True
            elif name_lower.startswith("combined_") or name_lower.startswith("batch_"):
                if not is_user:
                    should_delete = True
            else:
                prefix = f.name.split("_")[0]
                if prefix not in active_sids:
                    should_delete = True

            if should_delete:
                freed_bytes += calc_size(f)
                f.unlink(missing_ok=True)
                cleaned_output_files += 1

        for f in UPLOAD_DIR.iterdir():
            if not f.is_file():
                continue
            name_lower = f.name.lower()
            if is_authentic_user_manga(name=name_lower) and not purge_all:
                continue
            should_delete = False
            if purge_all:
                should_delete = True
            elif any(k in name_lower for k in test_keywords):
                should_delete = True
            else:
                prefix = f.name.split("_")[0]
                if prefix not in active_sids:
                    should_delete = True
            if should_delete:
                freed_bytes += calc_size(f)
                f.unlink(missing_ok=True)

    return JSONResponse(
        {
            "status": "success",
            "cleaned_sessions_count": len(cleaned_sids),
            "cleaned_sessions": cleaned_sids,
            "cleaned_output_files": cleaned_output_files,
            "freed_bytes": freed_bytes,
            "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        }
    )


@app.delete("/api/session/{session_id}/page/{page_index}")
async def delete_session_page(session_id: str, page_index: int):
    """Deletes a specific page from a document session and cleans up its files."""
    sess = SESSIONS.get(session_id) or get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    pages = sess.get("pages", [])
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(
            status_code=400, detail=f"Invalid page index: {page_index}. Total pages: {len(pages)}"
        )

    del_page = pages.pop(page_index)

    # Delete original image file from disk
    orig_path = Path(del_page.get("original_path", ""))
    if orig_path.exists():
        try:
            orig_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"Error deleting original page image: {e}")

    # Delete colorized image file from disk if present
    color_filename = del_page.get("filename")
    if color_filename:
        c_path = STORAGE_DIR / session_id / "colorized" / color_filename
        if c_path.exists():
            try:
                c_path.unlink(missing_ok=True)
            except Exception as e:
                print(f"Error deleting colorized page image: {e}")

    # Re-index remaining pages
    for i, p in enumerate(pages):
        p["page_index"] = i
        p["display_name"] = f"Page {i + 1}"

    sess["total_pages"] = len(pages)
    sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")
    if sess["total_pages"] == 0:
        sess["status"] = "idle"
    elif sess["processed_count"] == sess["total_pages"]:
        sess["status"] = "completed"

    save_session_meta(session_id)

    return JSONResponse(
        {
            "status": "success",
            "message": "Page deleted successfully",
            "total_pages": sess["total_pages"],
            "session": sess,
        }
    )


@app.delete("/api/sessions")
async def delete_all_sessions(
    req: Optional[BulkDeleteSessionsRequest] = Body(None),
    session_ids: Optional[str] = Query(None, description="Comma-separated session IDs to delete"),
):
    """
    Deletes all document sessions, uploads, and outputs, OR bulk deletes specified sessions
    if session_ids is provided via JSON body or query param.
    """
    target_ids = []
    if req and req.session_ids:
        target_ids.extend(req.session_ids)
    elif session_ids:
        target_ids.extend([s.strip() for s in session_ids.split(",") if s.strip()])

    if target_ids:
        deleted_ids = []
        failed_ids = []
        for sid in target_ids:
            try:
                remove_single_session_artifacts(sid)
                deleted_ids.append(sid)
            except Exception:
                failed_ids.append(sid)
        return JSONResponse(
            {
                "status": "success",
                "message": f"Successfully deleted {len(deleted_ids)} document session(s)",
                "deleted_session_ids": deleted_ids,
                "failed_session_ids": failed_ids,
                "count": len(deleted_ids),
            }
        )

    # Default fallback: delete all sessions
    for sess in SESSIONS.values():
        sess["cancel_requested"] = True

    EVENT_QUEUES.clear()
    SESSION_PALETTES.clear()

    # Clean sessions/ storage
    for item in STORAGE_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(str(item), ignore_errors=True)

    # Clean uploads/ directory
    for item in UPLOAD_DIR.iterdir():
        if item.is_file() and not item.name.startswith("."):
            try:
                item.unlink(missing_ok=True)
            except Exception:
                pass

    # Clean output/ directory
    for item in OUTPUT_DIR.iterdir():
        if item.is_file() and not item.name.startswith("."):
            try:
                item.unlink(missing_ok=True)
            except Exception:
                pass

    SESSIONS.clear()

    return JSONResponse(
        {"status": "success", "message": "All document sessions and files deleted successfully"}
    )


@app.get("/favicon.ico", include_in_schema=False)
async def get_favicon():
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/x-icon")
    return JSONResponse(status_code=404, content={"detail": "Favicon not found"})


# Serve Frontend static assets
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    import argparse
    import socket
    import threading
    import time
    import webbrowser

    parser = argparse.ArgumentParser(description="🎨 Kobean Manga Colorizer Web Studio")
    parser.add_argument("--host", default="127.0.0.1", help="Host IP to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable live code reloading")
    parser.add_argument(
        "--no-open", action="store_true", help="Do not automatically open browser on launch"
    )
    args = parser.parse_args()

    def is_port_busy(port: int, host: str = "127.0.0.1") -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex((host, port)) == 0

    if is_port_busy(args.port, args.host):
        print(f"\n⚠️  [Notice] Port {args.port} is already busy on {args.host}.")
        print(f"👉 Studio might already be running: http://{args.host}:{args.port}")
        print(f"👉 To terminate any old process: lsof -ti :{args.port} | xargs kill -9\n")

    if not args.no_open:

        def _launch_browser(host: str, port: int):
            url = f"http://{host}:{port}"
            for _ in range(40):
                time.sleep(0.25)
                if is_port_busy(port, host):
                    try:
                        webbrowser.open(url)
                    except Exception:
                        pass
                    break

        threading.Thread(target=_launch_browser, args=(args.host, args.port), daemon=True).start()

    banner = f"""
╔═══════════════════════════════════════════════════════════════╗
║               🎨  Kobean Manga Colorizer Studio               ║
╠═══════════════════════════════════════════════════════════════╣
║  🌐 Studio URL:    http://{args.host}:{args.port:<5}                             ║
║  ⚡ Hardware:      Apple Silicon MPS / CUDA / CPU             ║
║  📂 Workspace:     {str(BASE_DIR):<42} ║
║  🛑 Stop Studio:   Press CTRL + C                             ║
╚═══════════════════════════════════════════════════════════════╝
"""
    print(banner)

    import uvicorn

    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)
