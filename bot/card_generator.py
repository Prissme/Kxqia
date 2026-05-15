from __future__ import annotations

import asyncio
import io
import logging
import os
import random
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict

import aiohttp
import discord

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.warning("Pillow non installé — cards désactivées.")

# --- CONFIGURATION ---
_FONT_CACHE_DIR = Path(os.getenv("FONT_CACHE_DIR", "/tmp/bot_fonts"))
_SEKUYA_PATH = _FONT_CACHE_DIR / "Sekuya.ttf"

# Couleurs
BG_DARK = (10, 12, 25, 255)
BG_CARD = (18, 22, 45, 255)
NEON = (0, 200, 255, 255)
NEON_GLOW = (0, 200, 255, 80)
WHITE = (255, 255, 255, 255)
GREY = (150, 160, 200, 255)
BAR_BG = (35, 40, 75, 255)
GOLD = (255, 215, 0, 255)
SILVER = (192, 192, 192, 255)
BRONZE = (205, 127, 50, 255)

# --- UTILS PIL ---

def _ensure_font() -> Optional[Path]:
    if not _PIL_AVAILABLE: return None
    _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if _SEKUYA_PATH.exists(): return _SEKUYA_PATH
    try:
        css_url = "https://fonts.googleapis.com/css2?family=Sekuya&display=swap"
        req = urllib.request.Request(css_url, headers={"User-Agent": "Mozilla/5.0"})
        css = urllib.request.urlopen(req).read().decode()
        import re
        match = re.search(r"url\((https://[^)]+\.ttf[^)]*)\)", css)
        if not match: return None
        font_url = match.group(1)
        _SEKUYA_PATH.write_bytes(urllib.request.urlopen(font_url).read())
        return _SEKUYA_PATH
    except Exception as e:
        logger.warning(f"Font download failed: {e}")
        return None

def _load_font(size: int):
    path = _ensure_font()
    if path:
        try: return ImageFont.truetype(str(path), size)
        except: pass
    return ImageFont.load_default()

async def _fetch_avatar(url: Optional[str], size: int) -> Optional[Image.Image]:
    if not url: return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200: return None
                data = await resp.read()
        
        avatar = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)
        
        output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        output.paste(avatar, (0, 0), mask)
        return output
    except Exception as e:
        logger.warning(f"Avatar fetch error: {e}")
        return None

def _draw_xp_bar(draw: ImageDraw.ImageDraw, x, y, w, h, progress, color=NEON):
    # Background bar
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h//2, fill=BAR_BG)
    if progress <= 0: return
    # Filled bar
    width = int(w * max(0, min(1, progress)))
    if width > h: # Évite les bugs de rendu si trop petit
        draw.rounded_rectangle((x, y, x + width, y + h), radius=h//2, fill=color)

def _draw_glow_elements(image: Image.Image, frame_i: int):
    """ Ajoute un effet de particules et de lueurs diffuses """
    glow_layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow_layer)
    W, H = image.size
    
    # Particules Bokeh (cercles flous)
    random.seed(42) # Seed fixe pour que le mouvement soit fluide
    for _ in range(15):
        size = random.randint(10, 30)
        px = random.randint(0, W)
        py = (random.randint(0, H) - frame_i * 2) % H
        alpha = random.randint(20, 50)
        gd.ellipse((px, py, px+size, py+size), fill=(0, 200, 255, alpha))
    
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(5))
    return Image.alpha_composite(image, glow_layer)

# --- GÉNÉRATEURS DE FRAMES ---

def _build_xp_card_frames(name, avatar, level, xp_prog, xp_req, W=620, H=200):
    frames = []
    font_large = _load_font(40)
    font_med = _load_font(22)
    font_small = _load_font(16)
    
    for i in range(1): # Statique pour le moment (plus rapide), ou 10 pour animation
        base = Image.new("RGBA", (W, H), BG_DARK)
        draw = ImageDraw.Draw(base)
        
        # Cadre principal avec bordure néon
        draw.rounded_rectangle((10, 10, W-10, H-10), radius=20, fill=BG_CARD, outline=NEON, width=2)
        
        if avatar:
            # Ombre derrière l'avatar
            draw.ellipse((35, 35, 155, 155), fill=(0, 0, 0, 100))
            base.paste(avatar, (40, 40), avatar)
        
        # Textes
        draw.text((180, 40), name[:20], fill=WHITE, font=font_large)
        draw.text((180, 90), f"NIVEAU {level}", fill=NEON, font=font_med)
        
        # Stats XP
        xp_text = f"{xp_prog} / {xp_req} XP"
        draw.text((W - 180, 95), xp_text, fill=GREY, font=font_small)
        
        # Barre d'XP
        _draw_xp_bar(draw, 180, 130, 400, 20, xp_prog/xp_req if xp_req > 0 else 1)
        
        base = _draw_glow_elements(base, i)
        frames.append(base)
    return frames

def _build_levelup_frames(name, avatar, old_lv, new_lv, progress, req, W=620, H=180):
    frames = []
    for i in range(15):
        frame = Image.new("RGBA", (W, H), BG_DARK)
        draw = ImageDraw.Draw(frame)
        
        # Animation du cadre (pulse)
        border_alpha = int(150 + 105 * (i/15))
        draw.rounded_rectangle((5, 5, W-5, H-5), radius=25, fill=BG_CARD, outline=(0, 200, 255, border_alpha), width=3)
        
        if avatar:
            frame.paste(avatar, (30, 35), avatar)
            
        draw.text((170, 25), "LEVEL UP !", fill=NEON, font=_load_font(38))
        draw.text((170, 75), name, fill=WHITE, font=_load_font(24))
        draw.text((170, 110), f"Rang {old_lv} → {new_lv}", fill=GREY, font=_load_font(18))
        
        # Barre animée
        current_prog = (progress/req) * (i/15)
        _draw_xp_bar(draw, 170, 145, 400, 12, current_prog)
        
        frame = _draw_glow_elements(frame, i)
        frames.append(frame)
    return frames

# --- FONCTIONS PUBLIQUES ---

async def generate_xp_card(member_name, avatar_url, level, xp_total, xp_progress, xp_required):
    if not _PIL_AVAILABLE: return None
    avatar = await _fetch_avatar(avatar_url, 120)
    frames = _build_xp_card_frames(member_name, avatar, level, xp_progress, xp_required)
    
    buf = io.BytesIO()
    frames[0].save(buf, format="PNG")
    buf.seek(0)
    return buf

async def generate_levelup_card(member_name, avatar_url, old_level, new_level, xp_total, xp_progress, xp_required):
    if not _PIL_AVAILABLE: return None
    avatar = await _fetch_avatar(avatar_url, 110)
    frames = _build_levelup_frames(member_name, avatar, old_level, new_level, xp_progress, xp_required)
    
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=60, loop=0)
    buf.seek(0)
    return buf

async def generate_topxp_card(guild_name, entries, xp_to_level_fn):
    if not _PIL_AVAILABLE: return None
    
    # Récupération de tous les avatars en parallèle
    avatar_tasks = [_fetch_avatar(e.get("avatar_url"), 30) for e in entries[:10]]
    avatars = await asyncio.gather(*avatar_tasks)
    
    W, H = 620, 550
    base = Image.new("RGBA", (W, H), BG_DARK)
    draw = ImageDraw.Draw(base)
    draw.rounded_rectangle((10, 10, W-10, H-10), radius=20, fill=BG_CARD, outline=NEON, width=2)
    
    draw.text((30, 30), f"CLASSEMENT : {guild_name.upper()}", fill=NEON, font=_load_font(26))
    
    y_offset = 100
    for idx, e in enumerate(entries[:10]):
        # Couleur selon le rang
        rank_color = WHITE
        if idx == 0: rank_color = GOLD
        elif idx == 1: rank_color = SILVER
        elif idx == 2: rank_color = BRONZE
        
        # Background ligne
        if idx % 2 == 0:
            draw.rectangle((20, y_offset-5, W-20, y_offset+35), fill=(255, 255, 255, 5))
            
        # Rang et Avatar
        draw.text((30, y_offset), f"#{idx+1}", fill=rank_color, font=_load_font(20))
        
        av = avatars[idx]
        if av:
            base.paste(av, (80, y_offset-2), av)
            
        # Nom et Stats
        name = e.get("user_name", "Inconnu")[:18]
        xp = int(e.get("xp", 0))
        lv = xp_to_level_fn(xp)
        
        draw.text((130, y_offset), name, fill=WHITE, font=_load_font(18))
        draw.text((400, y_offset), f"LVL {lv}", fill=NEON, font=_load_font(16))
        draw.text((500, y_offset), f"{xp} XP", fill=GREY, font=_load_font(14))
        
        y_offset += 42

    base = _draw_glow_elements(base, 0)
    buf = io.BytesIO()
    base.save(buf, format="PNG")
    buf.seek(0)
    return buf
