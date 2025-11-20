import { ACTION_TYPES } from "../security/antiNuke.js";

function permissionsChanged(oldChannel, newChannel) {
  const oldPerms = Array.from(oldChannel.permissionOverwrites.cache.values()).map((p) => `${p.id}:${p.allow.bitfield}:${p.deny.bitfield}`).join("|");
  const newPerms = Array.from(newChannel.permissionOverwrites.cache.values()).map((p) => `${p.id}:${p.allow.bitfield}:${p.deny.bitfield}`).join("|");
  return oldPerms !== newPerms;
}

export default {
  name: "channelUpdate",
  async execute(oldChannel, newChannel) {
    if (!permissionsChanged(oldChannel, newChannel)) return;
    const { antiNuke } = newChannel.client.security;
    await antiNuke.handleGuildEvent(newChannel.guild, ACTION_TYPES.channelDelete);
  }
};
