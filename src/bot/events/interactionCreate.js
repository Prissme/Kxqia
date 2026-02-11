import { buildErrorEmbed, buildSuccessEmbed } from "../embeds.js";

export default {
  name: "interactionCreate",
  async execute(interaction) {
    if (interaction.isButton()) {
      const roleByButtonId = {
        role_scrims: "1451687979189014548",
        role_lfn: "1406762832720035891",
        role_ptv99: "1464693030937165825"
      };

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
    } else if (interaction.commandName === "ticket") {
      const { handleTicketCommand } = await import("../tickets.js");
      await handleTicketCommand(interaction);
    }
  }
};
