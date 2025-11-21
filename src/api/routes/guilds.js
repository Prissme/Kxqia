import express from "express";
import { getGuildOverview, getGuildDetails } from "../controllers/discord.js";

const router = express.Router();

export default function guildsRouter(client) {
  router.get("/", async (_req, res) => {
    const guilds = await getGuildOverview(client);
    res.json(guilds);
  });

  router.get("/:id", async (req, res) => {
    const guild = await getGuildDetails(client, req.params.id);
    if (!guild) return res.status(404).json({ error: "Guild not found" });
    res.json(guild);
  });

  return router;
}
