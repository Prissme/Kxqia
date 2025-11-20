export default {
  name: "guildMemberAdd",
  async execute(member) {
    const { antiRaid } = member.client.security;
    antiRaid.handleMemberJoin(member);
  }
};
