"""
manga_presets.py - Canonical Color Presets & Auto-Detection for Popular Manga.

Provides high-fidelity canonical color definitions for popular manga series
(One Piece, Doraemon, Slam Dunk, Dr. Slump, Dragon Ball, Naruto, Bleach, etc.),
automatic detection from filenames, prompt guidance for multimodal models,
and online lookup for unindexed titles.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PresetCharacter:
    """Canonical color definition for a single manga character."""

    name: str
    hair_hex: str = ""
    skin_hex: str = ""
    costume_hex: str = ""
    extra_hex: str = ""
    eye_hex: str = ""  # Canonical eye / iris color (e.g. #3E2723, #1E88E5, #2E7D32)
    notes: str = ""
    visual_traits: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.visual_traits:
            self.visual_traits = self._infer_visual_traits()
        if not self.keywords:
            self.keywords = self._infer_keywords()

    def _infer_visual_traits(self) -> list[str]:
        traits = []
        if self.hair_hex:
            hx = self.hair_hex.strip().lstrip("#")
            if len(hx) >= 6:
                try:
                    r, g, b = int(hx[:2], 16), int(hx[2:4], 16), int(hx[4:6], 16)
                    brightness = (r + g + b) / 3.0
                    if brightness < 55:
                        traits.append("black_hair")
                    elif brightness > 175:
                        traits.append("light_hair")
                    else:
                        traits.append("screentone_hair")
                except Exception:
                    pass
        n_lower = (self.notes + " " + self.name).lower()
        if "straw hat" in n_lower:
            traits.append("straw_hat")
        elif "hat" in n_lower or "cap" in n_lower:
            traits.append("hat")
        if "glasses" in n_lower:
            traits.append("glasses")
        if "winged" in n_lower or "wing" in n_lower:
            traits.append("winged_cap")
        if "antler" in n_lower or "fur" in n_lower:
            traits.append("antlers")
        if "whiskers" in n_lower or "bell" in n_lower or "doraemon" in n_lower:
            traits.append("round_head")
        if "chibi" in n_lower or "small" in n_lower or "kid" in n_lower or "child" in n_lower:
            traits.append("chibi")
        else:
            traits.append("standard_body")
        return traits

    def _infer_keywords(self) -> list[str]:
        kw = [self.name.lower()]
        for part in re.split(r"[\s\(\)\-\.]+", self.name):
            if len(part) >= 3 and part.lower() not in kw:
                kw.append(part.lower())
        return kw

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "hair_hex": self.hair_hex,
            "skin_hex": self.skin_hex,
            "costume_hex": self.costume_hex,
            "extra_hex": self.extra_hex,
            "eye_hex": self.eye_hex,
            "notes": self.notes,
            "visual_traits": self.visual_traits,
            "keywords": self.keywords,
        }

    @classmethod
    def from_dict(cls, d: dict) -> PresetCharacter:
        return cls(
            name=d.get("name", ""),
            hair_hex=d.get("hair_hex", ""),
            skin_hex=d.get("skin_hex", ""),
            costume_hex=d.get("costume_hex", ""),
            extra_hex=d.get("extra_hex", ""),
            eye_hex=d.get("eye_hex", ""),
            notes=d.get("notes", ""),
            visual_traits=d.get("visual_traits", []),
            keywords=d.get("keywords", []),
        )


@dataclass
class MangaPreset:
    """Color preset for a manga series with character palette and model tuning."""

    id: str
    title: str
    aliases: list[str]
    description: str
    recommended_style: str = "shonen_vivid"
    theme_color: str = "#e62c39"
    characters: list[PresetCharacter] = field(default_factory=list)
    prompt_guidance: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "aliases": self.aliases,
            "description": self.description,
            "recommended_style": self.recommended_style,
            "theme_color": self.theme_color,
            "characters": [c.to_dict() for c in self.characters],
            "prompt_guidance": self.prompt_guidance,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MangaPreset:
        characters = [PresetCharacter.from_dict(c) for c in d.get("characters", [])]
        return cls(
            id=d["id"],
            title=d["title"],
            aliases=d.get("aliases", []),
            description=d.get("description", ""),
            recommended_style=d.get("recommended_style", "shonen_vivid"),
            theme_color=d.get("theme_color", "#e62c39"),
            characters=characters,
            prompt_guidance=d.get("prompt_guidance", ""),
        )

    def build_prompt_guidance(self) -> str:
        """Constructs an authentic character color directive for AI models."""
        if self.prompt_guidance:
            return self.prompt_guidance

        parts = []
        for c in self.characters:
            details = []
            if c.hair_hex:
                details.append(f"hair {c.hair_hex}")
            if c.skin_hex:
                details.append(f"skin {c.skin_hex}")
            if c.costume_hex:
                details.append(f"costume {c.costume_hex}")
            if c.extra_hex:
                details.append(f"accents {c.extra_hex}")
            if details:
                parts.append(f"{c.name} ({', '.join(details)})")

        return f"Canonical anime palette for {self.title}: " + "; ".join(parts) + "."


# ─────────────────────────────────────────────────────────────────────
#  Built-in Canonical Manga Presets
# ─────────────────────────────────────────────────────────────────────

BUILTIN_PRESETS: list[MangaPreset] = [
    # ── 1. One Piece ─────────────────────────────────────────────────
    MangaPreset(
        id="one_piece",
        title="One Piece",
        aliases=[
            "one piece",
            "onepiece",
            "one_piece",
            "luffy",
            "straw hat",
            "strawhat",
            "eiichiro oda",
            "oda eiichiro",
        ],
        description="Straw Hat Pirates vibrant high-seas anime palette with iconic red vest, moss green hair, and straw hat golden tones.",
        recommended_style="shonen_vivid",
        theme_color="#E62C39",
        characters=[
            PresetCharacter(
                name="Monkey D. Luffy",
                hair_hex="#1C1B1F",
                skin_hex="#FCD0A1",
                costume_hex="#E62C39",
                extra_hex="#FBC920",
                notes="Red vest, blue shorts, straw hat with red band",
            ),
            PresetCharacter(
                name="Roronoa Zoro",
                hair_hex="#4E8752",
                skin_hex="#F5C596",
                costume_hex="#1B4332",
                extra_hex="#FFFFFF",
                notes="Moss green hair, dark green haramaki sash, white shirt",
            ),
            PresetCharacter(
                name="Nami",
                hair_hex="#EE7C3C",
                skin_hex="#FDE2C8",
                costume_hex="#1C51A1",
                extra_hex="#F1A722",
                notes="Vibrant orange hair, fair peach skin, denim blue top, gold staff",
            ),
            PresetCharacter(
                name="Sanji",
                hair_hex="#F4D06F",
                skin_hex="#FDE2C8",
                costume_hex="#1B1B1E",
                extra_hex="#457B9D",
                notes="Golden blond hair, black suit, blue dress shirt",
            ),
            PresetCharacter(
                name="Tony Tony Chopper",
                hair_hex="#8B5E34",
                skin_hex="#FCD0A1",
                costume_hex="#FF70A6",
                extra_hex="#2196F3",
                notes="Brown fur, pink hat with white cross, blue nose",
            ),
            PresetCharacter(
                name="Nico Robin",
                hair_hex="#1C1B24",
                skin_hex="#F9D7B8",
                costume_hex="#4A148C",
                extra_hex="#26C6DA",
                notes="Raven black hair, fair skin, purple/dark indigo jacket",
            ),
            PresetCharacter(
                name="Usopp",
                hair_hex="#212121",
                skin_hex="#DE9B61",
                costume_hex="#8D6E63",
                extra_hex="#FFD54F",
                notes="Black wool curls, warm tan, brown overalls, yellow bandana",
            ),
            PresetCharacter(
                name="Portgas D. Ace",
                hair_hex="#1C1B1F",
                skin_hex="#F5C596",
                costume_hex="#FF6F00",
                extra_hex="#1E88E5",
                notes="Black hair, orange cowboy hat, blue bead necklace",
            ),
        ],
        prompt_guidance=(
            "Colorize in vibrant Eiichiro Oda One Piece anime style: "
            "Luffy has black hair, peach skin, signature crimson red vest (#E62C39), straw hat (#FBC920); "
            "Zoro has moss green hair (#4E8752), green haramaki (#1B4332), white shirt; "
            "Nami has vivid orange hair (#EE7C3C), peach skin, blue denim; "
            "Sanji has golden blond hair (#F4D06F), black suit (#1B1B1E); "
            "Keep speech bubbles pure white with crisp black text."
        ),
    ),
    # ── 2. Doraemon ──────────────────────────────────────────────────
    MangaPreset(
        id="doraemon",
        title="Doraemon",
        aliases=["doraemon", "nobita", "fujiko fujio", "fujiko f fujio", "dorami"],
        description="Fujiko F. Fujio canonical palette: sky blue Doraemon body, yellow Nobita polo, and cherry red collar.",
        recommended_style="gemini_anime",
        theme_color="#0095D9",
        characters=[
            PresetCharacter(
                name="Doraemon",
                hair_hex="#0095D9",
                skin_hex="#FFFFFF",
                costume_hex="#ED1C24",
                extra_hex="#FFD400",
                notes="Sky blue body (#0095D9), white face/belly (#FFFFFF), red nose/collar (#ED1C24), golden bell (#FFD400)",
            ),
            PresetCharacter(
                name="Nobita Nobi",
                hair_hex="#212121",
                skin_hex="#FCE0CA",
                costume_hex="#FBC02D",
                extra_hex="#1565C0",
                notes="Black hair, warm fair skin, yellow polo shirt, navy shorts",
            ),
            PresetCharacter(
                name="Shizuka Minamoto",
                hair_hex="#3E2723",
                skin_hex="#FDE2C8",
                costume_hex="#EC407A",
                extra_hex="#FFFFFF",
                notes="Dark brown twintails, fair skin, pink dress/shirt",
            ),
            PresetCharacter(
                name="Gian (Takeshi)",
                hair_hex="#212121",
                skin_hex="#DE9B61",
                costume_hex="#FB8C00",
                extra_hex="#5D4037",
                notes="Black hair, tan skin, orange sweater with brown stripe",
            ),
            PresetCharacter(
                name="Suneo Honekawa",
                hair_hex="#212121",
                skin_hex="#FCE0CA",
                costume_hex="#42A5F5",
                extra_hex="#78909C",
                notes="Black hair, fair skin, light blue polo, slate shorts",
            ),
            PresetCharacter(
                name="Dorami",
                hair_hex="#FFD700",
                skin_hex="#FFFFFF",
                costume_hex="#E53935",
                extra_hex="#388E3C",
                notes="Golden yellow body, white belly, red bow ribbon, green checked tail",
            ),
        ],
        prompt_guidance=(
            "Colorize in classic Doraemon Fujiko F. Fujio anime style: "
            "Doraemon has vibrant sky blue body (#0095D9), pure white face and round belly (#FFFFFF), bright red nose and collar (#ED1C24), golden yellow bell (#FFD400); "
            "Nobita has black hair, fair skin, yellow polo shirt (#FBC02D), navy shorts; "
            "Shizuka has dark brown hair, pink dress (#EC407A); "
            "Keep speech bubbles pure white with crisp black text."
        ),
    ),
    # ── 3. Slam Dunk ─────────────────────────────────────────────────
    MangaPreset(
        id="slam_dunk",
        title="Slam Dunk",
        aliases=[
            "slam dunk",
            "slamdunk",
            "slam_dunk",
            "shohoku",
            "sakuragi",
            "hanamichi",
            "rukawa",
            "takehiko inoue",
        ],
        description="Takehiko Inoue high-intensity Shohoku red aesthetic with Sakuragi crimson hair and athletic court warmth.",
        recommended_style="shonen_vivid",
        theme_color="#E30016",
        characters=[
            PresetCharacter(
                name="Hanamichi Sakuragi",
                hair_hex="#E30016",
                skin_hex="#E5A66E",
                costume_hex="#C62828",
                extra_hex="#FFFFFF",
                notes="Fiery crimson red hair (#E30016), athletic tan skin, Shohoku red #10 jersey",
            ),
            PresetCharacter(
                name="Kaede Rukawa",
                hair_hex="#1A1A1A",
                skin_hex="#FAD2B8",
                costume_hex="#C62828",
                extra_hex="#212121",
                notes="Jet black hair, cool pale skin, Shohoku red #11 jersey, black arm band",
            ),
            PresetCharacter(
                name="Takenori Akagi",
                hair_hex="#111111",
                skin_hex="#C68642",
                costume_hex="#C62828",
                extra_hex="#FAFAFA",
                notes="Short black crew cut, deep tan, Shohoku red #4 jersey",
            ),
            PresetCharacter(
                name="Ryota Miyagi",
                hair_hex="#4E3629",
                skin_hex="#DE9B61",
                costume_hex="#C62828",
                extra_hex="#FFD54F",
                notes="Brown curly faux-hawk, tan skin, Shohoku red #7 jersey, gold earring",
            ),
            PresetCharacter(
                name="Hisashi Mitsui",
                hair_hex="#1F1F1F",
                skin_hex="#ECC099",
                costume_hex="#C62828",
                extra_hex="#E0E0E0",
                notes="Black hair, fair athletic skin, Shohoku red #14 jersey, white knee supporter",
            ),
            PresetCharacter(
                name="Akira Sendoh",
                hair_hex="#1C1B1F",
                skin_hex="#F5C596",
                costume_hex="#0288D1",
                extra_hex="#FFFFFF",
                notes="Black spiky up-do, athletic tan, Ryonan blue #7 jersey",
            ),
        ],
        prompt_guidance=(
            "Colorize in authentic Slam Dunk anime style: "
            "Shohoku basketball team wears iconic fiery red jerseys (#C62828) with white numbers and black side trim; "
            "Hanamichi Sakuragi has vibrant crimson-red hair (#E30016) and athletic tan skin; "
            "Kaede Rukawa has sleek black hair and pale skin; "
            "Basketball court has warm polished wood parquet floors and bright stadium arena lighting; "
            "Preserve speech bubbles pure white with crisp dark text."
        ),
    ),
    # ── 4. Dr. Slump ─────────────────────────────────────────────────
    MangaPreset(
        id="dr_slump",
        title="Dr. Slump",
        aliases=[
            "dr. slump",
            "dr slump",
            "dr_slump",
            "drslump",
            "arale",
            "norimaki",
            "penguin village",
            "akira toriyama",
        ],
        description="Akira Toriyama playful Penguin Village palette: Arale violet/purple hair, red winged cap, and cobalt blue overalls.",
        recommended_style="gemini_anime",
        theme_color="#8A2BE2",
        characters=[
            PresetCharacter(
                name="Arale Norimaki",
                hair_hex="#8A2BE2",
                skin_hex="#F4C5A0",
                costume_hex="#2962FF",
                extra_hex="#E53935",
                eye_hex="#1565C0",
                notes="Little robot girl with big round eyes and purple hair, peach skin, blue eyes",
            ),
            PresetCharacter(
                name="Dr. Senbei Norimaki",
                hair_hex="#212121",
                skin_hex="#F5C596",
                costume_hex="#7E57C2",
                extra_hex="#FFFFFF",
                eye_hex="#212121",
                notes="Adult man inventor with mustache, messy black hair, white lab coat or vest, dark eyes",
            ),
            PresetCharacter(
                name="Gatchan",
                hair_hex="#00E676",
                skin_hex="#FFE0B2",
                costume_hex="#FFEE58",
                extra_hex="#F48FB1",
                eye_hex="#1565C0",
                notes="Baby angel with small wings, emerald green hair, yellow jumpsuit, bright blue eyes",
            ),
            PresetCharacter(
                name="Midori Yamabuki",
                hair_hex="#4A148C",
                skin_hex="#FFF0E5",
                costume_hex="#E91E63",
                extra_hex="#FFEB3B",
                eye_hex="#2E7D32",
                notes="Tall adult woman school teacher, indigo or purple hair, fair porcelain skin, magenta dress, green eyes",
            ),
            PresetCharacter(
                name="Taro Soramame",
                hair_hex="#424242",
                skin_hex="#F5C596",
                costume_hex="#1565C0",
                extra_hex="#B71C1C",
                eye_hex="#212121",
                notes="Teenage boy delinquent with slicked black hair, leather jacket, dark eyes",
            ),
        ],
        prompt_guidance=(
            "Colorize in authentic Akira Toriyama Dr. Slump anime aesthetic matching Gemini demo standard: "
            "Arale Norimaki has vivid violet/purple hair (#8A2BE2), warm peach skin with rosy cheeks, red winged cap, and cobalt blue overalls (#2962FF); "
            "Dr. Senbei Norimaki has warm peach skin, dark hair, purple/grey vest, and white lab coat; "
            "Gatchan has bright emerald green hair and yellow jumpsuit; "
            "Environment features bright gradient sky, terracotta roof tiles, and glowing emerald/magenta lab glassware; "
            "Keep speech bubbles pure white with crisp black text."
        ),
    ),
    # ── 5. Dragon Ball / Dragon Ball Z ──────────────────────────────
    MangaPreset(
        id="dragon_ball",
        title="Dragon Ball / DBZ",
        aliases=[
            "dragon ball",
            "dragonball",
            "dragon_ball",
            "dbz",
            "dragon ball z",
            "goku",
            "vegeta",
            "saiyan",
        ],
        description="Iconic Dragon Ball anime colors: Turtle School vibrant orange gi, cobalt blue undershirt, and golden Super Saiyan hair.",
        recommended_style="shonen_vivid",
        theme_color="#FF6F00",
        characters=[
            PresetCharacter(
                name="Son Goku",
                hair_hex="#1A1A1A",
                skin_hex="#F5C596",
                costume_hex="#FF6F00",
                extra_hex="#0D47A1",
                notes="Black spiky hair (or #FFD700 Super Saiyan gold), Turtle School orange gi, cobalt blue belt",
            ),
            PresetCharacter(
                name="Vegeta",
                hair_hex="#1A1A1A",
                skin_hex="#F3C29E",
                costume_hex="#1565C0",
                extra_hex="#FFFFFF",
                notes="Jet black hair, navy blue bodysuit, white Saiyan armor with gold chest strap",
            ),
            PresetCharacter(
                name="Piccolo",
                hair_hex="#2E7D32",
                skin_hex="#4CAF50",
                costume_hex="#673AB7",
                extra_hex="#FFFFFF",
                notes="Namekian green skin (#4CAF50) with pink muscle patches, purple dogi robes, white cape",
            ),
            PresetCharacter(
                name="Future Trunks",
                hair_hex="#BA68C8",
                skin_hex="#FCE4D6",
                costume_hex="#283593",
                extra_hex="#455A64",
                notes="Lavender purple hair, pale skin, Capsule Corp indigo jacket, charcoal pants",
            ),
            PresetCharacter(
                name="Bulma",
                hair_hex="#00BCD4",
                skin_hex="#FFF0E5",
                costume_hex="#E91E63",
                extra_hex="#FF5722",
                notes="Turquoise/aqua blue hair, porcelain skin, pink dress, red ribbon",
            ),
        ],
        prompt_guidance=(
            "Colorize in classic Akira Toriyama Dragon Ball Z anime style: "
            "Goku has black spiky hair, warm peach skin, iconic Turtle School bright orange gi (#FF6F00), dark cobalt blue belt and undershirt (#0D47A1); "
            "Vegeta has black hair, navy blue suit, white and gold Saiyan battle armor; "
            "Piccolo has green skin (#4CAF50) and purple dogi robes (#673AB7); "
            "Keep speech bubbles pure white with crisp black text."
        ),
    ),
    # ── 6. Naruto ────────────────────────────────────────────────────
    MangaPreset(
        id="naruto",
        title="Naruto",
        aliases=[
            "naruto",
            "shippuden",
            "sasuke",
            "kakashi",
            "masashi kishimoto",
            "konoha",
            "uzumaki",
        ],
        description="Masashi Kishimoto ninja world palette: Naruto bright orange jumpsuit, Sasuke navy blue, and Kakashi green flak jacket.",
        recommended_style="shonen_vivid",
        theme_color="#FF6D00",
        characters=[
            PresetCharacter(
                name="Naruto Uzumaki",
                hair_hex="#FFD54F",
                skin_hex="#F5C296",
                costume_hex="#FF6D00",
                extra_hex="#1976D2",
                notes="Spiky blond hair, warm tan, bright orange jumpsuit, blue collar & headband",
            ),
            PresetCharacter(
                name="Sasuke Uchiha",
                hair_hex="#1A237E",
                skin_hex="#FCE4D6",
                costume_hex="#0D1B2A",
                extra_hex="#F8F9FA",
                notes="Dark navy blue-black hair, pale fair skin, dark navy shirt, white shorts",
            ),
            PresetCharacter(
                name="Sakura Haruno",
                hair_hex="#F48FB1",
                skin_hex="#FFF0E5",
                costume_hex="#C2185B",
                extra_hex="#880E4F",
                notes="Cherry blossom pink hair, fair skin, crimson red top, dark pink skirt",
            ),
            PresetCharacter(
                name="Kakashi Hatake",
                hair_hex="#B0BEC5",
                skin_hex="#FAD2B8",
                costume_hex="#2E7D32",
                extra_hex="#263238",
                notes="Silver/grey spiky hair, fair skin, Konoha green flak jacket, dark navy mask",
            ),
            PresetCharacter(
                name="Hinata Hyuga",
                hair_hex="#1A237E",
                skin_hex="#FFF0E5",
                costume_hex="#D1C4E9",
                extra_hex="#FFFFFF",
                notes="Dark blue-black hair, porcelain fair skin, lavender jacket, white byakugan eyes",
            ),
        ],
        prompt_guidance=(
            "Colorize in authentic Naruto anime style: "
            "Naruto has bright spiky blond hair (#FFD54F), warm tan skin, vibrant orange jumpsuit (#FF6D00) with blue collar; "
            "Sasuke has dark blue-black hair, pale cool skin, and navy blue shirt; "
            "Kakashi has silver/grey hair, Konoha green flak jacket (#2E7D32), and dark blue mask; "
            "Keep speech bubbles pure white."
        ),
    ),
    # ── 7. Bleach ────────────────────────────────────────────────────
    MangaPreset(
        id="bleach",
        title="Bleach",
        aliases=["bleach", "ichigo", "tite kubo", "shinigami", "soul society", "kurosaki"],
        description="Tite Kubo stark contrast aesthetic: Ichigo fiery bright orange hair with jet black Soul Reaper Shihakusho.",
        recommended_style="shonen_vivid",
        theme_color="#FF6F00",
        characters=[
            PresetCharacter(
                name="Ichigo Kurosaki",
                hair_hex="#FF6F00",
                skin_hex="#F5C596",
                costume_hex="#1A1A1A",
                extra_hex="#FFFFFF",
                notes="Fiery bright orange hair, peach skin, black Shihakusho shinigami robes, white lining",
            ),
            PresetCharacter(
                name="Rukia Kuchiki",
                hair_hex="#1A1A1A",
                skin_hex="#FCE4D6",
                costume_hex="#1A1A1A",
                extra_hex="#FFFFFF",
                notes="Jet black hair, pale fair skin, black shinigami robes",
            ),
            PresetCharacter(
                name="Orihime Inoue",
                hair_hex="#FF7043",
                skin_hex="#FFF0E5",
                costume_hex="#F8BBD0",
                extra_hex="#42A5F5",
                notes="Warm bright orange-brown hair, fair skin, pink school uniform, cyan hair clips",
            ),
            PresetCharacter(
                name="Renji Abarai",
                hair_hex="#D32F2F",
                skin_hex="#E5A66E",
                costume_hex="#1A1A1A",
                extra_hex="#FFFFFF",
                notes="Crimson red ponytail hair, athletic tan, black shinigami robes, white headband",
            ),
        ],
        prompt_guidance=(
            "Colorize in stylish Tite Kubo Bleach anime aesthetic: "
            "Ichigo has bright fiery orange hair (#FF6F00), peach skin, jet black shinigami kimono (#1A1A1A) with white undergarment lining; "
            "Clean contrast with pure white margins and crisp speech bubbles."
        ),
    ),
    # ── 8. Detective Conan ───────────────────────────────────────────
    MangaPreset(
        id="detective_conan",
        title="Detective Conan",
        aliases=[
            "detective conan",
            "case closed",
            "conan",
            "edogawa",
            "shinichi kudo",
            "gosho aoyama",
        ],
        description="Gosho Aoyama detective mystery palette: Conan royal blue jacket, crimson red bow tie, and Ran school uniform.",
        recommended_style="shonen_vivid",
        theme_color="#1565C0",
        characters=[
            PresetCharacter(
                name="Conan Edogawa",
                hair_hex="#212121",
                skin_hex="#FDE2C8",
                costume_hex="#1565C0",
                extra_hex="#D32F2F",
                notes="Dark brown/black spiky hair, peach skin, royal blue blazer, red bow tie, grey shorts",
            ),
            PresetCharacter(
                name="Ran Mouri",
                hair_hex="#3E2723",
                skin_hex="#FFF0E5",
                costume_hex="#43A047",
                extra_hex="#1E88E5",
                notes="Dark chestnut hair with signature horn, fair skin, Teitan green blazer, blue tie",
            ),
            PresetCharacter(
                name="Ai Haibara",
                hair_hex="#8D6E63",
                skin_hex="#FFF0E5",
                costume_hex="#8E24AA",
                extra_hex="#FFFFFF",
                notes="Strawberry blond/light reddish-brown hair, fair pale skin, purple sweater, white lab coat",
            ),
            PresetCharacter(
                name="Kaito Kid",
                hair_hex="#212121",
                skin_hex="#FDE2C8",
                costume_hex="#FFFFFF",
                extra_hex="#1976D2",
                notes="Black messy hair, fair skin, pure white tuxedo & silk top hat, blue shirt with red tie",
            ),
        ],
        prompt_guidance=(
            "Colorize in classic Detective Conan anime style: "
            "Conan wears royal blue blazer (#1565C0), crisp crimson red bow tie (#D32F2F), white shirt, grey shorts; "
            "Ran wears Teitan high green school blazer (#43A047); "
            "Keep speech bubbles pure white with crisp black text."
        ),
    ),
    # ── 9. Demon Slayer (Kimetsu no Yaiba) ───────────────────────────
    MangaPreset(
        id="demon_slayer",
        title="Demon Slayer",
        aliases=[
            "demon slayer",
            "kimetsu",
            "kimetsu no yaiba",
            "tanjiro",
            "nezuko",
            "koyoharu gotouge",
            "zenitsu",
            "inosuke",
        ],
        description="Ufotable / Koyoharu Gotouge Taisho-era palette: Tanjiro green/black checkered haori, Nezuko pink geometric kimono.",
        recommended_style="shonen_vivid",
        theme_color="#1B5E20",
        characters=[
            PresetCharacter(
                name="Tanjiro Kamado",
                hair_hex="#4A1521",
                skin_hex="#EBB89B",
                costume_hex="#1B5E20",
                extra_hex="#FAFAFA",
                notes="Dark burgundy hair with crimson tips, peach skin with forehead scar, green & black checkered haori",
            ),
            PresetCharacter(
                name="Nezuko Kamado",
                hair_hex="#1A1A1A",
                skin_hex="#FDE4D6",
                costume_hex="#F06292",
                extra_hex="#4CAF50",
                notes="Black hair with flame-orange tips (#FF6D00), pale skin, pink geometric kimono, green bamboo muzzle",
            ),
            PresetCharacter(
                name="Zenitsu Agatsuma",
                hair_hex="#FFD54F",
                skin_hex="#FCE0CA",
                costume_hex="#FB8C00",
                extra_hex="#FFFFFF",
                notes="Bright yellow hair with orange tips, fair skin, yellow/orange triangle pattern haori",
            ),
            PresetCharacter(
                name="Inosuke Hashibira",
                hair_hex="#1A237E",
                skin_hex="#E5A66E",
                costume_hex="#757575",
                extra_hex="#5D4037",
                notes="Black hair with navy blue tips, athletic tan skin, grey boar head mask, brown fur pants",
            ),
        ],
        prompt_guidance=(
            "Colorize in rich Demon Slayer Kimetsu no Yaiba anime style: "
            "Tanjiro has dark burgundy/crimson hair (#4A1521), iconic green and black checkered haori (#1B5E20); "
            "Nezuko has black hair with flame-orange tips, delicate pink geometric kimono (#F06292), green bamboo muzzle; "
            "Zenitsu has bright yellow/orange gradient hair and triangle haori (#FB8C00); "
            "Keep speech bubbles pure white."
        ),
    ),
    # ── 10. Attack on Titan ──────────────────────────────────────────
    MangaPreset(
        id="attack_on_titan",
        title="Attack on Titan",
        aliases=[
            "attack on titan",
            "shingeki no kyojin",
            "shingeki",
            "aot",
            "eren",
            "levi",
            "hajime isayama",
        ],
        description="Hajime Isayama gritty military palette: Scout Regiment leather brown jackets, emerald green cloaks, and Mikasa red scarf.",
        recommended_style="dark_fantasy",
        theme_color="#5D4037",
        characters=[
            PresetCharacter(
                name="Eren Yeager",
                hair_hex="#3E2723",
                skin_hex="#E0AC69",
                costume_hex="#5D4037",
                extra_hex="#33691E",
                notes="Dark brown hair, warm skin, Scout Regiment brown jacket, emerald green scout cloak",
            ),
            PresetCharacter(
                name="Mikasa Ackerman",
                hair_hex="#1A1A1A",
                skin_hex="#FCE4D6",
                costume_hex="#8B0000",
                extra_hex="#5D4037",
                notes="Jet black hair, pale fair skin, signature dark crimson red scarf, brown jacket",
            ),
            PresetCharacter(
                name="Levi Ackerman",
                hair_hex="#111111",
                skin_hex="#F8D7BE",
                costume_hex="#5D4037",
                extra_hex="#FFFFFF",
                notes="Black undercut hair, pale skin, brown Scout jacket, white cravat tie",
            ),
        ],
        prompt_guidance=(
            "Colorize in gritty Attack on Titan anime style: "
            "Scout Regiment members wear leather brown jackets (#5D4037) with Wings of Freedom crests and deep green cloaks (#33691E); "
            "Mikasa wears her signature dark red scarf (#8B0000); "
            "Keep speech bubbles pure white with crisp black text."
        ),
    ),
    # ── 11. Jujutsu Kaisen ───────────────────────────────────────────
    MangaPreset(
        id="jujutsu_kaisen",
        title="Jujutsu Kaisen",
        aliases=[
            "jujutsu kaisen",
            "jujutsu",
            "jjk",
            "gojo",
            "itadori",
            "sukuna",
            "gege akutami",
        ],
        description="Gege Akutami modern sorcery palette: Gojo radiant white hair with Six Eyes cyan blue, Yuji pink hair, dark navy uniforms.",
        recommended_style="shonen_vivid",
        theme_color="#1A1A24",
        characters=[
            PresetCharacter(
                name="Satoru Gojo",
                hair_hex="#FFFFFF",
                skin_hex="#FFF0E5",
                costume_hex="#1A1A24",
                extra_hex="#0288D1",
                notes="Snow white spiky hair, fair porcelain skin, dark navy high uniform, luminous Six Eyes cyan blue",
            ),
            PresetCharacter(
                name="Yuji Itadori",
                hair_hex="#F48FB1",
                skin_hex="#E5A66E",
                costume_hex="#1A1A24",
                extra_hex="#D32F2F",
                notes="Spiky pink hair with black undercut, athletic tan, dark navy uniform with red hoodie collar",
            ),
            PresetCharacter(
                name="Megumi Fushiguro",
                hair_hex="#1A1A2E",
                skin_hex="#F8D7BE",
                costume_hex="#1A1A24",
                extra_hex="#37474F",
                notes="Dark navy spiky hair, pale skin, dark navy high-collar uniform",
            ),
        ],
        prompt_guidance=(
            "Colorize in sleek Jujutsu Kaisen anime style: "
            "Jujutsu High uniforms are dark midnight navy (#1A1A24); "
            "Satoru Gojo has snow white hair (#FFFFFF) and glowing Six Eyes cyan blue (#0288D1); "
            "Yuji Itadori has pink spiky hair with dark undercut and red hooded collar; "
            "Keep speech bubbles pure white."
        ),
    ),
    # ── 12. My Hero Academia ─────────────────────────────────────────
    MangaPreset(
        id="my_hero_academia",
        title="My Hero Academia",
        aliases=[
            "my hero academia",
            "boku no hero",
            "mha",
            "bnha",
            "deku",
            "all might",
            "kohei horikoshi",
            "bakugo",
            "todoroki",
        ],
        description="Kohei Horikoshi vibrant comic superhero aesthetic: Deku teal green hero suit, Bakugo grenade orange, Todoroki half red/white.",
        recommended_style="shonen_vivid",
        theme_color="#00897B",
        characters=[
            PresetCharacter(
                name="Izuku Midoriya (Deku)",
                hair_hex="#1B5E20",
                skin_hex="#FCE0CA",
                costume_hex="#00897B",
                extra_hex="#D32F2F",
                notes="Dark forest green curly hair, fair skin with freckles, teal green hero suit, red high-top boots",
            ),
            PresetCharacter(
                name="Katsuki Bakugo",
                hair_hex="#FFF59D",
                skin_hex="#F5C596",
                costume_hex="#212121",
                extra_hex="#FF6D00",
                notes="Spiky ash blond hair, warm peach skin, black grenade suit with bright orange X brace",
            ),
            PresetCharacter(
                name="Shoto Todoroki",
                hair_hex="#D32F2F",
                skin_hex="#FFF0E5",
                costume_hex="#1565C0",
                extra_hex="#FAFAFA",
                notes="Split crimson red and pure white hair, deep blue hero suit, white boots",
            ),
            PresetCharacter(
                name="All Might",
                hair_hex="#FFD700",
                skin_hex="#F5C596",
                costume_hex="#1565C0",
                extra_hex="#D32F2F",
                notes="Golden blond antenna hair, deep tan, red/blue/white American hero suit",
            ),
        ],
        prompt_guidance=(
            "Colorize in vibrant My Hero Academia comic superhero anime style: "
            "Deku has dark green hair, teal green suit (#00897B), and bright red boots (#D32F2F); "
            "Bakugo has ash blond hair, black grenade suit with orange X accents; "
            "Todoroki has split red and white hair; "
            "Keep speech bubbles pure white."
        ),
    ),
    # ── 13. Chainsaw Man ─────────────────────────────────────────────
    MangaPreset(
        id="chainsaw_man",
        title="Chainsaw Man",
        aliases=["chainsaw man", "chainsawman", "denji", "makima", "tatsuki fujimoto", "power"],
        description="Tatsuki Fujimoto gritty cinematic palette: Denji blond hair with orange Pochita, Makima braided coral, Power red devil horns.",
        recommended_style="shonen_vivid",
        theme_color="#FF5722",
        characters=[
            PresetCharacter(
                name="Denji",
                hair_hex="#FFD54F",
                skin_hex="#F5C596",
                costume_hex="#FFFFFF",
                extra_hex="#FF5722",
                notes="Scruffy yellowish-blond hair, peach skin, white collared shirt, orange chainsaw/Pochita",
            ),
            PresetCharacter(
                name="Makima",
                hair_hex="#E57373",
                skin_hex="#FFF0E5",
                costume_hex="#1A1A1A",
                extra_hex="#FFD54F",
                notes="Braided pastel reddish-coral hair, porcelain skin, black Public Safety suit & tie, golden ringed eyes",
            ),
            PresetCharacter(
                name="Power",
                hair_hex="#FFE082",
                skin_hex="#FFF0E5",
                costume_hex="#1565C0",
                extra_hex="#D32F2F",
                notes="Strawberry blond hair with red devil horns (#D32F2F), fair skin, blue oversized track jacket",
            ),
            PresetCharacter(
                name="Aki Hayakawa",
                hair_hex="#1A237E",
                skin_hex="#FCE4D6",
                costume_hex="#1A1A1A",
                extra_hex="#37474F",
                notes="Midnight navy topknot hair, pale fair skin, black suit & tie, sword back-strap",
            ),
        ],
        prompt_guidance=(
            "Colorize in cinematic Tatsuki Fujimoto Chainsaw Man anime aesthetic: "
            "Public Safety devil hunters wear black suits with white shirts; "
            "Denji has blond hair and orange chainsaw accents (#FF5722); "
            "Makima has soft reddish-coral braided hair (#E57373) and golden concentric ring eyes; "
            "Power has light blond hair with crimson red horns (#D32F2F); "
            "Keep speech bubbles pure white."
        ),
    ),
    # ── 14. Spy x Family ─────────────────────────────────────────────
    MangaPreset(
        id="spy_x_family",
        title="Spy x Family",
        aliases=["spy x family", "spyxfamily", "anya", "forger", "tatsuya endo", "loid", "yor"],
        description="Tatsuya Endo elegant mid-century retro palette: Anya candy pink hair & green eyes, Loid sage green suit, Yor black dress.",
        recommended_style="gemini_anime",
        theme_color="#F48FB1",
        characters=[
            PresetCharacter(
                name="Anya Forger",
                hair_hex="#F48FB1",
                skin_hex="#FFF0E5",
                costume_hex="#212121",
                extra_hex="#FFD700",
                notes="Candy pink hair with black horn cones, emerald green eyes (#4CAF50), Eden Academy black uniform with gold trim",
            ),
            PresetCharacter(
                name="Loid Forger (Twilight)",
                hair_hex="#DCE775",
                skin_hex="#F5C596",
                costume_hex="#2E7D32",
                extra_hex="#C62828",
                notes="Pale blond hair, fair skin with blue eyes, sage green suit, red tie",
            ),
            PresetCharacter(
                name="Yor Forger (Thorn Princess)",
                hair_hex="#1A1A1A",
                skin_hex="#FFF0E5",
                costume_hex="#1A1A1A",
                extra_hex="#D32F2F",
                notes="Glossy black hair with gold rose headband, porcelain skin, black assassin dress with crimson rose lining",
            ),
        ],
        prompt_guidance=(
            "Colorize in elegant Spy x Family anime aesthetic: "
            "Anya has candy pink hair (#F48FB1) and sparkling emerald green eyes; "
            "Loid wears a tailored sage green suit (#2E7D32) and red tie; "
            "Yor has black hair and elegant black dress with crimson rose accents; "
            "Keep speech bubbles pure white with crisp black text."
        ),
    ),
    # ── 15. Death Note ───────────────────────────────────────────────
    MangaPreset(
        id="death_note",
        title="Death Note",
        aliases=["death note", "deathnote", "light yagami", "tsugumi ohba", "ryuk"],
        description="Tsugumi Ohba & Takeshi Obata gothic psychological thriller palette: Light auburn/brown hair, L pale skin with dark circles, Misa blond.",
        recommended_style="dark_fantasy",
        theme_color="#212121",
        characters=[
            PresetCharacter(
                name="Light Yagami",
                hair_hex="#8D6E63",
                skin_hex="#FCE0CA",
                costume_hex="#C29B38",
                extra_hex="#B71C1C",
                notes="Light brown hair, fair skin, tan/khaki school uniform blazer, crimson red tie",
            ),
            PresetCharacter(
                name="L (Lawliet)",
                hair_hex="#1A1A1A",
                skin_hex="#FFF0E5",
                costume_hex="#FFFFFF",
                extra_hex="#1565C0",
                notes="Messy jet black hair, pale porcelain skin with dark eye bags, white long-sleeve shirt, blue jeans",
            ),
            PresetCharacter(
                name="Misa Amane",
                hair_hex="#FFD54F",
                skin_hex="#FFF0E5",
                costume_hex="#1A1A1A",
                extra_hex="#C2185B",
                notes="Golden blond pigtails, fair skin, black gothic lolita leather outfit, cross necklace",
            ),
            PresetCharacter(
                name="Ryuk",
                hair_hex="#1A1A24",
                skin_hex="#CFD8DC",
                costume_hex="#1A1A1A",
                extra_hex="#D32F2F",
                notes="Spiky midnight blue/black hair, ash grey skin, black feathered leather suit, red eyes and red apples",
            ),
        ],
        prompt_guidance=(
            "Colorize in moody Death Note anime aesthetic: "
            "Light Yagami has brown hair (#8D6E63), tan blazer (#C29B38), red tie; "
            "L has messy black hair, pale skin with dark shadows around eyes, white shirt (#FFFFFF); "
            "Keep speech bubbles pure white with crisp black text."
        ),
    ),
    # ── 16. Fullmetal Alchemist ──────────────────────────────────────
    MangaPreset(
        id="fullmetal_alchemist",
        title="Fullmetal Alchemist",
        aliases=["fullmetal alchemist", "fullmetal", "fma", "edward elric", "hiromu arakawa"],
        description="Hiromu Arakawa industrial steampunk alchemy palette: Edward Elric golden blond hair and crimson coat, Roy Mustang military blue.",
        recommended_style="shonen_vivid",
        theme_color="#D32F2F",
        characters=[
            PresetCharacter(
                name="Edward Elric",
                hair_hex="#FFD54F",
                skin_hex="#F5C596",
                costume_hex="#D32F2F",
                extra_hex="#757575",
                notes="Golden blond braided hair, fair peach skin, signature bright crimson red hooded coat, silver automail",
            ),
            PresetCharacter(
                name="Alphonse Elric",
                hair_hex="#757575",
                skin_hex="#9E9E9E",
                costume_hex="#757575",
                extra_hex="#795548",
                notes="Steel grey armor body, brown leather loincloth, white transmutation symbol",
            ),
            PresetCharacter(
                name="Roy Mustang",
                hair_hex="#1A1A1A",
                skin_hex="#F5C596",
                costume_hex="#1565C0",
                extra_hex="#FFFFFF",
                notes="Short black hair, fair skin, Amestris military dark blue uniform, white ignition gloves",
            ),
        ],
        prompt_guidance=(
            "Colorize in Fullmetal Alchemist anime style: "
            "Edward Elric has golden blond hair (#FFD54F), vibrant crimson red coat (#D32F2F), black clothes, silver automail; "
            "Roy Mustang wears dark military blue uniform (#1565C0) with white gloves; "
            "Keep speech bubbles pure white."
        ),
    ),
    # ── 17. Hunter x Hunter ──────────────────────────────────────────
    MangaPreset(
        id="hunter_x_hunter",
        title="Hunter x Hunter",
        aliases=["hunter x hunter", "hunterxhunter", "hxh", "gon", "killua", "yoshihiro togashi"],
        description="Yoshihiro Togashi adventure palette: Gon spiky green/black hair and green outfit, Killua fluffy silver hair, Kurapika royal blue tabard.",
        recommended_style="shonen_vivid",
        theme_color="#4CAF50",
        characters=[
            PresetCharacter(
                name="Gon Freecss",
                hair_hex="#1B5E20",
                skin_hex="#E5A66E",
                costume_hex="#4CAF50",
                extra_hex="#FF6F00",
                notes="Spiky black hair with green sheen, sun-tanned skin, green jacket & shorts, orange lining",
            ),
            PresetCharacter(
                name="Killua Zoldyck",
                hair_hex="#ECEFF1",
                skin_hex="#FFF0E5",
                costume_hex="#5C6BC0",
                extra_hex="#1E88E5",
                notes="Fluffy silver/white hair, pale porcelain skin, indigo undershirt, electric blue aura",
            ),
            PresetCharacter(
                name="Kurapika",
                hair_hex="#FFD54F",
                skin_hex="#FFF0E5",
                costume_hex="#1565C0",
                extra_hex="#D32F2F",
                notes="Golden blond chin-length hair, porcelain skin, royal blue tabard with red/orange trim, scarlet glowing eyes",
            ),
            PresetCharacter(
                name="Hisoka Morow",
                hair_hex="#E91E63",
                skin_hex="#FFF0E5",
                costume_hex="#9C27B0",
                extra_hex="#00BCD4",
                notes="Magenta swept-back hair, pale skin, purple jester suit with playing card suits, cyan teardrop face paint",
            ),
        ],
        prompt_guidance=(
            "Colorize in vibrant Hunter x Hunter anime style: "
            "Gon has green-tipped spiky hair and green jacket (#4CAF50); "
            "Killua has fluffy silver hair (#ECEFF1) and pale skin; "
            "Kurapika has golden blond hair and royal blue outfit with red accents; "
            "Keep speech bubbles pure white."
        ),
    ),
    # ── 18. JoJo's Bizarre Adventure ─────────────────────────────────
    MangaPreset(
        id="jojo",
        title="JoJo's Bizarre Adventure",
        aliases=["jojo", "jojo's bizarre adventure", "stardust crusaders", "jotaro", "hirohiko araki", "dio"],
        description="Hirohiko Araki flamboyant high-fashion palette: Jotaro black coat with gold chain, DIO golden yellow jacket with green heart accents.",
        recommended_style="shonen_vivid",
        theme_color="#673AB7",
        characters=[
            PresetCharacter(
                name="Jotaro Kujo",
                hair_hex="#1A1A1A",
                skin_hex="#F5C596",
                costume_hex="#1A1A24",
                extra_hex="#FFD700",
                notes="Black hair blending into black school cap, dark uniform gakuran, heavy golden chain (#FFD700)",
            ),
            PresetCharacter(
                name="DIO",
                hair_hex="#FFD700",
                skin_hex="#F5C596",
                costume_hex="#FBC02D",
                extra_hex="#4CAF50",
                notes="Golden blond hair, golden yellow open jacket, emerald green heart headband and knee pads",
            ),
            PresetCharacter(
                name="Joseph Joestar",
                hair_hex="#5D4037",
                skin_hex="#E5A66E",
                costume_hex="#4E342E",
                extra_hex="#1E88E5",
                notes="Brown hair, athletic tan, brown tank top, blue and green striped scarf",
            ),
        ],
        prompt_guidance=(
            "Colorize in flamboyant Hirohiko Araki JoJo anime aesthetic: "
            "Jotaro wears black gakuran coat with thick golden neck chain (#FFD700); "
            "DIO has golden blond hair (#FFD700) with yellow outfit and green heart ornaments; "
            "Vivid atmospheric comic sound effects and pure white speech bubbles."
        ),
    ),
]


# ─────────────────────────────────────────────────────────────────────
#  Registry & Auto-Detection Engine
# ─────────────────────────────────────────────────────────────────────

PRESET_REGISTRY: dict[str, MangaPreset] = {p.id: p for p in BUILTIN_PRESETS}
CUSTOM_PRESETS_FILE = Path(__file__).resolve().parent / "sessions" / "custom_manga_presets.json"


def load_custom_presets():
    """Loads any user-saved custom or dynamically downloaded presets from disk."""
    if CUSTOM_PRESETS_FILE.exists():
        try:
            with open(CUSTOM_PRESETS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                for item in data.get("presets", []):
                    preset = MangaPreset.from_dict(item)
                    PRESET_REGISTRY[preset.id] = preset
        except Exception as e:
            print(f"[MangaPresets Warning] Could not load custom presets: {e}")


def save_custom_preset(preset: MangaPreset):
    """Persists a new or dynamically searched preset to disk."""
    PRESET_REGISTRY[preset.id] = preset
    try:
        CUSTOM_PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
        custom_list = [
            p.to_dict()
            for p in PRESET_REGISTRY.values()
            if p.id not in {bp.id for bp in BUILTIN_PRESETS}
        ]
        with open(CUSTOM_PRESETS_FILE, "w", encoding="utf-8") as f:
            json.dump({"presets": custom_list}, f, indent=2)
    except Exception as e:
        print(f"[MangaPresets Warning] Could not save custom preset: {e}")


# Initialize custom presets on import
load_custom_presets()


def normalize_text_for_matching(text: str) -> str:
    """Normalizes titles/filenames for robust keyword and alias matching."""
    text = text.lower()
    # Replace file extensions, punctuation and separators with spaces
    text = re.sub(r"\.(pdf|epub|cbz|cbr|zip|tar|gz|png|jpg|jpeg|webp)$", "", text)
    text = re.sub(r"[\-_\.\+\[\]\(\)\{\}~@#\$%^&\*=\\/|;:,<>?`]+", " ", text)
    return " ".join(text.split())


def detect_manga_preset(filename_or_title: str) -> Optional[MangaPreset]:
    """
    Auto-detects the matching manga preset from a filename or title.

    Matches against aliases using word boundary checking and token containment.
    Returns the most specific matching MangaPreset, or None if unrecognized.
    """
    if not filename_or_title:
        return None

    norm = normalize_text_for_matching(filename_or_title)
    if not norm:
        return None

    best_match: Optional[MangaPreset] = None
    max_matched_len = 0

    for preset in PRESET_REGISTRY.values():
        for alias in preset.aliases:
            norm_alias = normalize_text_for_matching(alias)
            if not norm_alias:
                continue

            # Exact phrase match or token sub-sequence match
            pattern = r"(?:^|\s)" + re.escape(norm_alias) + r"(?:\s|$)"
            if re.search(pattern, norm) or norm_alias in norm:
                if len(norm_alias) > max_matched_len:
                    max_matched_len = len(norm_alias)
                    best_match = preset

    return best_match


def get_all_presets() -> list[MangaPreset]:
    """Returns all registered manga presets (built-in + custom)."""
    return list(PRESET_REGISTRY.values())


def get_preset_by_id(preset_id: str) -> Optional[MangaPreset]:
    """Looks up a preset by its unique ID."""
    return PRESET_REGISTRY.get(preset_id)


# ─────────────────────────────────────────────────────────────────────
#  Online Search & Dynamic Preset Generator
# ─────────────────────────────────────────────────────────────────────

# Heuristic color mapping for common anime color words
COLOR_NAME_MAP = {
    "red": "#D32F2F",
    "crimson": "#C62828",
    "scarlet": "#E53935",
    "blue": "#1976D2",
    "navy": "#0D1B2A",
    "sky blue": "#42A5F5",
    "cyan": "#00BCD4",
    "turquoise": "#26C6DA",
    "green": "#388E3C",
    "emerald": "#00E676",
    "moss green": "#4E8752",
    "yellow": "#FBC02D",
    "gold": "#FFD700",
    "golden": "#FFD700",
    "blond": "#FFD54F",
    "blonde": "#FFD54F",
    "orange": "#F57C00",
    "purple": "#7B1FA2",
    "violet": "#8A2BE2",
    "lavender": "#BA68C8",
    "pink": "#E91E63",
    "peach": "#FCD0A1",
    "brown": "#5D4037",
    "chestnut": "#3E2723",
    "black": "#1C1B1F",
    "white": "#FFFFFF",
    "grey": "#757575",
    "gray": "#757575",
    "silver": "#ECEFF1",
}


def search_online_manga_preset(query: str) -> Optional[MangaPreset]:
    """
    Searches online knowledge bases (Wikipedia API / Anime data) for a manga title,
    extracts key characters and their canonical colors, generates a MangaPreset,
    and caches it for future auto-detection.
    """
    clean_query = query.strip()
    if not clean_query:
        return None

    # Check if we already have it in registry first
    existing = detect_manga_preset(clean_query) or PRESET_REGISTRY.get(clean_query.lower())
    if existing:
        return existing

    try:
        # Search Wikipedia API for characters of the manga
        search_term = f"{clean_query} manga characters"
        encoded = urllib.parse.quote(search_term)
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded}&format=json&utf8=1"

        req = urllib.request.Request(
            search_url, headers={"User-Agent": "KobeanMangaColorizer/1.0 (ColorPresetBot)"}
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            search_data = json.loads(response.read().decode("utf-8"))

        search_results = search_data.get("query", {}).get("search", [])
        if not search_results:
            return None

        # Pick the best page result (either a dedicated List of characters or main article)
        page_title = search_results[0]["title"]
        for res in search_results[:3]:
            if "characters" in res["title"].lower() or clean_query.lower() in res["title"].lower():
                page_title = res["title"]
                break

        # Fetch page extract and sections
        extract_url = (
            f"https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1"
            f"&titles={urllib.parse.quote(page_title)}&format=json&utf8=1"
        )
        req2 = urllib.request.Request(
            extract_url, headers={"User-Agent": "KobeanMangaColorizer/1.0 (ColorPresetBot)"}
        )
        with urllib.request.urlopen(req2, timeout=6) as response2:
            page_data = json.loads(response2.read().decode("utf-8"))

        pages = page_data.get("query", {}).get("pages", {})
        extract_text = ""
        for p in pages.values():
            extract_text = p.get("extract", "")
            break

        if not extract_text:
            return None

        # Parse character names and colors from the text
        characters: list[PresetCharacter] = []
        # Look for character headings: === Character Name === or == Main characters ==
        lines = extract_text.split("\n")
        current_char = None
        char_text_acc = []

        for line in lines:
            line_str = line.strip()
            # Detect character section header: === Name ===
            m_header = re.match(r"^===\s*([^=]+?)\s*===$", line_str)
            if m_header:
                if current_char and char_text_acc:
                    parsed = _parse_character_colors(current_char, " ".join(char_text_acc))
                    if parsed:
                        characters.append(parsed)
                current_char = m_header.group(1).strip()
                char_text_acc = []
            elif current_char:
                if line_str.startswith("=="):
                    # Section ended
                    if char_text_acc:
                        parsed = _parse_character_colors(current_char, " ".join(char_text_acc))
                        if parsed:
                            characters.append(parsed)
                    current_char = None
                    char_text_acc = []
                else:
                    char_text_acc.append(line_str)

        if current_char and char_text_acc:
            parsed = _parse_character_colors(current_char, " ".join(char_text_acc))
            if parsed:
                characters.append(parsed)

        # If header parsing yielded fewer than 2 characters, fallback to bullet lists
        if len(characters) < 2:
            bullet_pattern = r"(?:^|\n)\*\s*\*\*([A-Za-z\s\.\-']+)\*\*:\s*([^\n]+)"
            for m in re.finditer(bullet_pattern, extract_text):
                cname = m.group(1).strip()
                cdesc = m.group(2).strip()
                if len(cname.split()) <= 4:
                    parsed = _parse_character_colors(cname, cdesc)
                    if parsed and parsed.name not in {c.name for c in characters}:
                        characters.append(parsed)

        if not characters:
            # Create at least a base character with title
            characters = [
                PresetCharacter(
                    name=f"Protagonist ({clean_query})",
                    hair_hex="#1C1B1F",
                    skin_hex="#FCD0A1",
                    costume_hex="#E62C39",
                    notes="Auto-generated online preset",
                )
            ]

        # Generate preset ID and title
        clean_id = re.sub(r"[^a-z0-9]+", "_", clean_query.lower()).strip("_")
        preset = MangaPreset(
            id=clean_id,
            title=clean_query.title(),
            aliases=[clean_query.lower(), clean_query.lower().replace(" ", "")],
            description=f"Online auto-generated canonical palette for {clean_query}.",
            recommended_style="shonen_vivid",
            theme_color=characters[0].costume_hex or "#E62C39",
            characters=characters[:10],  # keep top 10 characters
        )
        save_custom_preset(preset)
        return preset
    except Exception as e:
        print(f"[Online Preset Search Error] {query}: {e}")
        return None


def _parse_character_colors(name: str, text: str) -> Optional[PresetCharacter]:
    """Helper to detect hair, skin, and clothing colors from character description text."""
    # Filter out obvious non-character headers
    if any(
        w in name.lower()
        for w in [
            "production",
            "reception",
            "plot",
            "voice",
            "cast",
            "media",
            "manga",
            "anime",
            "film",
            "music",
            "development",
            "concept",
            "creation",
            "appearance",
            "sequel",
            "prequel",
            "chapter",
            "volume",
            "criticism",
            "merchandise",
            "notes",
            "references",
            "bibliography",
        ]
    ):
        return None

    text_lower = text.lower()
    hair_hex = ""
    costume_hex = ""
    extra_hex = ""
    skin_hex = "#FCD0A1"  # standard warm anime peach skin tone

    # Detect hair color: e.g. "blond hair", "red hair", "black hair"
    for cname, chex in COLOR_NAME_MAP.items():
        if f"{cname} hair" in text_lower or f"hair is {cname}" in text_lower:
            hair_hex = chex
            break

    if not hair_hex:
        # Check spiky/long hair mentions or general hair
        for cname, chex in COLOR_NAME_MAP.items():
            if f"{cname} spiky" in text_lower or f"{cname} ponytail" in text_lower:
                hair_hex = chex
                break

    # Detect clothing color: e.g. "red robe", "green uniform", "black suit", "wears a vibrant red"
    garment_nouns = (
        "robe|jacket|shirt|suit|dress|coat|vest|uniform|cape|cloak|hoodie|kimono|gi|shorts|pants|clothes|outfit"
    )
    for cname, chex in COLOR_NAME_MAP.items():
        # Direct pattern: "red robe", "blue jacket", etc.
        if re.search(rf"\b{cname}\s+(?:{garment_nouns})\b", text_lower):
            costume_hex = chex
            break
        # Verb pattern: "wears a [optional adj] red [garment]"
        if re.search(rf"\b(?:wears|wearing|signature)\s+(?:\w+\s+){{0,2}}{cname}\b", text_lower):
            costume_hex = chex
            break
        # Reverse attribute: "uniform is red", "jacket is blue"
        if re.search(rf"\b(?:{garment_nouns})\s+is\s+{cname}\b", text_lower):
            costume_hex = chex
            break

    # Fallback default hair if none detected
    if not hair_hex:
        hair_hex = "#1C1B1F"  # black hair
    if not costume_hex:
        costume_hex = "#1565C0"  # anime blue

    return PresetCharacter(
        name=name.strip(),
        hair_hex=hair_hex,
        skin_hex=skin_hex,
        costume_hex=costume_hex,
        extra_hex=extra_hex,
        notes="Online extracted",
    )
