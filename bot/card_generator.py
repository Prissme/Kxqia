"""
card_generator.py — Refonte 2026 avec fond animé WebP/GIF
==========================================================
Le fichier GIFKxqia.webp doit se trouver à la racine du projet (même niveau que main.py).
Ce module le détecte automatiquement et l'utilise comme fond animé pour toutes les cartes.

Cartes produites :
  - Carte XP           (generate_xp_card)
  - Carte Level-Up     (generate_levelup_card)
  - Classement Top XP  (generate_topxp_card)

Si le fond est animé (plusieurs frames) → GIF animé en sortie.
Si le fond est statique (1 frame)       → PNG optimisé en sortie.

Structure attendue :
  /                   ← racine du projet
    GIFKxqia.webp     ← fond animé
    main.py
    bot/
      card_generator.py  ← ce fichier
"""

import asyncio
import io
import logging
import os
import urllib.request
from functools import partial
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageSequence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CHEMINS
# ---------------------------------------------------------------------------

# Ce fichier est dans bot/, donc parent().parent() = racine du projet
_ROOT    = Path(__file__).parent.parent
_BG_PATH = _ROOT / "GIFKxqia.webp"

_FONT_DIR = Path(os.getenv("FONT_CACHE_DIR", "/tmp/bot_fonts"))
_FONT_DIR.mkdir(parents=True, exist_ok=True)
_NOTO_PATH     = _FONT_DIR / "NotoSans-Regular.ttf"
_NOTO_BOLD     = _FONT_DIR / "NotoSans-Bold.ttf"
_NOTO_URL      = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Regular.ttf"
_NOTO_BOLD_URL = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Bold.ttf"

# ---------------------------------------------------------------------------
# DIMENSIONS DES CARTES
# ---------------------------------------------------------------------------

XP_W,  XP_H  = 680, 200
LU_W,  LU_H  = 680, 200
TOP_W, TOP_H = 680, 580

# ---------------------------------------------------------------------------
# PALETTE — Midnight Indigo (harmonie avec le fond bleu nuit du WebP)
# ---------------------------------------------------------------------------

GLASS    = (255, 255, 255, 30)
GLASS_BD = (255, 255, 255, 55)
NEON     = (0,   220, 255)
VIOLET   = (140,  80, 255)
TEXT_PRI = (240, 245, 255)
TEXT_SEC = (160, 175, 210)
TEXT_MUT = (100, 115, 155)
GOLD     = (255, 200,  60)
SILVER   = (185, 195, 215)
BRONZE   = (200, 130,  60)

# ---------------------------------------------------------------------------
# CACHE GLOBAL
# ---------------------------------------------------------------------------

_bg_frames_cache:   Optional[List[Image.Image]] = None
_bg_duration_cache: int                          = 80
_avatar_cache: dict = {}
_font_cache:   dict = {}
_fonts_loaded       = False


# ---------------------------------------------------------------------------
# POLICES
# ---------------------------------------------------------------------------

def _dl(url: str, dest: Path) -> bool:
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
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
# FOND ANIMÉ — chargement et cache
# ---------------------------------------------------------------------------

def _make_fallback_frames(w: int, h: int) -> List[Image.Image]:
    """Dégradé bleu nuit (1 frame) si GIFKxqia.webp est absent."""
    img = Image.new("RGBA", (w, h))
    d   = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(8  + (18 - 8)  * t)
        g = int(12 + (22 - 12) * t)
        b = int(35 + (58 - 35) * t)
        d.line([(0, y), (w, y)], fill=(r, g, b, 255))
    return [img]


def _load_bg_frames(w: int, h: int) -> Tuple[List[Image.Image], int]:
    """
    Charge GIFKxqia.webp depuis la racine du projet, extrait toutes les frames
    et les redimensionne à (w, h). Résultat mis en cache.

    Retourne (frames, duration_ms_par_frame).
    """
    global _bg_frames_cache, _bg_duration_cache

    # Cache hit (même taille)
    if _bg_frames_cache is not None and _bg_frames_cache[0].size == (w, h):
        return _bg_frames_cache, _bg_duration_cache

    if not _BG_PATH.exists():
        logger.warning(
            "Fond animé introuvable : %s — dégradé de secours utilisé.", _BG_PATH
        )
        _bg_frames_cache  = _make_fallback_frames(w, h)
        _bg_duration_cache = 80
        return _bg_frames_cache, _bg_duration_cache

    try:
        src      = Image.open(_BG_PATH)
        frames:  List[Image.Image] = []
        duration = 80

        for frame in ImageSequence.Iterator(src):
            dur = frame.info.get("duration", 80)
            if dur and dur > 0:
                duration = int(dur)
            resized = frame.convert("RGBA").resize((w, h), Image.LANCZOS)
            frames.append(resized.copy())

        if not frames:
            raise ValueError("Aucune frame dans le WebP.")

        _bg_frames_cache  = frames
        _bg_duration_cache = duration
        logger.info(
            "Fond animé chargé : %s (%d frames, %d ms/frame, taille %dx%d)",
            _BG_PATH.name, len(frames), duration, w, h,
        )
        return frames, duration

    except Exception as exc:
        logger.warning("Erreur chargement fond animé : %s — fallback.", exc)
        _bg_frames_cache  = _make_fallback_frames(w, h)
        _bg_duration_cache = 80
        return _bg_frames_cache, _bg_duration_cache


# ---------------------------------------------------------------------------
# AVATARS
# ---------------------------------------------------------------------------

async def _fetch_avatar(url: Optional[str], size: int) -> Optional[Image.Image]:
    if not url:
        return None
    key = (url, size)
    if key in _avatar_cache:
        return _avatar_cache[key]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status != 200:
                    _avatar_cache[key] = None
                    return None
                data = await resp.read()
        img  = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        out  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(img, mask=mask)
        _avatar_cache[key] = out
        return out
    except Exception as exc:
        logger.warning("Avatar fetch failed %s : %s", url, exc)
        _avatar_cache[key] = None
        return None


# ---------------------------------------------------------------------------
# HELPERS DESSIN
# ---------------------------------------------------------------------------

def _rounded_rect_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=r, fill=255)
    return mask


def _dark_overlay(canvas: Image.Image, alpha: int = 110) -> None:
    """Assombrit le fond pour améliorer la lisibilité du texte."""
    ov = Image.new("RGBA", canvas.size, (0, 0, 0, alpha))
    canvas.alpha_composite(ov)


def _glass_panel(canvas: Image.Image, x: int, y: int, w: int, h: int, r: int = 18) -> None:
    """Panneau glassmorphism semi-transparent par-dessus le fond."""
    panel = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d     = ImageDraw.Draw(panel)
    d.rounded_rectangle(
        (x, y, x + w, y + h), radius=r, fill=GLASS, outline=GLASS_BD, width=1
    )
    canvas.alpha_composite(panel)


def _draw_xp_bar(
    canvas: Image.Image, x: int, y: int, w: int, h: int, progress: float
) -> None:
    r    = h // 2
    prog = max(0.0, min(1.0, progress))

    # Fond de barre
    bg     = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bg_bar = Image.new("RGBA", (w, h), (255, 255, 255, 22))
    bg.paste(bg_bar, (x, y), _rounded_rect_mask(w, h, r))
    canvas.alpha_composite(bg)

    # Remplissage dégradé violet → cyan
    fill_w = max(r * 2, int(w * prog))
    if fill_w > 0:
        bar = Image.new("RGBA", (fill_w, h), (0, 0, 0, 0))
        for px in range(fill_w):
            t  = px / max(fill_w - 1, 1)
            rc = int(VIOLET[0] + (NEON[0] - VIOLET[0]) * t)
            gc = int(VIOLET[1] + (NEON[1] - VIOLET[1]) * t)
            bc = int(VIOLET[2] + (NEON[2] - VIOLET[2]) * t)
            ImageDraw.Draw(bar).line([(px, 0), (px, h)], fill=(rc, gc, bc, 255))
        filled = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        filled.paste(bar, (x, y), _rounded_rect_mask(fill_w, h, r))
        canvas.alpha_composite(filled)

    # Lueur néon sur le bord droit du fill
    glow_r = h + 4
    gx = x + fill_w - glow_r // 2
    gy = y + h // 2 - glow_r // 2
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    dg   = ImageDraw.Draw(glow)
    for i in range(glow_r, 0, -1):
        a = int(55 * (i / glow_r) ** 2)
        dg.ellipse(
            (gx + glow_r - i, gy + glow_r - i, gx + glow_r + i, gy + glow_r + i),
            fill=(*NEON, a),
        )
    canvas.alpha_composite(glow)


def _avatar_with_ring(
    canvas: Image.Image,
    avatar: Optional[Image.Image],
    cx: int, cy: int, av_size: int,
) -> None:
    ring_r = av_size // 2 + 3
    ring   = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d      = ImageDraw.Draw(ring)
    for i in range(8, 0, -1):
        a = int(35 * (i / 8))
        d.ellipse(
            (cx - ring_r - i, cy - ring_r - i, cx + ring_r + i, cy + ring_r + i),
            outline=(*NEON, a), width=1,
        )
    d.ellipse(
        (cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
        outline=(*NEON, 220), width=2,
    )
    canvas.alpha_composite(ring)

    if avatar:
        canvas.paste(avatar, (cx - av_size // 2, cy - av_size // 2), avatar)
    else:
        ph   = Image.new("RGBA", (av_size, av_size), (30, 40, 80, 255))
        mask = _rounded_rect_mask(av_size, av_size, av_size // 2)
        ph_l = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ph_l.paste(ph, (cx - av_size // 2, cy - av_size // 2), mask)
        canvas.alpha_composite(ph_l)


def _level_badge(
    canvas: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int, level: int
) -> None:
    label = f"LVL {level}"
    f     = _font(13, bold=True)
    bbox  = draw.textbbox((0, 0), label, font=f)
    tw    = bbox[2] - bbox[0]
    bw, bh = tw + 22, 22
    badge  = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bd     = ImageDraw.Draw(badge)
    bd.rounded_rectangle(
        (x, y, x + bw, y + bh), radius=bh // 2,
        fill=(*NEON, 28), outline=(*NEON, 110), width=1,
    )
    canvas.alpha_composite(badge)
    draw.text((x + 11, y + 4), label, font=f, fill=NEON)


# ---------------------------------------------------------------------------
# FRAME BUILDERS
# ---------------------------------------------------------------------------

def _build_xp_frame(
    bg_frame: Image.Image,
    name: str,
    avatar: Optional[Image.Image],
    level: int,
    xp_progress: int,
    xp_required: int,
    xp_total: int,
) -> Image.Image:
    W, H   = XP_W, XP_H
    canvas = bg_frame.copy().convert("RGBA")

    _dark_overlay(canvas, 100)

    PAD = 16
    _glass_panel(canvas, PAD, PAD, W - PAD * 2, H - PAD * 2, r=20)

    AV = 100
    CX = PAD + 20 + AV // 2
    CY = H // 2
    _avatar_with_ring(canvas, avatar, CX, CY, AV)

    draw = ImageDraw.Draw(canvas)
    TX   = CX + AV // 2 + 24

    # Nom + badge niveau
    f_name = _font(26, bold=True)
    name_s = name[:22] + ("…" if len(name) > 22 else "")
    draw.text((TX, PAD + 14), name_s, font=f_name, fill=TEXT_PRI)
    bbox = draw.textbbox((TX, PAD + 14), name_s, font=f_name)
    _level_badge(canvas, draw, bbox[2] + 12, PAD + 18, level)

    # Hint XP
    draw.text((TX, PAD + 46), f"{xp_progress:,} / {xp_required:,} XP",
              font=_font(13), fill=TEXT_MUT)

    # Barre XP
    BAR_X = TX
    BAR_Y = PAD + 74
    BAR_W = W - TX - PAD * 2 - 8
    BAR_H = 10
    ratio  = xp_progress / xp_required if xp_required > 0 else 1.0
    _draw_xp_bar(canvas, BAR_X, BAR_Y, BAR_W, BAR_H, ratio)
    draw.text((BAR_X + BAR_W + 8, BAR_Y - 1), f"{int(ratio * 100)}%",
              font=_font(12, bold=True), fill=NEON)

    # Total XP
    draw.text((TX, BAR_Y + BAR_H + 10), f"Total : {xp_total:,} XP",
              font=_font(12), fill=TEXT_SEC)

    # Ligne décorative verticale
    line = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(line).rectangle(
        (PAD + AV + 36, PAD + 24, PAD + AV + 37, H - PAD - 24),
        fill=(*NEON, 40),
    )
    canvas.alpha_composite(line)
    return canvas


def _build_levelup_frame(
    bg_frame: Image.Image,
    name: str,
    avatar: Optional[Image.Image],
    old_level: int,
    new_level: int,
    xp_progress: int,
    xp_required: int,
) -> Image.Image:
    W, H   = LU_W, LU_H
    canvas = bg_frame.copy().convert("RGBA")

    _dark_overlay(canvas, 90)

    # Halo doré de célébration
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dg   = ImageDraw.Draw(glow)
    for i in range(120, 0, -8):
        a = int(12 * (i / 120))
        dg.ellipse((W // 2 - i * 3, -i, W // 2 + i * 3, i * 2), fill=(*GOLD, a))
    canvas.alpha_composite(glow)

    PAD = 16
    _glass_panel(canvas, PAD, PAD, W - PAD * 2, H - PAD * 2, r=20)

    AV = 100
    CX = PAD + 20 + AV // 2
    CY = H // 2
    _avatar_with_ring(canvas, avatar, CX, CY, AV)

    draw = ImageDraw.Draw(canvas)
    TX   = CX + AV // 2 + 28

    draw.text((TX, PAD + 10), "LEVEL UP !", font=_font(30, bold=True), fill=GOLD)
    name_s = name[:22] + ("…" if len(name) > 22 else "")
    draw.text((TX, PAD + 46), name_s, font=_font(20, bold=True), fill=TEXT_PRI)
    draw.text((TX, PAD + 72), f"Niveau {old_level}  →  {new_level}",
              font=_font(16), fill=TEXT_SEC)

    BAR_X = TX
    BAR_Y = PAD + 100
    BAR_W = W - TX - PAD * 2 - 8
    BAR_H = 10
    ratio  = xp_progress / xp_required if xp_required > 0 else 1.0
    _draw_xp_bar(canvas, BAR_X, BAR_Y, BAR_W, BAR_H, ratio)
    draw.text((BAR_X, BAR_Y + BAR_H + 8), f"{xp_progress:,} / {xp_required:,} XP",
              font=_font(12), fill=TEXT_MUT)
    return canvas


def _build_topxp_frame(
    bg_frame: Image.Image,
    guild_name: str,
    entries: list,
    avatars: list,
    xp_to_level_fn: Callable,
) -> Image.Image:
    W, H   = TOP_W, TOP_H
    canvas = bg_frame.copy().convert("RGBA")

    _dark_overlay(canvas, 110)

    # Grille subtile
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dg   = ImageDraw.Draw(grid)
    for x in range(0, W, 40):
        dg.line([(x, 0), (x, H)], fill=(255, 255, 255, 5))
    for y in range(0, H, 40):
        dg.line([(0, y), (W, y)], fill=(255, 255, 255, 5))
    canvas.alpha_composite(grid)

    PAD = 14
    _glass_panel(canvas, PAD, PAD, W - PAD * 2, H - PAD * 2, r=20)

    draw    = ImageDraw.Draw(canvas)
    guild_s = guild_name[:28] + ("…" if len(guild_name) > 28 else "")
    draw.text((PAD + 18, PAD + 14), "CLASSEMENT",    font=_font(12),         fill=TEXT_MUT)
    draw.text((PAD + 18, PAD + 28), guild_s.upper(), font=_font(22, bold=True), fill=TEXT_PRI)

    sep = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sep).line(
        [(PAD + 18, PAD + 58), (W - PAD - 18, PAD + 58)],
        fill=(*NEON, 60), width=1,
    )
    canvas.alpha_composite(sep)

    ROW_H       = 46
    START_Y     = PAD + 68
    AV_SIZE     = 32
    RANK_COLORS = [GOLD, SILVER, BRONZE]

    for idx, entry in enumerate(entries[:10]):
        ry        = START_Y + idx * ROW_H
        rank_col  = RANK_COLORS[idx] if idx < 3 else TEXT_MUT

        # Fond de ligne alterné
        if idx % 2 == 0:
            row_bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(row_bg).rounded_rectangle(
                (PAD + 8, ry, W - PAD - 8, ry + ROW_H - 4),
                radius=10, fill=(255, 255, 255, 10),
            )
            canvas.alpha_composite(row_bg)

        draw.text((PAD + 16, ry + 12), f"#{idx + 1}", font=_font(15, bold=True), fill=rank_col)

        av   = avatars[idx] if idx < len(avatars) else None
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
        draw.text((av_x + AV_SIZE + 10, ry + 8), uname, font=_font(15, bold=True), fill=TEXT_PRI)

        xp_val  = int(entry.get("xp", 0) or 0)
        lv      = xp_to_level_fn(xp_val)
        rx      = W - PAD - 18

        lv_txt  = f"LVL {lv}"
        lv_bbox = draw.textbbox((0, 0), lv_txt, font=_font(13, bold=True))
        draw.text((rx - (lv_bbox[2] - lv_bbox[0]), ry + 8), lv_txt,
                  font=_font(13, bold=True), fill=NEON)

        xp_txt  = f"{xp_val:,} XP"
        xp_bbox = draw.textbbox((0, 0), xp_txt, font=_font(12))
        draw.text((rx - (xp_bbox[2] - xp_bbox[0]), ry + 25), xp_txt,
                  font=_font(12), fill=TEXT_SEC)

    return canvas


# ---------------------------------------------------------------------------
# ENCODAGE FINAL
# ---------------------------------------------------------------------------

def _encode_output(frames: List[Image.Image], duration: int) -> io.BytesIO:
    """
    1 frame  → PNG.
    N frames → GIF animé (boucle infinie).
    """
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
# BUILDERS SYNC (à exécuter dans un executor)
# ---------------------------------------------------------------------------

def _build_xp_card_sync(
    name: str,
    avatar: Optional[Image.Image],
    level: int,
    xp_progress: int,
    xp_required: int,
    xp_total: int,
) -> io.BytesIO:
    bg_frames, duration = _load_bg_frames(XP_W, XP_H)
    out_frames = [
        _build_xp_frame(f, name, avatar, level, xp_progress, xp_required, xp_total)
        for f in bg_frames
    ]
    return _encode_output(out_frames, duration)


def _build_levelup_sync(
    name: str,
    avatar: Optional[Image.Image],
    old_level: int,
    new_level: int,
    xp_progress: int,
    xp_required: int,
) -> io.BytesIO:
    bg_frames, duration = _load_bg_frames(LU_W, LU_H)
    out_frames = [
        _build_levelup_frame(f, name, avatar, old_level, new_level, xp_progress, xp_required)
        for f in bg_frames
    ]
    return _encode_output(out_frames, duration)


def _build_topxp_sync(
    guild_name: str,
    entries: list,
    avatars: list,
    xp_to_level_fn: Callable,
) -> io.BytesIO:
    bg_frames, duration = _load_bg_frames(TOP_W, TOP_H)
    out_frames = [
        _build_topxp_frame(f, guild_name, entries, avatars, xp_to_level_fn)
        for f in bg_frames
    ]
    return _encode_output(out_frames, duration)


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
) -> Optional[io.BytesIO]:
    avatar = await _fetch_avatar(avatar_url, 100)
    loop   = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(_build_xp_card_sync, member_name, avatar, level, xp_progress, xp_required, xp_total),
    )


async def generate_levelup_card(
    member_name: str,
    avatar_url: str,
    old_level: int,
    new_level: int,
    xp_total: int,
    xp_progress: int,
    xp_required: int,
) -> Optional[io.BytesIO]:
    avatar = await _fetch_avatar(avatar_url, 100)
    loop   = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(_build_levelup_sync, member_name, avatar, old_level, new_level, xp_progress, xp_required),
    )


async def generate_topxp_card(
    guild_name: str,
    entries: list,
    xp_to_level_fn: Callable[[int], int],
) -> Optional[io.BytesIO]:
    avatars = list(await asyncio.gather(*[
        _fetch_avatar(e.get("avatar_url"), 32) for e in entries[:10]
    ]))
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        partial(_build_topxp_sync, guild_name, entries[:10], avatars, xp_to_level_fn),
    )


# ---------------------------------------------------------------------------
# WARMUP — pré-charge polices + fond au démarrage du bot
# ---------------------------------------------------------------------------

def warmup_sync() -> None:
    _ensure_fonts()
    for size in (12, 13, 14, 15, 16, 20, 22, 24, 26, 30):
        _font(size, bold=False)
        _font(size, bold=True)
    _load_bg_frames(XP_W, XP_H)   # pré-charge pour la taille XP (partagée avec level-up)
    _load_bg_frames(TOP_W, TOP_H)  # pré-charge pour le top
    logger.info(
        "Warmup card_generator terminé — fond : %s",
        _BG_PATH.name if _BG_PATH.exists() else "dégradé fallback",
    )


async def warmup() -> None:
    await asyncio.get_event_loop().run_in_executor(None, warmup_sync)
