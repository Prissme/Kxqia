import { PermissionFlagsBits, ChannelType } from "discord.js";
import { recordStat, getConfig, getTrustLevels, pushEvent } from "../../db/database.js";
import { isTrusted } from "./trustLevels.js";

export class AntiRaid {
  constructor(client, logger) {
    this.client = client;
    this.logger = logger;
    this.joinBuckets = new Map();
    this.lockdownState = new Map();
  }

  handleMemberJoin(member) {
    const config = getConfig();
    const guildId = member.guild.id;
    const now = Date.now();
    const bucket = this.joinBuckets.get(guildId) || [];
    const fresh = bucket.filter((ts) => now - ts < 60 * 1000);
    fresh.push(now);
    this.joinBuckets.set(guildId, fresh);

    const accountAgeDays = (now - member.user.createdTimestamp) / (1000 * 60 * 60 * 24);
    const isYoung = accountAgeDays < config.raid.accountAgeDays;

    if (fresh.length >= config.raid.joinThreshold) {
      recordStat("raidAlerts");
      pushEvent({
        type: "raid",
        guildId,
        message: `Raid suspicion: ${fresh.length} joins in 60s. Account age < ${config.raid.accountAgeDays} days? ${isYoung}`
      });
      this.logger(guildId, `⚠️ Raid detected: ${fresh.length} joins in 60s. Young account: ${isYoung ? "yes" : "no"}.`);
      if (config.raid.lockdownOnRaid) {
        this.enableLockdown(member.guild, "Automatic raid lockdown");
      }
    }

    if (isYoung) {
      this.logger(guildId, `👤 New account ${member.user.tag} is ${accountAgeDays.toFixed(1)} days old.`);
      if (config.raid.kickYoungAccounts) {
        member.kick("Account too new during raid window").catch(() => {});
      } else if (config.raid.quarantineRoleId) {
        member.roles.add(config.raid.quarantineRoleId).catch(() => {});
      }
    }
  }

  async enableLockdown(guild, reason = "Lockdown enabled") {
    if (this.lockdownState.has(guild.id)) return;
    const previous = [];
    for (const channel of guild.channels.cache.values()) {
      if (channel.type !== ChannelType.GuildText) continue;
      const perm = channel.permissionOverwrites.cache.get(guild.roles.everyone.id);
      previous.push({ channelId: channel.id, allow: perm?.allow?.bitfield ?? 0n, deny: perm?.deny?.bitfield ?? 0n });
      await channel.permissionOverwrites.edit(guild.roles.everyone, {
        SendMessages: false,
        AddReactions: false
      }).catch(() => {});
    }
    this.lockdownState.set(guild.id, previous);
    this.logger(guild.id, `🚨 Lockdown enabled. Reason: ${reason}`);
  }

  async disableLockdown(guild, reason = "Lockdown disabled") {
    const previous = this.lockdownState.get(guild.id);
    if (!previous) return;
    for (const entry of previous) {
      const channel = guild.channels.cache.get(entry.channelId);
      if (!channel) continue;
      await channel.permissionOverwrites.edit(guild.roles.everyone, {
        allow: entry.allow,
        deny: entry.deny
      }).catch(() => {});
    }
    this.lockdownState.delete(guild.id);
    this.logger(guild.id, `✅ Lockdown disabled. Reason: ${reason}`);
  }

  async handleLockdownCommand(interaction, enable) {
    if (!interaction.isChatInputCommand()) return;
    const trust = getTrustLevels();
    const executorId = interaction.user.id;
    if (!isTrusted(executorId, trust)) {
      await interaction.reply({ content: "You are not trusted to run this command.", ephemeral: true });
      return;
    }

    if (enable) {
      await this.enableLockdown(interaction.guild, `Manual toggle by ${interaction.user.tag}`);
    } else {
      await this.disableLockdown(interaction.guild, `Manual toggle by ${interaction.user.tag}`);
    }
    await interaction.reply({ content: `Lockdown ${enable ? "enabled" : "disabled"}.`, ephemeral: true });
  }
}
