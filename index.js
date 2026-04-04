const { Client, GatewayIntentBits, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, Events, PermissionsBitField } = require('discord.js');
require('dotenv').config();

const CHANNEL_ID = '1267617798658457732';
const ROLE_COMP = '1406762832720035891';
const ROLE_LFN_NEWS = '1455197400560832676';
const ROLE_VOTES2PROFILS = '1473663706100531282';
const ROLE_POWER_LEAGUE = '1469030334510137398';
const ROLE_LADDER = '1489956692816035840';
const ROLE_RANKED = '1489956729104891975';
const ROLE_SCRIMS = '1489956747555766372';

const BUTTON_COMP = 'toggle_role_competitive';
const BUTTON_LFN_NEWS = 'toggle_role_lfn_news';
const BUTTON_VOTES2PROFILS = 'toggle_role_votes2profils';
const BUTTON_POWER_LEAGUE = 'toggle_role_power_league';
const BUTTON_LADDER = 'toggle_role_ladder';
const BUTTON_RANKED = 'toggle_role_ranked';
const BUTTON_SCRIMS = 'toggle_role_scrims';
const SAFE_ALLOWED_MENTIONS = { parse: [] };

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMembers],
});

function buildRoleEmbeds() {
  const embed1 = new EmbedBuilder()
    .setTitle('Choisis tes rôles')
    .setDescription(
      [
        "**Les ping d'annonces**",
        `• <@&${ROLE_COMP}> — Competitive pour toutes les compétitions du serveur`,
        `• <@&${ROLE_LFN_NEWS}> — LFN pour toutes les news sur la LFN`,
        `• <@&${ROLE_POWER_LEAGUE}> — Power League pour toutes les news sur la PL`,
      ].join('\n')
    );

  const embed2 = new EmbedBuilder()
    .setDescription(
      [
        '**Les ping teammates**',
        `• <@&${ROLE_LADDER}> — Ladder`,
        `• <@&${ROLE_RANKED}> — Ranked`,
        `• <@&${ROLE_SCRIMS}> — Scrims`,
      ].join('\n')
    );

  const embed3 = new EmbedBuilder()
    .setDescription(
      [
        '**Les ping autres**',
        `• <@&${ROLE_VOTES2PROFILS}> — Vote de Profils pour tous les 1v1 de profils ingame`,
      ].join('\n')
    );

  return [embed1, embed2, embed3];
}

function buildRoleButtons() {
  const row1 = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(BUTTON_COMP).setLabel('🏆 Competitive').setStyle(ButtonStyle.Success),
    new ButtonBuilder().setCustomId(BUTTON_LFN_NEWS).setLabel('📰 LFN').setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(BUTTON_POWER_LEAGUE).setLabel('⚡ Power League').setStyle(ButtonStyle.Primary)
  );

  const row2 = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(BUTTON_LADDER).setLabel('🎯 Ladder').setStyle(ButtonStyle.Primary),
    new ButtonBuilder().setCustomId(BUTTON_RANKED).setLabel('🥇 Ranked').setStyle(ButtonStyle.Secondary),
    new ButtonBuilder().setCustomId(BUTTON_SCRIMS).setLabel('⚔️ Scrims').setStyle(ButtonStyle.Danger)
  );

  const row3 = new ActionRowBuilder().addComponents(
    new ButtonBuilder().setCustomId(BUTTON_VOTES2PROFILS).setLabel('🗳️ Vote de Profils').setStyle(ButtonStyle.Secondary)
  );

  return [row1, row2, row3];
}

function isRolePanelMessage(message) {
  return (
    message.author?.id === client.user?.id &&
    message.embeds?.[0]?.title === 'Choisis tes rôles'
  );
}

function buildStatusEmbed(message, color) {
  return new EmbedBuilder().setDescription(message).setColor(color);
}

async function sendRoleMessage() {
  const channel = await client.channels.fetch(CHANNEL_ID).catch(() => null);
  if (!channel || !channel.isTextBased()) return;
  const payload = {
    embeds: buildRoleEmbeds(),
    components: buildRoleButtons(),
    allowedMentions: SAFE_ALLOWED_MENTIONS,
  };

  const existingMessages = await channel.messages.fetch({ limit: 20 }).catch(() => null);
  const existingPanel = existingMessages?.find((message) => isRolePanelMessage(message));

  if (existingPanel) {
    await existingPanel.edit(payload).catch(() => null);
    return;
  }

  await channel.send(payload);
}

async function handleToggle(interaction, roleId) {
  if (!interaction.inGuild()) return;

  const guild = interaction.guild;
  const me = guild.members.me || (await guild.members.fetchMe().catch(() => null));
  if (!me) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Membre du bot introuvable.", 0xed4245)],
      ephemeral: true,
      allowedMentions: SAFE_ALLOWED_MENTIONS
    });
  }

  if (!me.permissions.has(PermissionsBitField.Flags.ManageRoles)) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Je n'ai pas la permission Manage Roles.", 0xed4245)],
      ephemeral: true,
      allowedMentions: SAFE_ALLOWED_MENTIONS
    });
  }

  const role = guild.roles.cache.get(roleId) || (await guild.roles.fetch(roleId).catch(() => null));
  if (!role) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Rôle introuvable.", 0xed4245)],
      ephemeral: true,
      allowedMentions: SAFE_ALLOWED_MENTIONS
    });
  }

  if (me.roles.highest.comparePositionTo(role) <= 0) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Mon rôle est en dessous du rôle à attribuer.", 0xed4245)],
      ephemeral: true,
      allowedMentions: SAFE_ALLOWED_MENTIONS
    });
  }

  const member = await guild.members.fetch(interaction.user.id).catch(() => null);
  if (!member) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Membre introuvable.", 0xed4245)],
      ephemeral: true,
      allowedMentions: SAFE_ALLOWED_MENTIONS
    });
  }

  try {
    if (member.roles.cache.has(role.id)) {
      await member.roles.remove(role.id);
      return interaction.reply({
        embeds: [buildStatusEmbed("Rôle retiré ❌", 0x57f287)],
        ephemeral: true,
        allowedMentions: SAFE_ALLOWED_MENTIONS
      });
    }

    await member.roles.add(role.id);
    return interaction.reply({
      embeds: [buildStatusEmbed("Rôle ajouté ✅", 0x57f287)],
      ephemeral: true,
      allowedMentions: SAFE_ALLOWED_MENTIONS
    });
  } catch (error) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Erreur lors de la mise à jour du rôle.", 0xed4245)],
      ephemeral: true,
      allowedMentions: SAFE_ALLOWED_MENTIONS
    });
  }
}

client.once(Events.ClientReady, async () => {
  console.log(`Connecté en tant que ${client.user.tag}`);
  await sendRoleMessage();
});

client.on(Events.InteractionCreate, async (interaction) => {
  if (!interaction.isButton()) return;
  if (!interaction.inGuild()) return;

  if (interaction.customId === BUTTON_SCRIMS) {
    return handleToggle(interaction, ROLE_SCRIMS);
  }

  if (interaction.customId === BUTTON_COMP) {
    return handleToggle(interaction, ROLE_COMP);
  }

  if (interaction.customId === BUTTON_LFN_NEWS) {
    return handleToggle(interaction, ROLE_LFN_NEWS);
  }

  if (interaction.customId === BUTTON_VOTES2PROFILS) {
    return handleToggle(interaction, ROLE_VOTES2PROFILS);
  }

  if (interaction.customId === BUTTON_POWER_LEAGUE) {
    return handleToggle(interaction, ROLE_POWER_LEAGUE);
  }

  if (interaction.customId === BUTTON_LADDER) {
    return handleToggle(interaction, ROLE_LADDER);
  }

  if (interaction.customId === BUTTON_RANKED) {
    return handleToggle(interaction, ROLE_RANKED);
  }
});

client.login(process.env.DISCORD_TOKEN);
