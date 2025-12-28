import asyncio
import logging

import discord

VOICE_CATEGORY_ID = 1236724293631611021
TRIGGER_CHANNEL_NAME = "➕ Créer un vocal"
VOICE_NAME_PREFIX = "🎤"

logger = logging.getLogger(__name__)


class CustomVoiceManager:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self.created_channels: set[int] = set()

    async def initialize(self) -> None:
        await self.cleanup_abandoned_channels()

    async def handle_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if after.channel and self._is_trigger_channel(after.channel):
            await self._create_and_move(member, after.channel.category)
        if before.channel and self._is_custom_channel(before.channel):
            await self._cleanup_if_empty(before.channel)

    async def cleanup_abandoned_channels(self) -> int:
        category = self._get_voice_category()
        if category is None:
            return 0
        cleaned = 0
        for channel in category.voice_channels:
            if self._is_custom_channel(channel) and not channel.members:
                try:
                    await channel.delete(reason="Nettoyage des vocaux personnalisés")
                    self.created_channels.discard(channel.id)
                    cleaned += 1
                    logger.info("Salon vocal personnalisé supprimé: %s", channel.name)
                except discord.Forbidden:
                    logger.warning("Permissions insuffisantes pour supprimer %s.", channel.name)
                except discord.HTTPException:
                    logger.exception("Erreur lors de la suppression du salon %s.", channel.name)
        return cleaned

    def _get_voice_category(self) -> discord.CategoryChannel | None:
        for guild in self.bot.guilds:
            category = guild.get_channel(VOICE_CATEGORY_ID)
            if isinstance(category, discord.CategoryChannel):
                return category
        return None

    def _is_trigger_channel(self, channel: discord.VoiceChannel) -> bool:
        return channel.category_id == VOICE_CATEGORY_ID and channel.name == TRIGGER_CHANNEL_NAME

    def _is_custom_channel(self, channel: discord.VoiceChannel) -> bool:
        if channel.id in self.created_channels:
            return True
        if channel.category_id != VOICE_CATEGORY_ID:
            return False
        if channel.name == TRIGGER_CHANNEL_NAME:
            return False
        return channel.name.startswith(VOICE_NAME_PREFIX)

    async def _create_and_move(self, member: discord.Member, category: discord.CategoryChannel | None) -> None:
        if category is None:
            logger.warning("Catégorie vocale introuvable pour les vocaux personnalisés.")
            return

        overwrites = {
            member.guild.default_role: discord.PermissionOverwrite(
                view_channel=False,
                connect=False,
            ),
            member: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                move_members=True,
                mute_members=True,
                deafen_members=True,
                manage_channels=True,
            ),
        }

        channel_name = f"{VOICE_NAME_PREFIX} {member.display_name}"
        try:
            channel = await category.create_voice_channel(
                channel_name,
                overwrites=overwrites,
                reason=f"Vocal personnalisé créé pour {member}",
            )
        except discord.Forbidden:
            logger.warning("Permissions insuffisantes pour créer un vocal personnalisé.")
            return
        except discord.HTTPException:
            logger.exception("Erreur lors de la création du vocal personnalisé.")
            return

        self.created_channels.add(channel.id)
        logger.info("Salon vocal personnalisé créé: %s (%s)", channel.name, member)

        try:
            await member.move_to(channel, reason="Déplacement vers vocal personnalisé")
        except discord.Forbidden:
            logger.warning("Permissions insuffisantes pour déplacer %s.", member)
        except discord.HTTPException:
            logger.exception("Erreur lors du déplacement vers %s.", channel.name)

    async def _cleanup_if_empty(self, channel: discord.VoiceChannel) -> None:
        await asyncio.sleep(1)
        if channel.members:
            return
        try:
            await channel.delete(reason="Suppression vocal personnalisé vide")
            self.created_channels.discard(channel.id)
            logger.info("Salon vocal personnalisé supprimé: %s", channel.name)
        except discord.Forbidden:
            logger.warning("Permissions insuffisantes pour supprimer %s.", channel.name)
        except discord.HTTPException:
            logger.exception("Erreur lors de la suppression du salon %s.", channel.name)
