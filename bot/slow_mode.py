import datetime
from collections import defaultdict, deque
from typing import Any

import discord


class SlowModeManager:
    def __init__(self, bot: discord.Client, config: dict[str, Any]):
        self.bot = bot
        self.message_buckets: dict[int, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.last_applied: dict[int, int] = {}
        self.last_change: dict[int, datetime.datetime] = {}
        self.update_config(config)

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = (config or {}).get('slow_mode') or {}

    def handle_message(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        conf = self.config or {}
        if not conf.get('enabled', False):
            return
        now = datetime.datetime.utcnow()
        bucket = self.message_buckets[message.channel.id]
        bucket.append(now)
        window = max(int(conf.get('window_seconds', 60)), 10)
        while bucket and (now - bucket[0]).total_seconds() > window:
            bucket.popleft()
        rate = (len(bucket) / window) * 60
        tiers = conf.get('tiers') or []
        target = self._select_slowmode(rate, tiers)
        last = self.last_applied.get(message.channel.id, 0)
        cooldown = max(int(conf.get('min_update_interval_seconds', 15)), 5)
        if target == last:
            return
        last_change = self.last_change.get(message.channel.id)
        if last_change and (now - last_change).total_seconds() < cooldown:
            return
        if isinstance(message.channel, discord.TextChannel):
            try:
                self.bot.loop.create_task(message.channel.edit(slowmode_delay=target, reason='Auto slow mode'))
                self.last_applied[message.channel.id] = target
                self.last_change[message.channel.id] = now
            except Exception:
                return

    def _select_slowmode(self, rate_per_minute: float, tiers: list[dict[str, Any]]) -> int:
        selected = 0
        for tier in sorted(tiers, key=lambda t: t.get('threshold', 0), reverse=True):
            try:
                threshold = float(tier.get('threshold', 0))
                seconds = int(tier.get('seconds', 0))
            except (TypeError, ValueError):
                continue
            if rate_per_minute >= threshold:
                selected = max(selected, max(seconds, 0))
                break
        return selected
