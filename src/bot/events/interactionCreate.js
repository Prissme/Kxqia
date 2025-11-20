export default {
  name: "interactionCreate",
  async execute(interaction) {
    if (!interaction.isChatInputCommand()) return;
    if (interaction.commandName === "lockdown") {
      const enable = interaction.options.getString("state") === "enable";
      await interaction.client.security.antiRaid.handleLockdownCommand(interaction, enable);
    }
  }
};
