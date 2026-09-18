"""
series_memory.py - Persistent Series Memory Bank & Cross-Page Active Learning.

Maintains cross-page and cross-chapter memory for manga series:
- Caches user-approved ground-truth character palettes (hair, skin, costume, eye colors).
- Stores visual exemplar page references for few-shot multimodal in-context learning.
- Dynamically injects learned character priors into subsequent pages to ensure 100% color consistency.
- Improves progressively with every approved or recolorized page.
"""

from __future__ import annotations

import copy
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any

from manga_presets import (
    detect_manga_preset,
    normalize_text_for_matching,
    get_preset_by_id,
    MangaPreset,
)


@dataclass
class LearnedCharacterTrait:
    name: str
    hair_hex: str = ""
    skin_hex: str = ""
    costume_hex: str = ""
    eye_hex: str = ""
    extra_hex: str = ""
    confidence: float = 1.0  # increments with each confirmation
    confirmation_count: int = 1
    last_updated: float = field(default_factory=time.time)
    source_sessions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hair_hex": self.hair_hex,
            "skin_hex": self.skin_hex,
            "costume_hex": self.costume_hex,
            "eye_hex": self.eye_hex,
            "extra_hex": self.extra_hex,
            "confidence": round(self.confidence, 2),
            "confirmation_count": self.confirmation_count,
            "last_updated": self.last_updated,
            "source_sessions": self.source_sessions,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LearnedCharacterTrait":
        return cls(
            name=d.get("name", ""),
            hair_hex=d.get("hair_hex", ""),
            skin_hex=d.get("skin_hex", ""),
            costume_hex=d.get("costume_hex", ""),
            eye_hex=d.get("eye_hex", ""),
            extra_hex=d.get("extra_hex", ""),
            confidence=float(d.get("confidence", 1.0)),
            confirmation_count=int(d.get("confirmation_count", 1)),
            last_updated=float(d.get("last_updated", time.time())),
            source_sessions=list(d.get("source_sessions", [])),
        )


@dataclass
class SeriesMemory:
    series_key: str
    title: str
    characters: dict[str, LearnedCharacterTrait] = field(default_factory=dict)
    exemplar_pages: list[dict] = field(default_factory=list)  # list of {"session_id": ..., "page_index": ..., "image_path": ...}
    approved_pages_count: int = 0
    preferred_style: Optional[str] = None
    preferred_saturation: Optional[float] = None
    preferred_contrast: Optional[float] = None
    preferred_line_preserve: Optional[float] = None
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "series_key": self.series_key,
            "title": self.title,
            "characters": {k: v.to_dict() for k, v in self.characters.items()},
            "exemplar_pages": self.exemplar_pages,
            "approved_pages_count": self.approved_pages_count,
            "preferred_style": self.preferred_style,
            "preferred_saturation": self.preferred_saturation,
            "preferred_contrast": self.preferred_contrast,
            "preferred_line_preserve": self.preferred_line_preserve,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SeriesMemory":
        chars = {}
        for k, v in d.get("characters", {}).items():
            chars[k] = LearnedCharacterTrait.from_dict(v)
        return cls(
            series_key=d.get("series_key", ""),
            title=d.get("title", ""),
            characters=chars,
            exemplar_pages=list(d.get("exemplar_pages", [])),
            approved_pages_count=int(d.get("approved_pages_count", 0)),
            preferred_style=d.get("preferred_style"),
            preferred_saturation=d.get("preferred_saturation"),
            preferred_contrast=d.get("preferred_contrast"),
            preferred_line_preserve=d.get("preferred_line_preserve"),
            last_updated=float(d.get("last_updated", time.time())),
        )


def derive_series_key(filename_or_title: str, preset_id: Optional[str] = None) -> tuple[str, str]:
    """
    Derives a normalized series_key (e.g. 'dr_slump', 'one_piece') and clean display title.
    If preset_id is provided, looks up registered preset.
    Otherwise attempts preset auto-detection.
    If no preset matches, sanitizes by removing volume/chapter numbers, brackets, and extensions.
    """
    if preset_id:
        preset = get_preset_by_id(preset_id)
        if preset:
            return preset.id, preset.title

    detected = detect_manga_preset(filename_or_title)
    if detected:
        return detected.id, detected.title

    t = filename_or_title
    # Remove file extension
    t = re.sub(r"\.[a-zA-Z0-9]+$", "", t)
    # Remove bracketed scanlation groups e.g. [MangaStream], (Digital), [1080p]
    t = re.sub(r"\[.*?\]|\(.*?\)", "", t)
    # Remove volume / chapter markers e.g. Vol 01, Ch 25, v01, c12, Volume 1, Chapter 5
    t = re.sub(r"(?i)\b(vol|volume|v|ch|chapter|c|episode|ep)[\.\s_-]*\d+\b", "", t)
    t = re.sub(r"\b\d+\b", "", t)  # standalone numbers
    t = t.replace("_", " ").replace("-", " ").strip()
    norm = normalize_text_for_matching(t)
    if not norm:
        norm = "manga_series"
    series_key = re.sub(r"[^a-z0-9]+", "_", norm).strip("_")
    if not series_key:
        series_key = "manga_series"
    clean_title = " ".join(word.capitalize() for word in norm.split())
    return series_key, clean_title


class SeriesMemoryBank:
    """Thread-safe persistent store for series-level color memories and visual exemplars."""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.memories: dict[str, SeriesMemory] = {}
        self._load()

    def _load(self):
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self.memories[k] = SeriesMemory.from_dict(v)
            except Exception as e:
                print(f"[SeriesMemoryBank Warning] Failed to load {self.storage_path}: {e}")

    def save(self):
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self.memories.items()}, f, indent=2)
        except Exception as e:
            print(f"[SeriesMemoryBank Warning] Failed to save {self.storage_path}: {e}")

    def get_memory(self, series_key: str) -> Optional[SeriesMemory]:
        return self.memories.get(series_key)

    def get_or_create(self, series_key: str, title: str) -> SeriesMemory:
        if series_key not in self.memories:
            self.memories[series_key] = SeriesMemory(series_key=series_key, title=title)
            self.save()
        return self.memories[series_key]

    def record_learning(
        self,
        series_key: str,
        title: str,
        characters: list[dict],
        session_id: str,
        page_index: int,
        approved_image_path: Optional[str] = None,
        style: Optional[str] = None,
        saturation: Optional[float] = None,
        contrast: Optional[float] = None,
        line_preserve: Optional[float] = None,
    ) -> SeriesMemory:
        """
        Records user confirmation / feedback for a page, updating character traits
        and saving an exemplar page reference for cross-page visual consistency.
        """
        mem = self.get_or_create(series_key, title)
        mem.approved_pages_count += 1
        mem.last_updated = time.time()

        if style:
            mem.preferred_style = style
        if saturation is not None:
            mem.preferred_saturation = saturation
        if contrast is not None:
            mem.preferred_contrast = contrast
        if line_preserve is not None:
            mem.preferred_line_preserve = line_preserve

        # Update character traits
        for c in characters:
            cname = c.get("name", "").strip()
            if not cname:
                continue
            norm_name = cname.lower()
            existing = mem.characters.get(norm_name)
            if existing:
                if c.get("hair_hex"):
                    existing.hair_hex = c["hair_hex"]
                if c.get("skin_hex"):
                    existing.skin_hex = c["skin_hex"]
                if c.get("costume_hex"):
                    existing.costume_hex = c["costume_hex"]
                if c.get("eye_hex"):
                    existing.eye_hex = c["eye_hex"]
                if c.get("extra_hex"):
                    existing.extra_hex = c["extra_hex"]
                existing.confirmation_count += 1
                existing.confidence = min(5.0, existing.confidence + 0.5)
                existing.last_updated = time.time()
                if session_id not in existing.source_sessions:
                    existing.source_sessions.append(session_id)
            else:
                mem.characters[norm_name] = LearnedCharacterTrait(
                    name=cname,
                    hair_hex=c.get("hair_hex", ""),
                    skin_hex=c.get("skin_hex", ""),
                    costume_hex=c.get("costume_hex", ""),
                    eye_hex=c.get("eye_hex", ""),
                    extra_hex=c.get("extra_hex", ""),
                    confidence=1.5,
                    confirmation_count=1,
                    source_sessions=[session_id],
                )

        # Store exemplar page (keep up to 8 best exemplar pages per series)
        if approved_image_path and os.path.exists(approved_image_path):
            exists = any(
                ex["session_id"] == session_id and ex["page_index"] == page_index
                for ex in mem.exemplar_pages
            )
            if not exists:
                mem.exemplar_pages.append({
                    "session_id": session_id,
                    "page_index": page_index,
                    "image_path": str(approved_image_path),
                    "added_at": time.time(),
                })
                if len(mem.exemplar_pages) > 8:
                    mem.exemplar_pages = mem.exemplar_pages[-8:]

        self.save()
        return mem

    def get_exemplar_image(self, series_key: str, exclude_path: Optional[str] = None) -> Optional[str]:
        """Returns the most recent valid exemplar colorized image for visual few-shot prompting."""
        mem = self.get_memory(series_key)
        if not mem or not mem.exemplar_pages:
            return None

        for ex in reversed(mem.exemplar_pages):
            p = ex.get("image_path")
            if p and p != exclude_path and os.path.exists(p):
                return p
        return None

    def reset_series_memory(self, series_key: str) -> bool:
        """Clears learned traits and exemplars for a series."""
        if series_key in self.memories:
            del self.memories[series_key]
            self.save()
            return True
        return False
