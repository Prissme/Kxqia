export default {
  logChannelId: "", // channel where security logs are sent
  slowMode: {
    enabled: true,
    windowSeconds: 60,
    minUpdateIntervalSeconds: 15,
    tiers: [
      { threshold: 60, seconds: 10 },
      { threshold: 30, seconds: 5 },
      { threshold: 15, seconds: 2 }
    ]
  },
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
    channelUpdateLimit: 3,
    globalActionLimit: 4,
    botActionLimit: 1,
    auditLogMaxAge: 15,
    timeWindow: 30, // seconds
    punitiveAction: "strip", // strip roles or ban
    botPunitiveAction: "ban", // bots that nuke are banned/kicked by default
    protectBots: true,
    allowOwner: true
  }
};
