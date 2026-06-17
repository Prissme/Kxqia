import { recordStat, getConfig, getTrustLevels, pushEvent } from "../../db/database.js";
import { isTrusted, TRUST_LEVELS } from "./trustLevels.js";

const ACTION_TYPES = {
  channelDelete: "channelDelete",
  roleDelete: "roleDelete",
  ban: "ban",
  webhook: "webhook"
};

export class AntiNuke {
  constructor(client, logger) {
    this.client = client;
    this.logger = logger;
    this.actionBuckets = new Map();
  }

  async handleGuildEvent(guild, action) {
    try {
      const auditType = this.mapAuditType(action);
      if (!auditType) return;
      const logs = await guild.fetchAuditLogs({ type: auditType, limit: 1 });
      const entry = logs.entries.first();
      if (!entry) return;
      const executor = entry.executor;
      if (!executor || executor.id === this.client.user?.id) return;

      const config = getConfig();
      const protectBots = config.nuke.protectBots !== false;
      if (!executor.bot || !protectBots) {
        const trust = getTrustLevels();
        if (isTrusted(executor.id, trust)) return;
      }

      this.bumpAndCheck(guild, executor, action, config);
    } catch (err) {
      console.error("AntiNuke error", err);
    }
  }

  mapAuditType(action) {
    switch (action) {
      case ACTION_TYPES.channelDelete:
        return 12; // AuditLogEvent.ChannelDelete
      case ACTION_TYPES.roleDelete:
        return 32; // AuditLogEvent.RoleDelete
      case ACTION_TYPES.ban:
        return 22; // AuditLogEvent.MemberBanAdd
      case ACTION_TYPES.webhook:
        return 50; // AuditLogEvent.WebhookCreate
      default:
        return null;
    }
  }

  bumpAndCheck(guild, executor, action, config = getConfig()) {
    const now = Date.now();
    const windowMs = (config.nuke.timeWindow || 30) * 1000;
    const fresh = this.bumpBucket(`${guild.id}:${executor.id}:${action}`, now, windowMs);
    const globalFresh = this.bumpBucket(`${guild.id}:${executor.id}:global`, now, windowMs);

    const limits = {
      [ACTION_TYPES.channelDelete]: config.nuke.channelDeleteLimit,
      [ACTION_TYPES.roleDelete]: config.nuke.roleDeleteLimit,
      [ACTION_TYPES.ban]: config.nuke.banLimit,
      [ACTION_TYPES.webhook]: config.nuke.webhookCreateLimit
    };

    const protectBots = config.nuke.protectBots !== false;
    const actionLimit = executor.bot && protectBots
      ? Math.min(limits[action] || 1, config.nuke.botActionLimit || 1)
      : limits[action];
    const globalLimit = executor.bot && protectBots
      ? Math.min(config.nuke.globalActionLimit || 4, config.nuke.botActionLimit || 1)
      : config.nuke.globalActionLimit;

    if (fresh.length >= (actionLimit || Infinity) || globalFresh.length >= (globalLimit || Infinity)) {
      recordStat("nukeAlerts");
      pushEvent({
        type: "nuke",
        guildId: guild.id,
        message: `${executor.tag} exceeded ${action} limit (${fresh.length}/${actionLimit || limits[action]})`
      });
      this.logger(guild.id, `🚫 Nuke prevented: ${executor.tag} exceeded ${action} limit (${fresh.length}/${actionLimit || limits[action]}).`);
      this.applyPunishment(guild, executor, config);
      this.clearExecutorBuckets(guild.id, executor.id);
    }
  }

  bumpBucket(key, now, windowMs) {
    const bucket = this.actionBuckets.get(key) || [];
    const fresh = bucket.filter((ts) => now - ts < windowMs);
    fresh.push(now);
    this.actionBuckets.set(key, fresh);
    return fresh;
  }

  clearExecutorBuckets(guildId, executorId) {
    for (const key of this.actionBuckets.keys()) {
      if (key.startsWith(`${guildId}:${executorId}:`)) this.actionBuckets.delete(key);
    }
  }

  async applyPunishment(guild, executor, config) {
    const member = await guild.members.fetch(executor.id).catch(() => null);
    if (!member) return;

    const action = executor.bot ? (config.nuke.botPunitiveAction || "ban") : config.nuke.punitiveAction;
    if (action === "ban") {
      const banned = await member.ban({ reason: executor.bot ? "Anti-nuke bot trigger" : "Anti-nuke trigger" }).then(() => true).catch(() => false);
      if (banned) return;
      if (executor.bot) {
        const kicked = await member.kick("Anti-nuke bot trigger").then(() => true).catch(() => false);
        if (kicked) return;
      }
    }

    // default: strip dangerous permissions by removing elevated roles
    const safeRoles = member.roles.cache.filter((r) => !r.permissions.has("Administrator"));
    await member.roles.set(safeRoles).catch(() => {});
    await member.timeout(60 * 60 * 1000, "Anti-nuke timeout").catch(() => {});
  }
}

export { ACTION_TYPES };
