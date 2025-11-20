import { ACTION_TYPES } from "../security/antiNuke.js";

export default {
  name: "channelDelete",
  async execute(channel) {
    const { antiNuke } = channel.client.security;
    await antiNuke.handleGuildEvent(channel.guild, ACTION_TYPES.channelDelete);
  }
};
