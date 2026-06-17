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
        time_window = self._to_int(conf.get('timeWindow') or conf.get('time_window'), 30)
        audit_log_max_age = self._to_int(conf.get('auditLogMaxAge'), 15)
        threshold_map = {
            'channel_delete': self._to_int(conf.get('channelDeleteLimit'), 3),
            'role_delete': self._to_int(conf.get('roleDeleteLimit'), 5),
            'ban': self._to_int(conf.get('banLimit'), 10),
            'webhook': self._to_int(conf.get('webhookCreateLimit'), 3),
            'channel_update': self._to_int(conf.get('channelUpdateLimit', conf.get('channelDeleteLimit')), 3),
        }
        try:
            async for entry in guild.audit_logs(limit=3, action=audit_action):
                executor = entry.user
                if executor and self._is_recent_audit_entry(entry, audit_log_max_age):
                    break
            else:
                return
        except Exception:
            return
        if executor is None:
            return
        if self.bot.user and executor.id == self.bot.user.id:
            return

        is_bot_executor = bool(getattr(executor, 'bot', False))
        protect_bots = bool(conf.get('protectBots', True))
        if not is_bot_executor or not protect_bots:
            if is_trusted(str(executor.id), guild, allow_owner=conf.get('allowOwner', True)):
                return

        now = datetime.datetime.utcnow()
        threshold = threshold_map.get(action_type)
        if is_bot_executor and protect_bots:
            threshold = min(threshold or 1, self._to_int(conf.get('botActionLimit'), 1))

        action_count = self._bump_bucket(guild.id, executor.id, action_type, now, time_window)
        global_count = self._bump_bucket(guild.id, executor.id, '__global__', now, time_window)
        global_threshold = self._to_int(conf.get('globalActionLimit'), 4)
        if is_bot_executor and protect_bots:
            global_threshold = min(global_threshold, self._to_int(conf.get('botActionLimit'), 1))

        if (threshold and action_count >= threshold) or (global_threshold and global_count >= global_threshold):
            member = guild.get_member(executor.id)
            if member is None:
                try:
                    member = await guild.fetch_member(executor.id)
                except Exception:
                    member = None
            if member:
                await self._apply_punishment(guild, member, bot_executor=is_bot_executor)
            self.action_buckets[guild.id][executor.id].clear()

    def _bump_bucket(
        self,
        guild_id: int,
        executor_id: int,
        action_type: str,
        now: datetime.datetime,
        time_window: int,
    ) -> int:
        bucket = self.action_buckets[guild_id][executor_id][action_type]
        bucket.append(now)
        fresh = [ts for ts in bucket if (now - ts).total_seconds() <= time_window]
        self.action_buckets[guild_id][executor_id][action_type] = fresh
        return len(fresh)

    @staticmethod
    def _to_int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _is_recent_audit_entry(entry: discord.AuditLogEntry, max_age_seconds: int) -> bool:
        created_at = getattr(entry, 'created_at', None)
        if created_at is None:
            return True
        if created_at.tzinfo is not None:
            created_at = created_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return (datetime.datetime.utcnow() - created_at).total_seconds() <= max_age_seconds

    async def _apply_punishment(self, guild: discord.Guild, executor: discord.Member, bot_executor: bool = False):
        action = (self.config or {}).get('punitiveAction', 'strip')
        if bot_executor:
            action = (self.config or {}).get('botPunitiveAction', 'ban')

        if action == 'ban':
            try:
                await guild.ban(executor, reason='Anti-nuke protection: bot executor' if bot_executor else 'Anti-nuke protection')
                return
            except Exception:
                pass
            if bot_executor:
                try:
                    await executor.kick(reason='Anti-nuke protection: bot executor')
                    return
                except Exception:
                    pass

        try:
            roles_to_remove = [r for r in executor.roles if not r.is_default() and not r.managed]
            if roles_to_remove:
                await executor.remove_roles(*roles_to_remove, reason='Anti-nuke protection')
            if not bot_executor:
                await executor.timeout(datetime.timedelta(hours=1), reason='Anti-nuke protection')
        except Exception:
            return
