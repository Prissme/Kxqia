export async function getCurrentUser(client, userId) {
  if (!userId) return null;
  try {
    return await client.users.fetch(userId);
  } catch (err) {
    return null;
  }
}

export async function getGuildOverview(client) {
  return client.guilds.cache.map((guild) => ({
    id: guild.id,
    name: guild.name,
    memberCount: guild.memberCount,
    icon: guild.iconURL({ size: 128 }),
    joinedAt: guild.joinedTimestamp
  }));
}

export async function getGuildDetails(client, guildId) {
  const guild = client.guilds.cache.get(guildId);
  if (!guild) return null;
  const roles = guild.roles.cache
    .filter((r) => !r.managed)
    .map((role) => ({
      id: role.id,
      name: role.name,
      permissions: role.permissions.toArray()
    }));
  const channels = guild.channels.cache.map((channel) => ({
    id: channel.id,
    name: channel.name,
    type: channel.type
  }));
  return {
    id: guild.id,
    name: guild.name,
    icon: guild.iconURL({ size: 128 }),
    memberCount: guild.memberCount,
    roles,
    channels
  };
}
