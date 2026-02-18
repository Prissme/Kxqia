import asyncio
import datetime
import json
import logging
import os
import threading
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, jsonify, render_template, request, send_file
from flask_socketio import SocketIO

from database import db
from database.batch_manager import (
    batch_logger,
    register_signal_handlers,
    start_periodic_flush,
    stats_cache,
)
from database.models import Config
from bot.anti_nuke import AntiNuke
from bot.anti_raid import AntiRaid
from bot.custom_voice import CustomVoiceManager
from bot.trust_levels import get_trust_level, is_trusted
from bot.slow_mode import SlowModeManager

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s',
)
logger = logging.getLogger(__name__)
for noisy_logger in ("httpx", "engineio", "socketio"):
    logging.getLogger(noisy_logger).setLevel(logging.WARNING)

# --- Discord Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True
intents.messages = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or('!', 'e!'), intents=intents, help_command=None)
bot.trap_words: dict[int, str] = {}
custom_voice_manager = CustomVoiceManager(bot)
bot_status = {'ready': False}
LEGACY_VOTESTAFF_ROLE_ID = 1236738451018223768
CREDIT_REWARD_ROLE_ID = 1236739808844320829
CREDIT_DEFAULT = 5
CREDIT_PROMO_THRESHOLD = 10
ROLE_CHANNEL_ID = 1267617798658457732
ROLE_SCRIMS_ID = 1451687979189014548
ROLE_COMPETITIVE_ID = 1406762832720035891
ROLE_LFN_NEWS_ID = 1455197400560832676
ROLE_LFN_TEAM_ID = 1454475274296099058
ROLE_POWER_LEAGUE_ID = 1469030334510137398
ROLE_BUTTON_IDS = {
    "role_button_scrims",
    "role_button_competitive",
    "role_button_lfn_news",
    "role_button_lfn_team",
    "role_button_power_league",
}
_background_tasks_started = False
_role_view_added = False
_roles_view: Optional["RoleButtonsView"] = None

# --- Flask + SocketIO
app = Flask(__name__, template_folder='dashboard/templates', static_folder='dashboard/static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'change-me')
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

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


def _build_roles_embed(guild: Optional[discord.Guild]) -> discord.Embed:
    embed = discord.Embed(
        title="🎮 Choisis ton mode de jeu !",
        description=(
            "Sélectionne le rôle qui correspond à ta vibe et commence à jouer.\n\n"
            f"⚔️ <@&{ROLE_SCRIMS_ID}> — Pour les joueurs qui veulent grind le ladder.\n"
            f"🏆 <@&{ROLE_COMPETITIVE_ID}> — Pour les équipes et tournois sérieux.\n"
            f"📰 <@&{ROLE_LFN_NEWS_ID}> — Toutes les news intéressantes sur la LFN.\n"
            f"🤝 <@&{ROLE_LFN_TEAM_ID}> — Recherche équipe LFN.\n"
            f"⚡ <@&{ROLE_POWER_LEAGUE_ID}> — Pour s'inscrire à la Power League du serveur."
        ),
        color=0x5865F2,
    )
    embed.set_footer(text="Clique sur un bouton pour activer/désactiver ton rôle.")
    if guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


def _message_has_role_buttons(message: discord.Message) -> bool:
    if not message.components:
        return False
    for row in message.components:
        for component in row.children:
            if getattr(component, "custom_id", None) in ROLE_BUTTON_IDS:
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

    embed = _build_roles_embed(target_guild)
    view = _get_roles_view()
    await channel.send(embed=embed, view=view)
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

    @discord.ui.button(
        label="⚔️ Scrims / Ranked",
        style=discord.ButtonStyle.primary,
        custom_id="role_button_scrims",
    )
    async def scrims_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._toggle_role(interaction, ROLE_SCRIMS_ID, "Scrims / Ranked")

    @discord.ui.button(
        label="🏆 Competitive",
        style=discord.ButtonStyle.success,
        custom_id="role_button_competitive",
    )
    async def competitive_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._toggle_role(interaction, ROLE_COMPETITIVE_ID, "Competitive")

    @discord.ui.button(
        label="📰 LFN",
        style=discord.ButtonStyle.secondary,
        custom_id="role_button_lfn_news",
    )
    async def lfn_news_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._toggle_role(interaction, ROLE_LFN_NEWS_ID, "LFN")

    @discord.ui.button(
        label="🤝 LFN team",
        style=discord.ButtonStyle.secondary,
        custom_id="role_button_lfn_team",
    )
    async def lfn_team_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._toggle_role(interaction, ROLE_LFN_TEAM_ID, "LFN team")

    @discord.ui.button(
        label="⚡ Power League",
        style=discord.ButtonStyle.danger,
        custom_id="role_button_power_league",
    )
    async def power_league_button(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self._toggle_role(interaction, ROLE_POWER_LEAGUE_ID, "Power League")


def _role_is_assignable(bot_member: discord.Member, role: discord.Role) -> bool:
    return not role.managed and role < bot_member.top_role


def _get_bot_member(guild: discord.Guild) -> Optional[discord.Member]:
    return guild.me or guild.get_member(bot.user.id)


def _get_credit_roles(guild: discord.Guild) -> tuple[Optional[discord.Role], Optional[discord.Role]]:
    legacy_role = guild.get_role(LEGACY_VOTESTAFF_ROLE_ID)
    reward_role = guild.get_role(CREDIT_REWARD_ROLE_ID)
    return legacy_role, reward_role


async def _sync_credit_roles(member: discord.Member, credits: int) -> list[str]:
    guild = member.guild
    updates: list[str] = []
    bot_member = _get_bot_member(guild)
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        return ["Permissions insuffisantes pour gérer les rôles."]

    legacy_role, reward_role = _get_credit_roles(guild)

    if legacy_role and _role_is_assignable(bot_member, legacy_role):
        if credits <= 0 and legacy_role in member.roles:
            try:
                await member.remove_roles(legacy_role, reason="Crédits épuisés")
                updates.append("Rôle legacy retiré (crédits à 0).")
            except discord.Forbidden:
                updates.append("Permissions insuffisantes pour retirer le rôle legacy.")
            except discord.HTTPException:
                updates.append("Impossible de retirer le rôle legacy pour le moment.")
        elif credits > 0 and legacy_role not in member.roles:
            try:
                await member.add_roles(legacy_role, reason="Crédits attribués")
                updates.append("Rôle legacy ajouté.")
            except discord.Forbidden:
                updates.append("Permissions insuffisantes pour ajouter le rôle legacy.")
            except discord.HTTPException:
                updates.append("Impossible d'ajouter le rôle legacy pour le moment.")
    elif legacy_role is None:
        updates.append("Rôle legacy introuvable.")
    else:
        updates.append("Rôle legacy non attribuable (hiérarchie Discord).")

    if reward_role and _role_is_assignable(bot_member, reward_role):
        if credits >= CREDIT_PROMO_THRESHOLD and reward_role not in member.roles:
            try:
                await member.add_roles(reward_role, reason="Crédits atteints")
                updates.append("Rôle récompense ajouté (10 crédits).")
            except discord.Forbidden:
                updates.append("Permissions insuffisantes pour ajouter le rôle récompense.")
            except discord.HTTPException:
                updates.append("Impossible d'ajouter le rôle récompense pour le moment.")
    elif reward_role is None:
        updates.append("Rôle récompense introuvable.")
    else:
        updates.append("Rôle récompense non attribuable (hiérarchie Discord).")

    return updates


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


# --- Discord events and commands
@bot.event
async def on_ready():
    global _role_view_added
    _ensure_background_tasks()
    bot_status['ready'] = True
    logger.info('%s est connecté!', bot.user)
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
    try:
        await custom_voice_manager.initialize()
        logger.info("Système de vocaux personnalisés initialisé")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erreur lors de l'initialisation des vocaux: %s", exc)
    for guild in bot.guilds:
        db.record_daily_stats(date_value=datetime.date.today(), guild_id=str(guild.id), members_total=guild.member_count)
    socketio.emit('bot_status', {
        'status': 'online',
        'latency': round(bot.latency * 1000, 2) if bot.latency else None,
        'guilds': len(bot.guilds),
    })


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    await bot.process_commands(message)
    guild = message.guild
    if guild is None:
        return
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
    stats_cache.increment(
        date_value=datetime.date.today(),
        guild_id=str(guild.id),
        members_total=guild.member_count,
        messages_sent=1,
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
    db.record_daily_stats(
        date_value=datetime.date.today(),
        guild_id=str(member.guild.id),
        members_total=member.guild.member_count,
        members_joined=1,
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
    db.record_daily_stats(
        date_value=datetime.date.today(),
        guild_id=str(member.guild.id),
        members_total=member.guild.member_count,
        members_left=1,
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


@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Gère la création et suppression automatique de salons vocaux personnalisés."""
    try:
        await custom_voice_manager.handle_voice_state_update(member, before, after)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erreur dans le gestionnaire de vocaux: %s", exc)


@bot.command(name='help')
async def help_command(ctx: commands.Context):
    embed = discord.Embed(
        title='Commandes du Bot',
        description=(
            '**Modération:**\n'
            '`/purge` - Nettoyer et verrouiller un salon\n'
            '`/unpurge` - Rouvrir un salon verrouillé\n'
            '`!guidetest @membre` - Ajouter le rôle legacy et 5 crédits\n'
            '`e!addcredit @membre <raison>` - Ajouter un crédit\n'
            '`e!removecredit @membre <raison>` - Retirer un crédit\n'
            '`e!credits [@membre]` - Voir le solde et l’historique des crédits\n'
            '`e!clb` - Classement des staff par crédits\n\n'
            '**Analytics:**\n'
            '`/stats_last_3_months` - Auteurs uniques sur les 3 derniers mois\n'
            '`/stats_messages` - Classement par nombre de messages sur une période\n\n'
            '**Utilitaires:**\n'
            '`!ping` - Vérifier la latence du bot'
        ),
        color=0x5865F2
    )
    await ctx.send(embed=embed)


@bot.command(name='ping')
async def ping(ctx: commands.Context):
    await ctx.send(f'Pong! {round(bot.latency * 1000)}ms')


@bot.command(name='guidetest')
@commands.has_permissions(administrator=True)
async def guidetest(ctx: commands.Context, member: discord.Member):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return

    bot_member = _get_bot_member(ctx.guild)
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        await ctx.send("Je n'ai pas la permission de gérer les rôles.")
        return

    legacy_role, _ = _get_credit_roles(ctx.guild)
    if legacy_role is None:
        await ctx.send("Le rôle legacy est introuvable.")
        return
    if not _role_is_assignable(bot_member, legacy_role):
        await ctx.send("Je ne peux pas attribuer le rôle legacy (hiérarchie Discord).")
        return

    db.set_user_credits(str(ctx.guild.id), str(member.id), CREDIT_DEFAULT)
    if legacy_role not in member.roles:
        try:
            await member.add_roles(legacy_role, reason="Ajout via !guidetest")
        except discord.Forbidden:
            await ctx.send("Permissions insuffisantes pour attribuer le rôle legacy.")
            return
        except discord.HTTPException:
            await ctx.send("Impossible d'attribuer le rôle legacy pour le moment.")
            return

    updates = await _sync_credit_roles(member, CREDIT_DEFAULT)
    updates_text = f"\nMises à jour rôles: {', '.join(updates)}" if updates else ""
    db.record_credit_change(
        guild_id=str(ctx.guild.id),
        user_id=str(member.id),
        user_name=str(member),
        delta=CREDIT_DEFAULT,
        total=CREDIT_DEFAULT,
        reason="Ajout via !guidetest",
        actor_id=str(ctx.author.id),
        actor_name=str(ctx.author),
    )
    await ctx.send(f"✅ {member.mention} a reçu {CREDIT_DEFAULT} crédits.{updates_text}")


@bot.command(name='addcredit')
@commands.has_permissions(administrator=True)
async def addcredit(ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return
    if reason is None or not reason.strip():
        await ctx.send('Merci de fournir une raison : `e!addcredit @membre <raison>`.')
        return

    new_credits = db.increment_user_credits(str(ctx.guild.id), str(member.id), 1)
    updates = await _sync_credit_roles(member, new_credits)
    updates_text = f"\nMises à jour rôles: {', '.join(updates)}" if updates else ""
    db.record_credit_change(
        guild_id=str(ctx.guild.id),
        user_id=str(member.id),
        user_name=str(member),
        delta=1,
        total=new_credits,
        reason=reason.strip(),
        actor_id=str(ctx.author.id),
        actor_name=str(ctx.author),
    )
    await ctx.send(
        f"✅ {member.mention} gagne 1 crédit (total: {new_credits}). Raison : {reason.strip()}.{updates_text}"
    )


@bot.command(name='removecredit')
@commands.has_permissions(administrator=True)
async def removecredit(ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return
    if reason is None or not reason.strip():
        await ctx.send('Merci de fournir une raison : `e!removecredit @membre <raison>`.')
        return

    new_credits = db.increment_user_credits(str(ctx.guild.id), str(member.id), -1)
    updates = await _sync_credit_roles(member, new_credits)
    updates_text = f"\nMises à jour rôles: {', '.join(updates)}" if updates else ""
    db.record_credit_change(
        guild_id=str(ctx.guild.id),
        user_id=str(member.id),
        user_name=str(member),
        delta=-1,
        total=new_credits,
        reason=reason.strip(),
        actor_id=str(ctx.author.id),
        actor_name=str(ctx.author),
    )
    await ctx.send(
        f"⚠️ {member.mention} perd 1 crédit (total: {new_credits}). Raison : {reason.strip()}.{updates_text}"
    )


@bot.command(name='credits')
async def credits(ctx: commands.Context, member: Optional[discord.Member] = None):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return

    target = member or ctx.author
    total = db.get_user_credits(str(ctx.guild.id), str(target.id))
    history = db.get_credit_history(str(ctx.guild.id), str(target.id), limit=10)

    embed = discord.Embed(
        title=f"Crédits de {target.display_name}",
        color=0x5865F2,
    )
    embed.add_field(name="Solde actuel", value=str(total), inline=False)

    if history:
        lines = []
        for entry in history:
            delta = entry.get("delta")
            try:
                delta_value = int(delta)
            except (TypeError, ValueError):
                delta_value = 0
            reason = entry.get("reason") or "Raison non renseignée"
            actor = entry.get("actor_name") or entry.get("actor_id") or "Inconnu"
            total_value = entry.get("total")
            total_text = f" (total {total_value})" if total_value is not None else ""
            timestamp = entry.get("timestamp")
            date_text = "date inconnue"
            if isinstance(timestamp, str):
                try:
                    cleaned = timestamp.replace("Z", "+00:00")
                    date_text = datetime.datetime.fromisoformat(cleaned).strftime("%d/%m %H:%M")
                except ValueError:
                    date_text = timestamp
            emoji = "➕" if delta_value >= 0 else "➖"
            lines.append(f"{emoji} {delta_value:+d}{total_text} — {reason} (par {actor}) — {date_text}")
        embed.add_field(name="Historique récent", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="Historique récent", value="Aucun mouvement enregistré.", inline=False)

    await ctx.send(embed=embed)


@bot.command(name='clb')
async def credits_leaderboard(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée sur un serveur.')
        return

    staff_role = ctx.guild.get_role(LEGACY_VOTESTAFF_ROLE_ID)
    if staff_role is None:
        await ctx.send("Le rôle staff est introuvable.")
        return

    staff_members = [member for member in staff_role.members if not member.bot]
    if not staff_members:
        await ctx.send("Aucun staff trouvé pour établir le classement.")
        return

    top_entries = db.get_top_credits(
        str(ctx.guild.id),
        [str(member.id) for member in staff_members],
        limit=10,
    )
    if not top_entries:
        await ctx.send("Aucun crédit enregistré pour les staff pour le moment.")
        return

    lines = []
    for index, entry in enumerate(top_entries, start=1):
        member = ctx.guild.get_member(int(entry.get("user_id") or 0))
        name = member.display_name if member else f"ID {entry.get('user_id')}"
        credits_value = entry.get("credits", 0)
        lines.append(f"**{index}.** {name} — {credits_value} crédits")

    embed = discord.Embed(
        title="🏆 Classement des staff (crédits)",
        description="\n".join(lines),
        color=0x5865F2,
    )
    await ctx.send(embed=embed)


def _pcsd_main_embed() -> discord.Embed:
    embed = discord.Embed(
        title='PRISSCUP <:SD:1442143271685197987> – Tournoi <:NB:1442143671427399761>',
        description='Hosted by Prissme',
        color=0x00b8a9,
    )
    embed.add_field(
        name='Navigation',
        value='\n'.join(
            [
                'Utilise le menu ci-dessous pour voir :',
                '• Phase 1 – Qualifs (solo, TOP 4 pour avancer)',
                '• Phase 2 – Demi-finales (trio, 3 matchs)',
                '• Phase 3 – Finale (solo, 3 manches décisives)',
            ]
        ),
        inline=False,
    )
    embed.set_footer(text='Commande : !pcsd')
    return embed


def _pcsd_content_embed(option: str) -> discord.Embed:
    if option == 'phase1':
        embed = discord.Embed(
            title='PCSD – Phase 1 : Qualifs',
            description='\n'.join(
                [
                    'Première phase du tournoi : Survivant Solo. Objectif simple : rester dans le TOP 4.',
                ]
            ),
            color=0xf59e0b,
        )
        embed.add_field(
            name='Mode & objectif',
            value='\n'.join(
                [
                    '• Mode : Survivant Solo',
                    '• Faut faire TOP 4 pour avancer',
                    '• 5e ou pire = éliminé',
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name='Règles',
            value='\n'.join(
                [
                    '• 10 min de retard = DQ',
                    '• Pas de remake',
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name='Repères rapides',
            value='\n'.join(
                [
                    '• 24 joueurs au départ',
                    '• Seul le placement compte',
                    '• Les 4 premiers de chaque lobby passent en Phase 2',
                ]
            ),
            inline=False,
        )
        return embed

    if option == 'demi':
        embed = discord.Embed(
            title='PCSD – Phase 2 : Demi-finales',
            description='\n'.join(
                [
                    '12 joueurs restent. 3 matchs en Survivant Trio : chaque TOP 1 qualifie ses 3 joueurs.',
                ]
            ),
            color=0x2563eb,
        )
        embed.add_field(
            name='Composition des équipes',
            value='\n'.join(
                [
                    '• TOP1 de la Phase 1 ensemble',
                    '• TOP2 de la Phase 1 ensemble',
                    '• TOP3 de la Phase 1 ensemble',
                    '• TOP4 de la Phase 1 ensemble',
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name='Format des matchs',
            value='\n'.join(
                [
                    '• Mode : Survivant Trio',
                    '• Match 1 : TOP1 → les 3 joueurs qualifiés',
                    '• Match 2 : on relance avec 9 joueurs → TOP1 → qualifiés',
                    '• Match 3 : on relance avec 6 joueurs → TOP1 → qualifiés',
                    '• Total qualifiés : 9',
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name='Règles',
            value='\n'.join(
                [
                    '• 10 min de retard = DQ',
                    '• Pas de remake',
                    '• On rejoue immédiatement le lobby suivant après chaque TOP1',
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name='Ce qu’il faut retenir',
            value='\n'.join(
                [
                    '• 12 joueurs → 3 manches',
                    '• Chaque TOP1 qualifie son trio',
                    '• 9 joueurs au total passent en Phase 3',
                ]
            ),
            inline=False,
        )
        return embed

    if option == 'finale':
        embed = discord.Embed(
            title='PCSD – Phase 3 : Finale',
            description='\n'.join(
                [
                    '9 finalistes, 3 manches en Survivant Solo. Placement + kills = champion.',
                ]
            ),
            color=0x8b5cf6,
        )
        embed.add_field(
            name='Format',
            value='\n'.join(
                [
                    '• Mode : Survivant Solo',
                    '• 3 manches consécutives',
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name='Points',
            value='\n'.join(
                [
                    '• Placement = points (définis par l’host)',
                    '• Chaque kill = +2 points',
                    '• Total des 3 manches = classement final',
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name='Égalité',
            value='\n'.join(
                [
                    '• Égalité → 1v1 (mode au choix de l’host)',
                ]
            ),
            inline=False,
        )
        embed.add_field(
            name='Règles',
            value='\n'.join(
                [
                    '• 10 min de retard = DQ',
                    '• Pas de remake',
                ]
            ),
            inline=False,
        )
        return embed

    return _pcsd_main_embed()


def _pcsd_view() -> discord.ui.View:
    view = discord.ui.View(timeout=None)
    view.add_item(
        discord.ui.Select(
            custom_id='pcsd_menu',
            placeholder='Choisis une phase',
            options=[
                discord.SelectOption(label='Phase 1 – Qualifs', value='phase1'),
                discord.SelectOption(label='Phase 2 – Demi-finales', value='demi'),
                discord.SelectOption(label='Phase 3 – Finale', value='finale'),
            ],
        )
    )
    return view


@bot.command(name='pcsd')
async def pcsd(ctx: commands.Context):
    await ctx.send(embed=_pcsd_main_embed(), view=_pcsd_view())


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if (
        interaction.type == discord.InteractionType.component
        and interaction.data
        and interaction.data.get('custom_id') == 'pcsd_menu'
    ):
        values = interaction.data.get('values') or []
        selected = values[0] if values else 'phase1'
        await interaction.response.edit_message(embed=_pcsd_content_embed(selected), view=_pcsd_view())
        return

    await bot.process_application_commands(interaction)


@bot.command(name='syncstats')
@commands.has_permissions(administrator=True)
async def syncstats(ctx: commands.Context):
    if ctx.guild is None:
        await ctx.send('Cette commande doit être utilisée dans un serveur.')
        return

    await ctx.send("Synchronisation des statistiques... Cela peut prendre plusieurs minutes, ne lancez qu'une seule fois.")
    stats: Counter[datetime.date] = Counter()
    processed = 0
    for channel in _iter_message_channels(ctx.guild):
        permissions = channel.permissions_for(ctx.guild.me)
        if not (permissions.view_channel and permissions.read_message_history):
            continue
        async for message in channel.history(limit=None, oldest_first=True):
            if message.author.bot:
                continue
            stats[message.created_at.date()] += 1
            processed += 1

    for day, count in stats.items():
        db.record_daily_stats(
            date_value=day,
            guild_id=str(ctx.guild.id),
            members_total=ctx.guild.member_count,
            messages_sent=count,
        )

    db.log_event('analytics', 'info', 'Sync stats terminé', guild_id=str(ctx.guild.id), metadata={'messages_indexed': processed})
    await ctx.send(f'Synchronisation terminée : {processed} messages comptés sur {len(stats)} jours.')


@bot.command(name='cleanvoice')
@commands.has_permissions(administrator=True)
async def clean_voice(ctx: commands.Context):
    """Nettoie les salons vocaux personnalisés vides."""
    await ctx.send("🧹 Nettoyage des vocaux en cours...")
    cleaned = await custom_voice_manager.cleanup_abandoned_channels()
    await ctx.send(f"✅ Nettoyage terminé : {cleaned} salon(x) supprimé(s).")


@bot.tree.command(name='setup_roles', description='Renvoie l’embed des rôles dans le salon configuré')
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


@bot.event
async def on_command_completion(ctx: commands.Context):
    if ctx.guild is None:
        return
    db.record_daily_stats(
        date_value=datetime.date.today(),
        guild_id=str(ctx.guild.id),
        members_total=ctx.guild.member_count,
        commands_used=1,
    )


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
    socketio.emit('moderation_action', {
        'type': 'purge',
        'channel': channel.name,
        'user': str(interaction.user),
        'details': f"{len(deleted)} messages",
        'timestamp': datetime.datetime.utcnow().isoformat()
    })

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
    socketio.emit('moderation_action', {
        'type': 'unpurge',
        'channel': channel.name,
        'user': str(interaction.user),
        'details': reason or 'Rouverte',
        'timestamp': datetime.datetime.utcnow().isoformat()
    })

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


@bot.tree.command(name='lockdown', description='Active/désactive le lockdown du serveur')
@app_commands.describe(state='enable ou disable')
async def lockdown(interaction: discord.Interaction, state: str):
    await anti_raid.handle_lockdown_command(interaction, state.lower() == 'enable')


@bot.tree.command(name='stats_last_3_months', description='Compte les auteurs uniques ayant parlé durant les 3 derniers mois (historique inclus)')
async def stats_last_3_months(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    cutoff = discord.utils.utcnow() - datetime.timedelta(days=90)
    unique_authors, _ = await collect_message_stats(interaction.guild, cutoff)
    await interaction.followup.send(
        f"Auteurs uniques sur les 3 derniers mois : {unique_authors} (inclut les messages antérieurs au lancement du bot)",
        ephemeral=True,
    )


@bot.tree.command(name='stats_messages', description='Classement des membres ayant envoyé au moins N messages sur une période donnée (historique inclus)')
@app_commands.describe(min_messages='Nombre minimal de messages', window_days='Fenêtre de temps en jours')
async def stats_messages(interaction: discord.Interaction, min_messages: app_commands.Range[int, 1, 1000], window_days: app_commands.Range[int, 1, 365]):
    if interaction.guild is None:
        await interaction.response.send_message('Cette commande doit être utilisée dans un serveur.', ephemeral=True)
        return

    await interaction.response.defer(thinking=True)
    cutoff = discord.utils.utcnow() - datetime.timedelta(days=window_days)
    _, counter = await collect_message_stats(interaction.guild, cutoff)

    filtered = [(author_id, count) for author_id, count in counter.most_common() if count >= min_messages]
    if not filtered:
        await interaction.followup.send('Personne ne correspond à ces critères sur la période demandée.', ephemeral=True)
        return

    lines = []
    for position, (author_id, count) in enumerate(filtered, start=1):
        lines.append(f"{position}. <@{author_id}> — {count} messages")

    await interaction.followup.send("Classement des membres (historique inclus) :\n" + "\n".join(lines), ephemeral=True)


# --- Flask routes
@app.route('/')
def home():
    return render_template('index.html', title='Dashboard')


@app.route('/analytics')
def analytics_page():
    return render_template('analytics.html', title='Analytics')


@app.route('/moderation')
def moderation_page():
    return render_template('moderation.html', title='Modération')


@app.route('/logs')
def logs_page():
    return render_template('logs.html', title='Logs')


@app.route('/settings')
def settings_page():
    return render_template('settings.html', title='Settings')


@app.route('/security')
def security_page():
    return render_template('security.html', title='Sécurité')


@app.route('/health')
def health():
    ready = bot_status.get('ready', False)
    if ready:
        return jsonify({
            'status': 'ok',
            'bot': 'ready',
            'latency': round(bot.latency * 1000, 2) if bot.latency else None,
            'guilds': len(bot.guilds)
        }), 200
    return jsonify({'status': 'starting', 'bot': 'connecting'}), 503


@app.route('/api/stats/overview')
def stats_overview():
    overview = db.get_overview()
    chart_data = db.get_chart_data(days=7)
    top_channels = db.get_top_channels(limit=5, days=7)
    chart_data['channels'] = [
        {'label': _channel_label(row['channel_id']), 'value': row['message_count']} for row in top_channels
    ]
    chart_data.setdefault('events', [])
    chart_data.setdefault('heatmap', [])
    overview.update({
        'uptime': uptime(),
        'bot_status': 'online' if bot_status.get('ready') else 'offline',
        'latency': round(bot.latency * 1000, 2) if bot_status.get('ready') and bot.latency else None,
        'guilds': len(bot.guilds) if bot_status.get('ready') else 0,
        'chart_data': chart_data,
        'guild': _guild_metadata(),
    })
    return jsonify(overview)


@app.route('/api/analytics')
def api_analytics():
    now = datetime.datetime.utcnow()
    start_param = request.args.get('start')
    end_param = request.args.get('end')
    range_param = request.args.get('range', '7d')

    start_dt, end_dt = _resolve_range(now, range_param, start_param, end_param)
    summary = db.get_activity_summary(start_dt, end_dt)
    growth = db.get_member_growth(start_dt.date(), end_dt.date())
    messages_series = db.get_messages_timeseries(start_dt, end_dt)
    top_members = db.get_top_members_between(start_dt, end_dt)
    top_channels = db.get_top_channels_between(start_dt, end_dt)
    heatmap = db.get_heatmap_activity(start_dt, end_dt)

    period_days = max((end_dt - start_dt).total_seconds() / 86400, 1)
    average_per_day = round(summary['messages'] / period_days, 2)

    payload = {
        'range': range_param,
        'start': start_dt.isoformat(),
        'end': end_dt.isoformat(),
        'summary': {
            'active_members': summary['active_members'],
            'total_messages': summary['messages'],
            'average_per_day': average_per_day,
        },
        'members_chart': [{'label': row['label'], 'value': row['net']} for row in growth] or messages_series,
        'top_members': top_members,
        'top_channels': [
            {'channel_id': row['channel_id'], 'name': _channel_label(row['channel_id']), 'message_count': row['message_count']}
            for row in top_channels
        ],
        'heatmap': heatmap,
    }

    return jsonify(payload)


@app.route('/api/stats/messages')
def stats_messages_api():
    period = request.args.get('period', '7d')
    min_messages = int(request.args.get('min_messages', 1))
    days = _period_to_days(period)
    payload = [member for member in db.get_top_members(days=days) if member['count'] >= min_messages]
    return jsonify({'period': period, 'min_messages': min_messages, 'results': payload})


@app.route('/api/stats/channels')
def stats_channels_api():
    days = _period_to_days(request.args.get('period', '7d'))
    channels = db.get_top_channels(days=days, limit=10)
    payload = [
        {'channel_id': row['channel_id'], 'name': _channel_label(row['channel_id']), 'message_count': row['message_count']}
        for row in channels
    ]
    return jsonify(payload)


@app.route('/api/logs')
def api_logs():
    filters = {
        'type': request.args.get('type', 'all'),
        'search': request.args.get('search'),
        'start': request.args.get('start'),
        'end': request.args.get('end'),
    }
    return jsonify(db.get_logs(filters))


@app.route('/api/moderation/history')
def api_moderation_history():
    filters = {
        'type': request.args.get('type', 'all'),
        'date': request.args.get('date'),
    }
    channels = _guild_channels()
    response = db.get_moderation_history(filters)
    response['channels'] = channels
    return jsonify(response)


@app.route('/api/moderation/purge', methods=['POST'])
def api_purge():
    payload = request.get_json(force=True)
    amount = int(payload.get('amount', 0))
    if amount <= 0 or amount > 1000:
        return jsonify({'success': False, 'error': 'amount must be 1-1000'}), 400
    channel_id = str(payload.get('channel_id'))
    reason = payload.get('reason', '')
    db.add_moderation_action('purge', channel_id, f'#{channel_id}', 'dashboard', 'Dashboard', reason, {'messages_deleted': amount})
    db.log_event('moderation', 'info', f'Purge demandée via API ({amount})', channel_id=channel_id, user_name='Dashboard')
    socketio.emit('moderation_action', {
        'type': 'purge',
        'channel': channel_id,
        'user': 'Dashboard',
        'details': f'{amount} messages',
        'timestamp': datetime.datetime.utcnow().isoformat(),
    })
    socketio.emit('request_purge', {'channel_id': channel_id, 'amount': amount, 'reason': reason})
    return jsonify({'success': True, 'messages_deleted': amount})


@app.route('/api/moderation/unpurge', methods=['POST'])
def api_unpurge():
    payload = request.get_json(force=True)
    channel_id = str(payload.get('channel_id'))
    reason = payload.get('reason', '')
    db.add_moderation_action('unpurge', channel_id, f'#{channel_id}', 'dashboard', 'Dashboard', reason, {})
    db.log_event('moderation', 'info', 'Unpurge demandé via API', channel_id=channel_id, user_name='Dashboard')
    socketio.emit('request_unpurge', {'channel_id': channel_id, 'reason': reason})
    return jsonify({'success': True})


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    global config, slow_mode_manager, anti_nuke, anti_raid
    if request.method == 'GET':
        return jsonify(config.to_dict())
    payload = request.get_json(force=True)
    new_config = Config.from_mapping(payload)
    db.save_config(new_config)
    config = new_config
    slow_mode_manager.update_config(new_config.to_dict())
    anti_nuke.update_config(new_config.to_dict())
    anti_raid.update_config(new_config.to_dict())
    return jsonify({'success': True, 'config': new_config.to_dict()})


@app.route('/api/whitelist', methods=['GET'])
def api_get_whitelist():
    trust_levels = db.get_trust_levels()
    result = []
    for user_id, level in trust_levels.items():
        user = bot.get_user(int(user_id)) if bot_status.get('ready') else None
        result.append({
            'user_id': user_id,
            'username': str(user) if user else f"User {user_id}",
            'level': level,
        })
    return jsonify(result)


@app.route('/api/whitelist', methods=['POST'])
def api_add_whitelist():
    payload = request.get_json(force=True)
    user_id = payload.get('user_id')
    level = payload.get('level')
    if not user_id or level not in ['OWNER', 'TRUSTED_ADMIN', 'NORMAL_ADMIN', 'DEFAULT_USER']:
        return jsonify({'success': False, 'error': 'Invalid data'}), 400
    db.set_trust_level(user_id, level)
    db.log_event('security', 'info', f'Trust level changed: {user_id} → {level}')
    return jsonify({'success': True})


@app.route('/api/whitelist/<user_id>', methods=['DELETE'])
def api_remove_whitelist(user_id: str):
    db.remove_trust_level(user_id)
    db.log_event('security', 'info', f'Trust level removed: {user_id}')
    return jsonify({'success': True})


@app.route('/api/database/stats')
def api_database_stats():
    return jsonify(db.get_database_stats())


@app.route('/api/backup', methods=['POST'])
def api_backup():
    backup_path = db.backup_database()
    db.log_event('maintenance', 'info', 'Backup créé via API', path=str(backup_path))
    return send_file(
        backup_path,
        mimetype='application/octet-stream',
        as_attachment=True,
        download_name=backup_path.name,
    )


@app.route('/api/export/logs')
def export_logs():
    return _export_csv('logs')


@app.route('/api/export/config')
def export_config():
    path = Path('/tmp/config.json')
    path.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2))
    return send_file(path, mimetype='application/json', as_attachment=True, download_name='config.json')


@app.route('/api/export/stats')
def export_stats():
    return _export_csv('daily_stats')


def _export_csv(table: str):
    path = Path(f'/tmp/{table}.csv')
    rows = list(db.export_table(table))
    if not rows:
        path.write_text('')
        return send_file(path, mimetype='text/csv', as_attachment=True, download_name=f'{table}.csv')
    headers = rows[0].keys()
    with path.open('w', encoding='utf-8') as handle:
        handle.write(','.join(headers) + '\n')
        for row in rows:
            handle.write(','.join(str(row[h]) for h in headers) + '\n')
    return send_file(path, mimetype='text/csv', as_attachment=True, download_name=f'{table}.csv')


@app.route('/api/guilds')
def api_guilds():
    guilds = [_guild_metadata(g) for g in bot.guilds] if bot_status.get('ready') else []
    return jsonify(guilds)


@app.route('/api/guilds/<guild_id>')
def api_guild_detail(guild_id: str):
    guild = next((g for g in bot.guilds if str(g.id) == guild_id), None) if bot_status.get('ready') else None
    return jsonify(_guild_metadata(guild))


# --- Socket.IO events
@socketio.on('request_purge')
def handle_request_purge(data):
    db.log_event('moderation', 'info', 'Purge demandée via websocket', channel_id=data.get('channel_id'), user_name='Dashboard')
    socketio.emit('moderation_action', {
        'type': 'purge',
        'channel': data.get('channel_id'),
        'user': 'Dashboard',
        'details': f"{data.get('amount', 0)} messages",
        'timestamp': datetime.datetime.utcnow().isoformat(),
    })


@socketio.on('update_config')
def handle_update_config(data):
    new_cfg = Config.from_mapping(data)
    db.save_config(new_cfg)
    global config
    config = new_cfg
    slow_mode_manager.update_config(new_cfg.to_dict())
    anti_nuke.update_config(new_cfg.to_dict())
    anti_raid.update_config(new_cfg.to_dict())
    socketio.emit('config_updated', new_cfg.to_dict())


# --- Helpers

def _guild_metadata(guild: Optional[discord.Guild] = None) -> dict:
    if guild is None:
        return {'name': 'N/A', 'id': '--', 'members': 0, 'online': 0, 'bots': 0, 'created_at': '--', 'owner': '--', 'roles': []}
    roles = [role.name for role in sorted(guild.roles, key=lambda r: r.position, reverse=True)[:5]]
    return {
        'name': guild.name,
        'id': str(guild.id),
        'members': guild.member_count,
        'online': len([m for m in guild.members if m.status != discord.Status.offline]),
        'bots': len([m for m in guild.members if m.bot]),
        'created_at': guild.created_at.strftime('%Y-%m-%d'),
        'owner': str(guild.owner) if guild.owner else 'Unknown',
        'roles': roles,
    }


def _guild_channels() -> list[dict[str, str]]:
    if not bot_status.get('ready'):
        return []
    channels = []
    for guild in bot.guilds:
        for channel in guild.text_channels:
            channels.append({'id': str(channel.id), 'name': channel.name})
    return channels


def _channel_label(channel_id: str) -> str:
    if not bot_status.get('ready'):
        return f"#{channel_id}"
    try:
        channel = bot.get_channel(int(channel_id)) if channel_id else None
    except Exception:  # noqa: BLE001
        channel = None
    return f"#{channel.name}" if channel else f"#{channel_id}"


def _resolve_range(now: datetime.datetime, preset: str, start: str | None, end: str | None) -> tuple[datetime.datetime, datetime.datetime]:
    if start and end:
        try:
            start_dt = datetime.datetime.fromisoformat(start)
            end_dt = datetime.datetime.fromisoformat(end) + datetime.timedelta(days=1)
            return start_dt, end_dt
        except Exception:  # noqa: BLE001
            pass

    delta = _period_to_timedelta(preset)
    return now - delta, now


def _period_to_days(period: str) -> int:
    mapping = {'7d': 7, '30d': 30, '90d': 90}
    return mapping.get(period, 7)


def _period_to_timedelta(period: str) -> datetime.timedelta:
    mapping = {
        '10m': datetime.timedelta(minutes=10),
        '1h': datetime.timedelta(hours=1),
        '24h': datetime.timedelta(hours=24),
        '7d': datetime.timedelta(days=7),
        '30d': datetime.timedelta(days=30),
        '90d': datetime.timedelta(days=90),
    }
    return mapping.get(period, datetime.timedelta(days=7))


# --- Runner

def run_bot():
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error('ERREUR: Token Discord non trouvé!')
        return
    bot.run(token)


def run_flask():
    port = int(os.getenv('PORT', 8000))
    # allow_unsafe_werkzeug enables the built-in dev server in environments like Koyeb
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    run_flask()
