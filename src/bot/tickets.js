import {
  ActionRowBuilder,
  ButtonBuilder,
  ButtonStyle,
  ChannelType,
  EmbedBuilder,
  PermissionFlagsBits,
  SlashCommandBuilder,
  bold,
  inlineCode
} from "discord.js";
import {
  closeTicketRecord,
  createTicketRecord,
  getOpenTicket,
  getSupabase,
  getTicketByChannel
} from "../tickets/supabase.js";

export const TICKET_GUILD_ID = process.env.TICKET_GUILD_ID || "1376052088047665242";
const SUPPORT_ROLE_ID = process.env.TICKET_SUPPORT_ROLE_ID;
const CATEGORY_ID = process.env.TICKET_CATEGORY_ID;
const OPEN_TICKET_CUSTOM_ID = "ticket_open";

export const ticketCommand = new SlashCommandBuilder()
  .setName("ticket")
  .setDescription("Créer ou gérer un ticket support")
  .setDMPermission(false)
  .setDefaultMemberPermissions(PermissionFlagsBits.SendMessages)
  .addSubcommand((sub) =>
    sub
      .setName("ouvrir")
      .setDescription("Ouvre un ticket privé avec le staff")
      .addStringOption((opt) => opt.setName("sujet").setDescription("Sujet du ticket"))
  )
  .addSubcommand((sub) =>
    sub
      .setName("fermer")
      .setDescription("Ferme le ticket actuel")
      .addStringOption((opt) => opt.setName("raison").setDescription("Raison de la fermeture"))
  )
  .addSubcommand((sub) =>
    sub
      .setName("panel")
      .setDescription("Publie l'embed avec bouton pour ouvrir un ticket dans ce salon")
  );

function buildTicketPanel() {
  const embed = new EmbedBuilder()
    .setTitle("Besoin d'aide ?")
    .setDescription(
      "Clique sur le bouton ci-dessous pour ouvrir un ticket privé avec l'équipe support. " +
        "Un membre du staff te répondra dès que possible."
    )
    .setColor(0x5865f2);

  const button = new ButtonBuilder()
    .setCustomId(OPEN_TICKET_CUSTOM_ID)
    .setLabel("Ouvrir un ticket")
    .setEmoji("🎟️")
    .setStyle(ButtonStyle.Primary);

  return {
    embeds: [embed],
    components: [new ActionRowBuilder().addComponents(button)]
  };
}

function buildPermissions(guild, requesterId) {
  const base = [
    { id: guild.roles.everyone, deny: [PermissionFlagsBits.ViewChannel] },
    {
      id: requesterId,
      allow: [
        PermissionFlagsBits.ViewChannel,
        PermissionFlagsBits.SendMessages,
        PermissionFlagsBits.ReadMessageHistory,
        PermissionFlagsBits.AttachFiles,
        PermissionFlagsBits.EmbedLinks
      ]
    }
  ];

  if (SUPPORT_ROLE_ID) {
    base.push({
      id: SUPPORT_ROLE_ID,
      allow: [
        PermissionFlagsBits.ViewChannel,
        PermissionFlagsBits.SendMessages,
        PermissionFlagsBits.ManageMessages,
        PermissionFlagsBits.ReadMessageHistory
      ]
    });
  }

  return base;
}

async function createTicketChannel(interaction, topic) {
  const guild = interaction.guild;
  const name = `ticket-${interaction.user.username.toLowerCase().replace(/[^a-z0-9]/gi, "-")}`.slice(0, 90);

  return guild.channels.create({
    name,
    type: ChannelType.GuildText,
    parent: CATEGORY_ID || null,
    topic: topic || "Assistance membre",
    reason: `Ticket de ${interaction.user.tag}`,
    permissionOverwrites: buildPermissions(guild, interaction.user.id)
  });
}

async function handleOpen(interaction) {
  if (interaction.guildId !== TICKET_GUILD_ID) {
    return interaction.reply({
      ephemeral: true,
      content: "Le système de tickets est uniquement disponible sur le serveur support."
    });
  }

  const supabase = getSupabase();
  if (!supabase) {
    return interaction.reply({
      ephemeral: true,
      content: "Configuration Supabase manquante : impossible d'ouvrir un ticket."
    });
  }

  const existing = await getOpenTicket(TICKET_GUILD_ID, interaction.user.id);
  if (existing) {
    const channel = await interaction.guild.channels.fetch(existing.channel_id).catch(() => null);
    if (channel) {
      return interaction.reply({
        ephemeral: true,
        content: `Vous avez déjà un ticket ouvert : ${channel.toString()}`
      });
    }

    await closeTicketRecord(existing.channel_id, interaction.user.id, "missing_channel");
  }

  const topic = interaction.options.getString("sujet") || undefined;
  const channel = await createTicketChannel(interaction, topic);

  await createTicketRecord({
    guildId: TICKET_GUILD_ID,
    userId: interaction.user.id,
    channelId: channel.id,
    topic
  });

  const supportPing = SUPPORT_ROLE_ID ? `<@&${SUPPORT_ROLE_ID}>` : "l'équipe";
  await channel.send(
    `${supportPing} nouveau ticket ouvert par ${interaction.user} — décris ton problème pour qu'on puisse t'aider.\n` +
      `Sujet : ${inlineCode(topic || "non spécifié")}`
  );

  return interaction.reply({
    ephemeral: true,
    content: `Ticket créé : ${channel.toString()}`
  });
}

async function handlePanel(interaction) {
  if (interaction.guildId !== TICKET_GUILD_ID) {
    return interaction.reply({
      ephemeral: true,
      content: "Le panneau de tickets est réservé au serveur support."
    });
  }

  const canManagePanel = interaction.memberPermissions?.has(PermissionFlagsBits.ManageChannels);
  const hasSupportRole = SUPPORT_ROLE_ID && interaction.member?.roles?.cache?.has(SUPPORT_ROLE_ID);

  if (!canManagePanel && !hasSupportRole) {
    return interaction.reply({
      ephemeral: true,
      content: "Seul le staff peut publier le panneau de tickets."
    });
  }

  const panel = buildTicketPanel();
  await interaction.channel.send(panel);

  return interaction.reply({ ephemeral: true, content: "Panneau de tickets publié." });
}

async function handleClose(interaction) {
  const supabase = getSupabase();
  if (!supabase) {
    return interaction.reply({
      ephemeral: true,
      content: "Configuration Supabase manquante : impossible de fermer ce ticket."
    });
  }

  const ticket = await getTicketByChannel(interaction.channelId);
  if (!ticket) {
    return interaction.reply({ ephemeral: true, content: "Ce salon n'est pas reconnu comme un ticket." });
  }

  const isOwner = ticket.user_id === interaction.user.id;
  const hasSupportRole = SUPPORT_ROLE_ID
    ? interaction.member.roles.cache.has(SUPPORT_ROLE_ID)
    : interaction.memberPermissions.has(PermissionFlagsBits.ManageChannels);

  if (!isOwner && !hasSupportRole) {
    return interaction.reply({ ephemeral: true, content: "Seul le créateur ou le staff peut fermer ce ticket." });
  }

  const reason = interaction.options.getString("raison") || "Ticket clôturé";

  await closeTicketRecord(interaction.channelId, interaction.user.id);

  await interaction.channel.permissionOverwrites.edit(interaction.guild.roles.everyone, {
    ViewChannel: false
  });

  await interaction.channel.setName(`closed-${interaction.channel.name}`.slice(0, 90)).catch(() => {});
  await interaction.channel.send(
    `${bold("Ticket fermé")} par ${interaction.user}. Raison : ${inlineCode(reason)}. Le salon sera supprimé dans 1 heure.`
  );

  setTimeout(() => interaction.channel.delete("Ticket fermé").catch(() => {}), 60 * 60 * 1000);

  return interaction.reply({ ephemeral: true, content: "Ticket fermé." });
}

export async function handleTicketCommand(interaction) {
  const sub = interaction.options.getSubcommand();

  if (sub === "ouvrir") return handleOpen(interaction);
  if (sub === "fermer") return handleClose(interaction);
  if (sub === "panel") return handlePanel(interaction);

  return interaction.reply({ ephemeral: true, content: "Commande de ticket inconnue." });
}

export async function handleTicketButton(interaction) {
  if (interaction.customId !== OPEN_TICKET_CUSTOM_ID) return;

  // Re-use the same logic as the slash command while keeping the interaction response ephemeral
  const supabase = getSupabase();
  if (!supabase) {
    return interaction.reply({
      ephemeral: true,
      content: "Configuration Supabase manquante : impossible d'ouvrir un ticket."
    });
  }

  if (interaction.guildId !== TICKET_GUILD_ID) {
    return interaction.reply({ ephemeral: true, content: "Ce bouton n'est pas actif sur ce serveur." });
  }

  const existing = await getOpenTicket(TICKET_GUILD_ID, interaction.user.id);
  if (existing) {
    const channel = await interaction.guild.channels.fetch(existing.channel_id).catch(() => null);
    if (channel) {
      return interaction.reply({
        ephemeral: true,
        content: `Tu as déjà un ticket ouvert : ${channel.toString()}`
      });
    }

    await closeTicketRecord(existing.channel_id, interaction.user.id, "missing_channel");
  }

  const channel = await createTicketChannel(interaction, undefined);

  await createTicketRecord({
    guildId: TICKET_GUILD_ID,
    userId: interaction.user.id,
    channelId: channel.id,
    topic: null
  });

  const supportPing = SUPPORT_ROLE_ID ? `<@&${SUPPORT_ROLE_ID}>` : "l'équipe";
  await channel.send(
    `${supportPing} nouveau ticket ouvert par ${interaction.user} — décris ton problème pour qu'on puisse t'aider.\n` +
      `Sujet : ${inlineCode("non spécifié")}`
  );

  return interaction.reply({
    ephemeral: true,
    content: `Ticket créé : ${channel.toString()}`
  });
}
