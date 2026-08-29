import {
  Client,
  GatewayIntentBits,
  Partials,
  Collection,
  REST,
  Routes,
  SlashCommandBuilder,
  PermissionFlagsBits,
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
  const ROLE_COMPETITIVE_ID = "1451687979189014548";
  const ROLE_LFN_ID = "1406762832720035891";
  const ROLE_POWER_LEAGUE_ID = "1464693030937165825";
  const ROLE_LADDER_ID = "1489956692816035840";
  const ROLE_RANKED_ID = "1489956729104891975";
  const ROLE_SCRIMS_ID = "1489956747555766372";
  const ROLE_PROFILE_VOTE_ID = process.env.ROLE_PROFILE_VOTE_ID || "ROLE_ID_A_REMPLACER";
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
  const blacklist = new SlashCommandBuilder()
    .setName("blacklist")
    .setDescription("Afficher la blacklist ou ajouter un mot")
    .addStringOption((option) =>
      option
        .setName("mot")
        .setDescription("Mot à ajouter (laisse vide pour afficher la liste)")
        .setRequired(false)
    );
  client.commands.set(blacklist.name, blacklist);
  const removeBlacklist = new SlashCommandBuilder()
    .setName("removeblacklist")
    .setDescription("Retirer un mot de la blacklist")
    .addStringOption((option) =>
      option
        .setName("mot")
        .setDescription("Mot à retirer de la blacklist")
        .setRequired(true)
    );
  client.commands.set(removeBlacklist.name, removeBlacklist);
  const remake = new SlashCommandBuilder()
    .setName("remake")
    .setDescription("Supprime et recrée le salon actuel à l'identique")
    .setDefaultMemberPermissions(PermissionFlagsBits.ManageChannels)
    .setDMPermission(false);
  client.commands.set(remake.name, remake);
  client.commands.set(ticketCommand.name, ticketCommand);

  client.once("ready", async () => {
    const config = getConfig();
    const rest = new REST({ version: "10" }).setToken(process.env.DISCORD_TOKEN);
    const commandGuildId = process.env.GUILD_ID || TICKET_GUILD_ID;
    try {
      await rest.put(Routes.applicationGuildCommands(process.env.CLIENT_ID, commandGuildId), {
        body: [
          lockdown.toJSON(),
          trap.toJSON(),
          blacklist.toJSON(),
          removeBlacklist.toJSON(),
          remake.toJSON(),
          ticketCommand.toJSON()
        ]
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
      const embedAnnouncements = new EmbedBuilder()
        .setTitle("Choisis tes rôles")
        .setDescription(
          `**Les ping d'annonces**\n\n` +
            `• <@&${ROLE_COMPETITIVE_ID}> : Competitive pour toutes les compétitions du serveur\n` +
            `• <@&${ROLE_LFN_ID}> : LFN pour toutes les news sur la LFN\n` +
            `• <@&${ROLE_POWER_LEAGUE_ID}> : Power League pour toutes les news sur la PL`
        )
        .setColor(0x5865f2);

      const embedTeammates = new EmbedBuilder()
        .setDescription(
          `**Les ping teammates**\n\n` +
            `• <@&${ROLE_LADDER_ID}> : Ladder\n` +
            `• <@&${ROLE_RANKED_ID}> : Ranked\n` +
            `• <@&${ROLE_SCRIMS_ID}> : Scrims`
        )
        .setColor(0x5865f2);

      const embedOther = new EmbedBuilder()
        .setDescription(
          `**Les ping autres**\n\n` +
            `• ${
              ROLE_PROFILE_VOTE_ID === "ROLE_ID_A_REMPLACER"
                ? "Vote de Profils"
                : `<@&${ROLE_PROFILE_VOTE_ID}>`
            } : Vote de Profils pour tous les 1v1 de profils ingame`
        )
        .setColor(0x5865f2);

      const row1 = new ActionRowBuilder().addComponents(
        new ButtonBuilder()
          .setCustomId("role_competitive")
          .setLabel("Competitive")
          .setStyle(ButtonStyle.Primary),
        new ButtonBuilder()
          .setCustomId("role_lfn")
          .setLabel("LFN")
          .setStyle(ButtonStyle.Secondary),
        new ButtonBuilder()
          .setCustomId("role_power_league")
          .setLabel("Power League")
          .setStyle(ButtonStyle.Success)
      );

      const row2 = new ActionRowBuilder().addComponents(
        new ButtonBuilder()
          .setCustomId("role_ladder")
          .setLabel("Ladder")
          .setStyle(ButtonStyle.Primary),
        new ButtonBuilder()
          .setCustomId("role_ranked")
          .setLabel("Ranked")
          .setStyle(ButtonStyle.Secondary),
        new ButtonBuilder()
          .setCustomId("role_scrims")
          .setLabel("Scrims")
          .setStyle(ButtonStyle.Success)
      );

      const components = [row1, row2];
      if (ROLE_PROFILE_VOTE_ID !== "ROLE_ID_A_REMPLACER") {
        components.push(
          new ActionRowBuilder().addComponents(
            new ButtonBuilder()
              .setCustomId("role_profile_vote")
              .setLabel("Vote de Profils")
              .setStyle(ButtonStyle.Secondary)
          )
        );
      }

      const existing = await roleChannel.messages.fetch({ limit: 10 }).catch(() => null);
      const roleMessage = existing?.find(
        (message) =>
          message.author.id === client.user.id &&
          message.embeds?.[0]?.title === "Choisis tes rôles"
      );

      if (roleMessage) {
        await roleMessage
          .edit({ embeds: [embedAnnouncements, embedTeammates, embedOther], components })
          .catch(() => {});
      } else {
        await roleChannel
          .send({ embeds: [embedAnnouncements, embedTeammates, embedOther], components })
          .catch(() => {});
      }
    }
  });

  return client;
}
