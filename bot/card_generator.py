"""
card_generator.py — Refonte 2026 v5
=====================================================
- /xp et LevelUp : GIF animé avec 18 frames (BICUBIC)
- /topxp : PNG statique avec BackgroundTopXP à la racine
- Police Sekuya (Google Fonts) pour les textes majeurs (LEVEL UP, CLASSEMENT, titres)
- Overlay ultra-sombre (210 alpha) pour éviter que la lune blanche cache le pseudo
- Glow circle supprimé près de la barre XP
- Classement (#X/Y) affiché dans la carte XP
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
MAX_XP_FRAMES = 18  # 18 frames pour /xp et LevelUp
# ================================================================

_ROOT = Path(__file__).parent.parent
_BACKGROUND_TOPPXP_PATH = _ROOT / "BackgroundTopXP.webp"
_FONT_DIR = Path(os.getenv("FONT_CACHE_DIR", "/tmp/bot_fonts"))
_FONT_DIR.mkdir(parents=True, exist_ok=True)

_NOTO_PATH = _FONT_DIR / "NotoSans-Regular.ttf"
_NOTO_BOLD = _FONT_DIR / "NotoSans-Bold.ttf"
_SEKUYA_PATH = _FONT_DIR / "Sekuya-Regular.ttf"
_NOTO_URL = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Regular.ttf"
_NOTO_BOLD_URL = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Bold.ttf"
# Sekuya via Google Fonts static URL
_SEKUYA_URL = "https://fonts.gstatic.com/s/sekuya/v3/6xK_dThFKcWIqifdKh4lgg.ttf"

# Dimensions
XP_W, XP_H = 680, 200
LU_W, LU_H = 680, 200
TOP_W, TOP_H = 680, 580

# ========================= PALETTE =========================
OVERLAY_ALPHA = 210  # Overlay plus sombre pour éviter que la lune cache le pseudo
GLASS = (255, 255, 255, 20)
GLASS_BD = (255, 255, 255, 40)
NEON = (0, 220, 255)
VIOLET = (140, 80, 255)
TEXT_PRI = (255, 255, 255)
TEXT_SEC = (220, 230, 255)
TEXT_MUT = (180, 190, 220)
GOLD = (255, 210, 60)
SILVER = (200, 210, 230)
BRONZE = (220, 150, 80)

# ========================= CACHES =========================
_bg_cache: Dict[Tuple[int, int], Tuple[List[Image.Image], int]] = {}
_topxp_template: Optional[Image.Image] = None
_avatar_cache: Dict[Tuple[str, int], Optional[Image.Image]] = {}
_font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}
_fonts_loaded = False


# ========================= POLICES =========================
def _dl(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            data = response.read()
        dest.write_bytes(data)
        return True
    except Exception as exc:
        logger.warning("Échec téléchargement police %s : %s", url, exc)
        return False


def _ensure_fonts() -> None:
    global _fonts_loaded
    if _fonts_loaded:
        return
    if not _NOTO_PATH.exists():
        _dl(_NOTO_URL, _NOTO_PATH)
    if not _NOTO_BOLD.exists():
        _dl(_NOTO_BOLD_URL, _NOTO_BOLD)
    if not _SEKUYA_PATH.exists():
        _dl(_SEKUYA_URL, _SEKUYA_PATH)
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


def _font_sekuya(size: int) -> ImageFont.FreeTypeFont:
    """Police Sekuya pour les titres majeurs (LEVEL UP!, CLASSEMENT, etc.)"""
    key = ("sekuya", size)
    if key in _font_cache:
        return _font_cache[key]
    _ensure_fonts()
    if _SEKUYA_PATH.exists():
        try:
            f = ImageFont.truetype(str(_SEKUYA_PATH), size)
            _font_cache[key] = f
            return f
        except Exception:
            pass
    # Fallback vers NotoSans-Bold si Sekuya non disponible
    f = _font(size, bold=True)
    _font_cache[key] = f
    return f


# ========================= FOND ANIMÉ =========================
def _make_fallback_frames(w: int, h: int) -> List[Image.Image]:
    img = Image.new("RGBA", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(10 + (18 - 10) * t)
        g = int(14 + (26 - 14) * t)
        b = int(26 + (45 - 26) * t)
        d.line([(0, y), (w, y)], fill=(r, g, b, 255))
    return [img]


def _load_bg_frames(w: int, h: int, max_frames: Optional[int] = None) -> Tuple[List[Image.Image], int]:
    key = (w, h)
    if key in _bg_cache:
        frames, duration = _bg_cache[key]
        if max_frames:
            return frames[:max_frames], duration
        return frames, duration

    _BG_PATH = _ROOT / "GIFKxqia.webp"

    if not _BG_PATH.exists():
        logger.warning("Fond animé introuvable → fallback dégradé")
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


# ========================= TEMPLATES =========================
def _dark_overlay(canvas: Image.Image, alpha: int = OVERLAY_ALPHA) -> None:
    """Applique un overlay sombre renforcé."""
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, alpha))
    canvas.alpha_composite(overlay)


def _rounded_rect_mask(w: int, h: int, r: int) -> Image.Image:
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w, h), radius=r, fill=255)
    return mask


def _glass_panel(canvas: Image.Image, x: int, y: int, w: int, h: int, r: int = 18) -> None:
    panel = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    draw.rounded_rectangle(
        (x, y, x + w, y + h),
        radius=r,
        fill=GLASS,
        outline=GLASS_BD,
        width=1
    )
    canvas.alpha_composite(panel)


def _build_topxp_template() -> Image.Image:
    global _topxp_template
    if _topxp_template is not None:
        return _topxp_template.copy()

    if not _BACKGROUND_TOPPXP_PATH.exists():
        raise FileNotFoundError(f"Fichier BackgroundTopXP introuvable à {_BACKGROUND_TOPPXP_PATH}")

    bg = Image.open(_BACKGROUND_TOPPXP_PATH).convert("RGBA")
    bg = bg.resize((TOP_W, TOP_H), Image.BICUBIC)
    canvas = bg.copy()

    _dark_overlay(canvas, OVERLAY_ALPHA)

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
    # Titre "CLASSEMENT" en Sekuya
    draw.text((PAD + 18, PAD + 12), "CLASSEMENT", font=_font_sekuya(14), fill=TEXT_MUT)

    sep = Image.new("RGBA", (TOP_W, TOP_H), (0, 0, 0, 0))
    ImageDraw.Draw(sep).line(
        [(PAD + 18, PAD + 58), (TOP_W - PAD - 18, PAD + 58)],
        fill=(*NEON, 65),
        width=2
    )
    canvas.alpha_composite(sep)

    _topxp_template = canvas
    return canvas.copy()


# ========================= DRAW FUNCTIONS =========================
def _draw_xp_bar(canvas: Image.Image, x: int, y: int, w: int, h: int, progress: float, pct_label: bool = True) -> None:
    """Barre de XP avec pourcentage — sans glow circle."""
    r = h // 2
    prog = max(0.0, min(1.0, progress))

    # Fond de la barre
    bg = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    bg_mask = _rounded_rect_mask(w, h, r)
    bg.paste(Image.new("RGBA", (w, h), (255, 255, 255, 22)), (x, y), bg_mask)
    canvas.alpha_composite(bg)

    # Barre de progression (dégradé violet → cyan)
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

    # Label % (pas de glow circle)
    if pct_label:
        pct_txt = f"{int(prog * 100)}%"
        f_pct = _font(11, bold=True)
        draw = ImageDraw.Draw(canvas)
        bbox = draw.textbbox((0, 0), pct_txt, font=f_pct)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        tx = x + w - tw - 6
        ty = y + (h - th) // 2
        draw.text((tx + 1, ty + 1), pct_txt, font=f_pct, fill=(0, 0, 0, 200))
        draw.text((tx, ty), pct_txt, font=f_pct, fill=TEXT_PRI)


def _avatar_with_ring(canvas: Image.Image, avatar: Optional[Image.Image], cx: int, cy: int, av_size: int) -> None:
    """Avatar avec anneau lumineux."""
    ring_r = av_size // 2 + 3
    ring = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ring)
    for i in range(8, 0, -1):
        d.ellipse(
            (cx - ring_r - i, cy - ring_r - i, cx + ring_r + i, cy + ring_r + i),
            outline=(*NEON, int(35 * i / 8)),
            width=1
        )
    d.ellipse(
        (cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r),
        outline=(*NEON, 220),
        width=2
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


def _level_badge(canvas: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int, level: int) -> None:
    label = f"LVL {level}"
    f = _font(13, bold=True)
    bbox = draw.textbbox((0, 0), label, font=f)
    tw = bbox[2] - bbox[0]
    bw, bh = tw + 22, 22
    badge = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(badge).rounded_rectangle(
        (x, y, x + bw, y + bh),
        radius=bh // 2,
        fill=(*NEON, 28),
        outline=(*NEON, 110),
        width=1
    )
    canvas.alpha_composite(badge)
    draw.text((x + 11, y + 4), label, font=f, fill=NEON)


def _rank_badge(canvas: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int, rank_text: str) -> None:
    """Badge de classement (#X/Y) dans la carte XP."""
    f = _font(12, bold=True)
    bbox = draw.textbbox((0, 0), rank_text, font=f)
    tw = bbox[2] - bbox[0]
    bw, bh = tw + 18, 20
    badge = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(badge).rounded_rectangle(
        (x, y, x + bw, y + bh),
        radius=bh // 2,
        fill=(255, 210, 60, 30),
        outline=(255, 210, 60, 100),
        width=1
    )
    canvas.alpha_composite(badge)
    draw.text((x + 9, y + 3), rank_text, font=f, fill=GOLD)


# ========================= BUILD FRAMES =========================
def _build_xp_frame(
    template: Image.Image,
    name: str,
    avatar: Optional[Image.Image],
    level: int,
    xp_progress: int,
    xp_required: int,
    xp_total: int,
    rank: Optional[int] = None,
    total_members: Optional[int] = None,
) -> Image.Image:
    """Frame pour la carte XP avec classement."""
    canvas = template.copy()
    PAD = 16
    _glass_panel(canvas, PAD, PAD, XP_W - PAD * 2, XP_H - PAD * 2, r=20)

    AV = 100
    CX = PAD + 20 + AV // 2
    CY = XP_H // 2
    _avatar_with_ring(canvas, avatar, CX, CY, AV)

    draw = ImageDraw.Draw(canvas)
    TX = CX + AV // 2 + 24

    # Nom (NotoSans Bold)
    f_name = _font(24, bold=True)
    name_s = name[:22] + ("…" if len(name) > 22 else "")
    draw.text((TX, PAD + 12), name_s, font=f_name, fill=TEXT_PRI)

    # Badge LVL
    bbox = draw.textbbox((TX, PAD + 12), name_s, font=f_name)
    _level_badge(canvas, draw, bbox[2] + 8, PAD + 16, level)

    # XP info
    draw.text((TX, PAD + 44), f"{xp_progress:,} / {xp_required:,} XP", font=_font(14), fill=TEXT_SEC)

    # Barre XP (sans glow circle)
    BAR_X = TX
    BAR_Y = PAD + 72
    BAR_W = XP_W - PAD - 20 - TX
    ratio = xp_progress / xp_required if xp_required > 0 else 1.0
    _draw_xp_bar(canvas, BAR_X, BAR_Y, BAR_W, 14, ratio, True)

    # Total XP + classement sur la même ligne
    bottom_y = BAR_Y + 22
    total_txt = f"Total : {xp_total:,} XP"
    draw.text((TX, bottom_y), total_txt, font=_font(12), fill=TEXT_MUT)

    # Classement à droite
    if rank is not None:
        rank_txt = f"#{rank}" if total_members is None else f"#{rank}/{total_members}"
        _rank_badge(canvas, draw, XP_W - PAD - 20 - 80, bottom_y - 2, rank_txt)

    # Séparateur vertical
    line = Image.new("RGBA", (XP_W, XP_H), (0, 0, 0, 0))
    ImageDraw.Draw(line).rectangle(
        (PAD + AV + 36, PAD + 24, PAD + AV + 37, XP_H - PAD - 24),
        fill=(*NEON, 40)
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
    """Frame pour la carte LevelUp — titre en Sekuya."""
    canvas = template.copy()
    PAD = 16
    _glass_panel(canvas, PAD, PAD, LU_W - PAD * 2, LU_H - PAD * 2, r=20)

    AV = 100
    CX = PAD + 20 + AV // 2
    CY = LU_H // 2
    _avatar_with_ring(canvas, avatar, CX, CY, AV)

    draw = ImageDraw.Draw(canvas)
    TX = CX + AV // 2 + 28

    # "LEVEL UP !" en Sekuya
    draw.text((TX, PAD + 8), "LEVEL UP !", font=_font_sekuya(30), fill=GOLD)

    name_s = name[:22] + ("…" if len(name) > 22 else "")
    draw.text((TX, PAD + 46), name_s, font=_font(20, bold=True), fill=TEXT_PRI)
    draw.text((TX, PAD + 72), f"Niveau {old_level} → {new_level}", font=_font(16), fill=TEXT_SEC)

    # Barre XP (sans glow circle)
    BAR_X = TX
    BAR_Y = PAD + 100
    BAR_W = LU_W - PAD - 20 - TX
    ratio = xp_progress / xp_required if xp_required > 0 else 1.0
    _draw_xp_bar(canvas, BAR_X, BAR_Y, BAR_W, 14, ratio, True)

    draw.text((TX, BAR_Y + 22), f"{xp_progress:,} / {xp_required:,} XP", font=_font(12), fill=TEXT_SEC)
    return canvas


def _build_topxp_frame(
    template: Image.Image,
    entries: List[Dict],
    avatars: List[Optional[Image.Image]],
    xp_to_level_fn: Callable[[int], int]
) -> Image.Image:
    """Frame statique pour /topxp (PNG) — titre en Sekuya."""
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
                radius=10,
                fill=(255, 255, 255, 11)
            )
            canvas.alpha_composite(row_bg)

        # Numéro de rang
        draw.text((PAD + 16, ry + 11), f"#{idx + 1}", font=_font(16, bold=True), fill=rank_col)

        av = avatars[idx] if idx < len(avatars) else None
        av_x = PAD + 54
        av_y = ry + (ROW_H - 4 - AV_SIZE) // 2

        if av:
            ring = Image.new("RGBA", (TOP_W, TOP_H), (0, 0, 0, 0))
            ImageDraw.Draw(ring).ellipse(
                (av_x - 3, av_y - 3, av_x + AV_SIZE + 3, av_y + AV_SIZE + 3),
                outline=(*rank_col, 160),
                width=2
            )
            canvas.alpha_composite(ring)

            av_r = av.resize((AV_SIZE, AV_SIZE), Image.LANCZOS)
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
        draw.text(
            (rx - (lv_box[2] - lv_box[0]), ry + 7),
            lv_txt,
            font=_font(13, bold=True),
            fill=NEON
        )

        xp_txt = f"{xp_val:,} XP"
        xp_box = draw.textbbox((0, 0), xp_txt, font=_font(12))
        draw.text(
            (rx - (xp_box[2] - xp_box[0]), ry + 26),
            xp_txt,
            font=_font(12),
            fill=TEXT_SEC
        )

    return canvas


# ========================= ENCODAGE =========================
def _encode_output(frames: List[Image.Image], duration: int = 80) -> io.BytesIO:
    buf = io.BytesIO()
    if len(frames) == 1:
        frames[0].convert("RGB").save(buf, format="PNG", optimize=True, quality=95)
    else:
        rgba_frames = [f.convert("RGBA") for f in frames]
        rgba_frames[0].save(
            buf,
            format="GIF",
            save_all=True,
            append_images=rgba_frames[1:],
            loop=0,
            duration=duration,
            optimize=False,
            disposal=2
        )
    buf.seek(0)
    return buf


# ========================= BUILDERS SYNC =========================
def _build_xp_card_sync(
    name: str,
    avatar: Optional[Image.Image],
    level: int,
    xp_progress: int,
    xp_required: int,
    xp_total: int,
    rank: Optional[int] = None,
    total_members: Optional[int] = None,
) -> io.BytesIO:
    templates, duration = _load_bg_frames(XP_W, XP_H, MAX_XP_FRAMES)
    return _encode_output(
        [_build_xp_frame(t, name, avatar, level, xp_progress, xp_required, xp_total, rank, total_members) for t in templates],
        duration
    )


def _build_levelup_sync(
    name: str,
    avatar: Optional[Image.Image],
    old_level: int,
    new_level: int,
    xp_progress: int,
    xp_required: int,
) -> io.BytesIO:
    templates, duration = _load_bg_frames(LU_W, LU_H, MAX_XP_FRAMES)
    return _encode_output(
        [_build_levelup_frame(t, name, avatar, old_level, new_level, xp_progress, xp_required) for t in templates],
        duration
    )


def _build_topxp_sync(
    guild_name: str,
    entries: List[Dict],
    avatars: List[Optional[Image.Image]],
    xp_to_level_fn: Callable[[int], int]
) -> io.BytesIO:
    template = _build_topxp_template()
    return _encode_output([_build_topxp_frame(template, entries, avatars, xp_to_level_fn)])


# ========================= AVATAR FETCH =========================
async def _fetch_avatar(url: Optional[str], size: int) -> Optional[Image.Image]:
    if not url:
        return None
    key = (url, size)
    if key in _avatar_cache:
        return _avatar_cache[key]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=4)) as response:
                if response.status != 200:
                    _avatar_cache[key] = None
                    return None
                data = await response.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img = img.resize((size, size), Image.LANCZOS)
        mask = _rounded_rect_mask(size, size, size // 2)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(img, mask=mask)
        _avatar_cache[key] = out
        return out
    except Exception:
        _avatar_cache[key] = None
        return None


# ========================= API PUBLIQUE =========================
async def generate_xp_card(
    member_name: str,
    avatar_url: str,
    level: int,
    xp_total: int,
    xp_progress: int,
    xp_required: int,
    rank: Optional[int] = None,
    total_members: Optional[int] = None,
) -> Tuple[io.BytesIO, str]:
    """Génère une carte XP animée (GIF avec 18 frames) avec classement optionnel."""
    avatar = await _fetch_avatar(avatar_url, 100)
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None,
        partial(
            _build_xp_card_sync,
            member_name,
            avatar,
            level,
            xp_progress,
            xp_required,
            xp_total,
            rank,
            total_members,
        )
    )
    return buf, "xp_card.gif"


async def generate_levelup_card(
    member_name: str,
    avatar_url: str,
    old_level: int,
    new_level: int,
    xp_total: int,
    xp_progress: int,
    xp_required: int,
) -> Tuple[io.BytesIO, str]:
    """Génère une carte LevelUp animée (GIF avec 18 frames)."""
    avatar = await _fetch_avatar(avatar_url, 100)
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None,
        partial(
            _build_levelup_sync,
            member_name,
            avatar,
            old_level,
            new_level,
            xp_progress,
            xp_required,
        )
    )
    return buf, "levelup.gif"


async def generate_topxp_card(
    guild_name: str,
    entries: List[Dict],
    xp_to_level_fn: Callable[[int], int]
) -> Tuple[io.BytesIO, str]:
    """Génère une carte /topxp statique (PNG avec BackgroundTopXP)."""
    avatars = await asyncio.gather(*[
        _fetch_avatar(e.get("avatar_url"), 32) for e in entries[:10]
    ])
    loop = asyncio.get_event_loop()
    buf = await loop.run_in_executor(
        None,
        partial(
            _build_topxp_sync,
            guild_name,
            entries[:10],
            avatars,
            xp_to_level_fn
        )
    )
    return buf, "topxp.png"


# ========================= WARMUP =========================
def warmup_sync() -> None:
    """Précharge les ressources."""
    _ensure_fonts()
    for size in (12, 13, 14, 15, 16, 20, 22, 24, 26, 30):
        _font(size, False)
        _font(size, True)
    for size in (14, 16, 20, 24, 30):
        _font_sekuya(size)

    _load_bg_frames(XP_W, XP_H, MAX_XP_FRAMES)
    _load_bg_frames(LU_W, LU_H, MAX_XP_FRAMES)
    _build_topxp_template()

    logger.info(f"Warmup terminé — {MAX_XP_FRAMES} frames pour /xp et LevelUp, /topxp en PNG statique, police Sekuya chargée")


async def warmup() -> None:
    """Version asynchrone du warmup."""
    await asyncio.get_event_loop().run_in_executor(None, warmup_sync)
