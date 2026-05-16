"""
card_generator.py — Refonte 2026 v3.3 (Vitesse optimisée)
=====================================================
- !xp et LevelUp limités à 20 frames (au lieu de 37)
- /topxp optimisé (1 frame + grille allégée)
- Resize BICUBIC + template statique
"""

import asyncio
import io
import logging
import os
import urllib.request
from functools import partial
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageSequence

logger = logging.getLogger(__name__)

# ========================= CONFIGURATION =========================
MAX_XP_FRAMES = 20          # Change à 15 ou 25 si tu veux
# ================================================================

_ROOT = Path(__file__).parent.parent
_BG_PATH = _ROOT / "GIFKxqia.webp"
_FONT_DIR = Path(os.getenv("FONT_CACHE_DIR", "/tmp/bot_fonts"))
_FONT_DIR.mkdir(parents=True, exist_ok=True)

_NOTO_PATH = _FONT_DIR / "NotoSans-Regular.ttf"
_NOTO_BOLD = _FONT_DIR / "NotoSans-Bold.ttf"
_NOTO_URL = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Regular.ttf"
_NOTO_BOLD_URL = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Bold.ttf"

XP_W, XP_H = 680, 200
LU_W, LU_H = 680, 200
TOP_W, TOP_H = 680, 580

# ---------------------------------------------------------------------------
# PALETTE
# ---------------------------------------------------------------------------
GLASS = (255, 255, 255, 30)
GLASS_BD = (255, 255, 255, 55)
NEON = (0, 220, 255)
VIOLET = (140, 80, 255)
TEXT_PRI = (240, 245, 255)
TEXT_SEC = (200, 215, 240)
TEXT_MUT = (160, 175, 210)
GOLD = (255, 200, 60)
SILVER = (185, 195, 215)
BRONZE = (200, 130, 60)

# ---------------------------------------------------------------------------
# CACHES
# ---------------------------------------------------------------------------
_bg_cache: Dict[Tuple[int, int], Tuple[List[Image.Image], int]] = {}
_template_cache: Dict[Tuple[int, int], Tuple[List[Image.Image], int]] = {}
_topxp_template: Optional[Image.Image] = None
_avatar_cache: Dict[Tuple[str, int], Optional[Image.Image]] = {}
_font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
_fonts_loaded = False

# ---------------------------------------------------------------------------
# POLICES
# ---------------------------------------------------------------------------
def _dl(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=12).read()
        dest.write_bytes(data)
        return True
    except Exception as exc:
        logger.warning("Téléchargement police échoué %s : %s", url, exc)
        return False


def _ensure_fonts() -> None:
    global _fonts_loaded
    if _fonts_loaded:
        return
    if not _NOTO_PATH.exists():
        _dl(_NOTO_URL, _NOTO_PATH)
    if not _NOTO_BOLD.exists():
        _dl(_NOTO_BOLD_URL, _NOTO_BOLD)
    _fonts_loaded = True


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = ("b" if bold else "r", size)
    if key in _font_cache:
        return _font_cache[key]
    _ensure_fonts()
    path = _NOTO_BOLD if bold else _NOTO_PATH
    try:
        f = ImageFont.truetype(str(path), size)
    except Exception:
        f = ImageFont.load_default()
    _font_cache[key] = f
    return f


# ---------------------------------------------------------------------------
# FOND ANIMÉ
# ---------------------------------------------------------------------------
def _make_fallback_frames(w: int, h: int) -> List[Image.Image]:
    img = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(8 + (18 - 8) * t)
        g = int(12 + (22 - 12) * t)
        b = int(35 + (58 - 35) * t)
        d.line([(0, y), (w, y)], fill=(r, g, b, 255))
    return [img]


def _load_bg_frames(w: int, h: int, max_frames: Optional[int] = None) -> Tuple[List[Image.Image], int]:
    key = (w, h)
    if key in _bg_cache:
        frames, duration = _bg_cache[key]
        if max_frames:
            return frames[:max_frames], duration
        return frames, duration

    if not _BG_PATH.exists():
        logger.warning("Fond animé introuvable → fallback")
        result = (_make_fallback_frames(w, h), 80)
        _bg_cache[key] = result
        return result

    try:
        src = Image.open(_BG_PATH)
        frames: List[Image.Image] = []
        duration = 80
        target = max_frames or 999

        for i, frame in enumerate(ImageSequence.Iterator(src)):
            if i >= target:
                break
            dur = frame.info.get("duration", 80)
            if dur and dur > 0:
                duration = int(dur)
            # BICUBIC = beaucoup plus rapide
            resized = frame.convert("RGBA").resize((w, h), Image.BICUBIC)
            frames.append(resized.copy())

        logger.info("Fond chargé : %s → %dx%d (%d frames)", _BG_PATH.name, w, h, len(frames))
        _bg_cache[key] = (frames, duration)
        return frames, duration

    except Exception as exc:
        logger.warning("Erreur chargement fond → fallback : %s", exc)
        result = (_make_fallback_frames(w, h), 80)
        _bg_cache[key] = result
        return result


# ---------------------------------------------------------------------------
# TEMPLATES & HELPERS
# ---------------------------------------------------------------------------
def _build_topxp_template() -> Image.Image:
    global _topxp_template
    if _topxp_template is not None:
        return _topxp_template.copy()

    bg, _ = _load_bg_frames(TOP_W, TOP_H, max_frames=1)
    canvas = bg[0].copy().convert("RGBA")
    _dark_overlay(canvas, 105)

    # Grille plus légère et rapide
    grid = Image.new("RGBA", (TOP_W, TOP_H), (0, 0, 0, 0))
    dg = ImageDraw.Draw(grid)
    for x in range(0, TOP_W, 60):
        dg.line([(x, 0), (x, TOP_H)], fill=(255, 255, 255, 5))
    for y in range(0, TOP_H, 60):
        dg.line([(0, y), (TOP_W, y)], fill=(255, 255, 255, 5))
    canvas.alpha_composite(grid)

    PAD = 14
    _glass_panel(canvas, PAD, PAD, TOP_W - PAD * 2, TOP_H - PAD * 2, r=20)

    draw = ImageDraw.Draw(canvas)
    draw.text((PAD + 18, PAD + 14), "CLASSEMENT", font=_font(12), fill=TEXT_MUT)

    sep = Image.new("RGBA", (TOP_W, TOP_H), (0, 0, 0, 0))
    ImageDraw.Draw(sep).line([(PAD + 18, PAD + 58), (TOP_W - PAD - 18, PAD + 58)],
                             fill=(*NEON, 65), width=2)
    canvas.alpha_composite(sep)

    _topxp_template = canvas
    return canvas.copy()


def _dark_overlay(canvas: Image.Image, alpha: int = 110) -> None:
    canvas.alpha_composite(Image.new("RGBA", canvas.size, (0, 0, 0, alpha)))


def _rounded_rect_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=r, fill=255)
    return mask


def _glass_panel(canvas: Image.Image, x: int, y: int, w: int, h: int, r: int = 18) -> None:
    panel = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(panel).rounded_rectangle(
        (x, y, x + w, y + h), radius=r, fill=GLASS, outline=GLASS_BD, width=1
    )
    canvas.alpha_composite(panel)


# ---------------------------------------------------------------------------
# DRAW FUNCTIONS
# ---------------------------------------------------------------------------
def _draw_xp_bar(canvas: Image.Image, x: int, y: int, w: int, h: int, progress: float, pct_label: bool = True) -> None:
    r = h // 2
    prog = max(0.0, min(1.0, progress))
    bg = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bg.paste(Image.new("RGBA", (w, h), (255, 255, 255, 22)), (x, y), _rounded_rect_mask(w, h, r))
    canvas.alpha_composite(bg)

    fill_w = max(r * 2, int(w * prog))
    bar = Image.new("RGBA", (fill_w, h), (0, 0, 0, 0))
    for px in range(fill_w):
        t = px / max(fill_w - 1, 1)
        rc = int(VIOLET[0] + (NEON[0] - VIOLET[0]) * t)
        gc = int(VIOLET[1] + (NEON[1] - VIOLET[1]) * t)
        bc = int(VIOLET[2] + (NEON[2] - VIOLET[2]) * t)
        ImageDraw.Draw(bar).line([(px, 0), (px, h)], fill=(rc, gc, bc, 255))

    filled = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    filled.paste(bar, (x, y), _rounded_rect_mask(fill_w, h, r))
    canvas.alpha_composite(filled)

    # Glow
    glow_r = h + 4
    gx = x + fill_w - glow_r // 2
    gy = y + h // 2 - glow_r // 2
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    dg = ImageDraw.Draw(glow)
    for i in range(glow_r, 0, -1):
        a = int(55 * (i / glow_r) ** 2)
        dg.ellipse((gx + glow_r - i, gy + glow_r - i, gx + glow_r + i, gy + glow_r + i), fill=(*NEON, a))
    canvas.alpha_composite(glow)

    if pct_label:
        pct_txt = f"{int(prog * 100)}%"
        f_pct = _font(11, bold=True)
        draw = ImageDraw.Draw(canvas)
        bbox = draw.textbbox((0, 0), pct_txt, font=f_pct)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = x + w - tw - 6
        ty = y + (h - th) // 2
        draw.text((tx + 1, ty + 1), pct_txt, font=f_pct, fill=(0, 0, 0, 180))
        draw.text((tx, ty), pct_txt, font=f_pct, fill=TEXT_PRI)


def _avatar_with_ring(canvas: Image.Image, avatar: Optional[Image.Image], cx: int, cy: int, av_size: int) -> None:
    ring_r = av_size // 2 + 3
    ring = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)
    for i in range(8, 0, -1):
        d.ellipse((cx - ring_r - i, cy - ring_r - i, cx + ring_r + i, cy + ring_r + i),
                  outline=(*NEON, int(35 * i / 8)), width=1)
    d.ellipse((cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r), outline=(*NEON, 220), width=2)
    canvas.alpha_composite(ring)

    if avatar:
        canvas.paste(avatar, (cx - av_size // 2, cy - av_size // 2), avatar)
    else:
        ph = Image.new("RGBA", (av_size, av_size), (30, 40, 80, 255))
        mask = _rounded_rect_mask(av_size, av_size, av_size // 2)
        ph_l = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ph_l.paste(ph, (cx - av_size // 2, cy - av_size // 2), mask)
        canvas.alpha_composite(ph_l)


def _level_badge(canvas: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int, level: int) -> None:
    label = f"LVL {level}"
    f = _font(13, bold=True)
    bbox = draw.textbbox((0, 0), label, font=f)
    tw = bbox[2] - bbox[0]
    bw, bh = tw + 22, 22
    badge = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(badge).rounded_rectangle((x, y, x + bw, y + bh), radius=bh // 2,
                                            fill=(*NEON, 28), outline=(*NEON, 110), width=1)
    canvas.alpha_composite(badge)
    draw.text((x + 11, y + 4), label, font=f, fill=NEON)


# ---------------------------------------------------------------------------
# BUILD FRAMES
# ---------------------------------------------------------------------------
def _build_xp_frame(template: Image.Image, name: str, avatar: Optional[Image.Image],
                    level: int, xp_progress: int, xp_required: int, xp_total: int) -> Image.Image:
    canvas = template.copy()
    PAD = 16
    _glass_panel(canvas, PAD, PAD, XP_W - PAD * 2, XP_H - PAD * 2, r=20)

    AV = 100
    CX = PAD + 20 + AV // 2
    CY = XP_H // 2
    _avatar_with_ring(canvas, avatar, CX, CY, AV)

    draw = ImageDraw.Draw(canvas)
    TX = CX + AV // 2 + 24

    f_name = _font(26, bold=True)
    name_s = name[:22] + ("…" if len(name) > 22 else "")
    draw.text((TX, PAD + 14), name_s, font=f_name, fill=TEXT_PRI)

    bbox = draw.textbbox((TX, PAD + 14), name_s, font=f_name)
    _level_badge(canvas, draw, bbox[2] + 10, PAD + 18, level)

    draw.text((TX, PAD + 48), f"{xp_progress:,} / {xp_required:,} XP", font=_font(15), fill=TEXT_SEC)

    BAR_X = TX
    BAR_Y = PAD + 76
    BAR_W = XP_W - PAD - 20 - TX
    ratio = xp_progress / xp_required if xp_required > 0 else 1.0
    _draw_xp_bar(canvas, BAR_X, BAR_Y, BAR_W, 14, ratio, True)

    draw.text((TX, BAR_Y + 22), f"Total : {xp_total:,} XP", font=_font(13), fill=TEXT_MUT)

    line = Image.new("RGBA", (XP_W, XP_H), (0, 0, 0, 0))
    ImageDraw.Draw(line).rectangle((PAD + AV + 36, PAD + 24, PAD + AV + 37, XP_H - PAD - 24), fill=(*NEON, 40))
    canvas.alpha_composite(line)
    return canvas


def _build_levelup_frame(template: Image.Image, name: str, avatar: Optional[Image.Image],
                         old_level: int, new_level: int, xp_progress: int, xp_required: int) -> Image.Image:
    canvas = template.copy()
    PAD = 16
    _glass_panel(canvas, PAD, PAD, LU_W - PAD * 2, LU_H - PAD * 2, r=20)

    AV = 100
    CX = PAD + 20 + AV // 2
    CY = LU_H // 2
    _avatar_with_ring(canvas, avatar, CX, CY, AV)

    draw = ImageDraw.Draw(canvas)
    TX = CX + AV // 2 + 28

    draw.text((TX, PAD + 10), "LEVEL UP !", font=_font(30, bold=True), fill=GOLD)
    name_s = name[:22] + ("…" if len(name) > 22 else "")
    draw.text((TX, PAD + 46), name_s, font=_font(20, bold=True), fill=TEXT_PRI)
    draw.text((TX, PAD + 72), f"Niveau {old_level} → {new_level}", font=_font(16), fill=TEXT_SEC)

    BAR_X = TX
    BAR_Y = PAD + 102
    BAR_W = LU_W - PAD - 20 - TX
    ratio = xp_progress / xp_required if xp_required > 0 else 1.0
    _draw_xp_bar(canvas, BAR_X, BAR_Y, BAR_W, 14, ratio, True)

    draw.text((TX, BAR_Y + 22), f"{xp_progress:,} / {xp_required:,} XP", font=_font(13), fill=TEXT_SEC)
    return canvas


def _build_topxp_frame(template: Image.Image, entries: list, avatars: list, xp_to_level_fn: Callable) -> Image.Image:
    canvas = template.copy()
    draw = ImageDraw.Draw(canvas)
    PAD = 14
    ROW_H = 46
    START_Y = PAD + 68
    AV_SIZE = 32
    RANK_COLORS = [GOLD, SILVER, BRONZE]

    for idx, entry in enumerate(entries[:10]):
        ry = START_Y + idx * ROW_H
        rank_col = RANK_COLORS[idx] if idx < 3 else TEXT_MUT

        if idx % 2 == 0:
            row_bg = Image.new("RGBA", (TOP_W, TOP_H), (0, 0, 0, 0))
            ImageDraw.Draw(row_bg).rounded_rectangle(
                (PAD + 8, ry, TOP_W - PAD - 8, ry + ROW_H - 4),
                radius=10, fill=(255, 255, 255, 11)
            )
            canvas.alpha_composite(row_bg)

        draw.text((PAD + 16, ry + 11), f"#{idx + 1}", font=_font(16, bold=True), fill=rank_col)

        av = avatars[idx] if idx < len(avatars) else None
        av_x = PAD + 54
        av_y = ry + (ROW_H - 4 - AV_SIZE) // 2

        if av:
            ring = Image.new("RGBA", (TOP_W, TOP_H), (0, 0, 0, 0))
            ImageDraw.Draw(ring).ellipse(
                (av_x - 3, av_y - 3, av_x + AV_SIZE + 3, av_y + AV_SIZE + 3),
                outline=(*rank_col, 160), width=2
            )
            canvas.alpha_composite(ring)

            av_r = av.resize((AV_SIZE, AV_SIZE), Image.LANCZOS) if av.size != (AV_SIZE, AV_SIZE) else av
            mask = _rounded_rect_mask(AV_SIZE, AV_SIZE, AV_SIZE // 2)
            av_l = Image.new("RGBA", (TOP_W, TOP_H), (0, 0, 0, 0))
            av_l.paste(av_r, (av_x, av_y), mask)
            canvas.alpha_composite(av_l)

        uname = (entry.get("user_name") or "Inconnu")[:23]
        draw.text((av_x + AV_SIZE + 12, ry + 8), uname, font=_font(15, bold=True), fill=TEXT_PRI)

        xp_val = int(entry.get("xp", 0) or 0)
        lv = xp_to_level_fn(xp_val)
        rx = TOP_W - PAD - 20

        lv_txt = f"LVL {lv}"
        lv_box = draw.textbbox((0, 0), lv_txt, font=_font(13, bold=True))
        draw.text((rx - (lv_box[2] - lv_box[0]), ry + 7), lv_txt, font=_font(13, bold=True), fill=NEON)

        xp_txt = f"{xp_val:,} XP"
        xp_box = draw.textbbox((0, 0), xp_txt, font=_font(12))
        draw.text((rx - (xp_box[2] - xp_box[0]), ry + 26), xp_txt, font=_font(12), fill=TEXT_SEC)

    return canvas


# ---------------------------------------------------------------------------
# ENCODAGE
# ---------------------------------------------------------------------------
def _encode_output(frames: List[Image.Image], duration: int) -> io.BytesIO:
    buf = io.BytesIO()
    if len(frames) == 1:
        frames[0].convert("RGB").save(buf, format="PNG", optimize=True, quality=95)
    else:
        rgba = [f.convert("RGBA") for f in frames]
        rgba[0].save(buf, format="GIF", save_all=True, append_images=rgba[1:],
                     loop=0, duration=duration, optimize=False, disposal=2)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# BUILDERS SYNC
# ---------------------------------------------------------------------------
def _build_xp_card_sync(name: str, avatar: Optional[Image.Image], level: int,
                        xp_progress: int, xp_required: int, xp_total: int) -> io.BytesIO:
    templates, duration = _load_bg_frames(XP_W, XP_H, MAX_XP_FRAMES)
    return _encode_output(
        [_build_xp_frame(t, name, avatar, level, xp_progress, xp_required, xp_total) for t in templates],
        duration
    )


def _build_levelup_sync(name: str, avatar: Optional[Image.Image], old_level: int, new_level: int,
                        xp_progress: int, xp_required: int) -> io.BytesIO:
    templates, duration = _load_bg_frames(LU_W, LU_H, MAX_XP_FRAMES)
    return _encode_output(
        [_build_levelup_frame(t, name, avatar, old_level, new_level, xp_progress, xp_required) for t in templates],
        duration
    )


def _build_topxp_sync(guild_name: str, entries: list, avatars: list, xp_to_level_fn: Callable) -> io.BytesIO:
    template = _build_topxp_template()
    return _encode_output(
        [_build_topxp_frame(template, entries, avatars, xp_to_level_fn)],
        80
    )


# ---------------------------------------------------------------------------
# AVATAR FETCH
# ---------------------------------------------------------------------------
async def _fetch_avatar(url: Optional[str], size: int) -> Optional[Image.Image]:
    if not url:
        return None
    key = (url, size)
    if key in _avatar_cache:
        return _avatar_cache[key]
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=4)) as r:
                if r.status != 200:
                    _avatar_cache[key] = None
                    return None
                data = await r.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = _rounded_rect_mask(size, size, size // 2)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(img, mask=mask)
        _avatar_cache[key] = out
        return out
    except Exception:
        _avatar_cache[key] = None
        return None


# ---------------------------------------------------------------------------
# API PUBLIQUE
# ---------------------------------------------------------------------------
async def generate_xp_card(member_name: str, avatar_url: str, level: int,
                           xp_total: int, xp_progress: int, xp_required: int) -> Tuple[io.BytesIO, str]:
    avatar = await _fetch_avatar(avatar_url, 100)
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None, partial(_build_xp_card_sync, member_name, avatar, level, xp_progress, xp_required, xp_total)
    )
    return buf, "xp_card.gif"


async def generate_levelup_card(member_name: str, avatar_url: str, old_level: int, new_level: int,
                                xp_total: int, xp_progress: int, xp_required: int) -> Tuple[io.BytesIO, str]:
    avatar = await _fetch_avatar(avatar_url, 100)
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None, partial(_build_levelup_sync, member_name, avatar, old_level, new_level, xp_progress, xp_required)
    )
    return buf, "levelup.gif"


async def generate_topxp_card(guild_name: str, entries: list, xp_to_level_fn: Callable[[int], int]) -> Tuple[io.BytesIO, str]:
    avatars = list(await asyncio.gather(*[
        _fetch_avatar(e.get("avatar_url"), 32) for e in entries[:10]
    ]))
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None, partial(_build_topxp_sync, guild_name, entries[:10], avatars, xp_to_level_fn)
    )
    return buf, "topxp.png"


# ---------------------------------------------------------------------------
# WARMUP
# ---------------------------------------------------------------------------
def warmup_sync() -> None:
    _ensure_fonts()
    for size in (12, 13, 14, 15, 16, 20, 22, 26, 30):
        _font(size, False)
        _font(size, True)

    _load_bg_frames(XP_W, XP_H, MAX_XP_FRAMES)
    _load_bg_frames(LU_W, LU_H, MAX_XP_FRAMES)
    _build_topxp_template()

    logger.info(f"Warmup v3.3 terminé — Max {MAX_XP_FRAMES} frames pour XP")


async def warmup() -> None:
    await asyncio.get_event_loop().run_in_executor(None, warmup_sync)
