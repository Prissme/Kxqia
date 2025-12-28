const { Client, GatewayIntentBits, ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder, Events, PermissionsBitField } = require('discord.js');
require('dotenv').config();

const CHANNEL_ID = '1267617798658457732';
const ROLE_SCRIMS = '1451687979189014548';
const ROLE_COMP = '1406762832720035891';

const BUTTON_SCRIMS = 'toggle_role_scrims_ranked';
const BUTTON_COMP = 'toggle_role_competitive';

const client = new Client({
  intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMembers],
});

function buildRoleEmbed() {
  return new EmbedBuilder()
    .setTitle('Choisis tes rôles')
    .setDescription('Clique sur un bouton pour activer ou retirer un rôle (opt-in).');
}

function buildRoleButtons() {
  const scrimsButton = new ButtonBuilder()
    .setCustomId(BUTTON_SCRIMS)
    .setLabel('⚔️ Scrims / Ranked')
    .setStyle(ButtonStyle.Primary);

  const compButton = new ButtonBuilder()
    .setCustomId(BUTTON_COMP)
    .setLabel('🏆 Competitive')
    .setStyle(ButtonStyle.Success);

  return new ActionRowBuilder().addComponents(scrimsButton, compButton);
}

function buildStatusEmbed(message, color) {
  return new EmbedBuilder().setDescription(message).setColor(color);
}

async function sendRoleMessage() {
  const channel = await client.channels.fetch(CHANNEL_ID).catch(() => null);
  if (!channel || !channel.isTextBased()) return;
  await channel.send({ embeds: [buildRoleEmbed()], components: [buildRoleButtons()] });
}

async function handleToggle(interaction, roleId) {
  if (!interaction.inGuild()) return;

  const guild = interaction.guild;
  const me = guild.members.me || (await guild.members.fetchMe().catch(() => null));
  if (!me) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Membre du bot introuvable.", 0xed4245)],
      ephemeral: true
    });
  }

  if (!me.permissions.has(PermissionsBitField.Flags.ManageRoles)) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Je n'ai pas la permission Manage Roles.", 0xed4245)],
      ephemeral: true
    });
  }

  const role = guild.roles.cache.get(roleId) || (await guild.roles.fetch(roleId).catch(() => null));
  if (!role) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Rôle introuvable.", 0xed4245)],
      ephemeral: true
    });
  }

  if (me.roles.highest.comparePositionTo(role) <= 0) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Mon rôle est en dessous du rôle à attribuer.", 0xed4245)],
      ephemeral: true
    });
  }

  const member = await guild.members.fetch(interaction.user.id).catch(() => null);
  if (!member) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Membre introuvable.", 0xed4245)],
      ephemeral: true
    });
  }

  try {
    if (member.roles.cache.has(role.id)) {
      await member.roles.remove(role.id);
      return interaction.reply({
        embeds: [buildStatusEmbed("Rôle retiré ❌", 0x57f287)],
        ephemeral: true
      });
    }

    await member.roles.add(role.id);
    return interaction.reply({
      embeds: [buildStatusEmbed("Rôle ajouté ✅", 0x57f287)],
      ephemeral: true
    });
  } catch (error) {
    return interaction.reply({
      embeds: [buildStatusEmbed("Erreur lors de la mise à jour du rôle.", 0xed4245)],
      ephemeral: true
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
});

client.login(process.env.DISCORD_TOKEN);
