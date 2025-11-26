import { Client, GatewayIntentBits, Partials, Collection, REST, Routes, SlashCommandBuilder } from "discord.js";
import { AntiRaid } from "./security/antiRaid.js";
import { AntiNuke } from "./security/antiNuke.js";
import { SlowModeManager } from "./security/slowMode.js";
import { getConfig } from "../db/database.js";

export function createClient(logger) {
  const client = new Client({
    intents: [
      GatewayIntentBits.Guilds,
      GatewayIntentBits.GuildMembers,
      GatewayIntentBits.GuildBans,
      GatewayIntentBits.GuildMessages,
      GatewayIntentBits.GuildPresences,
      GatewayIntentBits.GuildWebhooks
    ],
    partials: [Partials.GuildMember]
  });

  client.security = {
    antiRaid: new AntiRaid(client, logger),
    antiNuke: new AntiNuke(client, logger),
    slowMode: new SlowModeManager(logger)
  };

  client.commands = new Collection();
  const lockdown = new SlashCommandBuilder()
    .setName("lockdown")
    .setDescription("Toggle lockdown mode")
    .addStringOption((option) =>
      option
        .setName("state")
        .setDescription("enable or disable")
        .setRequired(true)
        .addChoices(
          { name: "enable", value: "enable" },
          { name: "disable", value: "disable" }
        )
    );
  client.commands.set(lockdown.name, lockdown);

  client.once("ready", async () => {
    const config = getConfig();
    const rest = new REST({ version: "10" }).setToken(process.env.DISCORD_TOKEN);
    try {
      await rest.put(Routes.applicationGuildCommands(process.env.CLIENT_ID, process.env.GUILD_ID), {
        body: [lockdown.toJSON()]
      });
      console.log("Slash commands registered.");
    } catch (err) {
      console.error("Failed to register commands", err);
    }
    console.log(`Logged in as ${client.user.tag}`);
    if (config.logChannelId) {
      const channel = await client.channels.fetch(config.logChannelId).catch(() => null);
      if (channel) channel.send("Security bot is online.").catch(() => {});
    }
  });

  return client;
}
