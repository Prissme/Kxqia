# card_generator.py — VERSION OPTIMISÉE (COMPAT API + LOW MEMORY)
# Drop-in replacement : même API que ton ancien fichier

import asyncio
import io
import logging
from functools import partial
from typing import Callable, Optional

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageFilter

logger = logging.getLogger(__name__)

# ===================== CONFIG =====================
WIDTH_CARD = 620
HEIGHT_CARD = 200
WIDTH_TOP = 620
HEIGHT_TOP = 560
FORMAT = "PNG"  # 🔥 SAFE pour mémoire

# ===================== CACHE LIGHT =====================
_font_cache = {}
_avatar_cache = {}

# ===================== FONTS =====================
def _load_font(size: int):
    if size in _font_cache:
        return _font_cache[size]
    try:
        font = ImageFont.truetype("arial.ttf", size)
    except:
        font = ImageFont.load_default()
    _font_cache[size] = font
    return font

# ===================== AVATAR =====================
async def _fetch_avatar(url: Optional[str], size: int):
    if not url:
        return None
    key = (url, size)
    if key in _avatar_cache:
        return _avatar_cache[key]
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.read()
        img = Image.open(io.BytesIO(data)).convert("RGBA")
        img = img.resize((size, size))
        _avatar_cache[key] = img
        return img
    except:
        return None

# ===================== DRAW =====================
def _draw_bar(draw, x, y, w, h, progress):
    draw.rectangle((x, y, x+w, y+h), fill=(40, 40, 60))
    draw.rectangle((x, y, x+int(w*progress), y+h), fill=(0, 200, 255))

# ===================== BUILD XP CARD =====================
def _build_xp_card(member_name, avatar, level, xp_progress, xp_required, xp_total):
    img = Image.new("RGB", (WIDTH_CARD, HEIGHT_CARD), (15, 20, 40))
    draw = ImageDraw.Draw(img)

    font_big = _load_font(28)
    font_small = _load_font(16)

    if avatar:
        img.paste(avatar, (20, 40))

    draw.text((160, 30), member_name, font=font_big, fill=(255,255,255))
    draw.text((160, 70), f"LEVEL {level}", font=font_small, fill=(0,200,255))

    ratio = xp_progress / xp_required if xp_required else 1
    _draw_bar(draw, 160, 110, 400, 20, ratio)

    draw.text((160, 140), f"{xp_progress}/{xp_required} XP", font=font_small, fill=(200,200,200))

    return img

# ===================== BUILD LEVEL UP =====================
def _build_levelup(member_name, avatar, old_level, new_level, xp_progress, xp_required):
    img = Image.new("RGB", (WIDTH_CARD, HEIGHT_CARD), (15, 20, 40))
    draw = ImageDraw.Draw(img)

    font_big = _load_font(28)
    font_small = _load_font(16)

    if avatar:
        img.paste(avatar, (20, 40))

    draw.text((160, 30), "LEVEL UP!", font=font_big, fill=(0,200,255))
    draw.text((160, 70), member_name, font=font_small, fill=(255,255,255))
    draw.text((160, 100), f"{old_level} → {new_level}", font=font_small, fill=(200,200,200))

    ratio = xp_progress / xp_required if xp_required else 1
    _draw_bar(draw, 160, 130, 400, 15, ratio)

    return img

# ===================== BUILD TOP =====================
def _build_top(guild_name, entries, avatars, xp_to_level_fn):
    img = Image.new("RGB", (WIDTH_TOP, HEIGHT_TOP), (15, 20, 40))
    draw = ImageDraw.Draw(img)

    font_title = _load_font(24)
    font_row = _load_font(16)

    draw.text((20, 20), f"TOP {guild_name}", font=font_title, fill=(0,200,255))

    y = 80
    for i, e in enumerate(entries[:10]):
        name = e.get("user_name", "?")
        xp = e.get("xp", 0)
        lvl = xp_to_level_fn(xp)

        av = avatars[i] if i < len(avatars) else None
        if av:
            img.paste(av, (20, y))

        draw.text((60, y), f"#{i+1} {name}", font=font_row, fill=(255,255,255))
        draw.text((400, y), f"LVL {lvl}", font=font_row, fill=(0,200,255))
        draw.text((480, y), f"{xp}", font=font_row, fill=(200,200,200))

        y += 45

    return img

# ===================== ENCODE =====================
def _encode(img):
    buf = io.BytesIO()
    img = img.filter(ImageFilter.SHARPEN)
    img.save(buf, format=FORMAT)
    buf.seek(0)
    return buf

# ===================== PUBLIC API (COMPATIBLE) =====================
async def generate_xp_card(member_name, avatar_url, level, xp_total, xp_progress, xp_required):
    avatar = await _fetch_avatar(avatar_url, 100)
    loop = asyncio.get_event_loop()
    img = await loop.run_in_executor(
        None,
        partial(_build_xp_card, member_name, avatar, level, xp_progress, xp_required, xp_total),
    )
    return await loop.run_in_executor(None, partial(_encode, img))

async def generate_levelup_card(member_name, avatar_url, old_level, new_level, xp_total, xp_progress, xp_required):
    avatar = await _fetch_avatar(avatar_url, 100)
    loop = asyncio.get_event_loop()
    img = await loop.run_in_executor(
        None,
        partial(_build_levelup, member_name, avatar, old_level, new_level, xp_progress, xp_required),
    )
    return await loop.run_in_executor(None, partial(_encode, img))

async def generate_topxp_card(guild_name, entries, xp_to_level_fn):
    avatars = await asyncio.gather(*[_fetch_avatar(e.get("avatar_url"), 30) for e in entries[:10]])
    loop = asyncio.get_event_loop()
    img = await loop.run_in_executor(
        None,
        partial(_build_top, guild_name, entries, avatars, xp_to_level_fn),
    )
    return await loop.run_in_executor(None, partial(_encode, img))

# ===================== CACHE CONTROL =====================
def clear_caches():
    _avatar_cache.clear()
    if len(_font_cache) > 10:
        _font_cache.clear()

# ===================== WARMUP =====================
async def warmup():
    logger.info("Card generator ready (COMPAT + LOW MEMORY)")
