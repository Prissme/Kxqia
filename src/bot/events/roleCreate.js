import { ACTION_TYPES } from "../security/antiNuke.js";

export default {
  name: "roleCreate",
  async execute(role) {
    const { antiNuke } = role.client.security;
    await antiNuke.handleGuildEvent(role.guild, ACTION_TYPES.roleDelete);
  }
};
