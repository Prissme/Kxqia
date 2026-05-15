import asyncio
import datetime
import json
import logging
import os
import random
import re
from collections import Counter
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

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
from bot.level_roles import ensure_level_roles_exist, sync_level_roles
from bot.card_generator import generate_levelup_card, generate_topxp_card, generate_xp_card

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
)
logger = logging.getLogger(__name__)

# --- Discord Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.messages = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or('!', 'e!'), intents=intents, help_command=None)
bot.trap_words: dict[int, str] = {}
bot.blacklist_words: dict[int, set[str]] = {}

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
XP_PER_MESSAGE = 5
XP_COOLDOWN_SECONDS = 30
MAX_LEVEL = 99
XP_BASE_BY_LEVEL = 100
XP_GROWTH_FACTOR = 1.12
_xp_last_gain_at: dict[tuple[int, int], datetime.datetime] = {}
_background_tasks_started = False
_role_view_added = False
_roles_view: Optional["RoleButtonsView"] = None

URL_REGEX = re.compile(r"(https?://[^\s]+|www\.[^\s]+)", re.IGNORECASE)
DISCORD_INVITE_REGEX = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE)
ALLOWED_VIDEO_DOMAINS = ("youtube.com", "youtu.be", "tiktok.com")
ALLOWED_GIF_DOMAINS = (
    "tenor.com",
    "giphy.com",
    "discordapp.com",
    "discord.com",
)


def _is_privileged_member(member: discord.Member) -> bool:
    permissions = member.guild_permissions
    return permissions.administrator or permissions.manage_guild


def _is_allowed_link(url: str) -> bool:
    normalized = url.lower().strip("()[]<>.,!?\"'")
    if not normalized.startswith(("http://", "https://")):
        normalized = f"https://{normalized}"

    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()

    if path.endswith((".gif", ".gifv")):
        return True

    if any(host == domain or host.endswith(f".{domain}") for domain in ALLOWED_GIF_DOMAINS):
        return True

    return any(host == domain or host.endswith(f".{domain}") for domain in ALLOWED_VIDEO_DOMAINS)


def _extract_blocked_links(content: str) -> list[str]:
    blocked_links = []
    for raw_url in URL_REGEX.findall(content):
        if not _is_allowed_link(raw_url):
            blocked_links.append(raw_url)
    return blocked_links


start_time = datetime.datetime.utcnow()

# --- Database initialization
db.init_db()
config = db.load_config()

slow_mode_manager = SlowModeManager(bot, config.to_dict())
anti_nuke = AntiNuke(bot, config.to_dict())
anti_raid = AntiRaid(bot, config.to_dict())


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


# --- Rôles à boutons (embed + view persistante)
def uptime() -> str:
    delta = datetime.datetime.utcnow() - start_time
    days, remainder = divmod(delta.total_seconds(), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{int(days)}d {int(hours)}h {int(minutes)}m"


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
        except discord.NotFound:
            logger.error("Salon des rôles introuvable (ID %s).", ROLE_CHANNEL_ID)
            return
        except discord.Forbidden:
            logger.error("Permissions insuffisantes pour accéder au salon des rôles (%s).", ROLE_CHANNEL_ID)
            return
        except discord.HTTPException:
            logger.exception("Erreur HTTP lors de la récupération du salon des rôles.")
            return

    if not isinstance(channel, discord.TextChannel):
        logger.error("Le salon configuré pour les rôles n'est pas un salon textuel.")
        return

    target_guild = guild or channel.guild
    bot_member = target_guild.me or target_guild.get_member(bot.user.id)
    if bot_member is None:
        logger.error("Impossible de vérifier les permissions du bot pour l'envoi des rôles.")
        return
    permissions = channel.permissions_for(bot_member)
    if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
        logger.error(
            "Permissions insuffisantes pour envoyer l'embed des rôles dans %s.",
            channel.name,
        )
        return

    try:
        async for message in channel.history(limit=50):
            if message.author == bot.user and _message_has_role_buttons(message):
                await message.delete()
                logger.info("Ancien message de rôles supprimé dans %s.", channel.name)
    except discord.Forbidden:
        logger.warning("Impossible de supprimer les anciens messages de rôles (permissions manquantes).")
    except discord.HTTPException:
        logger.exception("Erreur lors de la suppression des anciens messages de rôles.")

    embeds = _build_roles_embeds(target_guild)
    view = _get_roles_view()
    await channel.send(embeds=embeds, view=view)
    logger.info("Embed des rôles envoyé (%s).", source)


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
            logger.warning("Rôle introuvable: %s", role_id)
            return

        bot_member = guild.me or guild.get_member(self.bot.user.id)
        if bot_member is None:
            await _send_ephemeral(interaction, "Impossible de vérifier les permissions du bot.")
            logger.error("Bot member introuvable pour le guild %s.", guild.id)
            return

        if not bot_member.guild_permissions.manage_roles:
            await _send_ephemeral(interaction, "Je n'ai pas la permission de gérer les rôles.")
            logger.warning("Permission Manage Roles manquante pour le bot.")
            return

        if role.managed or role >= bot_member.top_role:
            await _send_ephemeral(interaction, "Je ne peux pas attribuer ce rôle (hiérarchie Discord).")
            logger.warning("Rôle non attribuable: %s", role_id)
            return

        member = interaction.user
        try:
            if role in member.roles:
                await member.remove_roles(role, reason="Retrait via boutons de rôles")
                await _send_ephemeral(interaction, f"✅ Rôle {role.mention} retiré.")
                logger.info("Rôle %s retiré à %s.", role.name, member)
            else:
                await member.add_roles(role, reason="Ajout via boutons de rôles")
                await _send_ephemeral(interaction, f"✨ Rôle {role.mention} ajouté.")
                logger.info("Rôle %s ajouté à %s.", role.name, member)
        except discord.Forbidden:
            await _send_ephemeral(interaction, "Je n'ai pas la permission de modifier ce rôle.")
            logger.exception("Forbidden lors de la modification du rôle %s.", role_id)
        except discord.HTTPException:
            await _send_ephemeral(interaction, "Une erreur est survenue lors de la modification du rôle.")
            logger.exception("HTTPException lors de la modification du rôle %s.", role_id)

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


def _role_is_assignable(bot_member: discord.Member, role: discord.Role) -> bool:
    return not role.managed and role < bot_member.top_role


def _get_bot_member(guild: discord.Guild) -> Optional[discord.Member]:
    return guild.me or guild.get_member(bot.user.id)


# --- Discord helpers

def _iter_message_channels(guild: discord.Guild) -> Iterable[discord.abc.Messageable]:
    seen_ids = set()
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
    authors = set()
    counter: Counter[int] = Counter()
    for channel in _iter_message_channels(guild):
        permissions = channel.permissions_for(guild.me)
        if not (permissions.view_channel and permissions.read_message_history):
            continue
        async for message in channel.history(limit=None, after=cutoff, oldest_first=True):
            if message.author.bot:
                continue
            authors.add(message.author.id)
            counter[message.author.id] += 1
    return len(authors), counter


def _xp_required_for_next_level(level: int) -> int:
    """XP requis pour passer du niveau `level` au niveau `level + 1`."""
    if level < 0:
        return XP_BASE_BY_LEVEL
    return int(XP_BASE_BY_LEVEL * (XP_GROWTH_FACTOR ** level))


def _xp_total_for_level(level: int) -> int:
    """XP total cumulé nécessaire pour atteindre `level`."""
    if level <= 0:
        return 0
    total = 0
    for current_level in range(level):
        total += _xp_required_for_next_level(current_level)
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
        max_level_required = _xp_required_for_next_level(MAX_LEVEL - 1)
        return max_level_required, max_level_required
    base = _xp_total_for_level(level)
    required = _xp_required_for_next_level(level)
    return max(0, xp - base), required


def _build_progress_bar(progress: int, required: int, size: int = 12) -> str:
    if required <= 0:
        ratio = 1.0
    else:
        ratio = min(1.0, max(0.0, progress / required))
    filled = round(ratio * size)
    return f"{'█' * filled}{'░' * (size - filled)} {int(ratio * 100)}%"


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
        if isinstance(message.author, discord.Member):
            granted_role = await sync_level_roles(message.author, new_level, old_level)

            # --- Card stylée ---
            xp_progress, xp_required = _xp_in_current_level(new_xp)
            card_buf = await generate_levelup_card(
                member_name=message.author.display_name,
                avatar_url=str(message.author.display_avatar.url),
                old_level=old_level,
                new_level=new_level,
                xp_total=new_xp,
                xp_progress=xp_progress,
                xp_required=xp_required,
            )

            description = f"🎉 {message.author.mention} vient de passer au **niveau {new_level}** !"
            if granted_role:
                description += f"\nTu as obtenu le rôle {granted_role.mention} !"

            embed = discord.Embed(
                title="🆙 Level Up !",
                description=description,
                color=0x5865F2
            )

            if card_buf:
                file = discord.File(card_buf, filename="levelup.png")
                embed.set_image(url="attachment://levelup.png")
                await message.channel.send(embed=embed, file=file)
            else:
                await message.channel.send(embed=embed)
        else:
            embed = discord.Embed(
                title="🆙 Level Up !",
                description=f"🎉 {message.author.mention} vient de passer au **niveau {new_level}** !",
                color=0x5865F2
            )
            await message.channel.send(embed=embed)


# --- Discord events and commands
@bot.event
async def on_ready():
    global _role_view_added
    _ensure_background_tasks()
    logger.info('%s est connecté!', bot.user)

    for guild in bot.guilds:
        try:
            await ensure_level_roles_exist(guild)
            logger.info("Rôles de niveau vérifiés/créés pour %s", guild.name)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erreur lors de la création des rôles de niveau pour %s : %s", guild.name, exc)

    try:
        await bot.tree.sync()
    except Exception as exc:  # noqa: BLE001
        logger.exception('Sync des commandes échouée: %s', exc)
    
    if not _role_view_added:
        bot.add_view(_get_roles_view())
        _role_view_added = True
        logger.info("View persistante des rôles enregistrée.")
        
    try:
        await _send_roles_message(source="on_ready")
    except discord.HTTPException:
        logger.exception("Erreur lors de l'envoi automatique de l'embed des rôles.")


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Crée les rôles de niveau dès que le bot rejoint un nouveau serveur."""
    try:
        await ensure_level_roles_exist(guild)
        logger.info("Rôles de niveau créés pour le nouveau serveur %s", guild.name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erreur lors de la création des rôles de niveau pour %s : %s", guild.name, exc)


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
        contains_discord_invite = bool(DISCORD_INVITE_REGEX.search(lowered_content))
        blacklist_words = bot.blacklist_words.get(guild.id, set())
        contains_blacklisted_word = any(word in lowered_content for word in blacklist_words)

        if blocked_links or contains_discord_invite or contains_blacklisted_word:
            try:
                await message.delete()
            except discord.Forbidden:
                logger.warning("Impossible de supprimer un message bloqué (permissions manquantes).")
            except discord.HTTPException:
                logger.warning("Échec suppression message bloqué (HTTPException).")
            else:
                if contains_blacklisted_word:
                    await message.channel.send(
                        f"{message.author.mention} ton message a été supprimé (mot blacklisté).",
                        delete_after=6,
                    )
                    try:
                        await message.author.timeout(datetime.timedelta(seconds=60), reason="Utilisation d'un mot blacklisté")
                    except discord.Forbidden:
                        logger.warning(f"Impossible de timeout {message.author} (permissions manquantes).")
                    except discord.HTTPException:
                        logger.warning(f"Échec du timeout pour {message.author} (HTTPException).")
                else:
                    await message.channel.send(
                        f"{message.author.mention} les liens web et invitations Discord sont bloqués ici.",
                        delete_after=6,
                    )
                db.log_event(
                    'moderation',
                    'info',
                    'Message supprimé automatiquement',
                    user_id=str(message.author.id),
                    user_name=str(message.author),
                    channel_id=str(message.channel.id),
                    guild_id=str(guild.id),
                    metadata={
                        'contains_discord_invite': contains_discord_invite,
                        'blocked_links': blocked_links,
                        'contains_blacklisted_word': contains_blacklisted_word,
                    },
                )
                return

    await _grant_message_xp(message)
    await bot.process_commands(message)
    await batch_logger.log(
        {
            'type': 'message',
            'level': 'info',
            'message': 'Message reçu',
            'user_id': str(message.author.id),
            'user_name': str(message.author),
            'channel_id': str(message.channel.id),
            'guild_id': str(guild.id),
            'channel_name': message.channel.name,
            'metadata': {},
        }
    )
    slow_mode_manager.handle_message(message)
    trap_word = bot.trap_words.get(guild.id)
    if trap_word and trap_word in message.content.lower():
        bot.trap_words.pop(guild.id, None)
        if not isinstance(message.author, discord.Member):
            return
        try:
            await message.author.timeout(datetime.timedelta(minutes=10), reason=f"Trap déclenché: {trap_word}")
        except discord.Forbidden:
            await message.channel.send("Je n'ai pas la permission de mettre ce membre en timeout.")
            return
        except discord.HTTPException:
            await message.channel.send("Impossible d'appliquer le timeout pour le moment.")
            return
        await message.channel.send(f"🪤 {message.author.mention} a déclenché le trap et prend 10 minutes.")


@bot.event
async def on_member_join(member: discord.Member):
    db.log_event(
        'member',
        'info',
        'Nouveau membre',
        user_id=str(member.id),
        user_name=str(member),
        guild_id=str(member.guild.id),
    )
    anti_raid.handle_member_join(member)


@bot.event
async def on_member_remove(member: discord.Member):
    db.log_event(
        'member',
        'info',
        'Membre parti',
        user_id=str(member.id),
        user_name=str(member),
        guild_id=str(member.guild.id),
    )


@bot.event
async def on_guild_channel_delete(channel):
    await anti_nuke.handle_channel_delete(channel)


@bot.event
async def on_guild_role_delete(role):
    await anti_nuke.handle_role_delete(role)


@bot.event
async def on_member_ban(guild, user):
    await anti_nuke.handle_ban(guild)


@bot.event
async def on_webhooks_update(channel):
    await anti_nuke.handle_webhook_create(channel)


@bot.event
async def on_guild_channel_update(before, after):
    await anti_nuke.handle_channel_update(before, after)


@bot.command(name='ping')
async def ping(ctx: commands.Context):
    await ctx.send(f'Pong! {round(bot.latency * 1000)}ms')


@bot.command(name='syncroles')
@commands.has_permissions(manage_roles=True)
async def sync_roles_cmd(ctx: commands.Context):
    """Commande manuelle pour synchroniser les rôles XP de tous les membres."""
    if ctx.guild is None: return
    
    status_msg = await ctx.send("🔄 Synchronisation globale des rôles de niveau en cours... Cela peut prendre un moment.")
    
    count = 0
    # On itère sur tous les membres (nécessite l'intent members)
    for member in ctx.guild.members:
        if member.bot: continue
        
        entry = db.get_user_xp(str(ctx.guild.id), str(member.id))
        xp_value = int(entry.get('xp', 0) or 0)
        current_level = _xp_to_level(xp_value)
        
        if current_level > 0:
            # On force la synchro (old_level=0 pour s'assurer qu'il check tout l'historique)
            await sync_level_roles(member, current_level, 0)
            count += 1
            
    await status_msg.edit(content=f"✅ Synchronisation terminée ! {count} membres mis à jour.")


@bot.command(name='blacklist')
async def blacklist_cmd(ctx: commands.Context):
    """Affiche la liste des mots blacklistés du serveur."""
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return

    blacklist_words = bot.blacklist_words.get(ctx.guild.id, set())

    if not blacklist_words:
        embed = discord.Embed(
            title="📋 Liste des mots blacklistés",
            description="Aucun mot blacklisté pour le moment.",
            color=0x5865F2,
        )
        await ctx.send(embed=embed)
        return

    sorted_words = sorted(list(blacklist_words))
    words_text = '\n'.join([f"• `{word}`" for word in sorted_words])

    embed = discord.Embed(
        title="📋 Liste des mots blacklistés",
        description=f"**Total:** {len(blacklist_words)} mot(s)\n\n{words_text}",
        color=0x5865F2,
    )
    await ctx.send(embed=embed)


@bot.tree.command(name='removeblacklist', description='Retire un mot de la blacklist')
@app_commands.describe(mot='Mot à retirer de la blacklist')
async def removeblacklist(interaction: discord.Interaction, mot: str):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return

    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message('Impossible de vérifier tes permissions.', ephemeral=True)
        return

    if not _is_privileged_member(interaction.user):
        await interaction.response.send_message(
            'Tu dois être administrateur ou avoir la permission Gérer le serveur.',
            ephemeral=True,
        )
        return

    cleaned = mot.strip().lower()
    if not cleaned:
        await interaction.response.send_message('Le mot ne peut pas être vide.', ephemeral=True)
        return

    guild_words = bot.blacklist_words.get(interaction.guild.id, set())

    if cleaned not in guild_words:
        await interaction.response.send_message(f"Le mot `{cleaned}` n'est pas dans la blacklist.", ephemeral=True)
        return

    guild_words.remove(cleaned)
    db.log_event(
        'moderation',
        'info',
        'Mot retiré de la blacklist',
        user_id=str(interaction.user.id),
        user_name=str(interaction.user),
        channel_id=str(interaction.channel.id) if interaction.channel else None,
        guild_id=str(interaction.guild.id),
        metadata={'mot': cleaned},
    )
    await interaction.response.send_message(f"✅ `{cleaned}` a été retiré de la blacklist.", ephemeral=True)


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


@bot.command(name='xp')
async def xp_command(ctx: commands.Context, member: Optional[discord.Member] = None):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return

    target = member or ctx.author
    entry = db.get_user_xp(str(ctx.guild.id), str(target.id))
    xp_value = int(entry.get('xp', 0) or 0)
    level = _xp_to_level(xp_value)
    progress, required = _xp_in_current_level(xp_value)

    # Génération de l'image de la carte d'XP avec Pillow
    card_buf = await generate_xp_card(
        member_name=target.display_name,
        avatar_url=str(target.display_avatar.url),
        level=level,
        xp_total=xp_value,
        xp_progress=progress,
        xp_required=required,
    )

    embed = discord.Embed(
        title=f'XP de {target.display_name}',
        color=0x5865F2,
    )
    
    if card_buf:
        file = discord.File(card_buf, filename="xp_card.png")
        embed.set_image(url="attachment://xp_card.png")
        await ctx.send(embed=embed, file=file)
    else:
        # Fallback si Pillow n'arrive pas à générer l'image
        if level >= MAX_LEVEL:
            progress_text = 'Niveau max atteint (99)'
            progress_bar = _build_progress_bar(1, 1)
        else:
            progress_text = f'{progress}/{required} XP vers le niveau {level + 1}'
            progress_bar = _build_progress_bar(progress, required)

        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name='Niveau', value=str(level), inline=True)
        embed.add_field(name='XP total', value=f'{xp_value}/{MAX_XP}', inline=True)
        embed.add_field(name='Progression', value=progress_text, inline=False)
        embed.add_field(name='Barre de niveau', value=progress_bar, inline=False)
        await ctx.send(embed=embed)


@bot.command(name='topxp')
async def topxp_command(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return

    top_entries = db.get_top_xp(str(ctx.guild.id), limit=10)
    if not top_entries:
        await ctx.send('Aucune XP enregistrée pour le moment.')
        return

    enriched = []
    for entry in top_entries:
        user_id = entry.get('user_id')
        member = ctx.guild.get_member(int(user_id)) if user_id and str(user_id).isdigit() else None
        enriched.append({
            **entry,
            "user_name": member.display_name if member else (entry.get('user_name') or f'ID {user_id}'),
            "avatar_url": str(member.display_avatar.url) if member else None,
        })

    card_buf = await generate_topxp_card(
        guild_name=ctx.guild.name,
        entries=enriched,
        xp_to_level_fn=_xp_to_level,
    )

    if card_buf:
        file = discord.File(card_buf, filename="topxp.png")
        await ctx.send(file=file)
    else:
        lines = []
        for index, entry in enumerate(enriched, start=1):
            xp_value = int(entry.get('xp', 0) or 0)
            level = _xp_to_level(xp_value)
            lines.append(f'**{index}.** {entry["user_name"]} — Niveau {level} ({xp_value} XP)')
        embed = discord.Embed(
            title='🏆 Top XP du serveur',
            description='\n'.join(lines),
            color=0x5865F2,
        )
        await ctx.send(embed=embed)


@bot.tree.command(name='help', description='Liste des commandes disponibles pour les utilisateurs')
async def help_user(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Guide de l'utilisateur",
        description="Voici les commandes que vous pouvez utiliser sur le serveur :",
        color=0x5865F2
    )
    embed.add_field(name="✨ Expérience", value="`/xp [membre]` : Voir son niveau.\n`/topxp` : Voir le classement.", inline=False)
    embed.add_field(name="⚙️ Utilitaires", value="`!ping` : Vérifier la latence.\n`!blacklist` : Voir les mots interdits.", inline=False)
    embed.set_footer(text=f"Version du bot active | Uptime : {uptime()}")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name='helpadmin', description='Liste des commandes réservées à l\'administration')
@app_commands.checks.has_permissions(administrator=True)
async def help_admin(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛡️ Panneau d'Administration",
        description="Commandes de gestion et de modération :",
        color=0xFF0000
    )
    embed.add_field(name="🔨 Modération", value="`/purge [n]` : Nettoyer et lock le salon.\n`/unpurge` : Unlock le salon.\n`/trap [mot]` : Poser un piège.", inline=False)
    embed.add_field(name="🚫 Blacklist", value="`/addblacklist [mot]` : Bloquer un mot.\n`/removeblacklist [mot]` : Débloquer un mot.", inline=False)
    embed.add_field(name="📊 Système XP", value="`!syncroles` : Synchronise les rôles de tout le monde.\n`/setup_roles` : Relancer l'embed des rôles.", inline=False)
    embed.add_field(name="🛡️ Sécurité", value="`!securitycheck` : Vérifier l'Anti-Nuke / Anti-Raid.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name='setup_roles', description='Renvoie l\'embed des rôles dans le salon configuré')
async def setup_roles(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return
    if not interaction.user.guild_permissions.manage_roles:
        await interaction.response.send_message('Permissions insuffisantes pour utiliser cette commande.', ephemeral=True)
        return

    await interaction.response.defer(thinking=True, ephemeral=True)
    try:
        await _send_roles_message(source=f"setup_roles:{interaction.user}")
        await interaction.followup.send("Embed des rôles envoyé avec succès.", ephemeral=True)
    except discord.HTTPException:
        logger.exception("Erreur lors de l'envoi manuel de l'embed des rôles.")
        await interaction.followup.send("Impossible d'envoyer l'embed pour le moment.", ephemeral=True)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return
    logger.error('Error: %s', error)


@bot.tree.command(name='purge', description='Nettoie les messages et verrouille le salon pour les membres')
@app_commands.describe(amount='Nombre de messages à supprimer (1-1000)', reason='Raison affichée dans le journal')
async def purge(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000] = 100, reason: Optional[str] = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message('Permissions insuffisantes pour utiliser cette commande.', ephemeral=True)
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
        description=(
            "Ce salon vient d'être purgé et est désormais verrouillé pour les membres.\n"
            "Seuls les administrateurs peuvent y écrire."
        ),
        color=0xffa500
    )
    info_embed.add_field(name='Messages supprimés', value=str(len(deleted)), inline=True)
    if reason:
        info_embed.add_field(name='Raison', value=reason, inline=False)
    info_embed.set_footer(text=f'Action effectuée par {interaction.user.display_name}')

    db.add_moderation_action('purge', str(channel.id), channel.name, str(interaction.user.id), str(interaction.user), reason or '', {'messages_deleted': len(deleted)})
    db.log_event('moderation', 'info', 'Purge effectuée', user_id=str(interaction.user.id), user_name=str(interaction.user), channel_id=str(channel.id), metadata={'messages_deleted': len(deleted)})

    await channel.send(embed=info_embed)
    await interaction.followup.send(f'Purge terminée : {len(deleted)} messages supprimés.', ephemeral=True)


@bot.tree.command(name='unpurge', description='Rouvre un salon précédemment verrouillé')
@app_commands.describe(reason='Raison affichée dans le journal')
async def unpurge(interaction: discord.Interaction, reason: Optional[str] = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message('Permissions insuffisantes pour utiliser cette commande.', ephemeral=True)
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
        description='Les membres peuvent à nouveau envoyer des messages et créer des fils.',
        color=0x57F287
    )
    if reason:
        info_embed.add_field(name='Raison', value=reason, inline=False)
    info_embed.set_footer(text=f'Action effectuée par {interaction.user.display_name}')

    db.add_moderation_action('unpurge', str(channel.id), channel.name, str(interaction.user.id), str(interaction.user), reason or '', {})
    db.log_event('moderation', 'info', 'Unpurge effectué', user_id=str(interaction.user.id), user_name=str(interaction.user), channel_id=str(channel.id))

    await channel.send(embed=info_embed)
    await interaction.followup.send('Le salon est à nouveau disponible pour les membres.', ephemeral=True)


@bot.tree.command(name='trap', description='Définit un mot piégé pour mettre un membre en timeout')
@app_commands.describe(mot='Mot piégé qui déclenche un timeout')
async def trap(interaction: discord.Interaction, mot: str):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message('Permissions insuffisantes pour utiliser cette commande.', ephemeral=True)
        return

    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return

    trap_word = mot.strip().lower()
    if not trap_word:
        await interaction.response.send_message('Le mot piégé ne peut pas être vide.', ephemeral=True)
        return

    bot.trap_words[interaction.guild.id] = trap_word
    db.log_event(
        'moderation',
        'info',
        'Trap configuré',
        user_id=str(interaction.user.id),
        user_name=str(interaction.user),
        channel_id=str(interaction.channel.id) if interaction.channel else None,
        guild_id=str(interaction.guild.id),
        metadata={'mot': mot},
    )
    await interaction.response.send_message(
        f"🪤 La prochaine personne qui dit '{mot}' prend 10 minutes de timeout."
    )


@bot.tree.command(name='addblacklist', description='Ajoute un mot à supprimer automatiquement')
@app_commands.describe(mot='Mot à bloquer automatiquement')
async def addblacklist(interaction: discord.Interaction, mot: str):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return
    if not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message('Impossible de vérifier tes permissions.', ephemeral=True)
        return
    if not _is_privileged_member(interaction.user):
        await interaction.response.send_message(
            'Tu dois être administrateur ou avoir la permission Gérer le serveur.',
            ephemeral=True,
        )
        return

    cleaned = mot.strip().lower()
    if not cleaned:
        await interaction.response.send_message('Le mot blacklisté ne peut pas être vide.', ephemeral=True)
        return

    guild_words = bot.blacklist_words.setdefault(interaction.guild.id, set())
    guild_words.add(cleaned)
    db.log_event(
        'moderation',
        'info',
        'Mot ajouté à la blacklist',
        user_id=str(interaction.user.id),
        user_name=str(interaction.user),
        channel_id=str(interaction.channel.id) if interaction.channel else None,
        guild_id=str(interaction.guild.id),
        metadata={'mot': cleaned},
    )
    await interaction.response.send_message(f"✅ `{cleaned}` a été ajouté à la blacklist.")


def run_bot():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error('ERREUR: Token Discord non trouvé!')
        return
    bot.run(token)


if __name__ == '__main__':
    run_bot()
