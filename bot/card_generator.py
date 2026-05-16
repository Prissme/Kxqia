"""
card_generator.py — Refonte 2026 v3.1 (Optimisé sans perte d'animation)
=====================================================
Améliorations v3.1 :
  - Templates pré-calculés (fond + dark overlay)
  - Meilleure performance tout en gardant TOUTES les frames
  - Aucune perte de qualité ni d'animation
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

# ---------------------------------------------------------------------------
# CHEMINS
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent
_BG_PATH = _ROOT / "GIFKxqia.webp"
_FONT_DIR = Path(os.getenv("FONT_CACHE_DIR", "/tmp/bot_fonts"))
_FONT_DIR.mkdir(parents=True, exist_ok=True)

_NOTO_PATH = _FONT_DIR / "NotoSans-Regular.ttf"
_NOTO_BOLD = _FONT_DIR / "NotoSans-Bold.ttf"
_NOTO_URL = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Regular.ttf"
_NOTO_BOLD_URL = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Bold.ttf"

# ---------------------------------------------------------------------------
# DIMENSIONS
# ---------------------------------------------------------------------------
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
# FOND ANIMÉ + TEMPLATES
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
        return (frames[:max_frames] if max_frames else frames, duration)

    if not _BG_PATH.exists():
        logger.warning("Fond animé introuvable : %s — dégradé utilisé.", _BG_PATH)
        result = (_make_fallback_frames(w, h), 80)
        _bg_cache[key] = result
        return result

    try:
        src = Image.open(_BG_PATH)
        frames: List[Image.Image] = []
        duration = 80
        for frame in ImageSequence.Iterator(src):
            dur = frame.info.get("duration", 80)
            if dur and dur > 0:
                duration = int(dur)
            resized = frame.convert("RGBA").resize((w, h), Image.LANCZOS)
            frames.append(resized.copy())

        logger.info("Fond chargé : %s → %dx%d (%d frames, %dms/frame)",
                    _BG_PATH.name, w, h, len(frames), duration)
        _bg_cache[key] = (frames, duration)
        return (frames[:max_frames] if max_frames else frames, duration)

    except Exception as exc:
        logger.warning("Erreur chargement fond (%s) → fallback.", exc)
        result = (_make_fallback_frames(w, h), 80)
        _bg_cache[key] = result
        return result


def _get_templates(w: int, h: int, dark_alpha: int = 100) -> Tuple[List[Image.Image], int]:
    key = (w, h)
    if key in _template_cache:
        return _template_cache[key]

    bg_frames, duration = _load_bg_frames(w, h)
    templates = [frame.copy().convert("RGBA") for frame in bg_frames]
    for t in templates:
        _dark_overlay(t, dark_alpha)

    _template_cache[key] = (templates, duration)
    return _template_cache[key]


# ---------------------------------------------------------------------------
# HELPERS DESSIN
# ---------------------------------------------------------------------------
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


def _draw_xp_bar(
    canvas: Image.Image,
    x: int, y: int, w: int, h: int,
    progress: float,
    pct_label: bool = True,
) -> None:
    r = h // 2
    prog = max(0.0, min(1.0, progress))
    bg = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bg.paste(
        Image.new("RGBA", (w, h), (255, 255, 255, 22)),
        (x, y), _rounded_rect_mask(w, h, r),
    )
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
        dg.ellipse(
            (gx + glow_r - i, gy + glow_r - i, gx + glow_r + i, gy + glow_r + i),
            fill=(*NEON, a),
        )
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


def _avatar_with_ring(
    canvas: Image.Image,
    avatar: Optional[Image.Image],
    cx: int, cy: int, av_size: int,
) -> None:
    ring_r = av_size // 2 + 3
    ring = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)
    for i in range(8, 0, -1):
        d.ellipse(
            (cx - ring_r - i, cy - ring_r - i, cx + ring_r + i, cy + ring_r + i),
            outline=(*NEON, int(35 * i / 8)), width=1,
        )
    d.ellipse(
        (cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
        outline=(*NEON, 220), width=2,
    )
    canvas.alpha_composite(ring)

    if avatar:
        canvas.paste(avatar, (cx - av_size // 2, cy - av_size // 2), avatar)
    else:
        ph = Image.new("RGBA", (av_size, av_size), (30, 40, 80, 255))
        mask = _rounded_rect_mask(av_size, av_size, av_size // 2)
        ph_l = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ph_l.paste(ph, (cx - av_size // 2, cy - av_size // 2), mask)
        canvas.alpha_composite(ph_l)


def _level_badge(
    canvas: Image.Image, draw: ImageDraw.ImageDraw,
    x: int, y: int, level: int,
) -> None:
    label = f"LVL {level}"
    f = _font(13, bold=True)
    bbox = draw.textbbox((0, 0), label, font=f)
    tw = bbox[2] - bbox[0]
    bw, bh = tw + 22, 22
    badge = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(badge).rounded_rectangle(
        (x, y, x + bw, y + bh), radius=bh // 2,
        fill=(*NEON, 28), outline=(*NEON, 110), width=1,
    )
    canvas.alpha_composite(badge)
    draw.text((x + 11, y + 4), label, font=f, fill=NEON)


# ---------------------------------------------------------------------------
# BUILD FRAMES
# ---------------------------------------------------------------------------
def _build_xp_frame(
    template: Image.Image,
    name: str,
    avatar: Optional[Image.Image],
    level: int,
    xp_progress: int,
    xp_required: int,
    xp_total: int,
) -> Image.Image:
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

    draw.text((TX, PAD + 48), f"{xp_progress:,} / {xp_required:,} XP",
              font=_font(15), fill=TEXT_SEC)

    BAR_X = TX
    BAR_Y = PAD + 76
    BAR_W = XP_W - PAD - 20 - TX
    BAR_H = 14
    ratio = xp_progress / xp_required if xp_required > 0 else 1.0
    _draw_xp_bar(canvas, BAR_X, BAR_Y, BAR_W, BAR_H, ratio, pct_label=True)

    draw.text((TX, BAR_Y + BAR_H + 8), f"Total : {xp_total:,} XP",
              font=_font(13), fill=TEXT_MUT)

    # Ligne verticale
    line = Image.new("RGBA", (XP_W, XP_H), (0, 0, 0, 0))
    ImageDraw.Draw(line).rectangle(
        (PAD + AV + 36, PAD + 24, PAD + AV + 37, XP_H - PAD - 24),
        fill=(*NEON, 40),
    )
    canvas.alpha_composite(line)
    return canvas


def _build_levelup_frame(
    template: Image.Image,
    name: str,
    avatar: Optional[Image.Image],
    old_level: int,
    new_level: int,
    xp_progress: int,
    xp_required: int,
) -> Image.Image:
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
    draw.text((TX, PAD + 72), f"Niveau {old_level} → {new_level}",
              font=_font(16), fill=TEXT_SEC)

    BAR_X = TX
    BAR_Y = PAD + 102
    BAR_W = LU_W - PAD - 20 - TX
    BAR_H = 14
    ratio = xp_progress / xp_required if xp_required > 0 else 1.0
    _draw_xp_bar(canvas, BAR_X, BAR_Y, BAR_W, BAR_H, ratio, pct_label=True)

    draw.text((TX, BAR_Y + BAR_H + 6),
              f"{xp_progress:,} / {xp_required:,} XP", font=_font(13), fill=TEXT_SEC)
    return canvas


def _build_topxp_frame(
    bg_frame: Image.Image,
    guild_name: str,
    entries: list,
    avatars: list,
    xp_to_level_fn: Callable,
) -> Image.Image:
    W, H = TOP_W, TOP_H
    canvas = bg_frame.copy().convert("RGBA")
    _dark_overlay(canvas, 110)

    # Grille subtile
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dg = ImageDraw.Draw(grid)
    for x in range(0, W, 40):
        dg.line([(x, 0), (x, H)], fill=(255, 255, 255, 5))
    for y in range(0, H, 40):
        dg.line([(0, y), (W, y)], fill=(255, 255, 255, 5))
    canvas.alpha_composite(grid)

    PAD = 14
    _glass_panel(canvas, PAD, PAD, W - PAD * 2, H - PAD * 2, r=20)

    draw = ImageDraw.Draw(canvas)
    guild_s = guild_name[:28] + ("…" if len(guild_name) > 28 else "")
    draw.text((PAD + 18, PAD + 14), "CLASSEMENT", font=_font(12), fill=TEXT_MUT)
    draw.text((PAD + 18, PAD + 28), guild_s.upper(), font=_font(22, bold=True), fill=TEXT_PRI)

    # Séparateur
    sep = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sep).line(
        [(PAD + 18, PAD + 58), (W - PAD - 18, PAD + 58)],
        fill=(*NEON, 60), width=1,
    )
    canvas.alpha_composite(sep)

    ROW_H = 46
    START_Y = PAD + 68
    AV_SIZE = 32
    RANK_COLORS = [GOLD, SILVER, BRONZE]

    for idx, entry in enumerate(entries[:10]):
        ry = START_Y + idx * ROW_H
        rank_col = RANK_COLORS[idx] if idx < 3 else TEXT_MUT

        if idx % 2 == 0:
            row_bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(row_bg).rounded_rectangle(
                (PAD + 8, ry, W - PAD - 8, ry + ROW_H - 4),
                radius=10, fill=(255, 255, 255, 10),
            )
            canvas.alpha_composite(row_bg)

        draw.text((PAD + 16, ry + 12), f"#{idx + 1}", font=_font(15, bold=True), fill=rank_col)

        av = avatars[idx] if idx < len(avatars) else None
        av_x = PAD + 52
        av_y = ry + (ROW_H - 4 - AV_SIZE) // 2

        if av:
            ring2 = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(ring2).ellipse(
                (av_x - 2, av_y - 2, av_x + AV_SIZE + 2, av_y + AV_SIZE + 2),
                outline=(*rank_col, 140), width=1,
            )
            canvas.alpha_composite(ring2)

            av_r = av.resize((AV_SIZE, AV_SIZE), Image.LANCZOS)
            mask = _rounded_rect_mask(AV_SIZE, AV_SIZE, AV_SIZE // 2)
            av_l = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            av_l.paste(av_r, (av_x, av_y), mask)
            canvas.alpha_composite(av_l)

        uname = (entry.get("user_name") or "Inconnu")[:24]
        draw.text((av_x + AV_SIZE + 10, ry + 8), uname,
                  font=_font(15, bold=True), fill=TEXT_PRI)

        xp_val = int(entry.get("xp", 0) or 0)
        lv = xp_to_level_fn(xp_val)
        rx = W - PAD - 18

        lv_txt = f"LVL {lv}"
        lv_b = draw.textbbox((0, 0), lv_txt, font=_font(13, bold=True))
        draw.text((rx - (lv_b[2] - lv_b[0]), ry + 8), lv_txt,
                  font=_font(13, bold=True), fill=NEON)

        xp_txt = f"{xp_val:,} XP"
        xp_b = draw.textbbox((0, 0), xp_txt, font=_font(12))
        draw.text((rx - (xp_b[2] - xp_b[0]), ry + 25), xp_txt,
                  font=_font(12), fill=TEXT_SEC)

    return canvas


# ---------------------------------------------------------------------------
# ENCODAGE
# ---------------------------------------------------------------------------
def _encode_output(frames: List[Image.Image], duration: int) -> io.BytesIO:
    buf = io.BytesIO()
    if len(frames) == 1:
        frames[0].convert("RGB").save(buf, format="PNG", optimize=True)
    else:
        rgba = [f.convert("RGBA") for f in frames]
        rgba[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=rgba[1:],
            loop=0,
            duration=duration,
            optimize=False,
            disposal=2,
        )
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# BUILDERS SYNC
# ---------------------------------------------------------------------------
def _build_xp_card_sync(
    name: str, avatar: Optional[Image.Image],
    level: int, xp_progress: int, xp_required: int, xp_total: int,
) -> io.BytesIO:
    templates, duration = _get_templates(XP_W, XP_H, dark_alpha=100)
    return _encode_output(
        [_build_xp_frame(t, name, avatar, level, xp_progress, xp_required, xp_total)
         for t in templates],
        duration,
    )


def _build_levelup_sync(
    name: str, avatar: Optional[Image.Image],
    old_level: int, new_level: int, xp_progress: int, xp_required: int,
) -> io.BytesIO:
    templates, duration = _get_templates(LU_W, LU_H, dark_alpha=90)
    return _encode_output(
        [_build_levelup_frame(t, name, avatar, old_level, new_level, xp_progress, xp_required)
         for t in templates],
        duration,
    )


def _build_topxp_sync(
    guild_name: str, entries: list, avatars: list, xp_to_level_fn: Callable,
) -> io.BytesIO:
    bg_frames, duration = _load_bg_frames(TOP_W, TOP_H, max_frames=1)
    return _encode_output(
        [_build_topxp_frame(bg_frames[0], guild_name, entries, avatars, xp_to_level_fn)],
        duration,
    )


# ---------------------------------------------------------------------------
# API PUBLIQUE ASYNC
# ---------------------------------------------------------------------------
async def generate_xp_card(
    member_name: str,
    avatar_url: str,
    level: int,
    xp_total: int,
    xp_progress: int,
    xp_required: int,
) -> Tuple[io.BytesIO, str]:
    avatar = await _fetch_avatar(avatar_url, 100)
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None,
        partial(_build_xp_card_sync, member_name, avatar, level, xp_progress, xp_required, xp_total),
    )
    fname = "xp_card.gif"
    return buf, fname


async def generate_levelup_card(
    member_name: str,
    avatar_url: str,
    old_level: int,
    new_level: int,
    xp_total: int,
    xp_progress: int,
    xp_required: int,
) -> Tuple[io.BytesIO, str]:
    avatar = await _fetch_avatar(avatar_url, 100)
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None,
        partial(_build_levelup_sync, member_name, avatar, old_level, new_level, xp_progress, xp_required),
    )
    fname = "levelup.gif"
    return buf, fname


async def generate_topxp_card(
    guild_name: str,
    entries: list,
    xp_to_level_fn: Callable[[int], int],
) -> Tuple[io.BytesIO, str]:
    avatars = list(await asyncio.gather(*[
        _fetch_avatar(e.get("avatar_url"), 32) for e in entries[:10]
    ]))
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None,
        partial(_build_topxp_sync, guild_name, entries[:10], avatars, xp_to_level_fn),
    )
    return buf, "topxp.png"


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
    except Exception as exc:
        logger.warning("Avatar fetch failed %s : %s", url, exc)
        _avatar_cache[key] = None
        return None


# ---------------------------------------------------------------------------
# WARMUP
# ---------------------------------------------------------------------------
def warmup_sync() -> None:
    _ensure_fonts()
    for size in (12, 13, 14, 15, 16, 20, 22, 26, 30):
        _font(size, bold=False)
        _font(size, bold=True)

    _get_templates(XP_W, XP_H)
    _get_templates(LU_W, LU_H)

    logger.info("Warmup card_generator v3.1 OK — templates prêts")


async def warmup() -> None:
    await asyncio.get_event_loop().run_in_executor(None, warmup_sync)
