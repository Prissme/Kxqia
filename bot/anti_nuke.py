import datetime
from collections import defaultdict
from typing import Any

import discord
from discord import AuditLogAction

from bot.trust_levels import is_trusted


class AntiNuke:
    def __init__(self, bot: discord.Client, config: dict[str, Any]):
        self.bot = bot
        self.action_buckets: dict[int, dict[int, dict[str, list[datetime.datetime]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )
        self.update_config(config)

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = (config or {}).get('nuke', {})

    async def handle_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._handle_event(channel.guild, 'channel_delete', AuditLogAction.channel_delete)

    async def handle_role_delete(self, role: discord.Role):
        await self._handle_event(role.guild, 'role_delete', AuditLogAction.role_delete)

    async def handle_ban(self, guild: discord.Guild):
        await self._handle_event(guild, 'ban', AuditLogAction.ban)

    async def handle_webhook_create(self, channel: discord.abc.GuildChannel):
        await self._handle_event(channel.guild, 'webhook', AuditLogAction.webhook_create)

    async def handle_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if before.permissions_synced == after.permissions_synced and before.overwrites == after.overwrites:
            return
        await self._handle_event(after.guild, 'channel_update', AuditLogAction.overwrite_update)

    async def _handle_event(self, guild: discord.Guild, action_type: str, audit_action):
        conf = self.config or {}
        time_window = conf.get('timeWindow') or conf.get('time_window') or conf.get('time_window', 30)
        threshold_map = {
            'channel_delete': conf.get('channelDeleteLimit', 3),
            'role_delete': conf.get('roleDeleteLimit', 5),
            'ban': conf.get('banLimit', 10),
            'webhook': conf.get('webhookCreateLimit', 3),
            'channel_update': conf.get('channelDeleteLimit', 3),
        }
        try:
            async for entry in guild.audit_logs(limit=1, action=audit_action):
                executor = entry.user
                break
            else:
                return
        except Exception:
            return
        if executor is None:
            return
        if is_trusted(str(executor.id), guild, allow_owner=conf.get('allowOwner', True)):
            return
        now = datetime.datetime.utcnow()
        bucket = self.action_buckets[guild.id][executor.id][action_type]
        bucket.append(now)
        self.action_buckets[guild.id][executor.id][action_type] = [
            ts for ts in bucket if (now - ts).total_seconds() <= time_window
        ]
        threshold = threshold_map.get(action_type)
        if threshold and len(self.action_buckets[guild.id][executor.id][action_type]) >= threshold:
            member = guild.get_member(executor.id)
            if member:
                await self._apply_punishment(guild, member)
            self.action_buckets[guild.id][executor.id][action_type].clear()

    async def _apply_punishment(self, guild: discord.Guild, executor: discord.Member):
        action = (self.config or {}).get('punitiveAction', 'strip')
        if action == 'ban':
            try:
                await guild.ban(executor, reason='Anti-nuke protection')
            except Exception:
                pass
            return
        try:
            roles_to_remove = [r for r in executor.roles if r.is_default() is False]
            if roles_to_remove:
                await executor.remove_roles(*roles_to_remove, reason='Anti-nuke protection')
            await executor.timeout(datetime.timedelta(hours=1), reason='Anti-nuke protection')
        except Exception:
            return
