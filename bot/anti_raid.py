import datetime
from collections import defaultdict
from typing import Any

import discord

from bot.trust_levels import is_trusted


class AntiRaid:
    def __init__(self, bot: discord.Client, config: dict[str, Any]):
        self.bot = bot
        self.join_buckets: dict[int, list[datetime.datetime]] = defaultdict(list)
        self.lockdown_state: dict[int, list[tuple[int, dict[str, discord.PermissionOverwrite]]]] = {}
        self.update_config(config)

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = (config or {}).get('raid', {})

    def handle_member_join(self, member: discord.Member):
        conf = self.config or {}
        now = datetime.datetime.utcnow()
        bucket = self.join_buckets[member.guild.id]
        bucket.append(now)
        cutoff = now - datetime.timedelta(seconds=60)
        self.join_buckets[member.guild.id] = [ts for ts in bucket if ts >= cutoff]
        if len(self.join_buckets[member.guild.id]) >= conf.get('joinThreshold', 10):
            if conf.get('lockdownOnRaid', True):
                self.bot.loop.create_task(self.enable_lockdown(member.guild, 'Raid detection'))
        account_age_days = (now - member.created_at.replace(tzinfo=None)).days
        if account_age_days < conf.get('accountAgeDays', 7):
            if conf.get('kickYoungAccounts', False):
                self.bot.loop.create_task(member.kick(reason='Anti-raid: account too new'))
            elif conf.get('quarantineRoleId'):
                role = member.guild.get_role(int(conf['quarantineRoleId']))
                if role:
                    self.bot.loop.create_task(member.add_roles(role, reason='Anti-raid quarantine'))

    async def enable_lockdown(self, guild: discord.Guild, reason: str):
        if guild.id in self.lockdown_state:
            return
        self.lockdown_state[guild.id] = []
        for channel in guild.text_channels:
            overwrites = channel.overwrites_for(guild.default_role)
            self.lockdown_state[guild.id].append((channel.id, {guild.default_role.id: overwrites}))
            try:
                await channel.set_permissions(guild.default_role, send_messages=False, reason=reason)
            except Exception:
                continue

    async def disable_lockdown(self, guild: discord.Guild, reason: str):
        state = self.lockdown_state.get(guild.id)
        if not state:
            return
        for channel_id, permissions in state:
            channel = guild.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            overwrite = permissions.get(guild.default_role.id)
            if overwrite is None:
                continue
            try:
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            except Exception:
                continue
        self.lockdown_state.pop(guild.id, None)

    async def handle_lockdown_command(self, interaction: discord.Interaction, enable: bool):
        if not is_trusted(str(interaction.user.id), interaction.guild):
            await interaction.response.send_message('Action non autorisée.', ephemeral=True)
            return
        if enable:
            await self.enable_lockdown(interaction.guild, 'Manual lockdown command')
            await interaction.response.send_message('Lockdown activé.', ephemeral=True)
        else:
            await self.disable_lockdown(interaction.guild, 'Manual lockdown command')
            await interaction.response.send_message('Lockdown désactivé.', ephemeral=True)
