"""
voice_xp.py — Système d'XP vocal
==================================
- 2 XP par minute passée en vocal
- Conditions : minimum 2 membres humains dans le salon,
  membre ni muté (self_mute) ni sourd (self_deaf)
- Plafond journalier séparé : 1500 XP/jour
- Diminishing returns : -75% après 1000 XP vocal/jour
- Reset à minuit UTC (géré par main.py via reset_daily_voice_xp)
- Tick toutes les 60 secondes
"""

import asyncio
import datetime
import logging
from collections import defaultdict
from typing import Optional

import discord
from discord.ext import commands

logger = logging.getLogger(__name__)

# ── Constantes ────────────────────────────────────────────────────────────────
VOICE_XP_PER_MINUTE = 2
VOICE_XP_TICK_SECONDS = 60          # intervalle du tick
VOICE_DAILY_CAP = 1500              # plafond journalier vocal
VOICE_DAILY_THRESHOLD = 1000        # seuil diminishing returns
VOICE_DAILY_REDUCTION = 0.25        # multiplicateur après le seuil (25% = -75%)

# Salons à ignorer (AFK, etc.) — remplis depuis main.py si besoin
EXCLUDED_CHANNEL_IDS: set[int] = set()

# ── État en mémoire ───────────────────────────────────────────────────────────
# { guild_id: { user_id: xp_vocal_aujourd'hui } }
_daily_voice_xp: defaultdict = defaultdict(lambda: defaultdict(int))


# ── Helpers plafond ───────────────────────────────────────────────────────────

def get_daily_voice_xp(guild_id: int, user_id: int) -> int:
    return _daily_voice_xp[guild_id][user_id]


def reset_daily_voice_xp() -> None:
    """Remet à zéro tous les compteurs vocaux. À appeler depuis main.py à minuit UTC."""
    global _daily_voice_xp
    _daily_voice_xp = defaultdict(lambda: defaultdict(int))
    logger.info("Reset quotidien des XP vocaux effectué.")


def _add_daily_voice_xp(guild_id: int, user_id: int, amount: int) -> int:
    """
    Ajoute `amount` XP vocal en respectant le plafond et les diminishing returns.
    Retourne l'XP réellement accordé (0 si plafond atteint).
    """
    current = get_daily_voice_xp(guild_id, user_id)

    if current >= VOICE_DAILY_CAP:
        return 0

    # Calcule l'XP effectif selon la tranche
    if current >= VOICE_DAILY_THRESHOLD:
        actual = int(amount * VOICE_DAILY_REDUCTION)
    else:
        # Vérifie si on franchit le seuil dans ce tick
        if current + amount > VOICE_DAILY_THRESHOLD:
            # Partie avant le seuil au taux plein, partie après réduite
            full_part = VOICE_DAILY_THRESHOLD - current
            reduced_part = int((amount - full_part) * VOICE_DAILY_REDUCTION)
            actual = full_part + reduced_part
        else:
            actual = amount

    # Respect du plafond absolu
    actual = min(actual, VOICE_DAILY_CAP - current)
    if actual <= 0:
        return 0

    _daily_voice_xp[guild_id][user_id] = current + actual
    return actual


# ── Condition d'éligibilité ───────────────────────────────────────────────────

def _is_eligible(member: discord.Member, channel: discord.VoiceChannel) -> bool:
    """
    Un membre gagne de l'XP vocal si :
    - Il est dans un salon non exclu
    - Il n'est pas muté (self_mute) ni sourd (self_deaf)
    - Le salon contient au moins 2 membres humains non-bots
    """
    if channel.id in EXCLUDED_CHANNEL_IDS:
        return False

    vs = member.voice
    if vs is None:
        return False
    if vs.self_mute or vs.self_deaf:
        return False

    # Compte les membres humains présents (hors bots, hors AFK)
    human_count = sum(
        1 for m in channel.members
        if not m.bot
    )
    return human_count >= 2


# ── Tâche de fond principale ──────────────────────────────────────────────────

async def voice_xp_loop(bot: commands.Bot, db, xp_to_level_fn, handle_level_up_fn, max_xp: int) -> None:
    """
    Tâche asyncio à lancer dans on_ready :
        bot.loop.create_task(voice_xp_loop(bot, db, _xp_to_level, _handle_level_up, MAX_XP))

    Toutes les 60 secondes, parcourt tous les salons vocaux de tous les guilds
    et accorde l'XP aux membres éligibles.
    """
    await bot.wait_until_ready()
    logger.info("Tâche XP vocal démarrée.")

    while True:
        await asyncio.sleep(VOICE_XP_TICK_SECONDS)

        for guild in bot.guilds:
            for channel in guild.voice_channels:
                if channel.id in EXCLUDED_CHANNEL_IDS:
                    continue

                for member in channel.members:
                    if member.bot:
                        continue
                    if not _is_eligible(member, channel):
                        continue

                    guild_id = guild.id
                    user_id = member.id
                    guild_id_str = str(guild_id)
                    user_id_str = str(user_id)

                    actual_xp = _add_daily_voice_xp(guild_id, user_id, VOICE_XP_PER_MINUTE)
                    if actual_xp <= 0:
                        continue

                    try:
                        current = db.get_user_xp(guild_id_str, user_id_str)
                        current_xp = int(current.get('xp', 0) or 0)

                        if current_xp >= max_xp:
                            continue

                        old_level = xp_to_level_fn(current_xp)
                        new_xp = min(max_xp, current_xp + actual_xp)
                        db.set_user_xp(guild_id_str, user_id_str, str(member), new_xp)

                        new_level = xp_to_level_fn(new_xp)
                        if new_level > old_level:
                            await handle_level_up_fn(channel, member, old_level, new_level, new_xp)

                    except Exception as exc:
                        logger.error(
                            "Erreur XP vocal pour %s dans %s : %s",
                            member, guild.name, exc
                        )
