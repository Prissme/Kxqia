"""
main.py — Version ultra-optimisée pour Prissme TV
=========================================================
- /topxp : Cache 5min + avatars uniquement pour top 3
- Logs HTTP filtrés (plus de spam Koyeb)
- Toutes les fonctionnalités originales conservées
- Gestion des erreurs silencieuse
"""

import asyncio
import datetime
import io
import json
import logging
import os
import random
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

# --- Configuration du logging (filtre les requêtes HTTP bruyantes) ---
class HTTPFilter(logging.Filter):
    def filter(self, record):
        # Filtre les logs de requêtes HTTP de aiohttp/discord/supabase
        if "aiohttp" in record.name or "http" in record.name.lower():
            return False
        if "HTTP Request" in getattr(record, "message", ""):
            return False
        return True

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
    filters=[HTTPFilter()]  # Applique le filtre
)
logger = logging.getLogger(__name__)

# --- Imports locaux ---
from database import db
from database.batch_manager import (
    batch_logger,
    register_signal_handlers,
    start_periodic_flush,
)
from database.models import Config
from bot.anti_nuke import AntiNuke
from bot.anti_raid import AntiRaid
from bot.slow_mode import SlowModeManager
from bot.level_roles import sync_level_roles
from bot.card_generator import generate_levelup_card, generate_topxp_card, generate_xp_card

# --- Variables globales pour le cache ---
_topxp_cache: Optional[Tuple[io.BytesIO, str]] = None
_topxp_cache_time: datetime.datetime = datetime.datetime.min
_topxp_data_cache: dict = {}  # {guild_id: (data, timestamp)}

# --- Configuration Discord ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True
intents.reactions = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or('!', 'e!'), intents=intents, help_command=None)
bot.trap_words: dict[int, str] = {}
bot.blacklist_words: dict[int, set[str]] = {}

# --- IDs rôles / salons ---
ROLE_CHANNEL_ID = 1267617798658457732
ROLE_COMPETITIVE_ID = 1406762832720035891
ROLE_LFN_NEWS_ID = 1455197400560832676
ROLE_VOTES2PROFILS_ID = 1473663706100531282
ROLE_POWER_LEAGUE_ID = 1469030334510137398
ROLE_LADDER_ID = 1489956692816035840
ROLE_RANKED_ID = 1489956729104891975
ROLE_SCRIMS_ID = 1489956747555766372
ROLE_SELECT_CUSTOM_ID = "role_selector_menu"
ROLE_SELECT_VALUES = {
    "competitive": (ROLE_COMPETITIVE_ID, "Competitive"),
    "lfn_news": (ROLE_LFN_NEWS_ID, "LFN"),
    "power_league": (ROLE_POWER_LEAGUE_ID, "Power League"),
    "ladder": (ROLE_LADDER_ID, "Ladder"),
    "ranked": (ROLE_RANKED_ID, "Ranked"),
    "scrims": (ROLE_SCRIMS_ID, "Scrims"),
    "votes2profils": (ROLE_VOTES2PROFILS_ID, "Vote de Profils"),
}

# --- Rôles de niveau hardcodés ---
LEVEL_ROLES: dict[int, int] = {
    1: 1504936470849392731,
    5: 1504564311345987704,
    10: 1504564312092709005,
    15: 1504564313480761456,
    20: 1504564314693042278,
    30: 1504564315687227402,
    50: 1504564316827947069,
}

# --- XP Configuration ---
XP_PER_MESSAGE = 5
XP_PER_REACTION = 3
XP_COOLDOWN_SECONDS = 30
XP_REACT_COOLDOWN_SEC = 60
MAX_LEVEL = 99
XP_BASE_BY_LEVEL = 100
XP_GROWTH_FACTOR = 1.12

_xp_last_gain_at: dict[tuple[int, int], datetime.datetime] = {}
_xp_react_cooldown: dict[tuple[int, int, int], datetime.datetime] = {}

# --- URL Regex ---
URL_REGEX = re.compile(r"(https?://[^\s]+|www\.[^\s]+)", re.IGNORECASE)
DISCORD_INVITE_REGEX = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE)
ALLOWED_VIDEO_DOMAINS = ("youtube.com", "youtu.be", "tiktok.com")
ALLOWED_GIF_DOMAINS = ("tenor.com", "giphy.com", "discordapp.com", "discord.com")

start_time = datetime.datetime.utcnow()

# --- Initialisation ---
db.init_db()
config = db.load_config()

slow_mode_manager = SlowModeManager(bot, config.to_dict())
anti_nuke = AntiNuke(bot, config.to_dict())
anti_raid = AntiRaid(bot, config.to_dict())

_background_tasks_started = False
_role_view_added = False
_roles_view: Optional["RoleButtonsView"] = None

# --- Fonctions utilitaires ---
def _ensure_background_tasks() -> None:
    global _background_tasks_started
    if _background_tasks_started:
        return
    start_periodic_flush(bot.loop)
    register_signal_handlers(bot.loop)
    _background_tasks_started = True

def _get_roles_view() -> "RoleButtonsView":
    global _roles_view
    if _roles_view is None:
        _roles_view = RoleButtonsView(bot)
    return _roles_view

def uptime() -> str:
    delta = datetime.datetime.utcnow() - start_time
    days, remainder = divmod(delta.total_seconds(), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{int(days)}d {int(hours)}h {int(minutes)}m"

def _is_privileged_member(member: discord.Member) -> bool:
    permissions = member.guild_permissions
    return permissions.administrator or permissions.manage_guild

def _extract_blocked_links(content: str) -> list[str]:
    return [url for url in URL_REGEX.findall(content) if not _is_allowed_link(url)]

def _is_allowed_link(url: str) -> bool:
    normalized = url.lower().strip("()[]<>.,!?\"'")
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    if path.endswith((".gif", ".gifv")):
        return True
    if any(host == d or host.endswith(f".{d}") for d in ALLOWED_GIF_DOMAINS):
        return True
    return any(host == d or host.endswith(f".{d}") for d in ALLOWED_VIDEO_DOMAINS)

# --- XP Calculations ---
def _xp_required_for_next_level(level: int) -> int:
    if level < 0:
        return XP_BASE_BY_LEVEL
    return int(XP_BASE_BY_LEVEL * (XP_GROWTH_FACTOR ** level))

def _xp_total_for_level(level: int) -> int:
    if level <= 0:
        return 0
    total = 0
    for lvl in range(level):
        total += _xp_required_for_next_level(lvl)
    return total

MAX_XP = _xp_total_for_level(MAX_LEVEL)

def _xp_to_level(xp: int) -> int:
    if xp <= 0:
        return 0
    level = 0
    while level < MAX_LEVEL and xp >= _xp_total_for_level(level + 1):
        level += 1
    return level

def _xp_in_current_level(xp: int) -> tuple[int, int]:
    level = _xp_to_level(xp)
    if level >= MAX_LEVEL:
        req = _xp_required_for_next_level(MAX_LEVEL - 1)
        return req, req
    base = _xp_total_for_level(level)
    required = _xp_required_for_next_level(level)
    return max(0, xp - base), required

def _build_progress_bar(progress: int, required: int, size: int = 12) -> str:
    ratio = min(1.0, max(0.0, progress / required)) if required > 0 else 1.0
    filled = round(ratio * size)
    return f"{'█' * filled}{'░' * (size - filled)} {int(ratio * 100)}%"

# --- XP Role Management ---
def _get_level_role_for_level(level: int) -> Optional[int]:
    best = None
    for required_level in sorted(LEVEL_ROLES.keys()):
        if level >= required_level:
            best = LEVEL_ROLES[required_level]
    return best

async def _sync_level_roles_hardcoded(member: discord.Member, new_level: int) -> Optional[discord.Role]:
    guild = member.guild
    bot_member = guild.me or guild.get_member(bot.user.id)
    if bot_member is None:
        return None

    target_role_id = _get_level_role_for_level(new_level)
    granted_role = None

    roles_to_remove = [
        guild.get_role(role_id)
        for role_id in LEVEL_ROLES.values()
        if role_id != target_role_id and guild.get_role(role_id) in member.roles
    ]
    roles_to_remove = [r for r in roles_to_remove if r is not None]
    if roles_to_remove:
        try:
            await member.remove_roles(*roles_to_remove, reason="Mise à jour rôle de niveau")
        except (discord.Forbidden, discord.HTTPException):
            pass

    if target_role_id is not None:
        target_role = guild.get_role(target_role_id)
        if target_role and target_role not in member.roles:
            if not target_role.managed and target_role < bot_member.top_role:
                try:
                    await member.add_roles(target_role, reason=f"Niveau {new_level} atteint")
                    granted_role = target_role
                except (discord.Forbidden, discord.HTTPException):
                    pass
        elif target_role and target_role in member.roles:
            granted_role = target_role

    return granted_role

# --- XP Gain Functions ---
async def _grant_message_xp(message: discord.Message) -> None:
    if message.guild is None:
        return
    key = (message.guild.id, message.author.id)
    now = datetime.datetime.utcnow()
    last = _xp_last_gain_at.get(key)
    if last and (now - last).total_seconds() < XP_COOLDOWN_SECONDS:
        return

    guild_id = str(message.guild.id)
    user_id = str(message.author.id)
    current = db.get_user_xp(guild_id, user_id)
    current_xp = int(current.get('xp', 0) or 0)

    if current_xp >= MAX_XP:
        _xp_last_gain_at[key] = now
        return

    old_level = _xp_to_level(current_xp)
    new_xp = min(MAX_XP, current_xp + XP_PER_MESSAGE)
    db.set_user_xp(guild_id, user_id, str(message.author), new_xp)
    _xp_last_gain_at[key] = now

    new_level = _xp_to_level(new_xp)
    if new_level > old_level:
        await _handle_level_up(message.channel, message.author, old_level, new_level, new_xp)

async def _grant_reaction_xp(reaction: discord.Reaction, reactor: discord.Member) -> None:
    message = reaction.message
    if message.guild is None:
        return
    if reactor.bot:
        return
    author = message.author
    if author.bot:
        return
    if author.id == reactor.id:
        return

    guild_id = message.guild.id
    now = datetime.datetime.utcnow()
    ck = (guild_id, reactor.id, author.id)
    last = _xp_react_cooldown.get(ck)
    if last and (now - last).total_seconds() < XP_REACT_COOLDOWN_SEC:
        return
    _xp_react_cooldown[ck] = now

    # Increment reaction count in Supabase (silent)
    try:
        current = _get_reaction_count(guild_id, author.id)
        _increment_reaction_count(guild_id, author.id, str(author), current + 1)
    except Exception:
        pass  # Silent fail for reaction counting

    guild_id_str = str(guild_id)
    user_id_str = str(author.id)
    current = db.get_user_xp(guild_id_str, user_id_str)
    current_xp = int(current.get('xp', 0) or 0)

    if current_xp >= MAX_XP:
        return

    old_level = _xp_to_level(current_xp)
    new_xp = min(MAX_XP, current_xp + XP_PER_REACTION)
    db.set_user_xp(guild_id_str, user_id_str, str(author), new_xp)

    new_level = _xp_to_level(new_xp)
    if new_level > old_level:
        if isinstance(author, discord.Member):
            await _handle_level_up(message.channel, author, old_level, new_level, new_xp)

# --- Level Up Handler ---
async def _handle_level_up(
    channel: discord.abc.Messageable,
    member: discord.Member,
    old_level: int,
    new_level: int,
    new_xp: int,
) -> None:
    if not isinstance(member, discord.Member):
        return

    try:
        granted_role = await _sync_level_roles_hardcoded(member, new_level)
        xp_progress, xp_required = _xp_in_current_level(new_xp)

        card_buf, fname = await generate_levelup_card(
            member_name=member.display_name,
            avatar_url=str(member.display_avatar.url),
            old_level=old_level,
            new_level=new_level,
            xp_total=new_xp,
            xp_progress=xp_progress,
            xp_required=xp_required,
        )

        description = f"🎉 {member.mention} vient de passer au **niveau {new_level}** !"
        if granted_role:
            description += f"\nTu as obtenu le rôle {granted_role.mention} !"

        embed = discord.Embed(title="🆙 Level Up !", description=description, color=0x5865F2)

        if card_buf:
            embed.set_image(url=f"attachment://{fname}")
            await channel.send(embed=embed, file=discord.File(card_buf, filename=fname))
        else:
            await channel.send(embed=embed)
    except Exception:
        # Silent fail for level up cards
        try:
            await channel.send(f"🎉 {member.mention} vient de passer au **niveau {new_level}** !")
        except Exception:
            pass

# --- Reaction Count Functions (Silent) ---
def _get_reaction_count(guild_id: int, user_id: int) -> int:
    client = db._ensure_client()
    if not client:
        return 0
    try:
        resp = (
            client.table("reaction_counts")
            .select("count")
            .eq("guild_id", str(guild_id))
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        return int(resp.data[0].get("count") or 0) if resp.data else 0
    except Exception:
        return 0

def _increment_reaction_count(guild_id: int, user_id: int, user_name: str, count: int) -> None:
    client = db._ensure_client()
    if not client:
        return
    try:
        client.table("reaction_counts").upsert(
            {
                "guild_id": str(guild_id),
                "user_id": str(user_id),
                "user_name": user_name,
                "count": count,
            },
            on_conflict="guild_id,user_id",
        ).execute()
    except Exception:
        pass

def _get_top_reactions(guild_id: int, limit: int = 10) -> list[dict]:
    client = db._ensure_client()
    if not client:
        return []
    try:
        resp = (
            client.table("reaction_counts")
            .select("user_id,user_name,count")
            .eq("guild_id", str(guild_id))
            .order("count", desc=True)
            .limit(limit)
            .execute()
        )
        return resp.data or []
    except Exception:
        return []

# --- Roles Embed ---
def _build_roles_embeds(guild: Optional[discord.Guild]) -> list[discord.Embed]:
    embed_annonces = discord.Embed(
        title="Choisis tes rôles",
        description=(
            "**Les ping d'annonces**\n"
            f"🏆 <@&{ROLE_COMPETITIVE_ID}> — Competitive pour toutes les compétitions du serveur\n"
            f"📰 <@&{ROLE_LFN_NEWS_ID}> — LFN pour toutes les news sur la LFN\n"
            f"⚡ <@&{ROLE_POWER_LEAGUE_ID}> — Power League pour toutes les news sur la PL"
        ),
        color=0x5865F2,
    )
    if guild and guild.icon:
        embed_annonces.set_thumbnail(url=guild.icon.url)

    embed_teammates = discord.Embed(
        description=(
            "**Les ping teammates**\n"
            f"🎯 <@&{ROLE_LADDER_ID}> — Ladder\n"
            f"🥇 <@&{ROLE_RANKED_ID}> — Ranked\n"
            f"⚔️ <@&{ROLE_SCRIMS_ID}> — Scrims"
        ),
        color=0x5865F2,
    )

    embed_autres = discord.Embed(
        description=(
            "**Les ping autres**\n"
            f"🗳️ <@&{ROLE_VOTES2PROFILS_ID}> — Vote de Profils pour tous les 1v1 de profils ingame"
        ),
        color=0x5865F2,
    )
    embed_autres.set_footer(text="Choisis un rôle dans le menu déroulant pour l'activer/désactiver.")
    return [embed_annonces, embed_teammates, embed_autres]

def _message_has_role_buttons(message: discord.Message) -> bool:
    if not message.components:
        return False
    for row in message.components:
        for component in row.children:
            if getattr(component, "custom_id", None) == ROLE_SELECT_CUSTOM_ID:
                return True
    return False

async def _send_ephemeral(interaction: discord.Interaction, content: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True)
    else:
        await interaction.response.send_message(content, ephemeral=True)

async def _send_roles_message(source: str, guild: Optional[discord.Guild] = None) -> None:
    channel = bot.get_channel(ROLE_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(ROLE_CHANNEL_ID)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

    if not isinstance(channel, discord.TextChannel):
        return

    target_guild = guild or channel.guild
    bot_member = target_guild.me or target_guild.get_member(bot.user.id)
    if bot_member is None:
        return

    permissions = channel.permissions_for(bot_member)
    if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
        return

    try:
        async for message in channel.history(limit=50):
            if message.author == bot.user and _message_has_role_buttons(message):
                await message.delete()
                break
    except (discord.Forbidden, discord.HTTPException):
        pass

    embeds = _build_roles_embeds(target_guild)
    view = _get_roles_view()
    await channel.send(embeds=embeds, view=view)

# --- Role Selector View ---
class RoleButtonsView(discord.ui.View):
    def __init__(self, bot_instance: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot_instance

    async def _toggle_role(self, interaction: discord.Interaction, role_id: int, role_label: str) -> None:
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await _send_ephemeral(interaction, "Cette action doit être utilisée dans un serveur.")
            return

        guild = interaction.guild
        role = guild.get_role(role_id)
        if role is None:
            await _send_ephemeral(interaction, f"Le rôle **{role_label}** est introuvable.")
            return

        bot_member = guild.me or guild.get_member(self.bot.user.id)
        if bot_member is None:
            await _send_ephemeral(interaction, "Impossible de vérifier les permissions du bot.")
            return
        if not bot_member.guild_permissions.manage_roles:
            await _send_ephemeral(interaction, "Je n'ai pas la permission de gérer les rôles.")
            return
        if role.managed or role >= bot_member.top_role:
            await _send_ephemeral(interaction, "Je ne peux pas attribuer ce rôle (hiérarchie Discord).")
            return

        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Retrait via boutons de rôles")
                await _send_ephemeral(interaction, f"✅ Rôle {role.mention} retiré.")
            else:
                await member.add_roles(role, reason="Ajout via boutons de rôles")
                await _send_ephemeral(interaction, f"✨ Rôle {role.mention} ajouté.")
        except (discord.Forbidden, discord.HTTPException):
            await _send_ephemeral(interaction, "Je n'ai pas la permission de modifier ce rôle.")

    @discord.ui.select(
        custom_id=ROLE_SELECT_CUSTOM_ID,
        placeholder="🎮 Choisis un rôle à activer/désactiver",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(label="🏆 Competitive", value="competitive"),
            discord.SelectOption(label="📰 LFN", value="lfn_news"),
            discord.SelectOption(label="⚡ Power League", value="power_league"),
            discord.SelectOption(label="🎯 Ladder", value="ladder"),
            discord.SelectOption(label="🥇 Ranked", value="ranked"),
            discord.SelectOption(label="⚔️ Scrims", value="scrims"),
            discord.SelectOption(label="🗳️ Vote de Profils", value="votes2profils"),
        ],
    )
    async def role_selector(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_value = select.values[0] if select.values else None
        role_data = ROLE_SELECT_VALUES.get(selected_value or "")
        if role_data is None:
            await _send_ephemeral(interaction, "Rôle invalide sélectionné.")
            return
        role_id, role_label = role_data
        await self._toggle_role(interaction, role_id, role_label)

# --- Message Helpers ---
def _iter_message_channels(guild: discord.Guild) -> Iterable[discord.abc.Messageable]:
    seen_ids: set[int] = set()
    for channel in guild.text_channels:
        if channel.id in seen_ids:
            continue
        seen_ids.add(channel.id)
        yield channel
        for thread in channel.threads:
            if thread.id in seen_ids:
                continue
            seen_ids.add(thread.id)
            yield thread
    for thread in guild.threads:
        if thread.id in seen_ids:
            continue
        seen_ids.add(thread.id)
        yield thread

async def collect_message_stats(guild: discord.Guild, cutoff: datetime.datetime) -> tuple[int, Counter]:
    authors: set[int] = set()
    counter: Counter[int] = Counter()
    for channel in _iter_message_channels(guild):
        permissions = channel.permissions_for(guild.me)
        if not (permissions.view_channel and permissions.read_message_history):
            continue
        try:
            async for message in channel.history(limit=None, after=cutoff, oldest_first=True):
                if message.author.bot:
                    continue
                authors.add(message.author.id)
                counter[message.author.id] += 1
        except (discord.Forbidden, discord.HTTPException):
            continue
    return len(authors), counter

# --- Optimized /topxp with caching ---
async def _get_cached_topxp_data(guild_id: int) -> Optional[list]:
    """Get top XP data with 5-minute cache"""
    now = datetime.datetime.utcnow()
    cached = _topxp_data_cache.get(guild_id)
    if cached and (now - cached[1]).total_seconds() < 300:  # 5 minutes
        return cached[0]

    # Fetch fresh data
    try:
        data = db.get_top_xp(str(guild_id), limit=10)
        _topxp_data_cache[guild_id] = (data, now)
        return data
    except Exception:
        return None

@bot.tree.command(name='topxp', description='Affiche le classement XP du serveur')
async def topxp_slash(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée sur un serveur.', ephemeral=True)
        return

    await interaction.response.defer()

    try:
        # 1. Get cached data
        guild_id = interaction.guild.id
        top_entries = await _get_cached_topxp_data(guild_id)
        if not top_entries:
            await interaction.followup.send('Aucune XP enregistrée pour le moment.')
            return

        # 2. Check card cache
        global _topxp_cache, _topxp_cache_time
        now = datetime.datetime.utcnow()
        if _topxp_cache and (now - _topxp_cache_time).total_seconds() < 300:  # 5 minutes
            card_buf, fname = _topxp_cache
            await interaction.followup.send(file=discord.File(card_buf, filename=fname))
            return

        # 3. Prepare data - only fetch avatars for top 3
        enriched = []
        for idx, entry in enumerate(top_entries):
            user_id = entry.get('user_id')
            member = interaction.guild.get_member(int(user_id)) if user_id and str(user_id).isdigit() else None

            # Only fetch avatar for top 3
            avatar_url = None
            if idx < 3 and member:
                avatar_url = str(member.display_avatar.url)

            enriched.append({
                **entry,
                "user_name": member.display_name if member else (entry.get('user_name') or f'ID {user_id}'),
                "avatar_url": avatar_url,  # Only top 3 have avatars
            })

        # 4. Generate card
        card_buf, fname = await generate_topxp_card(
            guild_name=interaction.guild.name,
            entries=enriched,
            xp_to_level_fn=_xp_to_level,
        )

        # 5. Update cache
        _topxp_cache = (card_buf, fname)
        _topxp_cache_time = now

        if card_buf:
            await interaction.followup.send(file=discord.File(card_buf, filename=fname))
        else:
            # Fallback text
            lines = []
            for idx, entry in enumerate(enriched, start=1):
                xp_value = int(entry.get('xp', 0) or 0)
                level = _xp_to_level(xp_value)
                lines.append(f'**{idx}.** {entry["user_name"]} — Niveau {level} ({xp_value:,} XP)')
            embed = discord.Embed(title='🏆 Top XP du serveur', description='\n'.join(lines), color=0x5865F2)
            await interaction.followup.send(embed=embed)

    except Exception:
        await interaction.followup.send("Une erreur est survenue.", ephemeral=True)

# --- Discord Events ---
@bot.event
async def on_ready():
    global _role_view_added
    _ensure_background_tasks()
    logger.info('%s est connecté!', bot.user)

    for guild in bot.guilds:
        missing = [
            f"Niveau {lvl} (ID {rid})"
            for lvl, rid in LEVEL_ROLES.items()
            if guild.get_role(rid) is None
        ]
        if missing:
            logger.warning("Rôles de niveau introuvables dans '%s' : %s", guild.name, ", ".join(missing))
        else:
            logger.info("Tous les rôles de niveau sont présents dans '%s'.", guild.name)

    try:
        synced = await bot.tree.sync()
        logger.info("Slash commands synchronisées : %d commandes.", len(synced))
    except Exception:
        pass

    if not _role_view_added:
        bot.add_view(_get_roles_view())
        _role_view_added = True

    try:
        await _send_roles_message(source="on_ready")
    except Exception:
        pass

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    guild = message.guild
    if guild is None:
        return

    if isinstance(message.author, discord.Member) and not _is_privileged_member(message.author):
        lowered_content = message.content.lower()
        blocked_links = _extract_blocked_links(message.content)
        contains_invite = bool(DISCORD_INVITE_REGEX.search(lowered_content))
        blacklist_words = bot.blacklist_words.get(guild.id, set())
        contains_blacklisted = any(word in lowered_content for word in blacklist_words)

        if blocked_links or contains_invite or contains_blacklisted:
            try:
                await message.delete()
            except (discord.Forbidden, discord.HTTPException):
                pass
            else:
                if contains_blacklisted:
                    try:
                        await message.channel.send(
                            f"{message.author.mention} ton message a été supprimé (mot blacklisté).",
                            delete_after=6,
                        )
                        await message.author.timeout(datetime.timedelta(seconds=60), reason="Utilisation d'un mot blacklisté")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                else:
                    try:
                        await message.channel.send(
                            f"{message.author.mention} les liens web et invitations Discord sont bloqués ici.",
                            delete_after=6,
                        )
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                db.log_event(
                    'moderation', 'info', 'Message supprimé automatiquement',
                    user_id=str(message.author.id), user_name=str(message.author),
                    channel_id=str(message.channel.id), guild_id=str(guild.id),
                )
                return

    await _grant_message_xp(message)
    await bot.process_commands(message)
    try:
        await batch_logger.log({
            'type': 'message', 'level': 'info', 'message': 'Message reçu',
            'user_id': str(message.author.id), 'user_name': str(message.author),
            'channel_id': str(message.channel.id), 'guild_id': str(guild.id),
            'channel_name': message.channel.name, 'metadata': {},
        })
    except Exception:
        pass
    slow_mode_manager.handle_message(message)

    trap_word = bot.trap_words.get(guild.id)
    if trap_word and trap_word in message.content.lower():
        bot.trap_words.pop(guild.id, None)
        if not isinstance(message.author, discord.Member):
            return
        try:
            await message.author.timeout(datetime.timedelta(minutes=10), reason=f"Trap déclenché: {trap_word}")
            await message.channel.send(f"🪤 {message.author.mention} a déclenché le trap et prend 10 minutes.")
        except (discord.Forbidden, discord.HTTPException):
            pass

@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.User | discord.Member):
    if isinstance(user, discord.User):
        if reaction.message.guild is None:
            return
        try:
            user = await reaction.message.guild.fetch_member(user.id)
        except (discord.NotFound, discord.HTTPException):
            return
    await _grant_reaction_xp(reaction, user)

@bot.event
async def on_member_join(member: discord.Member):
    try:
        db.log_event('member', 'info', 'Nouveau membre',
                     user_id=str(member.id), user_name=str(member), guild_id=str(member.guild.id))
        anti_raid.handle_member_join(member)
    except Exception:
        pass

@bot.event
async def on_member_remove(member: discord.Member):
    try:
        db.log_event('member', 'info', 'Membre parti',
                     user_id=str(member.id), user_name=str(member), guild_id=str(member.guild.id))
    except Exception:
        pass

@bot.event
async def on_guild_channel_delete(channel):
    try:
        await anti_nuke.handle_channel_delete(channel)
    except Exception:
        pass

@bot.event
async def on_guild_role_delete(role):
    try:
        await anti_nuke.handle_role_delete(role)
    except Exception:
        pass

@bot.event
async def on_member_ban(guild, user):
    try:
        await anti_nuke.handle_ban(guild)
    except Exception:
        pass

@bot.event
async def on_webhooks_update(channel):
    try:
        await anti_nuke.handle_webhook_create(channel)
    except Exception:
        pass

@bot.event
async def on_guild_channel_update(before, after):
    try:
        await anti_nuke.handle_channel_update(before, after)
    except Exception:
        pass

@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    try:
        logger.error('Error: %s', error)
    except Exception:
        pass

# --- Prefix Commands ---
@bot.command(name='ping')
async def ping(ctx: commands.Context):
    await ctx.send(f'Pong! {round(bot.latency * 1000)}ms')

@bot.command(name='syncroles')
@commands.has_permissions(manage_roles=True)
async def sync_roles_cmd(ctx: commands.Context):
    if ctx.guild is None:
        return
    status_msg = await ctx.send("🔄 Synchronisation globale des rôles de niveau en cours...")
    count = 0
    for member in ctx.guild.members:
        if member.bot:
            continue
        entry = db.get_user_xp(str(ctx.guild.id), str(member.id))
        xp_value = int(entry.get('xp', 0) or 0)
        cur_level = _xp_to_level(xp_value)
        await _sync_level_roles_hardcoded(member, cur_level)
        count += 1
    await status_msg.edit(content=f"✅ Synchronisation terminée ! {count} membres mis à jour.")

@bot.command(name='blacklist')
async def blacklist_cmd(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return
    blacklist_words = bot.blacklist_words.get(ctx.guild.id, set())
    if not blacklist_words:
        embed = discord.Embed(title="📋 Liste des mots blacklistés",
                              description="Aucun mot blacklisté pour le moment.", color=0x5865F2)
        await ctx.send(embed=embed)
        return
    words_text = '\n'.join([f"• `{w}`" for w in sorted(blacklist_words)])
    embed = discord.Embed(
        title="📋 Liste des mots blacklistés",
        description=f"**Total:** {len(blacklist_words)} mot(s)\n\n{words_text}",
        color=0x5865F2,
    )
    await ctx.send(embed=embed)

@bot.command(name='rewards')
async def rewards_cmd(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return

    lines = []
    for level_threshold in sorted(LEVEL_ROLES.keys()):
        role_id = LEVEL_ROLES[level_threshold]
        role_obj = ctx.guild.get_role(role_id)
        if role_obj:
            lines.append(f"**Niveau {level_threshold}** → {role_obj.mention}")
        else:
            lines.append(f"**Niveau {level_threshold}** → <rôle introuvable ID {role_id}>")

    embed = discord.Embed(
        title="🏆 Récompenses de niveau XP",
        description="\n".join(lines),
        color=0x5865F2,
    )
    embed.set_footer(
        text=(
            f"Gagne de l'XP en envoyant des messages (+{XP_PER_MESSAGE} XP/msg, "
            f"cooldown {XP_COOLDOWN_SECONDS}s) et en recevant des réactions "
            f"(+{XP_PER_REACTION} XP/réaction)."
        )
    )
    if ctx.guild.icon:
        embed.set_thumbnail(url=ctx.guild.icon.url)
    await ctx.send(embed=embed)

@bot.command(name='xp')
async def xp_command_prefix(ctx: commands.Context, member: Optional[discord.Member] = None):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return

    target = member or ctx.author
    entry = db.get_user_xp(str(ctx.guild.id), str(target.id))
    xp_value = int(entry.get('xp', 0) or 0)
    level = _xp_to_level(xp_value)
    progress, required = _xp_in_current_level(xp_value)

    try:
        card_buf, fname = await generate_xp_card(
            member_name=target.display_name,
            avatar_url=str(target.display_avatar.url),
            level=level,
            xp_total=xp_value,
            xp_progress=progress,
            xp_required=required,
        )
        if card_buf:
            await ctx.send(file=discord.File(card_buf, filename=fname))
        else:
            progress_bar = _build_progress_bar(1, 1) if level >= MAX_LEVEL else _build_progress_bar(progress, required)
            await ctx.send(f"**{target.display_name}** — Niveau {level} | {xp_value} XP total\n{progress_bar}")
    except Exception:
        progress_bar = _build_progress_bar(1, 1) if level >= MAX_LEVEL else _build_progress_bar(progress, required)
        await ctx.send(f"**{target.display_name}** — Niveau {level} | {xp_value} XP total\n{progress_bar}")

@bot.command(name='reactlb')
async def reactlb(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return

    loop = asyncio.get_event_loop()
    entries = await loop.run_in_executor(None, lambda: _get_top_reactions(ctx.guild.id))
    if not entries:
        await ctx.send("Aucune réaction enregistrée pour le moment.")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for idx, row in enumerate(entries):
        user_id = row.get("user_id")
        count = int(row.get("count") or 0)
        member = ctx.guild.get_member(int(user_id)) if user_id and str(user_id).isdigit() else None
        name = member.display_name if member else (row.get("user_name") or f"ID {user_id}")
        prefix = medals[idx] if idx < 3 else f"**{idx + 1}.**"
        s = "s" if count > 1 else ""
        lines.append(f"{prefix} {name} — **{count}** réaction{s} reçue{s}")

    embed = discord.Embed(
        title="💬 Classement des réactions reçues",
        description="\n".join(lines),
        color=0x5865F2,
    )
    embed.set_footer(text="Données persistées — le compteur ne se remet pas à zéro au redémarrage.")
    await ctx.send(embed=embed)

@bot.command(name='securitycheck')
@commands.has_permissions(administrator=True)
async def security_check(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return
    nuke_cfg = anti_nuke.config or {}
    raid_cfg = anti_raid.config or {}
    checks = [
        ("Anti-nuke activé", bool(nuke_cfg)),
        ("Anti-raid activé", bool(raid_cfg)),
        ("Seuil suppression salons", int(nuke_cfg.get('channelDeleteLimit', 3)) > 0),
        ("Seuil suppression rôles", int(nuke_cfg.get('roleDeleteLimit', 5)) > 0),
        ("Seuil joins raid", int(raid_cfg.get('joinThreshold', 10)) > 0),
        ("Âge min compte (jours)", int(raid_cfg.get('accountAgeDays', 7)) >= 1),
    ]
    lines = [f"{'✅' if ok else '⚠️'} {label}" for label, ok in checks]
    lines.append(f"• Action punitive anti-nuke: `{nuke_cfg.get('punitiveAction', 'strip')}`")
    lines.append(f"• Lockdown auto anti-raid: `{raid_cfg.get('lockdownOnRaid', True)}`")
    lines.append(f"• Kick comptes récents: `{raid_cfg.get('kickYoungAccounts', False)}`")
    embed = discord.Embed(
        title="🛡️ Vérification sécurité anti-nuke / anti-raid",
        description='\n'.join(lines),
        color=0x2ecc71,
    )
    await ctx.send(embed=embed)

# --- Slash Commands ---
@bot.tree.command(name='help', description='Liste des commandes disponibles pour les utilisateurs')
async def help_user(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Guide de l'utilisateur",
        description="Voici les commandes que vous pouvez utiliser sur le serveur :",
        color=0x5865F2,
    )
    embed.add_field(
        name="✨ Expérience",
        value=(
            "`/xp [membre]` — Voir son niveau et son XP\n"
            "`/topxp` — Voir le classement XP du serveur\n"
            "`!xp [membre]` — Alias préfixe (image seule)\n"
            "`!rewards` — Voir tous les rôles de récompense XP\n"
            "`!reactlb` — Classement des réactions reçues"
        ),
        inline=False,
    )
    embed.add_field(
        name="⚙️ Utilitaires",
        value=(
            "`!ping` — Vérifier la latence du bot\n"
            "`!blacklist` — Voir les mots interdits sur le serveur"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Uptime : {uptime()}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='helpadmin', description='Liste des commandes réservées à l\'administration')
@app_commands.checks.has_permissions(administrator=True)
async def help_admin(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Panneau d'Administration",
        description="Commandes de gestion et de modération :",
        color=0xFF0000,
    )
    embed.add_field(
        name="🔨 Modération",
        value=(
            "`/purge [n]` — Nettoyer les messages et verrouiller le salon\n"
            "`/unpurge` — Rouvre un salon verrouillé\n"
            "`/trap [mot]` — Poser un mot piège (timeout 10 min)"
        ),
        inline=False,
    )
    embed.add_field(
        name="🚫 Blacklist",
        value=(
            "`/addblacklist [mot]` — Bloquer un mot automatiquement\n"
            "`/removeblacklist [mot]` — Débloquer un mot"
        ),
        inline=False,
    )
    embed.add_field(
        name="📊 Système XP",
        value=(
            "`!syncroles` — Synchronise les rôles de niveau de tous les membres\n"
            "`/setup_roles` — Relancer l'embed de sélection des rôles\n"
            "`/levelup` — Teste la carte LevelUp (simule un niveau up)"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛡️ Sécurité",
        value="`!securitycheck` — Vérifier la config Anti-Nuke / Anti-Raid",
        inline=False,
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='xp', description='Affiche votre niveau et votre XP (image seule)')
@app_commands.describe(membre='Membre dont vous voulez voir le profil XP')
async def xp_slash(interaction: discord.Interaction, membre: Optional[discord.Member] = None):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée sur un serveur.', ephemeral=True)
        return

    await interaction.response.defer()

    target = membre or interaction.user
    entry = db.get_user_xp(str(interaction.guild.id), str(target.id))
    xp_value = int(entry.get('xp', 0) or 0)
    level = _xp_to_level(xp_value)
    progress, required = _xp_in_current_level(xp_value)

    try:
        card_buf, fname = await generate_xp_card(
            member_name=target.display_name,
            avatar_url=str(target.display_avatar.url),
            level=level,
            xp_total=xp_value,
            xp_progress=progress,
            xp_required=required,
        )
        if card_buf:
            await interaction.followup.send(file=discord.File(card_buf, filename=fname))
        else:
            progress_bar = _build_progress_bar(1, 1) if level >= MAX_LEVEL else _build_progress_bar(progress, required)
            await interaction.followup.send(f"**{target.display_name}** — Niveau {level} | {xp_value} XP total\n{progress_bar}")
    except Exception:
        progress_bar = _build_progress_bar(1, 1) if level >= MAX_LEVEL else _build_progress_bar(progress, required)
        await interaction.followup.send(f"**{target.display_name}** — Niveau {level} | {xp_value} XP total\n{progress_bar}")

@bot.tree.command(name='levelup', description='Teste la carte LevelUp (simule un niveau up)')
@app_commands.describe(old_level='Ancien niveau', new_level='Nouveau niveau')
async def levelup_slash(interaction: discord.Interaction, old_level: int = 1, new_level: int = 2):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return

    await interaction.response.defer()

    try:
        avatar_url = str(interaction.user.display_avatar.url)
        xp_total = new_level * 1000
        xp_progress = 500
        xp_required = _xp_required_for_next_level(new_level)

        card_buf, fname = await generate_levelup_card(
            member_name=str(interaction.user),
            avatar_url=avatar_url,
            old_level=old_level,
            new_level=new_level,
            xp_total=xp_total,
            xp_progress=xp_progress,
            xp_required=xp_required,
        )

        if card_buf:
            await interaction.followup.send(file=discord.File(card_buf, filename=fname))
        else:
            await interaction.followup.send(f"Level Up de {old_level} à {new_level} !")
    except Exception:
        await interaction.followup.send("Une erreur est survenue.", ephemeral=True)

@bot.tree.command(name='setup_roles', description='Renvoie l\'embed des rôles dans le salon configuré')
async def setup_roles(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message('Permissions insuffisantes.', ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        await _send_roles_message(source=f"setup_roles:{interaction.user}")
        await interaction.followup.send("Embed des rôles envoyé avec succès.", ephemeral=True)
    except Exception:
        await interaction.followup.send("Impossible d'envoyer l'embed pour le moment.", ephemeral=True)

@bot.tree.command(name='purge', description='Nettoie les messages et verrouille le salon pour les membres')
@app_commands.describe(amount='Nombre de messages à supprimer (1-1000)', reason='Raison')
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000] = 100, reason: Optional[str] = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message('Permissions insuffisantes.', ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send('Cette commande ne peut être utilisée que dans un salon textuel.', ephemeral=True)
        return

    log_reason = reason or f'Purge demandée par {interaction.user}'
    deleted = await channel.purge(limit=amount, reason=log_reason)

    overwrite = channel.overwrites_for(interaction.guild.default_role) or discord.PermissionOverwrite()
    overwrite.send_messages = False
    overwrite.add_reactions = True
    overwrite.create_public_threads = False
    overwrite.create_private_threads = False
    overwrite.send_messages_in_threads = False
    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason='Salon verrouillé après purge')

    info_embed = discord.Embed(
        title='🔒 Salon verrouillé',
        description="Ce salon vient d'être purgé et est désormais verrouillé pour les membres.",
        color=0xffa500,
    )
    info_embed.add_field(name='Messages supprimés', value=str(len(deleted)), inline=True)
    if reason:
        info_embed.add_field(name='Raison', value=reason, inline=False)
    info_embed.set_footer(text=f'Action effectuée par {interaction.user.display_name}')

    db.add_moderation_action('purge', str(channel.id), channel.name, str(interaction.user.id), str(interaction.user), reason or '', {'messages_deleted': len(deleted)})
    try:
        db.log_event('moderation', 'info', 'Purge effectuée', user_id=str(interaction.user.id), user_name=str(interaction.user), channel_id=str(channel.id))
    except Exception:
        pass

    await channel.send(embed=info_embed)
    await interaction.followup.send(f'Purge terminée : {len(deleted)} messages supprimés.', ephemeral=True)

@bot.tree.command(name='unpurge', description='Rouvre un salon précédemment verrouillé')
@app_commands.describe(reason='Raison')
async def unpurge(interaction: discord.Interaction, reason: Optional[str] = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message('Permissions insuffisantes.', ephemeral=True)
        return
    await interaction.response.defer(thinking=True, ephemeral=True)
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.followup.send('Cette commande ne peut être utilisée que dans un salon textuel.', ephemeral=True)
        return

    overwrite = channel.overwrites_for(interaction.guild.default_role) or discord.PermissionOverwrite()
    overwrite.send_messages = True
    overwrite.add_reactions = True
    overwrite.create_public_threads = True
    overwrite.create_private_threads = True
    overwrite.send_messages_in_threads = True
    await channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason or 'Salon rouvert après unpurge')

    info_embed = discord.Embed(
        title='🔓 Salon rouvert',
        description='Les membres peuvent à nouveau envoyer des messages.',
        color=0x57F287,
    )
    if reason:
        info_embed.add_field(name='Raison', value=reason, inline=False)
    info_embed.set_footer(text=f'Action effectuée par {interaction.user.display_name}')

    db.add_moderation_action('unpurge', str(channel.id), channel.name, str(interaction.user.id), str(interaction.user), reason or '', {})
    try:
        db.log_event('moderation', 'info', 'Unpurge effectué', user_id=str(interaction.user.id), user_name=str(interaction.user), channel_id=str(channel.id))
    except Exception:
        pass

    await channel.send(embed=info_embed)
    await interaction.followup.send('Le salon est à nouveau disponible pour les membres.', ephemeral=True)

@bot.tree.command(name='trap', description='Définit un mot piégé pour mettre un membre en timeout')
@app_commands.describe(mot='Mot piégé qui déclenche un timeout')
async def trap(interaction: discord.Interaction, mot: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message('Permissions insuffisantes.', ephemeral=True)
        return
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return
    trap_word = mot.strip().lower()
    if not trap_word:
        await interaction.response.send_message('Le mot piégé ne peut pas être vide.', ephemeral=True)
        return
    bot.trap_words[interaction.guild.id] = trap_word
    try:
        db.log_event('moderation', 'info', 'Trap configuré',
                     user_id=str(interaction.user.id), user_name=str(interaction.user),
                     guild_id=str(interaction.guild.id), metadata={'mot': mot})
    except Exception:
        pass
    await interaction.response.send_message(
        f"🪤 La prochaine personne qui dit `{mot}` prend 10 minutes de timeout."
    )

@bot.tree.command(name='addblacklist', description='Ajoute un mot à supprimer automatiquement')
@app_commands.describe(mot='Mot à bloquer automatiquement')
async def addblacklist(interaction: discord.Interaction, mot: str):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return
    if not isinstance(interaction.user, discord.Member) or not _is_privileged_member(interaction.user):
        await interaction.response.send_message('Permissions insuffisantes.', ephemeral=True)
        return
    cleaned = mot.strip().lower()
    if not cleaned:
        await interaction.response.send_message('Le mot blacklisté ne peut pas être vide.', ephemeral=True)
        return
    bot.blacklist_words.setdefault(interaction.guild.id, set()).add(cleaned)
    try:
        db.log_event('moderation', 'info', 'Mot ajouté à la blacklist',
                     user_id=str(interaction.user.id), user_name=str(interaction.user),
                     guild_id=str(interaction.guild.id), metadata={'mot': cleaned})
    except Exception:
        pass
    await interaction.response.send_message(f"✅ `{cleaned}` a été ajouté à la blacklist.")

@bot.tree.command(name='removeblacklist', description='Retire un mot de la blacklist')
@app_commands.describe(mot='Mot à retirer de la blacklist')
async def removeblacklist(interaction: discord.Interaction, mot: str):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return
    if not isinstance(interaction.user, discord.Member) or not _is_privileged_member(interaction.user):
        await interaction.response.send_message('Permissions insuffisantes.', ephemeral=True)
        return
    cleaned = mot.strip().lower()
    guild_words = bot.blacklist_words.get(interaction.guild.id, set())
    if cleaned not in guild_words:
        await interaction.response.send_message(f"Le mot `{cleaned}` n'est pas dans la blacklist.", ephemeral=True)
        return
    guild_words.remove(cleaned)
    try:
        db.log_event('moderation', 'info', 'Mot retiré de la blacklist',
                     user_id=str(interaction.user.id), user_name=str(interaction.user),
                     guild_id=str(interaction.guild.id), metadata={'mot': cleaned})
    except Exception:
        pass
    await interaction.response.send_message(f"✅ `{cleaned}` a été retiré de la blacklist.", ephemeral=True)

# --- Bot Startup ---
def run_bot():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error('ERREUR: Token Discord non trouvé!')
        return
    bot.run(token)

if __name__ == '__main__':
    run_bot()
