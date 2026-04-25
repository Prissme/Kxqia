import { buildErrorEmbed, buildSuccessEmbed } from "../embeds.js";

export default {
  name: "interactionCreate",
  async execute(interaction) {
    if (interaction.isButton()) {
      const roleByButtonId = {
        role_competitive: "1451687979189014548",
        role_lfn: "1406762832720035891",
        role_power_league: "1464693030937165825",
        role_ladder: "1489956692816035840",
        role_ranked: "1489956729104891975",
        role_scrims: "1489956747555766372"
      };
      if (process.env.ROLE_PROFILE_VOTE_ID) {
        roleByButtonId.role_profile_vote = process.env.ROLE_PROFILE_VOTE_ID;
      }

      if (interaction.customId === "ticket_open") {
        const { handleTicketButton } = await import("../tickets.js");
        await handleTicketButton(interaction);
        return;
      }
      if (roleByButtonId[interaction.customId]) {
        const roleId = roleByButtonId[interaction.customId];
        const member = interaction.member;
        if (!member || !interaction.guild) {
          await interaction.reply({
            embeds: [buildErrorEmbed("Impossible de mettre à jour ton rôle.")],
            ephemeral: true
          });
          return;
        }
        const hasRole = member.roles.cache.has(roleId);
        if (hasRole) {
          await member.roles.remove(roleId).catch(() => {});
          await interaction.reply({
            embeds: [buildSuccessEmbed(`<@&${roleId}> retiré.`)],
            ephemeral: true
          });
        } else {
          await member.roles.add(roleId).catch(() => {});
          await interaction.reply({
            embeds: [buildSuccessEmbed(`<@&${roleId}> ajouté.`)],
            ephemeral: true
          });
        }
        return;
      }
    }

    if (!interaction.isChatInputCommand()) return;
    if (interaction.commandName === "lockdown") {
      const enable = interaction.options.getString("state") === "enable";
      await interaction.client.security.antiRaid.handleLockdownCommand(interaction, enable);
    } else if (interaction.commandName === "trap") {
      const word = interaction.options.getString("mot");
      await interaction.client.security.trap.handleCommand(interaction, word);
    } else if (interaction.commandName === "blacklist") {
      const word = interaction.options.getString("mot");
      await interaction.client.security.trap.handleBlacklistCommand(interaction, word);
    } else if (interaction.commandName === "removeblacklist") {
      const word = interaction.options.getString("mot");
      await interaction.client.security.trap.handleRemoveBlacklistCommand(interaction, word);
    } else if (interaction.commandName === "ticket") {
      const { handleTicketCommand } = await import("../tickets.js");
      await handleTicketCommand(interaction);
    } else if (interaction.commandName === "remake") {
      if (!interaction.guild || !interaction.channel) {
        await interaction.reply({
          embeds: [buildErrorEmbed("Cette commande doit être utilisée dans un serveur.")],
          ephemeral: true
        });
        return;
      }

      if (!interaction.channel.isTextBased()) {
        await interaction.reply({
          embeds: [buildErrorEmbed("Ce type de salon n'est pas supporté pour /remake.")],
          ephemeral: true
        });
        return;
      }

      await interaction.deferReply({ ephemeral: true });

      const oldChannel = interaction.channel;
      const clonedChannel = await oldChannel.clone({
        reason: `/remake demandé par ${interaction.user.tag}`
      });
      await clonedChannel.setPosition(oldChannel.position).catch(() => {});
      await oldChannel.delete(`/remake demandé par ${interaction.user.tag}`).catch(() => {});

      await interaction.editReply({
        embeds: [buildSuccessEmbed(`Salon recréé: ${clonedChannel}`)]
      });
    }
  }
};
