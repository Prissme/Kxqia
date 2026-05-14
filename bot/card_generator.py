"""
Modern Image Cards Generator (Neon / Gaming Style)
- Level-up card
- Leaderboard card
Style inspiré : néon bleu / glow / propre (type ton image)
"""

from __future__ import annotations

import io
import os
import logging
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
    logger.warning("Pillow non installé")

# ---------------------------------------------------------------------------
# FONT (SEKUYA CLEAN)
# ---------------------------------------------------------------------------
FONT_DIR = Path("/tmp/fonts")
FONT_PATH = FONT_DIR / "Sekuya.ttf"


def ensure_font():
    if not _PIL_AVAILABLE:
        return None

    FONT_DIR.mkdir(parents=True, exist_ok=True)

    if FONT_PATH.exists():
        return FONT_PATH

    try:
        css_url = "https://fonts.googleapis.com/css2?family=Sekuya&display=swap"

        req = urllib.request.Request(css_url, headers={
            "User-Agent": "Mozilla/5.0"
        })

        css = urllib.request.urlopen(req).read().decode()

        import re
        match = re.search(r"url\((https://[^)]+\.ttf[^)]*)\)", css)

        if not match:
            return None

        font_url = match.group(1)

        FONT_PATH.write_bytes(urllib.request.urlopen(font_url).read())
        return FONT_PATH

    except Exception as e:
        logger.warning(f"Font download failed: {e}")
        return None


def load_font(size):
    path = ensure_font()

    if path:
        try:
            return ImageFont.truetype(str(path), size)
        except:
            pass

    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# COLORS (NEON STYLE)
# ---------------------------------------------------------------------------
BG = (8, 10, 20)
CARD = (20, 25, 45)
NEON = (0, 200, 255)
NEON_SOFT = (0, 200, 255, 80)
WHITE = (255, 255, 255)
GREY = (140, 150, 180)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

async def fetch_avatar(url, size):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.read()

        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img = img.resize((size, size))

        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)

        out = Image.new("RGBA", (size, size))
        out.paste(img, (0, 0), mask)

        return out
    except:
        return None


def neon_glow(base, color=(0, 200, 255), radius=25):
    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((-50, -50, 300, 200), fill=(*color, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(radius))
    return Image.alpha_composite(base, glow)


# ---------------------------------------------------------------------------
# LEVEL UP CARD
# ---------------------------------------------------------------------------

async def generate_levelup_card(
    username: str,
    avatar_url: str,
    old_level: int,
    new_level: int,
    xp: int,
    xp_required: int
):
    if not _PIL_AVAILABLE:
        return None

    W, H = 700, 220

    img = Image.new("RGBA", (W, H), BG)
    img = neon_glow(img)

    draw = ImageDraw.Draw(img)

    # Card
    draw.rounded_rectangle((0, 0, W, H), 25, fill=CARD)

    # Fonts
    title_f = load_font(50)
    name_f = load_font(28)
    small_f = load_font(18)

    # TEXT
    draw.text((200, 30), "LEVEL UP", font=title_f, fill=NEON)

    draw.text((200, 95), username, font=name_f, fill=WHITE)

    draw.text((200, 130), f"{old_level} → {new_level}", font=small_f, fill=GREY)

    # BAR
    progress = xp / xp_required if xp_required else 0
    bar_w = int(350 * progress)

    draw.rectangle((200, 170, 550, 185), fill=(40, 45, 70))
    draw.rectangle((200, 170, 200 + bar_w, 185), fill=NEON)

    # Avatar
    avatar = await fetch_avatar(avatar_url, 120)
    if avatar:
        img.paste(avatar, (50, 50), avatar)

    # EXPORT
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return buf


# ---------------------------------------------------------------------------
# LEADERBOARD
# ---------------------------------------------------------------------------

async def generate_leaderboard(entries):
    if not _PIL_AVAILABLE:
        return None

    W = 700
    ROW = 70
    H = 100 + ROW * len(entries)

    img = Image.new("RGBA", (W, H), BG)
    img = neon_glow(img)

    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle((0, 0, W, H), 25, fill=CARD)

    title_f = load_font(40)
    name_f = load_font(22)
    small_f = load_font(16)

    draw.text((30, 20), "TOP PLAYERS", font=title_f, fill=NEON)

    for i, e in enumerate(entries):
        y = 100 + i * ROW

        draw.text((30, y), f"#{i+1}", font=name_f, fill=WHITE)
        draw.text((100, y), e["name"], font=name_f, fill=WHITE)
        draw.text((500, y), f"{e['xp']} XP", font=small_f, fill=GREY)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    return buf