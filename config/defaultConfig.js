export default {
  logChannelId: "", // channel where security logs are sent
  raid: {
    joinThreshold: 10, // joins in 60s before triggering raid
    accountAgeDays: 7, // minimum account age to be considered safe
    lockdownOnRaid: true,
    kickYoungAccounts: false,
    quarantineRoleId: "" // optional role to assign to young accounts instead of kick
  },
  nuke: {
    channelDeleteLimit: 3,
    roleDeleteLimit: 5,
    banLimit: 10,
    webhookCreateLimit: 3,
    timeWindow: 30, // seconds
    punitiveAction: "strip", // strip roles or ban
    allowOwner: true
  }
};
