import { ACTION_TYPES } from "../security/antiNuke.js";

export default {
  name: "guildBanAdd",
  async execute(ban) {
    const guild = ban.guild;
    const { antiNuke } = guild.client.security;
    await antiNuke.handleGuildEvent(guild, ACTION_TYPES.ban);
  }
};
