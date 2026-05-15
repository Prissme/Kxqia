"""
card_generator.py — Version améliorée 2026
GIF de bien meilleure qualité tout en gardant une bonne vitesse.
"""

import asyncio
import io
import logging
import os
import re
import unicodedata
import urllib.request
from functools import partial
from pathlib import Path
from typing import Callable, Optional

import aiohttp

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chemins
# ---------------------------------------------------------------------------
_FONT_CACHE_DIR = Path(os.getenv("FONT_CACHE_DIR", "/tmp/bot_fonts"))
_SEKUYA_PATH    = _FONT_CACHE_DIR / "Sekuya.ttf"
_NOTO_PATH      = _FONT_CACHE_DIR / "NotoSans.ttf"
_BG_GIF_URL     = (
    "https://64.media.tumblr.com/50bc02e1080b949b2bd58c9353e4d779/"
    "b81f0327a444c7a5-c3/s540x810/6420baec988b32ab0c087abdc0d2bf9601ae512c.gif"
)
_BG_GIF_PATH = _FONT_CACHE_DIR / "bg_animated.gif"

# ---------------------------------------------------------------------------
# Couleurs
# ---------------------------------------------------------------------------
NEON    = (0, 200, 255, 255)
WHITE   = (255, 255, 255, 255)
GREY    = (200, 210, 230, 255)
BAR_BG  = (20, 25, 55, 180)
GOLD    = (255, 215, 0, 255)
SILVER  = (192, 192, 192, 255)
BRONZE  = (205, 127, 50, 255)
OVERLAY = (0, 0, 0, 175)
SHADOW  = (0, 0, 0, 230)

MAX_FRAMES_CARD = 18
MAX_FRAMES_TOP  = 14

# ---------------------------------------------------------------------------
# Caches globaux
# ---------------------------------------------------------------------------
_fonts_ready: bool = False
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

_raw_bg_frames: list[Image.Image] = []
_raw_bg_duration: int = 60
_bg_loaded: bool = False

_prepared_cache: dict[tuple[int, int, int], tuple[list[Image.Image], int]] = {}
_avatar_cache: dict[tuple[str, int], Optional[Image.Image]] = {}


# ---------------------------------------------------------------------------
# Polices
# ---------------------------------------------------------------------------
_NOTO_SANS_URL = (
    "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Regular.ttf"
)


def _dl(url: str, dest: Path) -> bool:
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=10).read()
        dest.write_bytes(data)
        return True
    except Exception as exc:
        logger.warning("Téléchargement échoué %s : %s", url, exc)
        return False


def _ensure_fonts() -> None:
    global _fonts_ready
    if _fonts_ready:
        return
    _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not _SEKUYA_PATH.exists():
        try:
            css = urllib.request.urlopen(
                urllib.request.Request(
                    "https://fonts.googleapis.com/css2?family=Sekuya&display=swap",
                    headers={"User-Agent": "Mozilla/5.0"},
                ),
                timeout=10,
            ).read().decode()
            m = re.search(r"url\[](https://[^)]+\.ttf[^)]*)\)", css)
            if m:
                _dl(m.group(1), _SEKUYA_PATH)
        except Exception:
            pass

    if not _NOTO_PATH.exists():
        _dl(_NOTO_SANS_URL, _NOTO_PATH)

    _fonts_ready = True


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    key = ("sekuya", size)
    if key in _font_cache:
        return _font_cache[key]
    _ensure_fonts()
    for p in (_SEKUYA_PATH, _NOTO_PATH):
        if p.exists():
            try:
                f = ImageFont.truetype(str(p), size)
                _font_cache[key] = f
                return f
            except Exception:
                pass
    f = ImageFont.load_default()
    _font_cache[key] = f
    return f


def _load_noto(size: int) -> ImageFont.FreeTypeFont:
    key = ("noto", size)
    if key in _font_cache:
        return _font_cache[key]
    _ensure_fonts()
    if _NOTO_PATH.exists():
        try:
            f = ImageFont.truetype(str(_NOTO_PATH), size)
            _font_cache[key] = f
            return f
        except Exception:
            pass
    f = ImageFont.load_default()
    _font_cache[key] = f
    return f


# ---------------------------------------------------------------------------
# GIF de fond
# ---------------------------------------------------------------------------

def _load_raw_bg_gif() -> None:
    global _raw_bg_frames, _raw_bg_duration, _bg_loaded
    if _bg_loaded:
        return

    _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not _BG_GIF_PATH.exists():
        try:
            req  = urllib.request.Request(_BG_GIF_URL, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=20).read()
            _BG_GIF_PATH.write_bytes(data)
            logger.info("GIF de fond téléchargé (%d octets).", len(data))
        except Exception as exc:
            logger.warning("GIF fond indisponible : %s", exc)
            _bg_loaded = True
            return

    try:
        gif = Image.open(_BG_GIF_PATH)
        _raw_bg_duration = int(gif.info.get("duration", 60) or 60)
        frames: list[Image.Image] = []
        try:
            while True:
                frames.append(gif.copy().convert("RGBA"))
                gif.seek(gif.tell() + 1)
        except EOFError:
            pass
        _raw_bg_frames = frames
        logger.info("GIF brut chargé : %d frames, %d ms/frame.", len(frames), _raw_bg_duration)
    except Exception as exc:
        logger.warning("Erreur lecture GIF : %s", exc)

    _bg_loaded = True


def _get_prepared_frames(w: int, h: int, max_frames: int) -> tuple[list[Image.Image], int]:
    key = (w, h, max_frames)
    if key in _prepared_cache:
        return _prepared_cache[key]

    _load_raw_bg_gif()

    if not _raw_bg_frames:
        fallback = Image.new("RGBA", (w, h), (10, 12, 25, 255))
        _prepared_cache[key] = ([fallback], 60)
        return _prepared_cache[key]

    step    = max(1, len(_raw_bg_frames) // max_frames)
    sampled = _raw_bg_frames[::step][:max_frames]

    prepared: list[Image.Image] = []
    for frame in sampled:
        fitted = ImageOps.fit(frame, (w, h), method=Image.LANCZOS)
        fitted = ImageEnhance.Brightness(fitted).enhance(0.52)
        prepared.append(fitted)

    _prepared_cache[key] = (prepared, _raw_bg_duration)
    logger.info("Frames préparées mises en cache %dx%d (%d frames).", w, h, len(prepared))
    return _prepared_cache[key]


def _get_frames_copy(w: int, h: int, max_frames: int) -> tuple[list[Image.Image], int]:
    frames, duration = _get_prepared_frames(w, h, max_frames)
    return [f.copy() for f in frames], duration


# ---------------------------------------------------------------------------
# Helpers de dessin
# ---------------------------------------------------------------------------

def _draw_shadow_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
    offset: int = 2,
) -> None:
    sx, sy = xy[0] + offset, xy[1] + offset
    draw.text((sx + 1, sy + 1), text, font=font, fill=SHADOW)
    draw.text((sx,     sy),     text, font=font, fill=SHADOW)
    draw.text(xy,               text, font=font, fill=fill)


def _draw_xp_bar(
    draw: ImageDraw.ImageDraw,
    x: int, y: int, w: int, h: int,
    progress: float,
) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=BAR_BG)
    ratio    = max(0.0, min(1.0, progress))
    filled_w = int(w * ratio)
    if filled_w > h:
        draw.rounded_rectangle((x, y, x + filled_w, y + h), radius=h // 2, fill=NEON)


def _sanitize_text(text: str, max_len: int = 28) -> str:
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        cp = ord(ch)
        if unicodedata.category(ch) in ("Mn", "Cf") or cp == 0x200D:
            i += 1; continue
        if 0x1F3FB <= cp <= 0x1F3FF:
            i += 1; continue
        if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or \
           (0xFE00  <= cp <= 0xFE0F)  or (0xE0000 <= cp <= 0xE007F):
            result.append("?"); i += 1; continue
        if 0x1F1E0 <= cp <= 0x1F1FF:
            result.append("?")
            i += 2 if i + 1 < len(text) and 0x1F1E0 <= ord(text[i + 1]) <= 0x1F1FF else 1
            continue
        result.append(ch); i += 1
    clean = "".join(result).strip()
    return clean[:max_len] if clean else "Joueur"


# ---------------------------------------------------------------------------
# Avatar
# ---------------------------------------------------------------------------

async def _fetch_avatar(url: Optional[str], size: int) -> Optional[Image.Image]:
    if not url:
        return None
    key = (url, size)
    if key in _avatar_cache:
        return _avatar_cache[key]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    _avatar_cache[key] = None
                    return None
                data = await resp.read()
        av   = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        out  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(av, mask=mask)
        _avatar_cache[key] = out
        return out
    except Exception as exc:
        logger.warning("Erreur avatar %s : %s", url, exc)
        _avatar_cache[key] = None
        return None


# ---------------------------------------------------------------------------
# **ENCODAGE GIF AMÉLIORÉ**
# ---------------------------------------------------------------------------

def _encode_gif(frames: list[Image.Image], duration: int) -> io.BytesIO:
    """Version améliorée : meilleure qualité visuelle"""
    processed = []

    for frame in frames:
        # Conversion + netteté pour compenser la compression GIF
        img = frame.convert("RGB")
        img = img.filter(ImageFilter.SHARPEN)        # ← très important
        img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=120, threshold=3))

        # Meilleure quantification
        quantized = img.quantize(
            colors=256,                              # 256 au lieu de 128
            method=Image.Quantize.MEDIANCUT,         # meilleur pour les néons et textes
            dither=Image.Dither.FLOYDSTEINBERG       # dithering de qualité
        )
        processed.append(quantized)

    buf = io.BytesIO()
    processed[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=processed[1:],
        duration=duration,
        loop=0,
        optimize=True,
        disposal=2,                     # important pour animation fluide
    )
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Construction des cartes
# ---------------------------------------------------------------------------

def _build_xp_card_sync(
    name: str,
    avatar: Optional[Image.Image],
    level: int,
    xp_progress: int,
    xp_required: int,
    xp_total: int,
) -> tuple[list[Image.Image], int]:

    W, H = 620, 200
    frames, duration = _get_frames_copy(W, H, MAX_FRAMES_CARD)

    font_name  = _load_font(34)
    font_level = _load_noto(20)
    font_small = _load_noto(15)

    name_clean = _sanitize_text(name, 24)
    ratio      = xp_progress / xp_required if xp_required > 0 else 1.0

    static_ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(static_ov).rounded_rectangle((150, 15, 600, 185), radius=16, fill=OVERLAY)

    halo = None
    if avatar:
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse((11, 36, 151, 176), fill=(0, 200, 255, 90))

    output: list[Image.Image] = []

    for frame in frames:
        frame.alpha_composite(static_ov)

        if avatar and halo:
            frame.alpha_composite(halo)
            frame.paste(avatar, (15, 40), avatar)

        draw = ImageDraw.Draw(frame)
        _draw_shadow_text(draw, (163, 25),  name_clean,                          font_name,  WHITE)
        _draw_shadow_text(draw, (163, 72),  f"NIVEAU {level}",                   font_level, NEON)
        _draw_shadow_text(draw, (420, 74),  f"{xp_progress}/{xp_required} XP",   font_small, GREY)
        _draw_xp_bar(draw, 163, 112, 425, 18, ratio)
        _draw_shadow_text(draw, (163 + 212 - 15, 114), f"{int(ratio * 100)}%",   font_small, WHITE)
        _draw_shadow_text(draw, (163, 145), f"Total : {xp_total} XP",            font_small, GREY)

        output.append(frame)

    return output, duration


def _build_levelup_sync(
    name: str,
    avatar: Optional[Image.Image],
    old_level: int,
    new_level: int,
    xp_progress: int,
    xp_required: int,
) -> tuple[list[Image.Image], int]:

    W, H = 620, 180
    frames, duration = _get_frames_copy(W, H, MAX_FRAMES_CARD)

    font_title = _load_font(34)
    font_name  = _load_noto(22)
    font_rank  = _load_noto(18)
    font_small = _load_noto(14)

    name_clean = _sanitize_text(name, 24)
    n          = len(frames)

    static_ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(static_ov).rounded_rectangle((145, 12, 603, 168), radius=16, fill=OVERLAY)

    output: list[Image.Image] = []

    for idx, frame in enumerate(frames):
        frame.alpha_composite(static_ov)
        anim = idx / max(n - 1, 1)

        if avatar:
            halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            pulse = int(60 + 80 * abs(anim - 0.5) * 2)
            ImageDraw.Draw(halo).ellipse((17, 35, 127, 145), fill=(0, 200, 255, pulse))
            frame.alpha_composite(halo)
            frame.paste(avatar, (22, 40), avatar)

        draw = ImageDraw.Draw(frame)
        _draw_shadow_text(draw, (158, 18), "LEVEL UP !",                       font_title, NEON)
        _draw_shadow_text(draw, (158, 66), name_clean,                         font_name,  WHITE)
        _draw_shadow_text(draw, (158, 96), f"Rang {old_level} → {new_level}", font_rank,  GREY)
        ratio = (xp_progress / xp_required if xp_required > 0 else 1.0) * anim
        _draw_xp_bar(draw, 158, 128, 435, 14, ratio)
        _draw_shadow_text(draw, (158, 148), f"{xp_progress} / {xp_required}", font_small, GREY)

        output.append(frame)

    return output, duration


def _build_topxp_sync(
    guild_name: str,
    entries: list[dict],
    avatars: list[Optional[Image.Image]],
    xp_to_level_fn: Callable[[int], int],
) -> tuple[list[Image.Image], int]:

    W, H = 620, 560
    frames, duration = _get_frames_copy(W, H, MAX_FRAMES_TOP)

    font_title = _load_font(26)
    font_row   = _load_noto(17)
    font_xp    = _load_noto(14)

    guild_clean = _sanitize_text(guild_name, 36)
    rank_colors = [GOLD, SILVER, BRONZE]

    static_ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(static_ov).rounded_rectangle((8, 8, 612, 552), radius=20, fill=OVERLAY)

    row_ovs: list[Optional[Image.Image]] = []
    y = 68
    for idx in range(len(entries[:10])):
        if idx % 2 == 0:
            ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(ov).rectangle((16, y - 2, 604, y + 38), fill=(255, 255, 255, 12))
            row_ovs.append(ov)
        else:
            row_ovs.append(None)
        y += 46

    output: list[Image.Image] = []

    for frame in frames:
        frame.alpha_composite(static_ov)
        draw = ImageDraw.Draw(frame)

        _draw_shadow_text(draw, (20, 18), f"CLASSEMENT  {guild_clean.upper()}", font_title, NEON)
        draw.line((20, 58, 600, 58), fill=(0, 200, 255, 100), width=1)

        y = 68
        for idx, entry in enumerate(entries[:10]):
            ov = row_ovs[idx]
            if ov is not None:
                frame.alpha_composite(ov)

            rank_color = rank_colors[idx] if idx < 3 else WHITE
            _draw_shadow_text(draw, (20, y + 6), f"#{idx + 1}", font_row, rank_color)

            av = avatars[idx] if idx < len(avatars) else None
            if av:
                frame.paste(av, (64, y + 4), av)

            name_clean = _sanitize_text(entry.get("user_name", "Inconnu"), 24)
            _draw_shadow_text(draw, (102, y + 6), name_clean, font_row, WHITE)

            xp_val = int(entry.get("xp", 0) or 0)
            lv     = xp_to_level_fn(xp_val)
            _draw_shadow_text(draw, (390, y + 7), f"LVL {lv}",       font_xp, NEON, offset=2)
            _draw_shadow_text(draw, (470, y + 7), f"{xp_val:,} XP",  font_xp, GREY, offset=2)
            y += 46

        output.append(frame)

    return output, duration


# ---------------------------------------------------------------------------
# API publique (async)
# ---------------------------------------------------------------------------

async def generate_xp_card(
    member_name: str,
    avatar_url: str,
    level: int,
    xp_total: int,
    xp_progress: int,
    xp_required: int,
) -> Optional[io.BytesIO]:
    if not Image:  # Pillow disponible ?
        return None
    avatar = await _fetch_avatar(avatar_url, 120)
    loop = asyncio.get_event_loop()
    frames, duration = await loop.run_in_executor(
        None, partial(_build_xp_card_sync, member_name, avatar, level, xp_progress, xp_required, xp_total)
    )
    return await loop.run_in_executor(None, partial(_encode_gif, frames, duration))


async def generate_levelup_card(
    member_name: str,
    avatar_url: str,
    old_level: int,
    new_level: int,
    xp_total: int,
    xp_progress: int,
    xp_required: int,
) -> Optional[io.BytesIO]:
    if not Image:
        return None
    avatar = await _fetch_avatar(avatar_url, 100)
    loop = asyncio.get_event_loop()
    frames, duration = await loop.run_in_executor(
        None, partial(_build_levelup_sync, member_name, avatar, old_level, new_level, xp_progress, xp_required)
    )
    return await loop.run_in_executor(None, partial(_encode_gif, frames, duration))


async def generate_topxp_card(
    guild_name: str,
    entries: list[dict],
    xp_to_level_fn: Callable[[int], int],
) -> Optional[io.BytesIO]:
    if not Image:
        return None
    avatars = list(await asyncio.gather(*[
        _fetch_avatar(e.get("avatar_url"), 30) for e in entries[:10]
    ]))
    loop = asyncio.get_event_loop()
    frames, duration = await loop.run_in_executor(
        None, partial(_build_topxp_sync, guild_name, entries[:10], avatars, xp_to_level_fn)
    )
    return await loop.run_in_executor(None, partial(_encode_gif, frames, duration))


# ---------------------------------------------------------------------------
# Warmup
# ---------------------------------------------------------------------------

def warmup_sync() -> None:
    _ensure_fonts()
    _load_raw_bg_gif()
    for w, h, mf in (
        (620, 200, MAX_FRAMES_CARD),
        (620, 180, MAX_FRAMES_CARD),
        (620, 560, MAX_FRAMES_TOP),
    ):
        _get_prepared_frames(w, h, mf)
    logger.info("Warmup card_generator terminé.")


async def warmup() -> None:
    await asyncio.get_event_loop().run_in_executor(None, warmup_sync)
