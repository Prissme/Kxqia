import { EmbedBuilder } from "discord.js";

export const EMBED_COLOR = 0x5865f2;
export const SUCCESS_COLOR = 0x57f287;
export const ERROR_COLOR = 0xed4245;

export function buildInfoEmbed(description, title) {
  const embed = new EmbedBuilder().setDescription(description).setColor(EMBED_COLOR);
  if (title) embed.setTitle(title);
  return embed;
}

export function buildSuccessEmbed(description, title) {
  const embed = new EmbedBuilder().setDescription(description).setColor(SUCCESS_COLOR);
  if (title) embed.setTitle(title);
  return embed;
}

export function buildErrorEmbed(description, title) {
  const embed = new EmbedBuilder().setDescription(description).setColor(ERROR_COLOR);
  if (title) embed.setTitle(title);
  return embed;
}
