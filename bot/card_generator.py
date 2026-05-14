from __future__ import annotations

import io
import logging
import os
import random
import urllib.request
from pathlib import Path
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PIL
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
# COLORS
# ---------------------------------------------------------------------------
BG_DARK = (10, 12, 25, 255)
BG_CARD = (20, 25, 50, 255)
NEON = (0, 200, 255, 255)
NEON_SOFT = (0, 200, 255, 60)
WHITE = (255, 255, 255, 255)
GREY = (150, 160, 200, 255)
BAR_BG = (40, 45, 70, 255)


# ---------------------------------------------------------------------------
# STARFIELD ANIMATION 🌌
# ---------------------------------------------------------------------------
def _generate_stars(seed=0, count=60, w=620, h=180):
    random.seed(seed)
    return [
        [random.randint(0, w), random.randint(0, h), random.randint(1, 3)]
        for _ in range(count)
    ]


def _draw_starfield(draw, stars, frame_i, speed=1):
    for x, y, r in stars:
        ny = (y + frame_i * speed) % 180
        alpha = 120 + (r * 40)
        draw.ellipse(
            (x, ny, x + r, ny + r),
            fill=(255, 255, 255, alpha),
        )


# ---------------------------------------------------------------------------
# AVATAR
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


# ---------------------------------------------------------------------------
# XP BAR
# ---------------------------------------------------------------------------
def _xp_bar(draw, x, y, w, h, progress):
    draw.rounded_rectangle((x, y, x + w, y + h), 8, fill=BAR_BG)
    filled = int(w * max(0, min(1, progress)))
    if filled > 0:
        draw.rounded_rectangle((x, y, x + filled, y + h), 8, fill=NEON)


# ---------------------------------------------------------------------------
# LEVEL UP FRAMES 🎬
# ---------------------------------------------------------------------------
def _build_levelup_frames(member_name, avatar, old_level, new_level, xp_progress, xp_required, W=620, H=180):
    frames = []
    stars = _generate_stars()

    for i in range(14):
        card = Image.new("RGBA", (W, H), BG_DARK)
        draw = ImageDraw.Draw(card)

        # star background
        _draw_starfield(draw, stars, i)

        # glow pulse
        glow = Image.new("RGBA", card.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)

        pulse = (i / 14)
        gd.ellipse((-80, -80, 300, 200), fill=(0, 200, 255, int(40 + 60 * pulse)))
        glow = glow.filter(ImageFilter.GaussianBlur(40))
        card = Image.alpha_composite(card, glow)

        draw = ImageDraw.Draw(card)
        draw.rounded_rectangle((0, 0, W, H), 20, fill=BG_CARD)

        font_title = _load_font(36)
        font_sub = _load_font(20)
        font_small = _load_font(14)

        TEXT_X = 170

        draw.text((TEXT_X, 25), "LEVEL UP", fill=NEON, font=font_title)
        draw.text((TEXT_X, 70), member_name[:20], fill=WHITE, font=font_sub)
        draw.text((TEXT_X, 100), f"{old_level} → {new_level}", fill=GREY, font=font_small)

        progress = (xp_progress / xp_required) * pulse if xp_required else 0
        _xp_bar(draw, TEXT_X, 130, 350, 12, progress)

        if avatar:
            card.paste(avatar, (30, 35), avatar)

        frames.append(card)

    return frames


# ---------------------------------------------------------------------------
# TOP XP FRAMES 🔥
# ---------------------------------------------------------------------------
def _build_topxp_frames(entries, xp_to_level_fn, guild_name, W=620, H=500):
    frames = []
    stars = _generate_stars(count=90, h=500)

    for i in range(10):
        card = Image.new("RGBA", (W, H), BG_DARK)
        draw = ImageDraw.Draw(card)

        _draw_starfield(draw, stars, i, speed=1)

        draw.rounded_rectangle((0, 0, W, H), 20, fill=BG_CARD)

        font_title = _load_font(28)
        font_name = _load_font(16)

        draw.text((20, 20), "TOP XP", fill=NEON, font=font_title)
        draw.text((20, 55), guild_name[:30], fill=GREY, font=_load_font(12))

        for idx, e in enumerate(entries[:10]):
            y = 100 + idx * 35

            xp = int(e.get("xp", 0))
            level = xp_to_level_fn(xp)

            draw.text((20, y), f"#{idx+1}", fill=WHITE, font=font_name)

            AV = 30
            ax, ay = 60, y - 5

            avatar_url = e.get("avatar_url")
            if avatar_url:
                avatar = None  # lazy (optional optimization)
            else:
                avatar = None

            draw.text((100, y), e.get("user_name", "User")[:18], fill=WHITE, font=font_name)
            draw.text((400, y), f"LV {level}", fill=NEON, font=_load_font(14))
            draw.text((470, y), f"{xp} XP", fill=GREY, font=_load_font(12))

        frames.append(card)

    return frames


# ---------------------------------------------------------------------------
# LEVEL UP CARD 🎬
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

    avatar = await _fetch_avatar(avatar_url, 110)

    frames = _build_levelup_frames(
        member_name,
        avatar,
        old_level,
        new_level,
        xp_progress,
        xp_required,
    )

    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=70,
        loop=0,
        disposal=2,
    )

    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# TOP XP CARD 🔥
# ---------------------------------------------------------------------------
async def generate_topxp_card(
    guild_name: str,
    entries: list[dict],
    xp_to_level_fn,
) -> Optional[io.BytesIO]:

    if not _PIL_AVAILABLE:
        return None

    frames = _build_topxp_frames(entries, xp_to_level_fn, guild_name)

    buf = io.BytesIO()
    frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=90,
        loop=0,
        disposal=2,
    )

    buf.seek(0)
    return buf