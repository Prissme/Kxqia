import dotenv from "dotenv";
import fs from "fs";
import path from "path";
import { createClient } from "./src/bot/client.js";
import { startDashboard } from "./src/dashboard/server.js";
import { getConfig } from "./src/db/database.js";
import { fileURLToPath } from "url";

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function logger(guildId, message) {
  console.log(`[${guildId}] ${message}`);
  const config = getConfig();
  if (!config.logChannelId) return;
  const channel = client.channels.cache.get(config.logChannelId);
  if (channel) channel.send(message).catch(() => {});
}

const client = createClient(logger);

const eventPath = path.join(__dirname, "src", "bot", "events");
for (const file of fs.readdirSync(eventPath)) {
  if (!file.endsWith(".js")) continue;
  const event = await import(path.join(eventPath, file));
  const handler = event.default;
  if (!handler) continue;
  client.on(handler.name, (...args) => handler.execute(...args));
}

startDashboard(client);

client.login(process.env.DISCORD_TOKEN);
