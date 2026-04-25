export default {
  name: "messageCreate",
  async execute(message) {
    if (message.guild && !message.author.bot) {
      const imageAttachmentsCount = message.attachments.filter((attachment) => {
        if (attachment.contentType?.startsWith("image/")) return true;
        if (typeof attachment.width === "number" || typeof attachment.height === "number") return true;
        return /\.(png|jpe?g|gif|webp|bmp|tiff|svg)$/i.test(attachment.name || "");
      }).size;
      if (imageAttachmentsCount === 4) {
        await message.delete().catch(() => {});
        return;
      }
    }

    const { slowMode, trap } = message.client.security;
    trap.handleMessage(message);
    slowMode.handleMessage(message);
  }
};
