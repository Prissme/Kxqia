import { PermissionsBitField } from "discord.js";
import { buildErrorEmbed, buildInfoEmbed } from "../embeds.js";

const TRAP_TIMEOUT_MS = 10 * 60 * 1000;

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export class TrapManager {
  constructor(logger) {
    this.logger = logger;
    this.traps = new Map();
    this.blacklistedWords = new Map();
  }

  async handleCommand(interaction, word) {
    if (!interaction.guild) {
      await interaction.reply({
        embeds: [buildErrorEmbed("Cette commande doit être utilisée dans un serveur.")],
        ephemeral: true
      });
      return;
    }

    const cleaned = word.trim();
    if (!cleaned) {
      await interaction.reply({
        embeds: [buildErrorEmbed("Merci de fournir un mot valide.")],
        ephemeral: true
      });
      return;
    }

    const me = interaction.guild.members.me;
    const canTimeout = me?.permissions.has(PermissionsBitField.Flags.ModerateMembers);
    if (!canTimeout) {
      await interaction.reply({
        embeds: [buildErrorEmbed("Je n'ai pas la permission de mettre des timeouts.")],
        ephemeral: true
      });
      return;
    }

    this.traps.set(interaction.guild.id, {
      word: cleaned,
      regex: new RegExp(`\\b${escapeRegExp(cleaned)}\\b`, "i")
    });

    await interaction.reply({
      embeds: [buildInfoEmbed(`🪤 La prochaine personne qui dit "${cleaned}" prend 10 minutes.`)]
    });
  }

  async handleMessage(message) {
    if (!message.guild || message.author.bot) return;

    const blacklist = this.blacklistedWords.get(message.guild.id);
    if (blacklist?.size && this.matchesBlacklistedWord(message.content, blacklist)) {
      await message.delete().catch(() => {});
      return;
    }

    const trap = this.traps.get(message.guild.id);
    if (!trap) return;

    if (!trap.regex.test(message.content)) return;

    this.traps.delete(message.guild.id);

    const member = message.member;
    if (!member) return;

    try {
      await member.timeout(TRAP_TIMEOUT_MS, `Trap word triggered: ${trap.word}`);
      await message.channel.send({
        embeds: [buildInfoEmbed(`🪤 ${member} a déclenché le trap et prend 10 minutes.`)]
      });
    } catch (error) {
      this.logger?.(message.guild.id, `Failed to timeout ${member.user.tag} for trap: ${error?.message || error}`);
    }
  }

  async handleBlacklistCommand(interaction, word) {
    if (!interaction.guild) {
      await interaction.reply({
        embeds: [buildErrorEmbed("Cette commande doit être utilisée dans un serveur.")],
        ephemeral: true
      });
      return;
    }

    if (!word) {
      const blacklist = this.blacklistedWords.get(interaction.guild.id);
      if (!blacklist?.size) {
        await interaction.reply({
          embeds: [buildInfoEmbed("Aucun mot blacklisté pour le moment.")],
          ephemeral: true
        });
        return;
      }

      const words = [...blacklist].sort((a, b) => a.localeCompare(b, "fr")).map((entry) => `• \`${entry}\``).join("\n");
      await interaction.reply({
        embeds: [buildInfoEmbed(`Mots blacklistés (${blacklist.size}) :\n${words}`)],
        ephemeral: true
      });
      return;
    }

    const cleaned = word.trim().toLowerCase();
    if (!cleaned) {
      await interaction.reply({
        embeds: [buildErrorEmbed("Merci de fournir un mot valide.")],
        ephemeral: true
      });
      return;
    }

    const blacklist = this.getOrCreateBlacklist(interaction.guild.id);
    blacklist.add(cleaned);

    await interaction.reply({
      embeds: [buildInfoEmbed(`Mot ajouté à la blacklist : \`${cleaned}\`.`)],
      ephemeral: true
    });
  }

  async handleRemoveBlacklistCommand(interaction, word) {
    if (!interaction.guild) {
      await interaction.reply({
        embeds: [buildErrorEmbed("Cette commande doit être utilisée dans un serveur.")],
        ephemeral: true
      });
      return;
    }

    const cleaned = (word || "").trim().toLowerCase();
    if (!cleaned) {
      await interaction.reply({
        embeds: [buildErrorEmbed("Merci de fournir un mot valide.")],
        ephemeral: true
      });
      return;
    }

    const blacklist = this.blacklistedWords.get(interaction.guild.id);
    if (!blacklist?.has(cleaned)) {
      await interaction.reply({
        embeds: [buildErrorEmbed(`Le mot \`${cleaned}\` n'est pas blacklisté.`)],
        ephemeral: true
      });
      return;
    }

    blacklist.delete(cleaned);
    if (blacklist.size === 0) {
      this.blacklistedWords.delete(interaction.guild.id);
    }

    await interaction.reply({
      embeds: [buildInfoEmbed(`Mot retiré de la blacklist : \`${cleaned}\`.`)],
      ephemeral: true
    });
  }

  getOrCreateBlacklist(guildId) {
    const existing = this.blacklistedWords.get(guildId);
    if (existing) return existing;
    const created = new Set();
    this.blacklistedWords.set(guildId, created);
    return created;
  }

  matchesBlacklistedWord(content, blacklist) {
    if (!content) return false;
    for (const word of blacklist) {
      const regex = new RegExp(`\\b${escapeRegExp(word)}\\b`, "i");
      if (regex.test(content)) return true;
    }
    return false;
  }
}
