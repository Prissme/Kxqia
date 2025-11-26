import { ChannelType, PermissionsBitField } from "discord.js";
import { getConfig } from "../../db/database.js";

export class SlowModeManager {
  constructor(logger) {
    this.logger = logger;
    this.messageBuckets = new Map();
    this.lastApplied = new Map();
    this.lastChange = new Map();
  }

  handleMessage(message) {
    if (!message.guild || message.author.bot) return;

    const config = getConfig();
    const slowModeConfig = config.slowMode;
    if (!slowModeConfig?.enabled) return;

    const channel = message.channel;
    if (!this.canApplySlowMode(channel, message.guild)) return;

    const now = Date.now();
    const windowMs = (slowModeConfig.windowSeconds || 60) * 1000;
    const bucket = this.messageBuckets.get(channel.id) || [];
    const fresh = bucket.filter((ts) => now - ts < windowMs);
    fresh.push(now);
    this.messageBuckets.set(channel.id, fresh);

    const ratePerMinute = (fresh.length * 60000) / windowMs;
    const target = this.selectSlowMode(ratePerMinute, slowModeConfig.tiers || []);

    const current = this.lastApplied.get(channel.id) ?? channel.rateLimitPerUser ?? 0;
    if (target === current) return;

    const minInterval = (slowModeConfig.minUpdateIntervalSeconds || 15) * 1000;
    const lastChange = this.lastChange.get(channel.id) || 0;
    const isIncrease = target > current;
    if (!isIncrease && now - lastChange < minInterval) return;

    channel
      .setRateLimitPerUser(target, "Automatic slow mode adjustment")
      .then(() => {
        this.lastApplied.set(channel.id, target);
        this.lastChange.set(channel.id, now);
        const action = target === 0 ? "disabled" : `${target}s`;
        this.logger(channel.guild.id, `⏱️ Slow mode ${action} in #${channel.name} (${ratePerMinute.toFixed(1)} msg/min).`);
      })
      .catch(() => {});
  }

  canApplySlowMode(channel, guild) {
    const allowedTypes = [ChannelType.GuildText, ChannelType.GuildAnnouncement];
    if (!channel || !allowedTypes.includes(channel.type)) return false;
    if (typeof channel.setRateLimitPerUser !== "function") return false;
    const me = guild.members.me;
    if (!me) return false;
    const permissions = channel.permissionsFor(me);
    return permissions?.has(PermissionsBitField.Flags.ManageChannels);
  }

  selectSlowMode(ratePerMinute, tiers) {
    let target = 0;
    for (const tier of tiers) {
      if (ratePerMinute >= tier.threshold) {
        target = tier.seconds;
      }
    }
    return target;
  }
}
