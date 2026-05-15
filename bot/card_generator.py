from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import unicodedata
import urllib.request
from functools import partial
from pathlib import Path
from typing import Any, Callable, Optional, List

import aiohttp

logger = logging.getLogger(__name__)

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps, ImageEnhance
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False
    logger.warning("Pillow non installé — cards désactivées.")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_FONT_CACHE_DIR = Path(os.getenv("FONT_CACHE_DIR", "/tmp/bot_fonts"))
_SEKUYA_PATH    = _FONT_CACHE_DIR / "Sekuya.ttf"
_NOTO_PATH      = _FONT_CACHE_DIR / "NotoSans.ttf"
_EMOJI_PATH     = _FONT_CACHE_DIR / "NotoEmoji.ttf"

# GIF de fond partagé (téléchargé une seule fois)
_BG_GIF_URL  = "https://64.media.tumblr.com/50bc02e1080b949b2bd58c9353e4d779/b81f0327a444c7a5-c3/s540x810/6420baec988b32ab0c087abdc0d2bf9601ae512c.gif"
_BG_GIF_PATH = _FONT_CACHE_DIR / "bg_animated.gif"

# Cache global des frames préparées par (width, height, max_frames)
_prepared_frames_cache: dict[tuple[int, int, int], tuple[List[Image.Image], int]] = {}
_bg_frames_cache: Optional[List[Image.Image]] = None
_bg_duration_cache: int = 60

# Cache global des polices chargées
_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

# Couleurs
NEON     = (0, 200, 255, 255)
WHITE    = (255, 255, 255, 255)
GREY     = (200, 210, 230, 255)   # plus clair pour meilleure lisibilité
BAR_BG   = (20, 25, 55, 180)
GOLD     = (255, 215, 0, 255)
SILVER   = (192, 192, 192, 255)
BRONZE   = (205, 127, 50, 255)
OVERLAY  = (0, 0, 0, 175)   # fond semi-transparent plus opaque
SHADOW   = (0, 0, 0, 230)   # ombre plus marquée

# Limites GIF
MAX_FRAMES_CARD = 25
MAX_FRAMES_TOP  = 20

# ---------------------------------------------------------------------------
# Utilitaires – polices (avec cache)
# ---------------------------------------------------------------------------

_NOTO_SANS_URL  = "https://github.com/openmaptiles/fonts/raw/master/noto-sans/NotoSans-Regular.ttf"
_NOTO_EMOJI_URL = "https://raw.githubusercontent.com/notofonts/notofonts.github.io/noto-monthly-release-2025.12.01/fonts/NotoSansSymbols/hinted/ttf/NotoSansSymbols-Regular.ttf"

_fonts_downloaded = False


def _download_file(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=10).read()
        dest.write_bytes(data)
        return True
    except Exception as exc:
        logger.warning("Téléchargement échoué %s : %s", url, exc)
        return False


def _ensure_fonts() -> None:
    """Télécharge les polices si absentes — exécuté une seule fois."""
    global _fonts_downloaded
    if _fonts_downloaded:
        return

    _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not _SEKUYA_PATH.exists():
        try:
            css_url = "https://fonts.googleapis.com/css2?family=Sekuya&display=swap"
            req     = urllib.request.Request(css_url, headers={"User-Agent": "Mozilla/5.0"})
            css     = urllib.request.urlopen(req, timeout=10).read().decode()
            match   = re.search(r"url\((https://[^)]+\.ttf[^)]*)\)", css)
            if match:
                _download_file(match.group(1), _SEKUYA_PATH)
        except Exception as exc:
            logger.warning("Police Sekuya indisponible : %s", exc)

    if not _NOTO_PATH.exists():
        for _url in [
            _NOTO_SANS_URL,
            "https://github.com/ryanoasis/nerd-fonts/raw/master/src/unpatched-fonts/Noto/Sans/NotoSans-Regular.ttf",
            "https://github.com/prezly/noto-sans/raw/master/fonts/NotoSans-Regular.ttf",
        ]:
            if _download_file(_url, _NOTO_PATH):
                break

    if not _EMOJI_PATH.exists():
        for _url in [
            _NOTO_EMOJI_URL,
            "https://raw.githubusercontent.com/notofonts/notofonts.github.io/noto-monthly-release-2025.12.01/fonts/NotoSansSymbols2/hinted/ttf/NotoSansSymbols2-Regular.ttf",
        ]:
            if _download_file(_url, _EMOJI_PATH):
                break

    _fonts_downloaded = True


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Charge Sekuya (avec cache) puis NotoSans comme fallback."""
    key = ("sekuya", size)
    if key in _font_cache:
        return _font_cache[key]
    _ensure_fonts()
    for path in (_SEKUYA_PATH, _NOTO_PATH):
        if path.exists():
            try:
                font = ImageFont.truetype(str(path), size)
                _font_cache[key] = font
                return font
            except Exception:
                continue
    font = ImageFont.load_default()
    _font_cache[key] = font
    return font


def _load_noto(size: int) -> ImageFont.FreeTypeFont:
    """Charge NotoSans (avec cache)."""
    key = ("noto", size)
    if key in _font_cache:
        return _font_cache[key]
    _ensure_fonts()
    if _NOTO_PATH.exists():
        try:
            font = ImageFont.truetype(str(_NOTO_PATH), size)
            _font_cache[key] = font
            return font
        except Exception:
            pass
    font = ImageFont.load_default()
    _font_cache[key] = font
    return font


# ---------------------------------------------------------------------------
# Utilitaires – texte / emojis
# ---------------------------------------------------------------------------

def _sanitize_text(text: str, max_len: int = 28) -> str:
    """
    Nettoie un pseudo — limite étendue à 28 caractères par défaut.
    Garde les caractères Latin, Cyrillic, Greek, CJK, Arabic + ASCII étendu.
    """
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        cp = ord(ch)

        if unicodedata.category(ch) in ("Mn", "Cf") or cp == 0x200D:
            i += 1
            continue

        if 0x1F3FB <= cp <= 0x1F3FF:
            i += 1
            continue

        if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or \
           (0xFE00 <= cp <= 0xFE0F)   or (0xE0000 <= cp <= 0xE007F):
            result.append("?")
            i += 1
            continue

        if 0x1F1E0 <= cp <= 0x1F1FF:
            result.append("?")
            i += 2 if i + 1 < len(text) and 0x1F1E0 <= ord(text[i + 1]) <= 0x1F1FF else 1
            continue

        result.append(ch)
        i += 1

    clean = "".join(result).strip()
    return clean[:max_len] if clean else "Joueur"


# ---------------------------------------------------------------------------
# Utilitaires – dessin
# ---------------------------------------------------------------------------

def _draw_shadow_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
    shadow_offset: int = 2,
    shadow_blur: bool = False,
) -> None:
    """Dessine un texte avec ombre portée double pour meilleure lisibilité."""
    sx, sy = xy[0] + shadow_offset, xy[1] + shadow_offset
    # Double shadow pour plus de contraste
    draw.text((sx + 1, sy + 1), text, font=font, fill=SHADOW)
    draw.text((sx, sy), text, font=font, fill=SHADOW)
    draw.text(xy, text, font=font, fill=fill)


def _draw_xp_bar(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    h: int,
    progress: float,
    color: tuple = NEON,
) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=BAR_BG)
    ratio = max(0.0, min(1.0, progress))
    filled_w = int(w * ratio)
    if filled_w > h:
        draw.rounded_rectangle((x, y, x + filled_w, y + h), radius=h // 2, fill=color)


def _draw_overlay(image: Image.Image, x: int, y: int, w: int, h: int, radius: int = 12) -> None:
    """Rectangle semi-transparent pour améliorer la lisibilité du texte."""
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=OVERLAY)
    image.alpha_composite(overlay)


# ---------------------------------------------------------------------------
# GIF de fond — chargement et préparation avec cache
# ---------------------------------------------------------------------------

def _load_bg_gif_sync() -> tuple[List[Image.Image], int]:
    """Charge le GIF depuis le disque (ou le télécharge). Résultat mis en cache."""
    global _bg_frames_cache, _bg_duration_cache

    if _bg_frames_cache is not None:
        return _bg_frames_cache, _bg_duration_cache

    _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if not _BG_GIF_PATH.exists():
        try:
            req  = urllib.request.Request(_BG_GIF_URL, headers={"User-Agent": "Mozilla/5.0"})
            data = urllib.request.urlopen(req, timeout=15).read()
            _BG_GIF_PATH.write_bytes(data)
            logger.info("GIF de fond téléchargé (%d octets).", len(data))
        except Exception as exc:
            logger.warning("Impossible de télécharger le GIF de fond : %s", exc)
            _bg_frames_cache = []
            return [], 60

    try:
        gif = Image.open(_BG_GIF_PATH)
        duration = gif.info.get("duration", 60)
        frames: List[Image.Image] = []
        try:
            while True:
                frames.append(gif.copy().convert("RGBA"))
                gif.seek(gif.tell() + 1)
        except EOFError:
            pass
        _bg_frames_cache  = frames
        _bg_duration_cache = int(duration) if duration else 60
        logger.info("GIF de fond chargé : %d frames, %d ms/frame.", len(frames), _bg_duration_cache)
        return frames, _bg_duration_cache
    except Exception as exc:
        logger.warning("Erreur lecture GIF : %s", exc)
        _bg_frames_cache = []
        return [], 60


def _prepare_bg_frames(
    target_w: int,
    target_h: int,
    max_frames: int,
) -> tuple[List[Image.Image], int]:
    """
    Sélectionne, recadre et redimensionne les frames du GIF de fond.
    Résultat mis en cache par (target_w, target_h, max_frames).
    """
    cache_key = (target_w, target_h, max_frames)
    if cache_key in _prepared_frames_cache:
        return _prepared_frames_cache[cache_key]

    all_frames, duration = _load_bg_gif_sync()

    if not all_frames:
        fallback = Image.new("RGBA", (target_w, target_h), (10, 12, 25, 255))
        result = ([fallback], 60)
        _prepared_frames_cache[cache_key] = result
        return result

    step    = max(1, len(all_frames) // max_frames)
    sampled = all_frames[::step][:max_frames]

    prepared: List[Image.Image] = []
    for frame in sampled:
        fitted = ImageOps.fit(frame, (target_w, target_h), method=Image.LANCZOS)
        fitted = ImageEnhance.Brightness(fitted).enhance(0.50)  # légèrement plus sombre
        prepared.append(fitted)

    result = (prepared, duration)
    _prepared_frames_cache[cache_key] = result
    logger.info("Frames préparées mises en cache pour %dx%d (%d frames).", target_w, target_h, len(prepared))
    return result


# ---------------------------------------------------------------------------
# Avatar
# ---------------------------------------------------------------------------

# Cache des avatars téléchargés
_avatar_cache: dict[tuple[str, int], Optional[Image.Image]] = {}


async def _fetch_avatar(url: Optional[str], size: int) -> Optional[Image.Image]:
    if not url:
        return None

    cache_key = (url, size)
    if cache_key in _avatar_cache:
        return _avatar_cache[cache_key]

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    _avatar_cache[cache_key] = None
                    return None
                data = await resp.read()

        avatar = Image.open(io.BytesIO(data)).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
        output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        output.paste(avatar, mask=mask)
        # Ajouter un contour néon autour de l'avatar
        _avatar_cache[cache_key] = output
        return output
    except Exception as exc:
        logger.warning("Erreur avatar : %s", exc)
        _avatar_cache[cache_key] = None
        return None


# ---------------------------------------------------------------------------
# Construction des frames – carte XP (620×200)
# ---------------------------------------------------------------------------

def _build_xp_card_frames_sync(
    name: str,
    avatar: Optional[Image.Image],
    level: int,
    xp_progress: int,
    xp_required: int,
    xp_total: int,
) -> tuple[List[Image.Image], int]:

    W, H = 620, 200
    bg_frames, duration = _prepare_bg_frames(W, H, MAX_FRAMES_CARD)

    font_name  = _load_font(34)
    font_level = _load_noto(20)
    font_small = _load_noto(15)

    name_clean = _sanitize_text(name, 24)
    ratio      = xp_progress / xp_required if xp_required > 0 else 1.0

    output_frames: List[Image.Image] = []

    for bg in bg_frames:
        frame = bg.copy()

        # Overlay plus opaque pour meilleure lisibilité
        _draw_overlay(frame, x=150, y=15, w=450, h=170, radius=16)

        # Avatar
        if avatar:
            av_size = 120
            av_x, av_y = 15, 40
            halo = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            ImageDraw.Draw(halo).ellipse(
                (av_x - 4, av_y - 4, av_x + av_size + 4, av_y + av_size + 4),
                fill=(0, 200, 255, 90),
            )
            frame.alpha_composite(halo)
            frame.paste(avatar, (av_x, av_y), avatar)

        draw = ImageDraw.Draw(frame)

        # Nom
        _draw_shadow_text(draw, (163, 25), name_clean, font_name, WHITE)

        # Niveau
        _draw_shadow_text(draw, (163, 72), f"NIVEAU {level}", font_level, NEON)

        # XP (plus lisible avec GREY plus clair)
        xp_label = f"{xp_progress} / {xp_required} XP"
        _draw_shadow_text(draw, (420, 74), xp_label, font_small, GREY)

        # Barre XP
        _draw_xp_bar(draw, 163, 112, 425, 18, ratio)

        # Pourcentage
        pct_label = f"{int(ratio * 100)}%"
        _draw_shadow_text(draw, (163 + 425 // 2 - 15, 114), pct_label, font_small, WHITE)

        # XP total
        _draw_shadow_text(draw, (163, 145), f"Total : {xp_total} XP", font_small, GREY)

        output_frames.append(frame)

    return output_frames, duration


# ---------------------------------------------------------------------------
# Construction des frames – Level Up (620×180)
# ---------------------------------------------------------------------------

def _build_levelup_frames_sync(
    name: str,
    avatar: Optional[Image.Image],
    old_level: int,
    new_level: int,
    xp_progress: int,
    xp_required: int,
) -> tuple[List[Image.Image], int]:

    W, H = 620, 180
    bg_frames, duration = _prepare_bg_frames(W, H, MAX_FRAMES_CARD)

    font_title = _load_font(34)
    font_name  = _load_noto(22)
    font_rank  = _load_noto(18)
    font_small = _load_noto(14)

    name_clean  = _sanitize_text(name, 24)
    n_frames    = len(bg_frames)
    output_frames: List[Image.Image] = []

    for idx, bg in enumerate(bg_frames):
        frame = bg.copy()
        anim  = idx / max(n_frames - 1, 1)

        _draw_overlay(frame, x=145, y=12, w=458, h=156, radius=16)

        if avatar:
            av_size = 100
            av_x, av_y = 22, 40
            halo = Image.new("RGBA", frame.size, (0, 0, 0, 0))
            pulse_alpha = int(60 + 80 * abs(anim - 0.5) * 2)
            ImageDraw.Draw(halo).ellipse(
                (av_x - 5, av_y - 5, av_x + av_size + 5, av_y + av_size + 5),
                fill=(0, 200, 255, pulse_alpha),
            )
            frame.alpha_composite(halo)
            frame.paste(avatar, (av_x, av_y), avatar)

        draw = ImageDraw.Draw(frame)

        _draw_shadow_text(draw, (158, 18), "LEVEL UP !", font_title, NEON)
        _draw_shadow_text(draw, (158, 66), name_clean,   font_name,  WHITE)
        _draw_shadow_text(draw, (158, 96), f"Rang {old_level} → {new_level}", font_rank, GREY)

        ratio = (xp_progress / xp_required if xp_required > 0 else 1.0) * anim
        _draw_xp_bar(draw, 158, 128, 435, 14, ratio)

        xp_label = f"{xp_progress} / {xp_required}"
        _draw_shadow_text(draw, (158, 148), xp_label, font_small, GREY)

        output_frames.append(frame)

    return output_frames, duration


# ---------------------------------------------------------------------------
# Construction des frames – Top XP (620×550)
# ---------------------------------------------------------------------------

def _build_topxp_frames_sync(
    guild_name: str,
    entries: list[dict],
    avatars: list[Optional[Image.Image]],
    xp_to_level_fn: Callable[[int], int],
) -> tuple[List[Image.Image], int]:

    W, H = 620, 560
    bg_frames, duration = _prepare_bg_frames(W, H, MAX_FRAMES_TOP)

    # Titre en Sekuya, plus grand
    font_title  = _load_font(26)
    font_row    = _load_noto(17)
    font_small  = _load_noto(13)
    font_xp     = _load_noto(14)    # police dédiée XP, légèrement plus grande

    # Limite étendue pour le nom du serveur
    guild_clean = _sanitize_text(guild_name, 36)
    rank_colors = [GOLD, SILVER, BRONZE]
    output_frames: List[Image.Image] = []

    for bg in bg_frames:
        frame = bg.copy()

        # Overlay global
        _draw_overlay(frame, x=8, y=8, w=604, h=544, radius=20)

        draw = ImageDraw.Draw(frame)

        # Titre serveur — Sekuya + grand
        title_text = f"CLASSEMENT  {guild_clean.upper()}"
        _draw_shadow_text(draw, (20, 18), title_text, font_title, NEON, shadow_offset=2)

        # Séparateur
        draw.line((20, 58, 600, 58), fill=(0, 200, 255, 100), width=1)

        y = 68
        for idx, entry in enumerate(entries[:10]):
            rank_color = rank_colors[idx] if idx < 3 else WHITE

            # Fond de ligne alterné légèrement plus visible
            if idx % 2 == 0:
                row_ov = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                ImageDraw.Draw(row_ov).rectangle(
                    (16, y - 2, 604, y + 38), fill=(255, 255, 255, 12)
                )
                frame.alpha_composite(row_ov)
                draw = ImageDraw.Draw(frame)

            # Rang
            _draw_shadow_text(draw, (20, y + 6), f"#{idx + 1}", font_row, rank_color)

            # Avatar
            av = avatars[idx] if idx < len(avatars) else None
            if av:
                small_av = av.resize((30, 30), Image.LANCZOS)
                frame.paste(small_av, (64, y + 4), small_av)
                draw = ImageDraw.Draw(frame)

            # Nom — limite étendue à 24 caractères
            name_clean = _sanitize_text(entry.get("user_name", "Inconnu"), 24)
            _draw_shadow_text(draw, (102, y + 6), name_clean, font_row, WHITE)

            # Niveau + XP — côté droit, plus lisible
            xp_val = int(entry.get("xp", 0) or 0)
            lv     = xp_to_level_fn(xp_val)

            # Fond pour le niveau
            lv_text = f"LVL {lv}"
            xp_text = f"{xp_val:,} XP"

            _draw_shadow_text(draw, (390, y + 7), lv_text,  font_xp,   NEON,  shadow_offset=2)
            _draw_shadow_text(draw, (470, y + 7), xp_text,  font_xp,   GREY,  shadow_offset=2)

            y += 46

        output_frames.append(frame)

    return output_frames, duration


# ---------------------------------------------------------------------------
# Helpers – encodage GIF
# ---------------------------------------------------------------------------

def _encode_gif(frames: List[Image.Image], duration: int) -> io.BytesIO:
    """Convertit une liste de frames RGBA en GIF dans un BytesIO."""
    rgb_frames = [f.convert("RGB") for f in frames]
    buf = io.BytesIO()
    rgb_frames[0].save(
        buf,
        format="GIF",
        save_all=True,
        append_images=rgb_frames[1:],
        duration=duration,
        loop=0,
        optimize=False,
    )
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# API publique (async)
# ---------------------------------------------------------------------------

async def generate_xp_card(
    member_name: str,
    avatar_url: str,
    level: int,
    xp_total: int,
    xp_progress: int,
    xp_required: int,
) -> Optional[io.BytesIO]:
    if not _PIL_AVAILABLE:
        return None

    avatar = await _fetch_avatar(avatar_url, 120)

    loop = asyncio.get_event_loop()
    fn   = partial(
        _build_xp_card_frames_sync,
        member_name,
        avatar,
        level,
        xp_progress,
        xp_required,
        xp_total,
    )
    frames, duration = await loop.run_in_executor(None, fn)

    encode_fn = partial(_encode_gif, frames, duration)
    buf = await loop.run_in_executor(None, encode_fn)
    return buf


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

    avatar = await _fetch_avatar(avatar_url, 100)

    loop = asyncio.get_event_loop()
    fn   = partial(
        _build_levelup_frames_sync,
        member_name,
        avatar,
        old_level,
        new_level,
        xp_progress,
        xp_required,
    )
    frames, duration = await loop.run_in_executor(None, fn)

    encode_fn = partial(_encode_gif, frames, duration)
    buf = await loop.run_in_executor(None, encode_fn)
    return buf


async def generate_topxp_card(
    guild_name: str,
    entries: list[dict],
    xp_to_level_fn: Callable[[int], int],
) -> Optional[io.BytesIO]:
    if not _PIL_AVAILABLE:
        return None

    avatar_tasks = [_fetch_avatar(e.get("avatar_url"), 30) for e in entries[:10]]
    avatars      = list(await asyncio.gather(*avatar_tasks))

    loop = asyncio.get_event_loop()
    fn   = partial(
        _build_topxp_frames_sync,
        guild_name,
        entries[:10],
        avatars,
        xp_to_level_fn,
    )
    frames, duration = await loop.run_in_executor(None, fn)

    encode_fn = partial(_encode_gif, frames, duration)
    buf = await loop.run_in_executor(None, encode_fn)
    return buf
