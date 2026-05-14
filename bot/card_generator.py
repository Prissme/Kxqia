from __future__ import annotations

import io
import logging
import os
import urllib.request
from pathlib import Path
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pillow
# ---------------------------------------------------------------------------
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.warning("Pillow non installé — cards désactivées.")


# ---------------------------------------------------------------------------
# FONT SEKUYA
# ---------------------------------------------------------------------------
_FONT_CACHE_DIR = Path(os.getenv("FONT_CACHE_DIR", "/tmp/bot_fonts"))
_SEKUYA_PATH = _FONT_CACHE_DIR / "Sekuya.ttf"


def _ensure_font() -> Optional[Path]:
    if not _PIL_AVAILABLE:
        return None

    _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if _SEKUYA_PATH.exists():
        return _SEKUYA_PATH

    try:
        css_url = "https://fonts.googleapis.com/css2?family=Sekuya&display=swap"
        req = urllib.request.Request(css_url, headers={"User-Agent": "Mozilla/5.0"})
        css = urllib.request.urlopen(req).read().decode()

        import re
        match = re.search(r"url\((https://[^)]+\.ttf[^)]*)\)", css)

        if not match:
            return None

        font_url = match.group(1)
        _SEKUYA_PATH.write_bytes(urllib.request.urlopen(font_url).read())

        return _SEKUYA_PATH

    except Exception as e:
        logger.warning(f"Font download failed: {e}")
        return None


def _load_font(size: int):
    path = _ensure_font()

    if path:
        try:
            return ImageFont.truetype(str(path), size)
        except:
            pass

    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# COLORS (NEON STYLE)
# ---------------------------------------------------------------------------
BG_DARK = (10, 12, 25, 255)
BG_CARD = (20, 25, 50, 255)
NEON = (0, 200, 255, 255)
NEON_SOFT = (0, 200, 255, 60)
WHITE = (255, 255, 255, 255)
GREY = (150, 160, 200, 255)
BAR_BG = (40, 45, 70, 255)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

async def _fetch_avatar(url: str, size: int):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.read()

        avatar = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size))

        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)

        out = Image.new("RGBA", (size, size))
        out.paste(avatar, (0, 0), mask)

        return out
    except Exception as e:
        logger.warning(f"Avatar error: {e}")
        return None


def _xp_bar(draw, x, y, w, h, progress):
    draw.rounded_rectangle((x, y, x + w, y + h), 8, fill=BAR_BG)

    filled = int(w * max(0, min(1, progress)))
    if filled > 0:
        draw.rounded_rectangle((x, y, x + filled, y + h), 8, fill=NEON)


def _add_glow(card):
    glow = Image.new("RGBA", card.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-80, -80, 300, 200), fill=NEON_SOFT)
    glow = glow.filter(ImageFilter.GaussianBlur(40))
    return Image.alpha_composite(card, glow)


# ---------------------------------------------------------------------------
# LEVEL UP
# ---------------------------------------------------------------------------

async def generate_levelup_card(
    member_name: str,
    avatar_url: str,
    old_level: int,
    new_level: int,
    xp_total: int,
    xp_progress: int,
    xp_required: int,
) -> Optional[io.BytesIO]:

    if not _PIL_AVAILABLE:
        return None

    W, H = 620, 180
    card = Image.new("RGBA", (W, H), BG_DARK)
    card = _add_glow(card)

    draw = ImageDraw.Draw(card)

    draw.rounded_rectangle((0, 0, W, H), 20, fill=BG_CARD)

    font_title = _load_font(36)
    font_sub = _load_font(20)
    font_small = _load_font(14)

    TEXT_X = 170

    draw.text((TEXT_X, 25), "LEVEL UP", fill=NEON, font=font_title)
    draw.text((TEXT_X, 70), member_name[:20], fill=WHITE, font=font_sub)
    draw.text((TEXT_X, 100), f"{old_level} → {new_level}", fill=GREY, font=font_small)

    progress = xp_progress / xp_required if xp_required else 0
    _xp_bar(draw, TEXT_X, 130, 350, 12, progress)

    draw.text((TEXT_X, 145), f"{xp_progress}/{xp_required} XP", fill=GREY, font=_load_font(12))

    avatar = await _fetch_avatar(avatar_url, 110)
    if avatar:
        card.paste(avatar, (30, 35), avatar)

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)

    return buf


# ---------------------------------------------------------------------------
# LEADERBOARD AVEC AVATARS 🔥
# ---------------------------------------------------------------------------

async def generate_topxp_card(
    guild_name: str,
    entries: list[dict],
    xp_to_level_fn,
) -> Optional[io.BytesIO]:

    if not _PIL_AVAILABLE:
        return None

    ROW = 60
    H = 100 + ROW * len(entries[:10])
    W = 620

    card = Image.new("RGBA", (W, H), BG_DARK)
    card = _add_glow(card)

    draw = ImageDraw.Draw(card)

    draw.rounded_rectangle((0, 0, W, H), 20, fill=BG_CARD)

    font_title = _load_font(26)
    font_name = _load_font(16)

    draw.text((20, 20), "TOP XP", fill=NEON, font=font_title)
    draw.text((20, 55), guild_name[:30], fill=GREY, font=_load_font(12))

    for i, e in enumerate(entries[:10]):
        y = 100 + i * ROW

        xp = int(e.get("xp", 0))
        level = xp_to_level_fn(xp)

        # Rank
        draw.text((20, y), f"#{i+1}", fill=WHITE, font=font_name)

        # Avatar
        AV_SIZE = 40
        av_x = 70
        av_y = y - 5

        avatar_url = e.get("avatar_url")

        if avatar_url:
            avatar = await _fetch_avatar(avatar_url, AV_SIZE)
            if avatar:
                card.paste(avatar, (av_x, av_y), avatar)
        else:
            draw.ellipse((av_x, av_y, av_x + AV_SIZE, av_y + AV_SIZE), fill=(60, 70, 120))

        # Name
        draw.text((av_x + 55, y), e.get("user_name", "User")[:18], fill=WHITE, font=font_name)

        # Level
        draw.text((400, y), f"LV {level}", fill=NEON, font=_load_font(14))

        # XP
        draw.text((470, y), f"{xp} XP", fill=GREY, font=_load_font(12))

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)

    return buf