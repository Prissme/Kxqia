"""
card_generator.py — Refonte Complète 2026
Priorités : vitesse maximale + rendu visuel premium
- PNG statique (10-30x plus rapide que GIF/WebP animé)
- Cache agressif multi-niveaux
- Composition moderne : glassmorphism, dégradés, typographie soignée
- Rendu async non-bloquant
"""

import asyncio
import io
import logging
import math
import os
import urllib.request
from functools import lru_cache, partial
from pathlib import Path
from typing import Callable, Optional

import aiohttp
from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CHEMINS & CONFIGURATION
# ---------------------------------------------------------------------------
_FONT_DIR = Path(os.getenv("FONT_CACHE_DIR", "/tmp/bot_fonts"))
_FONT_DIR.mkdir(parents=True, exist_ok=True)

_NOTO_PATH  = _FONT_DIR / "NotoSans-Regular.ttf"
_NOTO_BOLD  = _FONT_DIR / "NotoSans-Bold.ttf"

_NOTO_URL      = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Regular.ttf"
_NOTO_BOLD_URL = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Bold.ttf"

# ---------------------------------------------------------------------------
# PALETTE — Thème "Midnight Indigo"
# ---------------------------------------------------------------------------
# Fond carte XP
BG_TOP    = (8,  12,  35)   # bleu nuit profond
BG_BOT    = (18, 22,  58)   # indigo sombre

# Glassmorphism panneau
GLASS     = (255, 255, 255, 18)
GLASS_BD  = (255, 255, 255, 40)

# Accent néon cyan
NEON      = (0,  220, 255)
NEON_DIM  = (0,  180, 210, 80)

# Accent violet pour dégradé barre XP
VIOLET    = (140, 80, 255)

# Textes
TEXT_PRI  = (240, 245, 255)
TEXT_SEC  = (150, 165, 200)
TEXT_MUT  = (90,  105, 140)

# Récompenses
GOLD      = (255, 200,  60)
SILVER    = (185, 195, 215)
BRONZE    = (200, 130,  60)

# Taille carte XP
XP_W, XP_H   = 680, 200
# Taille carte level-up
LU_W, LU_H   = 680, 200
# Taille top XP
TOP_W, TOP_H = 680, 580

# ---------------------------------------------------------------------------
# POLICES
# ---------------------------------------------------------------------------
_fonts_loaded = False
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _dl(url: str, dest: Path) -> bool:
    try:
        req  = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=12).read()
        dest.write_bytes(data)
        return True
    except Exception as e:
        logger.warning("Téléchargement police échoué %s : %s", url, e)
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
    key = ("bold" if bold else "regular", size)
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
# CACHE AVATARS
# ---------------------------------------------------------------------------
_avatar_cache: dict[tuple[str, int], Optional[Image.Image]] = {}


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
        img  = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        out  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(img, mask=mask)
        _avatar_cache[key] = out
        return out
    except Exception as e:
        logger.warning("Avatar fetch failed %s : %s", url, e)
        _avatar_cache[key] = None
        return None


# ---------------------------------------------------------------------------
# HELPERS DESSIN
# ---------------------------------------------------------------------------

def _make_gradient_bg(w: int, h: int, top: tuple, bot: tuple) -> Image.Image:
    """Fond dégradé vertical lisse."""
    img = Image.new("RGB", (w, h))
    for y in range(h):
        t  = y / (h - 1)
        r  = int(top[0] + (bot[0] - top[0]) * t)
        g  = int(top[1] + (bot[1] - top[1]) * t)
        b  = int(top[2] + (bot[2] - top[2]) * t)
        ImageDraw.Draw(img).line([(0, y), (w, y)], fill=(r, g, b))
    return img


def _make_gradient_bar(w: int, h: int, c1: tuple, c2: tuple) -> Image.Image:
    """Dégradé horizontal pour la barre XP."""
    bar = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for x in range(w):
        t = x / max(w - 1, 1)
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        ImageDraw.Draw(bar).line([(x, 0), (x, h)], fill=(r, g, b, 255))
    return bar


def _rounded_rect_mask(w: int, h: int, r: int) -> Image.Image:
    """Masque RGBA pour coins arrondis."""
    mask = Image.new("L", (w, h), 0)
    d    = ImageDraw.Draw(mask)
    d.rounded_rectangle((0, 0, w, h), radius=r, fill=255)
    return mask


def _draw_xp_bar(
    canvas: Image.Image,
    x: int, y: int, w: int, h: int,
    progress: float,
) -> None:
    """Barre XP avec fond, dégradé arrondi et lueur."""
    r = h // 2

    # Fond
    bg_layer = Image.new("RGBA", (w, h), (255, 255, 255, 25))
    mask     = _rounded_rect_mask(w, h, r)
    canvas.paste(Image.new("RGBA", canvas.size, (0, 0, 0, 0)), (0, 0))

    bg_full  = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bg_full.paste(bg_layer, (x, y), mask)
    canvas.alpha_composite(bg_full)

    # Remplissage dégradé
    fill_w = max(r * 2, int(w * max(0.0, min(1.0, progress))))
    if fill_w > 0:
        bar_img  = _make_gradient_bar(fill_w, h, VIOLET, NEON)
        bar_mask = _rounded_rect_mask(fill_w, h, r)
        bar_rgba = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        bar_rgba.paste(bar_img, (x, y), bar_mask)
        canvas.alpha_composite(bar_rgba)

    # Lueur sur le bord droit du fill
    glow_r = h
    gx = x + fill_w - glow_r // 2
    gy = y + h // 2 - glow_r // 2
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d    = ImageDraw.Draw(glow)
    for i in range(glow_r, 0, -1):
        alpha = int(60 * (i / glow_r) ** 2)
        d.ellipse((gx + glow_r - i, gy + glow_r - i,
                   gx + glow_r + i, gy + glow_r + i),
                  fill=(*NEON, alpha))
    canvas.alpha_composite(glow)


def _glass_panel(canvas: Image.Image, x: int, y: int, w: int, h: int, r: int = 18) -> None:
    """Panneau glassmorphism (fond semi-transparent + bordure)."""
    panel = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d     = ImageDraw.Draw(panel)
    d.rounded_rectangle((x, y, x + w, y + h), radius=r, fill=GLASS, outline=GLASS_BD, width=1)
    canvas.alpha_composite(panel)


def _text_shadow(draw: ImageDraw.ImageDraw, xy: tuple, text: str, font, fill: tuple, offset: int = 2):
    ox, oy = xy
    shadow_fill = (0, 0, 0, 160) if len(fill) < 4 else (0, 0, 0, 160)
    # draw shadow (pure draw, no alpha—approximation)
    draw.text((ox + offset, oy + offset), text, font=font, fill=(0, 0, 0))
    draw.text(xy, text, font=font, fill=fill)


def _avatar_with_ring(canvas: Image.Image, avatar: Optional[Image.Image], cx: int, cy: int, av_size: int) -> None:
    """Colle l'avatar centré en (cx, cy) avec anneau néon."""
    ring_r = av_size // 2 + 3
    ring   = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d      = ImageDraw.Draw(ring)
    # halo extérieur diffus
    for i in range(8, 0, -1):
        a = int(40 * (i / 8))
        d.ellipse(
            (cx - ring_r - i, cy - ring_r - i, cx + ring_r + i, cy + ring_r + i),
            outline=(*NEON, a), width=1,
        )
    # anneau net
    d.ellipse((cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
              outline=(*NEON, 220), width=2)
    canvas.alpha_composite(ring)

    if avatar:
        canvas.paste(avatar, (cx - av_size // 2, cy - av_size // 2), avatar)
    else:
        # Placeholder couleur
        ph = Image.new("RGBA", (av_size, av_size), (30, 40, 80, 255))
        mask = _rounded_rect_mask(av_size, av_size, av_size // 2)
        ph_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ph_layer.paste(ph, (cx - av_size // 2, cy - av_size // 2), mask)
        canvas.alpha_composite(ph_layer)


def _level_badge(canvas: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int, level: int) -> None:
    """Badge niveau pill avec dégradé."""
    label = f"LVL {level}"
    f     = _font(14, bold=True)
    bbox  = draw.textbbox((0, 0), label, font=f)
    tw    = bbox[2] - bbox[0]
    bw    = tw + 24
    bh    = 22

    badge = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bd    = ImageDraw.Draw(badge)
    bd.rounded_rectangle((x, y, x + bw, y + bh), radius=bh // 2,
                          fill=(*NEON, 30), outline=(*NEON, 120), width=1)
    canvas.alpha_composite(badge)
    draw.text((x + 12, y + 4), label, font=f, fill=NEON)


def _encode_png(img: Image.Image) -> io.BytesIO:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# CARTE XP
# ---------------------------------------------------------------------------

def _build_xp_card_sync(
    name: str,
    avatar: Optional[Image.Image],
    level: int,
    xp_progress: int,
    xp_required: int,
    xp_total: int,
) -> io.BytesIO:
    W, H = XP_W, XP_H

    # Fond
    bg = _make_gradient_bg(W, H, BG_TOP, BG_BOT).convert("RGBA")

    # Accent arc en haut à gauche
    accent = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    da = ImageDraw.Draw(accent)
    for i in range(60, 0, -1):
        da.ellipse((-i, -i, i * 3, i * 3), outline=(*VIOLET, max(0, i // 2)), width=1)
    bg.alpha_composite(accent)

    # Panneau verre
    PAD = 16
    _glass_panel(bg, PAD, PAD, W - PAD * 2, H - PAD * 2, r=20)

    # Avatar
    AV = 100
    CX = PAD + 20 + AV // 2
    CY = H // 2
    _avatar_with_ring(bg, avatar, CX, CY, AV)

    # Zone texte
    draw = ImageDraw.Draw(bg)
    TX = CX + AV // 2 + 24

    # Nom
    f_name = _font(26, bold=True)
    name_s = name[:22] + ("…" if len(name) > 22 else "")
    draw.text((TX, PAD + 14), name_s, font=f_name, fill=TEXT_PRI)

    # Badge niveau
    bbox_name = draw.textbbox((TX, PAD + 14), name_s, font=f_name)
    badge_x   = bbox_name[2] + 12
    _level_badge(bg, draw, badge_x, PAD + 18, level)

    # XP hint
    f_small = _font(13)
    hint    = f"{xp_progress:,} / {xp_required:,} XP"
    draw.text((TX, PAD + 46), hint, font=f_small, fill=TEXT_MUT)

    # Barre XP
    BAR_X = TX
    BAR_Y = PAD + 74
    BAR_W = W - TX - PAD * 2 - 8
    BAR_H = 10
    ratio  = xp_progress / xp_required if xp_required > 0 else 1.0
    _draw_xp_bar(bg, BAR_X, BAR_Y, BAR_W, BAR_H, ratio)

    # Pourcentage
    pct_txt = f"{int(ratio * 100)}%"
    draw.text((BAR_X + BAR_W + 8, BAR_Y - 1), pct_txt, font=_font(12, bold=True), fill=NEON)

    # Total XP
    draw.text((TX, BAR_Y + BAR_H + 10),
              f"Total : {xp_total:,} XP", font=_font(12), fill=TEXT_SEC)

    # Ligne décorative verticale
    line_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dl         = ImageDraw.Draw(line_layer)
    dl.rectangle((PAD + AV + 36, PAD + 24, PAD + AV + 37, H - PAD - 24),
                 fill=(*NEON, 40))
    bg.alpha_composite(line_layer)

    return _encode_png(bg)


# ---------------------------------------------------------------------------
# CARTE LEVEL-UP
# ---------------------------------------------------------------------------

def _build_levelup_sync(
    name: str,
    avatar: Optional[Image.Image],
    old_level: int,
    new_level: int,
    xp_progress: int,
    xp_required: int,
) -> io.BytesIO:
    W, H = LU_W, LU_H

    # Fond avec accent doré
    bg = _make_gradient_bg(W, H, (10, 8, 30), (25, 18, 60)).convert("RGBA")

    # Halo doré diffus (célébration)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dg   = ImageDraw.Draw(glow)
    for i in range(100, 0, -5):
        a = int(15 * (i / 100))
        dg.ellipse((W // 2 - i * 3, -i, W // 2 + i * 3, i * 2), fill=(*GOLD, a))
    bg.alpha_composite(glow)

    PAD = 16
    _glass_panel(bg, PAD, PAD, W - PAD * 2, H - PAD * 2, r=20)

    # Avatar
    AV = 100
    CX = PAD + 20 + AV // 2
    CY = H // 2
    _avatar_with_ring(bg, avatar, CX, CY, AV)

    draw = ImageDraw.Draw(bg)
    TX   = CX + AV // 2 + 28

    # "LEVEL UP !" — titre
    f_title = _font(30, bold=True)
    draw.text((TX, PAD + 10), "LEVEL UP !", font=f_title, fill=GOLD)

    # Nom
    name_s = name[:22] + ("…" if len(name) > 22 else "")
    draw.text((TX, PAD + 46), name_s, font=_font(20, bold=True), fill=TEXT_PRI)

    # Flèche de niveau
    f_lvl  = _font(16)
    arrow  = f"Niveau {old_level}  →  {new_level}"
    draw.text((TX, PAD + 72), arrow, font=f_lvl, fill=TEXT_SEC)

    # Barre XP
    BAR_X = TX
    BAR_Y = PAD + 100
    BAR_W = W - TX - PAD * 2 - 8
    BAR_H = 10
    ratio  = xp_progress / xp_required if xp_required > 0 else 1.0
    _draw_xp_bar(bg, BAR_X, BAR_Y, BAR_W, BAR_H, ratio)

    draw.text((BAR_X, BAR_Y + BAR_H + 8),
              f"{xp_progress:,} / {xp_required:,} XP", font=_font(12), fill=TEXT_MUT)

    return _encode_png(bg)


# ---------------------------------------------------------------------------
# CARTE TOP XP
# ---------------------------------------------------------------------------

def _build_topxp_sync(
    guild_name: str,
    entries: list[dict],
    avatars: list[Optional[Image.Image]],
    xp_to_level_fn: Callable,
) -> io.BytesIO:
    W, H = TOP_W, TOP_H

    bg = _make_gradient_bg(W, H, BG_TOP, (12, 16, 48)).convert("RGBA")

    # Arrière-plan nuancé — grille subtile
    grid = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dg   = ImageDraw.Draw(grid)
    for x in range(0, W, 40):
        dg.line([(x, 0), (x, H)], fill=(255, 255, 255, 4))
    for y in range(0, H, 40):
        dg.line([(0, y), (W, y)], fill=(255, 255, 255, 4))
    bg.alpha_composite(grid)

    PAD = 14
    _glass_panel(bg, PAD, PAD, W - PAD * 2, H - PAD * 2, r=20)

    draw = ImageDraw.Draw(bg)

    # En-tête
    guild_s = guild_name[:28] + ("…" if len(guild_name) > 28 else "")
    draw.text((PAD + 18, PAD + 14), "CLASSEMENT", font=_font(12), fill=TEXT_MUT)
    draw.text((PAD + 18, PAD + 28), guild_s.upper(), font=_font(22, bold=True), fill=TEXT_PRI)

    # Ligne séparatrice néon
    sep = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds  = ImageDraw.Draw(sep)
    ds.line([(PAD + 18, PAD + 58), (W - PAD - 18, PAD + 58)], fill=(*NEON, 60), width=1)
    bg.alpha_composite(sep)

    ROW_H    = 46
    START_Y  = PAD + 68
    AV_SIZE  = 32
    RANK_COLORS = [GOLD, SILVER, BRONZE]

    for idx, entry in enumerate(entries[:10]):
        ry = START_Y + idx * ROW_H

        # Fond alterné
        if idx % 2 == 0:
            row_bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dr     = ImageDraw.Draw(row_bg)
            dr.rounded_rectangle(
                (PAD + 8, ry, W - PAD - 8, ry + ROW_H - 4), radius=10,
                fill=(255, 255, 255, 8),
            )
            bg.alpha_composite(row_bg)

        # Rank
        rank_col = RANK_COLORS[idx] if idx < 3 else TEXT_MUT
        draw.text((PAD + 16, ry + 12), f"#{idx + 1}", font=_font(15, bold=True), fill=rank_col)

        # Avatar miniature
        av  = avatars[idx] if idx < len(avatars) else None
        av_x = PAD + 52
        av_y = ry + (ROW_H - 4 - AV_SIZE) // 2
        if av:
            # Cercle miniature
            ring = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dr2  = ImageDraw.Draw(ring)
            dr2.ellipse((av_x - 2, av_y - 2, av_x + AV_SIZE + 2, av_y + AV_SIZE + 2),
                        outline=(*rank_col, 140), width=1)
            bg.alpha_composite(ring)
            av_resized = av.resize((AV_SIZE, AV_SIZE), Image.LANCZOS)
            mask       = _rounded_rect_mask(AV_SIZE, AV_SIZE, AV_SIZE // 2)
            av_layer   = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            av_layer.paste(av_resized, (av_x, av_y), mask)
            bg.alpha_composite(av_layer)

        # Nom
        uname   = (entry.get("user_name") or "Inconnu")[:24]
        draw.text((av_x + AV_SIZE + 10, ry + 8), uname,
                  font=_font(15, bold=True), fill=TEXT_PRI)

        # XP + Niveau
        xp_val  = int(entry.get("xp", 0) or 0)
        lv      = xp_to_level_fn(xp_val)
        right_x = W - PAD - 18

        lv_txt  = f"LVL {lv}"
        lv_bbox = draw.textbbox((0, 0), lv_txt, font=_font(13, bold=True))
        lv_w    = lv_bbox[2] - lv_bbox[0]
        draw.text((right_x - lv_w, ry + 8), lv_txt, font=_font(13, bold=True), fill=NEON)

        xp_txt  = f"{xp_val:,} XP"
        xp_bbox = draw.textbbox((0, 0), xp_txt, font=_font(12))
        xp_w    = xp_bbox[2] - xp_bbox[0]
        draw.text((right_x - xp_w, ry + 25), xp_txt, font=_font(12), fill=TEXT_SEC)

    return _encode_png(bg)


# ---------------------------------------------------------------------------
# API PUBLIQUE
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
    entries: list[dict],
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
# WARMUP — pré-charge les polices au démarrage
# ---------------------------------------------------------------------------

def warmup_sync() -> None:
    _ensure_fonts()
    # Pré-charge les tailles les plus utilisées
    for size in (12, 13, 14, 15, 16, 20, 22, 24, 26, 30):
        _font(size, bold=False)
        _font(size, bold=True)
    logger.info("Warmup card_generator terminé — Mode : PNG statique")


async def warmup() -> None:
    await asyncio.get_event_loop().run_in_executor(None, warmup_sync)
