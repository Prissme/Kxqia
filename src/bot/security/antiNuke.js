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
      if (!executor || executor.bot) return;

      const trust = getTrustLevels();
      if (isTrusted(executor.id, trust)) return;

      this.bumpAndCheck(guild, executor, action);
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

  bumpAndCheck(guild, executor, action) {
    const config = getConfig();
    const key = `${guild.id}:${executor.id}:${action}`;
    const now = Date.now();
    const windowMs = (config.nuke.timeWindow || 30) * 1000;

    const bucket = this.actionBuckets.get(key) || [];
    const fresh = bucket.filter((ts) => now - ts < windowMs);
    fresh.push(now);
    this.actionBuckets.set(key, fresh);

    const limits = {
      [ACTION_TYPES.channelDelete]: config.nuke.channelDeleteLimit,
      [ACTION_TYPES.roleDelete]: config.nuke.roleDeleteLimit,
      [ACTION_TYPES.ban]: config.nuke.banLimit,
      [ACTION_TYPES.webhook]: config.nuke.webhookCreateLimit
    };

    if (fresh.length >= (limits[action] || Infinity)) {
      recordStat("nukeAlerts");
      pushEvent({
        type: "nuke",
        guildId: guild.id,
        message: `${executor.tag} exceeded ${action} limit (${fresh.length}/${limits[action]})`
      });
      this.logger(guild.id, `🚫 Nuke prevented: ${executor.tag} exceeded ${action} limit (${fresh.length}/${limits[action]}).`);
      this.applyPunishment(guild, executor, config);
    }
  }

  async applyPunishment(guild, executor, config) {
    const member = await guild.members.fetch(executor.id).catch(() => null);
    if (!member) return;

    if (config.nuke.punitiveAction === "ban") {
      await member.ban({ reason: "Anti-nuke trigger" }).catch(() => {});
      return;
    }

    // default: strip dangerous permissions by removing elevated roles
    const safeRoles = member.roles.cache.filter((r) => !r.permissions.has("Administrator"));
    await member.roles.set(safeRoles).catch(() => {});
    await member.timeout(60 * 60 * 1000, "Anti-nuke timeout").catch(() => {});
  }
}

export { ACTION_TYPES };
