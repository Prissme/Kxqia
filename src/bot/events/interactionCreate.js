export default {
  name: "interactionCreate",
  async execute(interaction) {
    if (interaction.isButton()) {
      if (interaction.customId === "ticket_open") {
        const { handleTicketButton } = await import("../tickets.js");
        await handleTicketButton(interaction);
      }
      return;
    }

    if (!interaction.isChatInputCommand()) return;
    if (interaction.commandName === "lockdown") {
      const enable = interaction.options.getString("state") === "enable";
      await interaction.client.security.antiRaid.handleLockdownCommand(interaction, enable);
    } else if (interaction.commandName === "ticket") {
      const { handleTicketCommand } = await import("../tickets.js");
      await handleTicketCommand(interaction);
    }
  }
};
