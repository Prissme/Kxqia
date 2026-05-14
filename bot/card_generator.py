"""
Génération de cards d'images stylées avec Pillow.
- Level-up card
- Leaderboard (top XP) card
Police : Sekuya (Google Fonts) avec fallback DejaVu.
"""

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
# Police Sekuya
# ---------------------------------------------------------------------------
_FONT_CACHE_DIR = Path(os.getenv("FONT_CACHE_DIR", "/tmp/bot_fonts"))
_SEKUYA_PATH = _FONT_CACHE_DIR / "Sekuya.ttf"

# Pillow optionnel — import paresseux pour ne pas bloquer le démarrage
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.warning("Pillow non installé — les cards d'images sont désactivées.")


def _ensure_font() -> Optional[Path]:
    """Télécharge Sekuya si absent et retourne le chemin, ou None."""
    if not _PIL_AVAILABLE:
        return None

    _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if _SEKUYA_PATH.exists():
        return _SEKUYA_PATH

    # Tentative de téléchargement via l'API Google Fonts CSS puis extraction de l'URL TTF
    try:
        css_url = (
            "https://fonts.googleapis.com/css2?family=Sekuya&display=swap"
        )
        req = urllib.request.Request(css_url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            css_text = resp.read().decode("utf-8")

        # Extraire l'URL src : url(...)
        import re
        match = re.search(r"url\((https://[^)]+\.ttf[^)]*)\)", css_text)
        if not match:
            logger.warning("URL TTF Sekuya introuvable dans le CSS.")
            return None

        font_url = match.group(1).strip("'\"")
        req2 = urllib.request.Request(font_url, headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        })
        with urllib.request.urlopen(req2, timeout=15) as resp2:
            _SEKUYA_PATH.write_bytes(resp2.read())

        logger.info("Police Sekuya téléchargée → %s", _SEKUYA_PATH)
        return _SEKUYA_PATH

    except Exception as exc:
        logger.warning("Impossible de télécharger Sekuya : %s", exc)
        return None


def _load_font(size: int) -> "ImageFont.FreeTypeFont | ImageFont.ImageFont":
    """Charge Sekuya à la taille donnée, ou une police système en fallback."""
    if not _PIL_AVAILABLE:
        raise RuntimeError("Pillow non disponible")

    font_path = _ensure_font()
    if font_path and font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception as exc:
            logger.warning("Erreur chargement Sekuya : %s", exc)

    # Fallbacks système
    for system_path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]:
        if Path(system_path).exists():
            try:
                return ImageFont.truetype(system_path, size)
            except Exception:
                continue

    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _fetch_avatar(url: str, size: int) -> "Optional[Image.Image]":
    """Télécharge et redimensionne un avatar Discord en cercle RGBA."""
    if not _PIL_AVAILABLE:
        return None
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.read()
        avatar = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        result.paste(avatar, (0, 0), mask)
        return result
    except Exception as exc:
        logger.warning("Erreur téléchargement avatar : %s", exc)
        return None


def _rounded_rect(draw: "ImageDraw.Draw", xy: tuple, radius: int, fill: tuple) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def _xp_bar(draw: "ImageDraw.Draw", x: int, y: int, w: int, h: int,
             progress: float, bg: tuple, fg: tuple, radius: int = 6) -> None:
    """Dessine une barre de progression XP."""
    _rounded_rect(draw, (x, y, x + w, y + h), radius, bg)
    filled = max(int(w * min(1.0, max(0.0, progress))), radius * 2 if progress > 0 else 0)
    if filled > 0:
        _rounded_rect(draw, (x, y, x + filled, y + h), radius, fg)


# ---------------------------------------------------------------------------
# Palette & constantes
# ---------------------------------------------------------------------------

BG_DARK      = (18, 18, 28, 255)
BG_CARD      = (28, 30, 50, 255)
ACCENT       = (88, 101, 242, 255)     # blurple
ACCENT_2     = (87, 242, 135, 255)     # vert
GOLD         = (255, 215, 0, 255)
WHITE        = (255, 255, 255, 255)
GREY         = (160, 160, 180, 255)
BORDER       = (55, 58, 90, 255)
BAR_BG       = (40, 42, 65, 255)


# ---------------------------------------------------------------------------
# Level-up card
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
    """
    Génère une card level-up et retourne un BytesIO PNG.
    Retourne None si Pillow n'est pas disponible.
    """
    if not _PIL_AVAILABLE:
        return None

    W, H = 620, 180
    AVATAR_SIZE = 120
    AVATAR_X, AVATAR_Y = 24, 30

    card = Image.new("RGBA", (W, H), BG_DARK)
    draw = ImageDraw.Draw(card)

    # Fond arrondi
    _rounded_rect(draw, (0, 0, W, H), 20, BG_CARD)

    # Bordure subtile
    draw.rounded_rectangle((0, 0, W - 1, H - 1), radius=20, outline=BORDER, width=2)

    # Lueur accent en haut à gauche
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-40, -40, 220, 120), fill=(*ACCENT[:3], 30))
    card = Image.alpha_composite(card, glow)
    draw = ImageDraw.Draw(card)

    # Avatar
    avatar = await _fetch_avatar(avatar_url, AVATAR_SIZE)
    if avatar:
        # Halo autour de l'avatar
        halo = Image.new("RGBA", card.size, (0, 0, 0, 0))
        hd = ImageDraw.Draw(halo)
        hd.ellipse(
            (AVATAR_X - 4, AVATAR_Y - 4, AVATAR_X + AVATAR_SIZE + 4, AVATAR_Y + AVATAR_SIZE + 4),
            fill=(*ACCENT[:3], 80),
        )
        card = Image.alpha_composite(card, halo)
        draw = ImageDraw.Draw(card)
        card.paste(avatar, (AVATAR_X, AVATAR_Y), avatar)

    # Texte "LEVEL UP !"
    TEXT_X = AVATAR_X + AVATAR_SIZE + 24
    font_title = _load_font(38)
    font_sub   = _load_font(20)
    font_small = _load_font(15)

    draw.text((TEXT_X, 22), "LEVEL UP !", fill=GOLD, font=font_title)

    # Nom du membre
    draw.text((TEXT_X, 68), member_name[:24], fill=WHITE, font=font_sub)

    # Niveaux
    level_text = f"{old_level}  →  {new_level}"
    draw.text((TEXT_X, 96), level_text, fill=GREY, font=font_small)

    # Barre XP
    BAR_X = TEXT_X
    BAR_Y = 125
    BAR_W = W - TEXT_X - 24
    BAR_H = 14
    progress_ratio = xp_progress / xp_required if xp_required > 0 else 0
    _xp_bar(draw, BAR_X, BAR_Y, BAR_W, BAR_H, progress_ratio, BAR_BG, ACCENT)

    # XP texte
    xp_text = f"{xp_progress} / {xp_required} XP"
    draw.text((BAR_X, BAR_Y + 18), xp_text, fill=GREY, font=_load_font(13))

    # Badge niveau (coin droit)
    badge_r = 30
    bx = W - badge_r - 18
    by = H // 2 - badge_r
    draw.ellipse((bx - badge_r, by, bx + badge_r, by + badge_r * 2), fill=ACCENT)
    lv_str = str(new_level)
    font_badge = _load_font(22 if new_level < 10 else 18)
    # Centre du texte dans le badge
    bbox = draw.textbbox((0, 0), lv_str, font=font_badge)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((bx - tw // 2, by + badge_r - th // 2), lv_str, fill=WHITE, font=font_badge)

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# Leaderboard card
# ---------------------------------------------------------------------------

async def generate_topxp_card(
    guild_name: str,
    entries: list[dict],  # [{"user_id", "user_name", "xp", avatar_url?}]
    xp_to_level_fn,       # callable(xp: int) -> int
) -> Optional[io.BytesIO]:
    """
    Génère une card leaderboard XP et retourne un BytesIO PNG.
    `entries` : liste triée décroissante, max 10 entrées.
    Retourne None si Pillow n'est pas disponible.
    """
    if not _PIL_AVAILABLE:
        return None

    MAX_ENTRIES = min(len(entries), 10)
    ROW_H = 64
    HEADER_H = 72
    W = 620
    H = HEADER_H + ROW_H * MAX_ENTRIES + 20
    AV_SIZE = 44
    PAD = 14

    card = Image.new("RGBA", (W, H), BG_DARK)
    draw = ImageDraw.Draw(card)

    # Fond principal
    _rounded_rect(draw, (0, 0, W, H), 20, BG_CARD)
    draw.rounded_rectangle((0, 0, W - 1, H - 1), radius=20, outline=BORDER, width=2)

    # Dégradé header — on dessine directement sur la card sans alpha_composite séparé
    draw.rounded_rectangle((0, 0, W, HEADER_H + 20), radius=20, fill=(*ACCENT[:3], 40))

    font_title  = _load_font(28)
    font_sub    = _load_font(13)
    font_name   = _load_font(16)
    font_rank   = _load_font(20)
    font_xp     = _load_font(13)

    # Titre
    draw.text((PAD + 4, 14), "🏆  Top XP", fill=GOLD, font=font_title)
    draw.text((PAD + 4, 48), guild_name[:40], fill=GREY, font=font_sub)

    # Lignes du leaderboard
    for i, entry in enumerate(entries[:MAX_ENTRIES]):
        y = HEADER_H + i * ROW_H

        # Fond alterné subtil — dessin direct sur la card (pas d'alpha_composite)
        if i % 2 == 0:
            draw.rectangle((0, y, W, y + ROW_H), fill=(255, 255, 255, 6))

        # Séparateur
        draw.line([(PAD, y), (W - PAD, y)], fill=BORDER, width=1)

        # Rang
        rank_color = GOLD if i == 0 else (192, 192, 192, 255) if i == 1 else (205, 127, 50, 255) if i == 2 else GREY
        rank_str = f"#{i + 1}"
        draw.text((PAD, y + (ROW_H - 24) // 2), rank_str, fill=rank_color, font=font_rank)

        # Avatar
        av_x = PAD + 42
        av_y = y + (ROW_H - AV_SIZE) // 2
        avatar_url = entry.get("avatar_url")
        if avatar_url:
            av = await _fetch_avatar(avatar_url, AV_SIZE)
            if av:
                card.paste(av, (av_x, av_y), av)
        else:
            # Placeholder cercle coloré avec initiale
            ph = Image.new("RGBA", (AV_SIZE, AV_SIZE), (0, 0, 0, 0))
            phd = ImageDraw.Draw(ph)
            phd.ellipse((0, 0, AV_SIZE, AV_SIZE), fill=(*ACCENT[:3], 120))
            initial = (entry.get("user_name") or "?")[0].upper()
            phd.text((AV_SIZE // 2 - 6, AV_SIZE // 2 - 9), initial, fill=WHITE, font=_load_font(18))
            card.paste(ph, (av_x, av_y), ph)

        # Rafraîchir draw après paste
        draw = ImageDraw.Draw(card)

        # Nom + XP
        text_x = av_x + AV_SIZE + 10
        name = (entry.get("user_name") or f"User {entry.get('user_id', '?')}")[:22]
        xp_val = int(entry.get("xp", 0) or 0)
        level = xp_to_level_fn(xp_val)

        draw.text((text_x, y + 10), name, fill=WHITE, font=font_name)
        draw.text((text_x, y + 32), f"Niveau {level}  •  {xp_val:,} XP", fill=GREY, font=font_xp)

        # Badge XP à droite
        xp_badge = f"LV {level}"
        bw = 54
        bh = 22
        bx = W - bw - PAD
        by2 = y + (ROW_H - bh) // 2
        _rounded_rect(draw, (bx, by2, bx + bw, by2 + bh), 6, ACCENT)
        bbox = draw.textbbox((0, 0), xp_badge, font=_load_font(12))
        tw = bbox[2] - bbox[0]
        draw.text((bx + (bw - tw) // 2, by2 + 4), xp_badge, fill=WHITE, font=_load_font(12))

    buf = io.BytesIO()
    card.save(buf, format="PNG")
    buf.seek(0)
    return buf
