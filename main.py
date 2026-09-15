import os
import shutil
import uuid
import json
import asyncio
import re
from typing import Dict, List, Optional, Any
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from file_processor import MangaFileProcessor
from colorizer_engine import MangaColorizerEngine, CharacterPalette, CharacterEntry

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

# Instantiate core engines
file_processor = MangaFileProcessor(storage_dir=str(STORAGE_DIR))
colorizer_engine = MangaColorizerEngine()

# Session state store
# session_id -> { "file_path": str, "filename": str, "ext": str, "pages": [...], "status": "idle"|"processing"|"completed", "progress": {...} }
SESSIONS: Dict[str, dict] = {}
# session_id -> asyncio.Queue for SSE events
EVENT_QUEUES: Dict[str, List[asyncio.Queue]] = {}

# Global Active Batch Tracking
CURRENT_BATCH: Dict[str, Any] = {
    "is_running": False,
    "total_docs": 0,
    "completed_docs": 0,
    "current_index": 0,
    "current_session_id": None,
    "session_ids": []
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
    if session_id in SESSIONS:
        return SESSIONS[session_id]

    sess_dir = STORAGE_DIR / session_id
    if not sess_dir.exists():
        return None

    meta_path = sess_dir / "meta.json"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                sess = json.load(f)
                if "pages" in sess:
                    sess["processed_count"] = sum(1 for p in sess["pages"] if p.get("status") == "colorized")
                    if sess.get("total_pages") and sess["processed_count"] == sess["total_pages"]:
                        sess["status"] = "completed"
                SESSIONS[session_id] = sess
                if session_id not in EVENT_QUEUES:
                    EVENT_QUEUES[session_id] = []
                return sess
        except Exception as e:
            print(f"[Session Warning] Error loading meta.json for {session_id}: {e}")

    # Fallback auto-recovery from disk session folders
    orig_dir = sess_dir / "original"
    if orig_dir.exists():
        orig_files = sorted(list(orig_dir.glob("*.*")))
        if orig_files:
            pages = []
            colorized_dir = sess_dir / "colorized"
            for idx, p_path in enumerate(orig_files):
                c_path = colorized_dir / p_path.name
                is_colored = c_path.exists()
                pages.append({
                    "page_index": idx,
                    "display_name": f"Page {idx + 1}",
                    "filename": p_path.name,
                    "original_path": str(p_path),
                    "status": "colorized" if is_colored else "pending",
                    "colorized_url": f"/api/session/{session_id}/image/colorized/{p_path.name}" if is_colored else None,
                    "engine_used": "ResNeXt-50/101 Generator + Vibrant Chroma (MPS)" if is_colored else None
                })
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
                "model_name": "resnext-v2-manga"
            }
            SESSIONS[session_id] = recovered
            if session_id not in EVENT_QUEUES:
                EVENT_QUEUES[session_id] = []
            save_session_meta(session_id)
            return recovered
    return None

class ColorizeRequest(BaseModel):
    session_id: str
    model_provider: str = "google_nano" # "google_nano", "apple_foundation", "local_smart"
    model_name: str = "nano-banana"
    api_key: Optional[str] = ""
    style: str = "gemini_anime"
    saturation: float = 1.2
    contrast: float = 1.1
    line_preserve: float = 0.85
    selected_pages: Optional[List[int]] = None
    skip_if_colored: bool = False
    force_recolorize: bool = False   # when True, re-run even if page already has a colorized file

class BatchColorizeRequest(BaseModel):
    session_ids: List[str]
    model_provider: str = "google_nano"
    model_name: str = "nano-banana"
    api_key: Optional[str] = ""
    style: str = "gemini_anime"
    saturation: float = 1.2
    contrast: float = 1.1
    line_preserve: float = 0.85
    skip_if_colored: bool = False

class BatchExportRequest(BaseModel):
    session_ids: List[str]
    format: Optional[str] = "auto"

class CombinedExportRequest(BaseModel):
    session_ids: Optional[List[str]] = None
    format: str = "epub"   # "epub" or "pdf"
    title: Optional[str] = "Colorized Manga Collection"
    sync: Optional[bool] = False

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

# ── Character Palette models ─────────────────────────────────────────

class CharacterEntryModel(BaseModel):
    name: str
    hair_hex: str = ""
    skin_hex: str = ""
    costume_hex: str = ""
    extra_hex: str = ""

class PaletteUpsertRequest(BaseModel):
    session_id: str
    character: CharacterEntryModel

class PaletteDeleteRequest(BaseModel):
    session_id: str
    character_name: str

# In-memory palette store: session_id -> CharacterPalette
SESSION_PALETTES: Dict[str, CharacterPalette] = {}


def _get_palette(session_id: str) -> CharacterPalette:
    """Returns the palette for a session, creating an empty one if not present."""
    if session_id not in SESSION_PALETTES:
        SESSION_PALETTES[session_id] = CharacterPalette()
    return SESSION_PALETTES[session_id]


@app.post("/api/upload")
async def upload_files(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    batch_id: Optional[str] = Form(None)
):
    upload_list = []
    if files:
        upload_list.extend(files)
    if file:
        upload_list.append(file)

    if not upload_list:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    ALLOWED_EXTENSIONS = [".pdf", ".epub", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".zip"]
    effective_batch_id = batch_id or str(uuid.uuid4())
    created_sessions = []

    for uploaded_file in upload_list:
        ext = Path(uploaded_file.filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue

        session_id = str(uuid.uuid4())
        upload_path = UPLOAD_DIR / f"{session_id}_{uploaded_file.filename}"

        with open(upload_path, "wb") as buffer:
            content = await uploaded_file.read()
            buffer.write(content)

        try:
            pages_meta = file_processor.process_input_file(str(upload_path), session_id)
        except Exception as e:
            if upload_path.exists():
                upload_path.unlink()
            print(f"[Upload Parse Error] {uploaded_file.filename}: {e}")
            continue

        for page in pages_meta:
            page["status"] = "pending"
            page["colorized_url"] = None

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
            "model_name": "nano-banana"
        }
        SESSIONS[session_id] = sess_obj
        EVENT_QUEUES[session_id] = []
        save_session_meta(session_id)
        created_sessions.append(sess_obj)

    if not created_sessions:
        raise HTTPException(status_code=400, detail="Failed to parse any of the uploaded files.")

    session_summaries = []
    for s in created_sessions:
        session_summaries.append({
            "session_id": s["session_id"],
            "batch_id": effective_batch_id,
            "filename": s["filename"],
            "ext": s["ext"],
            "total_pages": s["total_pages"],
            "status": s["status"],
            "processed_count": s["processed_count"]
        })

    primary = created_sessions[0]
    return JSONResponse({
        "status": "success",
        "batch_id": effective_batch_id,
        "total_files": len(created_sessions),
        "sessions": session_summaries,
        # backward compatibility fields:
        "session_id": primary["session_id"],
        "filename": primary["filename"],
        "total_pages": primary["total_pages"],
        "pages": primary["pages"]
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
                s.get("total_pages", 0)
            ),
            reverse=True
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
async def stream_progress(session_id: str):
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    q = asyncio.Queue()
    if session_id not in EVENT_QUEUES:
        EVENT_QUEUES[session_id] = []
    EVENT_QUEUES[session_id].append(q)

    async def event_generator():
        try:
            # Yield initial status
            init_data = {
                "type": "init",
                "session": sess
            }
            yield f"data: {json.dumps(init_data)}\n\n"

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

    await notify_sse_listeners(session_id, {
        "type": "start",
        "total": sess["total_pages"],
        "model_provider": req.model_provider,
        "model_name": req.model_name
    })

    pages = sess["pages"]
    target_pages = req.selected_pages if req.selected_pages is not None else list(range(len(pages)))

    session_dir = STORAGE_DIR / session_id
    colorized_dir = session_dir / "colorized"
    colorized_dir.mkdir(parents=True, exist_ok=True)

    # Ensure processed_count strictly reflects actual colorized pages
    sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")

    for idx in target_pages:
        # Check if cancellation was requested before processing next page
        if sess.get("cancel_requested"):
            sess["status"] = "cancelled"
            for p in pages:
                if p.get("status") == "processing":
                    p["status"] = "pending"
            await notify_sse_listeners(session_id, {
                "type": "cancelled",
                "processed_count": sess["processed_count"],
                "total": sess["total_pages"]
            })
            return

        if idx >= len(pages):
            continue
        
        page_info = pages[idx]
        orig_path = page_info["original_path"]
        color_filename = page_info["filename"]
        output_path = str(colorized_dir / color_filename)

        # Skip if page is already colorized and output file exists on disk,
        # UNLESS the caller explicitly requested a force recolorize.
        if (not req.force_recolorize
                and page_info.get("status") == "colorized"
                and Path(output_path).exists()
                and Path(output_path).stat().st_size > 0):
            if not page_info.get("colorized_url"):
                page_info["colorized_url"] = f"/api/session/{session_id}/image/colorized/{color_filename}"
            continue

        # When forcing recolorize, reset page status so the UI shows it as in-flight
        if req.force_recolorize:
            page_info["status"] = "pending"
            page_info.pop("skipped_colored", None)


        page_info["status"] = "processing"
        
        await notify_sse_listeners(session_id, {
            "type": "page_update",
            "page_index": idx,
            "status": "processing",
            "progress": f"{idx + 1}/{len(pages)}"
        })

        try:
            # Resolve palette for this session (if any characters are defined)
            palette = SESSION_PALETTES.get(session_id)
            if palette and not palette.characters:
                palette = None

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
            )

            # Check again immediately after colorizing in case cancel was pressed mid-task
            if sess.get("cancel_requested"):
                sess["status"] = "cancelled"
                page_info["status"] = "colorized"
                page_info["colorized_url"] = f"/api/session/{session_id}/image/colorized/{color_filename}"
                sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")
                await notify_sse_listeners(session_id, {
                    "type": "cancelled",
                    "processed_count": sess["processed_count"],
                    "total": sess["total_pages"]
                })
                return

            # "skipped_colored" counts as colorized — output was copied as-is
            eff_status = "colorized"
            page_info["status"] = eff_status
            page_info["colorized_url"] = f"/api/session/{session_id}/image/colorized/{color_filename}"
            page_info["engine_used"] = res.get("engine", req.model_provider)
            if res.get("status") == "skipped_colored":
                page_info["skipped_colored"] = True

            sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")
            save_session_meta(session_id)

            await notify_sse_listeners(session_id, {
                "type": "page_update",
                "page_index": idx,
                "status": "colorized",
                "colorized_url": page_info["colorized_url"],
                "engine": page_info["engine_used"],
                "processed_count": sess["processed_count"],
                "total": sess["total_pages"]
            })

        except Exception as e:
            print(f"Error colorizing page {idx}: {e}")
            page_info["status"] = "error"
            page_info["error_msg"] = str(e)
            save_session_meta(session_id)

            await notify_sse_listeners(session_id, {
                "type": "page_update",
                "page_index": idx,
                "status": "error",
                "error": str(e)
            })

    sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")
    sess["status"] = "completed"
    save_session_meta(session_id)
    await notify_sse_listeners(session_id, {
        "type": "completed",
        "total_processed": sess["processed_count"]
    })

@app.post("/api/colorize/start")
async def start_colorization(req: ColorizeRequest):
    session_id = req.session_id
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    if sess["status"] == "processing":
        raise HTTPException(status_code=400, detail="Colorization already in progress")

    sess["cancel_requested"] = False
    sess["status"] = "processing"
    save_session_meta(session_id)
    
    # Launch worker directly on main event loop using asyncio.create_task
    asyncio.create_task(_async_colorization_worker(session_id, req))
    return JSONResponse({"status": "started", "session_id": session_id})

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

    await notify_sse_listeners(session_id, {
        "type": "cancelled",
        "processed_count": sess["processed_count"],
        "total": sess["total_pages"]
    })

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
        palette = SESSION_PALETTES.get(session_id)
        if palette and not palette.characters:
            palette = None

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
        )

        page_info["status"] = "colorized"
        page_info["colorized_url"] = f"/api/session/{session_id}/image/colorized/{color_filename}"
        page_info["engine_used"] = res.get("engine", req.model_provider)
        if res.get("status") == "skipped_colored":
            page_info["skipped_colored"] = True


        # Update processed_count and status
        sess["processed_count"] = sum(1 for p in pages if p.get("status") == "colorized")
        if sess["processed_count"] == sess.get("total_pages", len(pages)):
            sess["status"] = "completed"

        save_session_meta(session_id)

        await notify_sse_listeners(session_id, {
            "type": "page_update",
            "page_index": req.page_index,
            "status": "colorized",
            "colorized_url": page_info["colorized_url"],
            "engine": page_info["engine_used"],
            "processed_count": sess["processed_count"],
            "total": sess.get("total_pages", len(pages))
        })

        return JSONResponse({
            "status": "success",
            "page_index": req.page_index,
            "colorized_url": page_info["colorized_url"],
            "engine": page_info["engine_used"],
            "page_info": page_info,
            "processed_count": sess["processed_count"],
            "total_pages": sess.get("total_pages", len(pages))
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")

@app.get("/api/palette/{session_id}")
async def get_palette(session_id: str):
    """Returns the character color palette for the given session."""
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    palette = _get_palette(session_id)
    return JSONResponse({"session_id": session_id, "palette": palette.to_dict()})


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
    )
    # Replace existing entry by name, or append
    palette.characters = [c for c in palette.characters if c.name.lower() != new_entry.name.lower()]
    palette.characters.append(new_entry)

    return JSONResponse({
        "status": "ok",
        "session_id": req.session_id,
        "palette": palette.to_dict()
    })


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

    return JSONResponse({
        "status": "ok",
        "removed": removed,
        "session_id": session_id,
        "palette": palette.to_dict()
    })


@app.delete("/api/palette/{session_id}")
async def clear_palette(session_id: str):
    """Clears all characters from the session palette."""
    sess = get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    SESSION_PALETTES[session_id] = CharacterPalette()
    return JSONResponse({"status": "ok", "session_id": session_id, "palette": {"characters": []}})


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

    if format_override == "epub":
        out_filename = f"colorized_manga_epubs_{batch_token}.zip"
    elif format_override == "pdf":
        out_filename = f"colorized_manga_pdfs_{batch_token}.zip"
    else:
        out_filename = f"colorized_manga_collection_{batch_token}.zip"

    output_filepath = str(OUTPUT_DIR / f"batch_{out_filename}")

    try:
        file_processor.build_batch_export(sessions_data, output_filepath, format_override=format_override)
        download_url = f"/api/download/batch/{out_filename}"
        return JSONResponse({
            "status": "success",
            "format": format_override,
            "download_url": download_url,
            "filename": out_filename,
            "total_documents": len(sessions_data)
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch export failed: {str(e)}")


# ── Combined Export Background State ──────────────────────────────────
COMBINED_EXPORTS: Dict[str, dict] = {}
COMBINED_EXPORT_QUEUES: Dict[str, List[asyncio.Queue]] = {}


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
    title: str
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
        if fmt == "pdf":
            await asyncio.to_thread(
                file_processor.build_combined_pdf,
                sessions_data,
                output_filepath,
                title,
                progress_callback=on_progress,
                cancel_check=check_cancelled
            )
        else:
            await asyncio.to_thread(
                file_processor.build_combined_epub,
                sessions_data,
                output_filepath,
                title,
                progress_callback=on_progress,
                cancel_check=check_cancelled
            )

        if job.get("cancel_requested"):
            job["status"] = "cancelled"
            if os.path.exists(output_filepath):
                try:
                    os.remove(output_filepath)
                except Exception:
                    pass
            await notify_combined_sse(job_id, {
                "type": "cancelled",
                "job_id": job_id,
                "message": "Combined export cancelled."
            })
            return

        job["status"] = "completed"
        if "progress" not in job or not job["progress"]:
            job["progress"] = {}
        job["progress"]["percent"] = 100
        download_url = f"/api/download/combined/{out_filename}"
        job["download_url"] = download_url
        await notify_combined_sse(job_id, {
            "type": "completed",
            "job_id": job_id,
            "download_url": download_url,
            "filename": out_filename,
            "total_volumes": len(sessions_data),
            "title": title
        })

    except InterruptedError:
        job["status"] = "cancelled"
        if os.path.exists(output_filepath):
            try:
                os.remove(output_filepath)
            except Exception:
                pass
        await notify_combined_sse(job_id, {
            "type": "cancelled",
            "job_id": job_id,
            "message": "Combined export cancelled."
        })
    except Exception as e:
        print(f"[Combined Export Error] Job {job_id} failed: {e}")
        job["status"] = "error"
        job["error"] = str(e)
        if os.path.exists(output_filepath):
            try:
                os.remove(output_filepath)
            except Exception:
                pass
        await notify_combined_sse(job_id, {
            "type": "error",
            "job_id": job_id,
            "error": str(e)
        })


@app.post("/api/export/combined")
async def export_combined_volume(req: CombinedExportRequest):
    """
    Merges all queued volumes into a single file for seamless e-reader reading.

    - format='epub'  → one EPUB3 with chapter-level TOC per volume (Kindle, Kobo, Apple Books)
    - format='pdf'   → one PDF with bookmarks per volume
    """
    sessions_data = []
    if req.session_ids:
        for sid in req.session_ids:
            sess = SESSIONS.get(sid) or get_or_restore_session(sid)
            if sess:
                sessions_data.append(sess)

    # Fallback to all sessions in memory / on disk if none matched or none supplied
    if not sessions_data:
        for sid, sess in list(SESSIONS.items()):
            if sess and sess not in sessions_data:
                sessions_data.append(sess)
        for d in sorted(STORAGE_DIR.iterdir()):
            if d.is_dir():
                sess = get_or_restore_session(d.name)
                if sess and sess not in sessions_data:
                    sessions_data.append(sess)

    if not sessions_data:
        raise HTTPException(status_code=404, detail="No valid sessions found to export")

    fmt   = (req.format or "epub").lower().strip()
    title = (req.title or "Colorized Manga Collection").strip() or "Colorized Manga Collection"
    # Sanitize title for filename
    clean_title = re.sub(r'[^a-zA-Z0-9_\- ]', '', title).strip().replace(' ', '_')
    if not clean_title:
        clean_title = "manga_collection"
    token = str(uuid.uuid4())[:8]
    n     = len(sessions_data)
    total_pages = sum(len(s.get("pages", [])) for s in sessions_data)

    out_ext = ".pdf" if fmt == "pdf" else ".epub"
    out_filename   = f"{clean_title}_{token}{out_ext}"
    output_filepath = str(OUTPUT_DIR / f"combined_{out_filename}")

    # Synchronous execution mode (for automated tests or simple scripts)
    if req.sync:
        try:
            if fmt == "pdf":
                await asyncio.to_thread(file_processor.build_combined_pdf, sessions_data, output_filepath, title)
            else:
                await asyncio.to_thread(file_processor.build_combined_epub, sessions_data, output_filepath, title)
            return JSONResponse({
                "status": "success",
                "format": fmt,
                "download_url": f"/api/download/combined/{out_filename}",
                "filename": out_filename,
                "total_volumes": n,
                "title": title,
            })
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
        "progress": {
            "percent": 0,
            "processed_pages": 0,
            "total_pages": total_pages,
            "status": "Starting export..."
        }
    }
    COMBINED_EXPORTS[job_id] = job_info

    asyncio.create_task(
        _async_combined_export_worker(
            job_id, sessions_data, output_filepath, out_filename, fmt, title
        )
    )

    return JSONResponse({
        "status": "started",
        "job_id": job_id,
        "format": fmt,
        "total_volumes": n,
        "total_pages": total_pages,
        "title": title,
        "stream_url": f"/api/export/combined/stream/{job_id}",
        "cancel_url": f"/api/export/combined/cancel/{job_id}"
    })


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
                "progress": job.get("progress", {})
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
    await notify_combined_sse(job_id, {
        "type": "cancelled",
        "job_id": job_id,
        "message": "Combined export cancellation requested."
    })
    return JSONResponse({"status": "cancelled", "job_id": job_id})


@app.get("/api/export/combined/status/{job_id}")
async def get_combined_export_status(job_id: str):
    """Returns the current progress status of a combined export job."""
    job = COMBINED_EXPORTS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Combined export job not found")
    return JSONResponse({
        "job_id": job_id,
        "status": job.get("status"),
        "progress": job.get("progress", {}),
        "cancel_requested": job.get("cancel_requested", False)
    })


@app.get("/api/download/combined/{filename}")
async def download_combined_file(filename: str):
    """Serves a combined single-volume export file."""
    out_filepath = str(OUTPUT_DIR / f"combined_{filename}")
    if not os.path.exists(out_filepath):
        raise HTTPException(status_code=404, detail="Combined export not found or expired")
    ext = Path(filename).suffix.lower()
    media_type = "application/epub+zip" if ext == ".epub" else "application/pdf"
    return FileResponse(out_filepath, filename=filename, media_type=media_type)



@app.post("/api/export/{session_id}")
async def export_document(session_id: str, format: Optional[str] = None):
    if session_id in ("combined", "batch"):
        raise HTTPException(status_code=400, detail=f"'{session_id}' is a reserved route, not a session ID.")
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
            raise HTTPException(status_code=400, detail=f"Unsupported export format: {target_format}. Supported: pdf, epub, zip, image")

        download_url = f"/api/download/{session_id}/{out_filename}"
        return JSONResponse({
            "status": "success",
            "format": target_format,
            "download_url": download_url,
            "filename": out_filename
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")

@app.get("/api/download/{session_id}/{filename}")
async def download_file(session_id: str, filename: str):
    out_filepath = str(OUTPUT_DIR / f"{session_id}_{filename}")
    if not os.path.exists(out_filepath):
        raise HTTPException(status_code=404, detail="File not found or export expired")

    return FileResponse(
        out_filepath,
        filename=filename,
        media_type="application/octet-stream"
    )

@app.get("/api/sessions")
async def list_sessions(batch_id: Optional[str] = None):
    """Returns list of active/cached sessions, optionally filtered by batch_id, naturally sorted by filename."""
    dirs = [d for d in STORAGE_DIR.iterdir() if d.is_dir()]
    for d in dirs:
        if d.name not in SESSIONS:
            get_or_restore_session(d.name)

    results = []
    for sess in SESSIONS.values():
        if batch_id and sess.get("batch_id") != batch_id:
            continue
        pages = sess.get("pages", [])
        if pages:
            actual_count = sum(1 for p in pages if p.get("status") == "colorized")
            sess["processed_count"] = actual_count
            if actual_count >= len(pages):
                sess["status"] = "completed"

        results.append({
            "session_id": sess["session_id"],
            "batch_id": sess.get("batch_id"),
            "filename": sess["filename"],
            "ext": sess.get("ext", ""),
            "total_pages": sess.get("total_pages", 0),
            "processed_count": sess.get("processed_count", 0),
            "status": sess.get("status", "idle")
        })

    def _sort_key(s):
        fn = s.get("filename", "").lower()
        parts = [int(text) if text.isdigit() else text for text in re.split(r'(\d+)', fn)]
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
        return JSONResponse({
            "status": "already_running",
            "message": "Batch colorization is already running",
            "batch": CURRENT_BATCH
        })

    valid_sessions = []
    for sid in req.session_ids:
        sess = SESSIONS.get(sid) or get_or_restore_session(sid)
        if sess:
            valid_sessions.append(sid)

    if not valid_sessions:
        raise HTTPException(status_code=404, detail="No valid sessions found for batch colorization")

    CURRENT_BATCH = {
        "is_running": True,
        "total_docs": len(valid_sessions),
        "completed_docs": 0,
        "current_index": 0,
        "current_session_id": valid_sessions[0] if valid_sessions else None,
        "session_ids": valid_sessions
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
                    p for p in pages
                    if p.get("status") != "colorized" or not (colorized_dir / p.get("filename", "")).exists()
                ]

                if not uncolorized and len(pages) > 0:
                    sess["status"] = "completed"
                    sess["processed_count"] = len(pages)
                    save_session_meta(sid)
                    CURRENT_BATCH["completed_docs"] += 1
                    await notify_sse_listeners(sid, {
                        "type": "completed",
                        "total_processed": len(pages),
                        "batch_info": {
                            "current_doc_idx": idx + 1,
                            "total_docs": len(valid_sessions),
                            "completed_docs": CURRENT_BATCH["completed_docs"]
                        }
                    })
                    continue

                single_req = ColorizeRequest(
                    session_id=sid,
                    model_provider=req.model_provider,
                    model_name=req.model_name,
                    api_key=req.api_key,
                    style=req.style,
                    saturation=req.saturation,
                    contrast=req.contrast,
                    line_preserve=req.line_preserve
                )
                await _async_colorization_worker(sid, single_req)
                CURRENT_BATCH["completed_docs"] += 1
        finally:
            CURRENT_BATCH["is_running"] = False
            CURRENT_BATCH["current_session_id"] = None

    asyncio.create_task(_run_batch())
    return JSONResponse({
        "status": "started",
        "message": f"Batch colorization started for {len(valid_sessions)} documents",
        "session_ids": valid_sessions
    })

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
        return JSONResponse({
            "status": "success",
            "message": f"Document session {session_id} already deleted",
            "deleted_session_id": session_id
        })

    # Ensure removed from in-memory dictionary
    SESSIONS.pop(session_id, None)

    # Cancel if running
    if sess:
        sess["cancel_requested"] = True

    # Remove event listeners
    EVENT_QUEUES.pop(session_id, None)

    # Remove storage folder in sessions/
    if sess_dir.exists():
        shutil.rmtree(str(sess_dir), ignore_errors=True)

    # Remove original uploaded file from uploads/ if it exists
    if sess and sess.get("file_path"):
        try:
            up_path = Path(sess["file_path"])
            if up_path.exists() and "uploads" in str(up_path.resolve()):
                up_path.unlink(missing_ok=True)
        except Exception as e:
            print(f"Error removing upload file: {e}")

    # Remove any exported archives from output/ matching this session
    for out_f in OUTPUT_DIR.glob(f"{session_id}_*"):
        try:
            out_f.unlink(missing_ok=True)
        except Exception:
            pass

    return JSONResponse({
        "status": "success",
        "message": f"Document session {session_id} deleted successfully",
        "deleted_session_id": session_id
    })

@app.delete("/api/session/{session_id}/page/{page_index}")
async def delete_session_page(session_id: str, page_index: int):
    """Deletes a specific page from a document session and cleans up its files."""
    sess = SESSIONS.get(session_id) or get_or_restore_session(session_id)
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    pages = sess.get("pages", [])
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(status_code=400, detail=f"Invalid page index: {page_index}. Total pages: {len(pages)}")

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

    return JSONResponse({
        "status": "success",
        "message": "Page deleted successfully",
        "total_pages": sess["total_pages"],
        "session": sess
    })

@app.delete("/api/sessions")
async def delete_all_sessions():
    """Deletes all document sessions, uploads, and outputs."""
    for sess in SESSIONS.values():
        sess["cancel_requested"] = True

    EVENT_QUEUES.clear()

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

    return JSONResponse({
        "status": "success",
        "message": "All document sessions and files deleted successfully"
    })

@app.get("/favicon.ico", include_in_schema=False)
async def get_favicon():
    favicon_path = STATIC_DIR / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path, media_type="image/x-icon")
    return JSONResponse(status_code=404, content={"detail": "Favicon not found"})

# Serve Frontend static assets
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

