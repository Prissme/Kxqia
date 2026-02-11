import {
  Client,
  GatewayIntentBits,
  Partials,
  Collection,
  REST,
  Routes,
  SlashCommandBuilder,
  EmbedBuilder,
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle
} from "discord.js";
import { AntiRaid } from "./security/antiRaid.js";
import { AntiNuke } from "./security/antiNuke.js";
import { SlowModeManager } from "./security/slowMode.js";
import { TrapManager } from "./security/trap.js";
import { getConfig } from "../db/database.js";
import { TICKET_GUILD_ID, ticketCommand } from "./tickets.js";
import { buildInfoEmbed } from "./embeds.js";

export function createClient(logger) {
  const ROLE_CHANNEL_ID = "1267617798658457732";
  const ROLE_SCRIMS_ID = "1451687979189014548";
  const ROLE_LFN_ID = "1406762832720035891";
  const ROLE_PTV99_ID = "1464693030937165825";
  const client = new Client({
    intents: [
      GatewayIntentBits.Guilds,
      GatewayIntentBits.GuildMembers,
      GatewayIntentBits.GuildBans,
      GatewayIntentBits.GuildMessages,
      GatewayIntentBits.GuildPresences,
      GatewayIntentBits.GuildWebhooks,
      GatewayIntentBits.MessageContent
    ],
    partials: [Partials.GuildMember]
  });

  client.security = {
    antiRaid: new AntiRaid(client, logger),
    antiNuke: new AntiNuke(client, logger),
    slowMode: new SlowModeManager(logger),
    trap: new TrapManager(logger)
  };

  client.logger = logger;

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
  const trap = new SlashCommandBuilder()
    .setName("trap")
    .setDescription("Configurer un mot piégé")
    .addStringOption((option) =>
      option
        .setName("mot")
        .setDescription("Le mot qui déclenche le piège")
        .setRequired(true)
    );
  client.commands.set(trap.name, trap);
  client.commands.set(ticketCommand.name, ticketCommand);

  client.once("ready", async () => {
    const config = getConfig();
    const rest = new REST({ version: "10" }).setToken(process.env.DISCORD_TOKEN);
    const commandGuildId = process.env.GUILD_ID || TICKET_GUILD_ID;
    try {
      await rest.put(Routes.applicationGuildCommands(process.env.CLIENT_ID, commandGuildId), {
        body: [lockdown.toJSON(), trap.toJSON(), ticketCommand.toJSON()]
      });
      console.log("Slash commands registered.");
    } catch (err) {
      console.error("Failed to register commands", err);
    }
    console.log(`Logged in as ${client.user.tag}`);
    if (config.logChannelId) {
      const channel = await client.channels.fetch(config.logChannelId).catch(() => null);
      if (channel) {
        channel.send({ embeds: [buildInfoEmbed("Security bot is online.")] }).catch(() => {});
      }
    }

    const roleChannel = await client.channels.fetch(ROLE_CHANNEL_ID).catch(() => null);
    if (roleChannel?.isTextBased()) {
      const embed = new EmbedBuilder()
        .setTitle("Choisis tes rôles")
        .setDescription(
          `Sélectionne les rôles qui t'intéressent :\n\n` +
            `• <@&${ROLE_SCRIMS_ID}> : scrims fun/sérieux + recherche ranked\n` +
            `• <@&${ROLE_LFN_ID}> : LFN + Cups\n` +
            `• <@&${ROLE_PTV99_ID}> : si tu veux être branché sur les actus de PTV99`
        )
        .setColor(0x5865f2);

      const row = new ActionRowBuilder().addComponents(
        new ButtonBuilder()
          .setCustomId("role_scrims")
          .setLabel("Scrims / Ranked")
          .setStyle(ButtonStyle.Primary),
        new ButtonBuilder()
          .setCustomId("role_lfn")
          .setLabel("LFN / Cups")
          .setStyle(ButtonStyle.Secondary),
        new ButtonBuilder()
          .setCustomId("role_ptv99")
          .setLabel("Actus PTV99")
          .setStyle(ButtonStyle.Success)
      );

      const existing = await roleChannel.messages.fetch({ limit: 10 }).catch(() => null);
      const roleMessage = existing?.find(
        (message) =>
          message.author.id === client.user.id &&
          message.embeds?.[0]?.title === "Choisis tes rôles"
      );

      if (roleMessage) {
        await roleMessage.edit({ embeds: [embed], components: [row] }).catch(() => {});
      } else {
        await roleChannel.send({ embeds: [embed], components: [row] }).catch(() => {});
      }
    }
  });

  return client;
}
