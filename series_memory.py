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
    auto_learned_count: int = 0
    auto_refine_enabled: bool = True
    auto_harvest_threshold: float = 0.82
    auto_refine_interval: int = 5
    unrefined_pages_count: int = 0
    quality_scores: dict[str, float] = field(default_factory=dict)
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
            "auto_learned_count": self.auto_learned_count,
            "auto_refine_enabled": self.auto_refine_enabled,
            "auto_harvest_threshold": self.auto_harvest_threshold,
            "auto_refine_interval": self.auto_refine_interval,
            "unrefined_pages_count": self.unrefined_pages_count,
            "quality_scores": self.quality_scores,
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
            auto_learned_count=int(d.get("auto_learned_count", 0)),
            auto_refine_enabled=bool(d.get("auto_refine_enabled", True)),
            auto_harvest_threshold=float(d.get("auto_harvest_threshold", 0.82)),
            auto_refine_interval=int(d.get("auto_refine_interval", 5)),
            unrefined_pages_count=int(d.get("unrefined_pages_count", 0)),
            quality_scores=dict(d.get("quality_scores", {})),
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

    def get_or_create(self, series_key: str, title: str = "") -> SeriesMemory:
        if series_key not in self.memories:
            display_title = title or " ".join(w.capitalize() for w in series_key.replace("_", " ").split())
            self.memories[series_key] = SeriesMemory(series_key=series_key, title=display_title)
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
        pinned: bool = False,
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

        # Store exemplar page with character metadata, style, and luminance
        if approved_image_path and os.path.exists(approved_image_path):
            exists_idx = None
            for i, ex in enumerate(mem.exemplar_pages):
                if ex.get("session_id") == session_id and ex.get("page_index") == page_index:
                    exists_idx = i
                    break

            char_names = [c.get("name", "").strip() for c in characters if isinstance(c, dict) and c.get("name")]
            char_names = [n for n in char_names if n]

            # Compute lightweight luminance summary
            mean_l = 128.0
            try:
                from PIL import Image as PILImage
                with PILImage.open(approved_image_path) as im:
                    thumb = im.convert("L").resize((32, 32))
                    import numpy as np
                    mean_l = float(np.array(thumb).mean())
            except Exception:
                pass

            # Persist exemplar image to series exemplars folder
            exemplar_dir = self.storage_path.parent / "series_exemplars" / series_key
            exemplar_dir.mkdir(parents=True, exist_ok=True)
            dst_name = f"p{page_index}_{Path(approved_image_path).name}"
            dst_path = exemplar_dir / dst_name
            try:
                import shutil
                if Path(approved_image_path).resolve() != dst_path.resolve():
                    shutil.copy2(approved_image_path, dst_path)
                persisted_path = str(dst_path)
            except Exception:
                persisted_path = str(approved_image_path)

            ex_data = {
                "session_id": session_id,
                "page_index": page_index,
                "image_path": persisted_path,
                "characters": char_names,
                "character_names": char_names,
                "style": style or mem.preferred_style or "manga",
                "added_at": time.time(),
                "pinned": bool(pinned),
                "mean_l": round(mean_l, 1),
            }

            if exists_idx is not None:
                # Update existing entry while preserving pinned state if not explicitly pinned
                ex_data["pinned"] = pinned or mem.exemplar_pages[exists_idx].get("pinned", False)
                mem.exemplar_pages[exists_idx] = ex_data
            else:
                mem.exemplar_pages.append(ex_data)
                if len(mem.exemplar_pages) > 12:
                    pinned_items = [ex for ex in mem.exemplar_pages if ex.get("pinned")]
                    unpinned_items = [ex for ex in mem.exemplar_pages if not ex.get("pinned")]
                    keep_unpinned = unpinned_items[-(12 - len(pinned_items)):]
                    mem.exemplar_pages = pinned_items + keep_unpinned

        self.save()
        return mem

    def record_auto_harvest(
        self,
        series_key: str,
        title: str,
        session_id: str,
        page_index: int,
        approved_image_path: str,
        quality_score: dict,
        characters: Optional[list] = None,
        style: Optional[str] = None,
    ) -> tuple[SeriesMemory, bool]:
        """
        Confidence-gated auto-harvest: when a colorized page exceeds the quality threshold,
        automatically incorporates it into Series Memory as a high-confidence exemplar,
        records metrics, increments unrefined counters, and determines if auto-refinement should trigger.
        """
        mem = self.get_or_create(series_key, title)
        page_key = f"{session_id}_{page_index}"
        overall_score = float(quality_score.get("overall_score", 0.0))
        mem.quality_scores[page_key] = overall_score

        if not quality_score.get("auto_learn_eligible", False):
            self.save()
            return mem, False

        # Record learning into exemplars and character traits
        self.record_learning(
            series_key=series_key,
            title=title,
            characters=characters or [],
            session_id=session_id,
            page_index=page_index,
            approved_image_path=approved_image_path,
            style=style,
        )

        mem.auto_learned_count += 1
        mem.unrefined_pages_count += 1
        self.save()

        should_refine = bool(
            mem.auto_refine_enabled
            and mem.unrefined_pages_count >= mem.auto_refine_interval
        )
        return mem, should_refine

    def update_auto_refine_settings(
        self,
        series_key: str,
        enabled: Optional[bool] = None,
        threshold: Optional[float] = None,
        interval: Optional[int] = None,
    ) -> SeriesMemory:
        """Updates auto-refine and active-learning thresholds for a series."""
        mem = self.get_or_create(series_key)
        if enabled is not None:
            mem.auto_refine_enabled = bool(enabled)
        if threshold is not None:
            import numpy as np
            mem.auto_harvest_threshold = float(np.clip(threshold, 0.50, 0.98))
        if interval is not None:
            mem.auto_refine_interval = max(1, int(interval))
        self.save()
        return mem

    def reset_unrefined_counter(self, series_key: str) -> None:
        """Resets unrefined pages counter after an adapter fine-tuning cycle completes."""
        mem = self.get_memory(series_key)
        if mem:
            mem.unrefined_pages_count = 0
            self.save()

    def find_best_exemplars(
        self,
        series_key: str,
        target_image_path: Optional[str] = None,
        active_character_names: Optional[list[str]] = None,
        exclude_path: Optional[str] = None,
        max_count: int = 2,
    ) -> list[dict]:
        """
        Ranks and returns the top matching exemplar pages based on:
        1. Pinned status (always prioritized).
        2. Character overlap (pages with characters appearing on the target page score highest).
        3. Lighting / luminance similarity (if target image is provided).
        4. Recency.
        """
        mem = self.get_memory(series_key)
        if not mem or not mem.exemplar_pages:
            return []

        # Calculate target luminance if target image exists
        target_l = 128.0
        if target_image_path and os.path.exists(target_image_path):
            try:
                from PIL import Image as PILImage
                with PILImage.open(target_image_path) as im:
                    thumb = im.convert("L").resize((32, 32))
                    import numpy as np
                    target_l = float(np.array(thumb).mean())
            except Exception:
                pass

        target_chars_lower = set()
        if active_character_names:
            target_chars_lower = {n.lower().strip() for n in active_character_names if n}

        scored = []
        now = time.time()
        for ex in mem.exemplar_pages:
            p = ex.get("image_path")
            if not p or p == exclude_path or not os.path.exists(p):
                continue

            score = 0.0
            # 1. Pinned
            if ex.get("pinned"):
                score += 50.0

            # 2. Character overlap
            ex_chars = [c.lower().strip() for c in ex.get("characters", [])]
            if target_chars_lower:
                overlap = sum(1 for c in ex_chars if c in target_chars_lower)
                score += overlap * 20.0
            elif ex_chars:
                score += len(ex_chars) * 2.0

            # 3. Luminance closeness (max +5.0)
            ex_l = ex.get("mean_l", 128.0)
            l_diff = abs(target_l - ex_l)
            score += max(0.0, 5.0 - (l_diff / 25.0))

            # 4. Recency (max +2.0)
            age_days = (now - ex.get("added_at", now)) / 86400.0
            score += max(0.0, 2.0 - min(2.0, age_days * 0.1))

            scored.append((score, ex))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:max_count]]

    def get_exemplar_image(
        self,
        series_key: str,
        exclude_path: Optional[str] = None,
        active_character_names: Optional[list[str]] = None,
        target_image_path: Optional[str] = None,
    ) -> Optional[str]:
        """Returns the single best matching exemplar image path."""
        best = self.find_best_exemplars(
            series_key=series_key,
            target_image_path=target_image_path,
            active_character_names=active_character_names,
            exclude_path=exclude_path,
            max_count=1,
        )
        if best:
            return best[0].get("image_path")
        # Fallback to direct reverse scan if needed
        mem = self.get_memory(series_key)
        if mem and mem.exemplar_pages:
            for ex in reversed(mem.exemplar_pages):
                p = ex.get("image_path")
                if p and p != exclude_path and os.path.exists(p):
                    return p
        return None

    def remove_exemplar(
        self,
        series_key: str,
        page_index: int,
        session_id: Optional[str] = None,
    ) -> bool:
        """Removes an exemplar page from memory by series_key and page_index."""
        mem = self.get_memory(series_key)
        if not mem:
            return False
        before = len(mem.exemplar_pages)
        removed_items = [
            ex for ex in mem.exemplar_pages
            if (ex.get("page_index") == page_index and (session_id is None or ex.get("session_id") == session_id))
        ]
        mem.exemplar_pages = [
            ex for ex in mem.exemplar_pages
            if not (ex.get("page_index") == page_index and (session_id is None or ex.get("session_id") == session_id))
        ]
        if len(mem.exemplar_pages) < before:
            self.save()
            for ex in removed_items:
                img_p = ex.get("image_path")
                if img_p and os.path.exists(img_p) and "series_exemplars" in str(img_p):
                    try:
                        os.remove(img_p)
                    except Exception:
                        pass
            return True
        return False

    def pin_exemplar(
        self,
        series_key: str,
        page_index: int,
        pinned: bool = True,
        session_id: Optional[str] = None,
    ) -> bool:
        """Sets the pinned priority flag for a specific exemplar page."""
        mem = self.get_memory(series_key)
        if not mem:
            return False
        for ex in mem.exemplar_pages:
            if ex.get("page_index") == page_index and (session_id is None or ex.get("session_id") == session_id):
                ex["pinned"] = pinned
                self.save()
                return True
        return False

    def reset_series_memory(self, series_key: str) -> bool:
        """Clears learned traits and exemplars for a series."""
        if series_key in self.memories:
            del self.memories[series_key]
            self.save()
            return True
        return False
