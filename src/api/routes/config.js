import express from "express";
import { z } from "zod";
import { getConfig, updateConfig } from "../../db/database.js";
import { requireManager } from "../middlewares/permissions.js";

const router = express.Router();

const raidSchema = z.object({
  joinThreshold: z.number().int().min(1).max(50),
  accountAgeDays: z.number().int().min(0).max(365),
  lockdownOnRaid: z.boolean(),
  kickYoungAccounts: z.boolean(),
  quarantineRoleId: z.string().optional()
});

const nukeSchema = z.object({
  channelDeleteLimit: z.number().int().min(1).max(50),
  roleDeleteLimit: z.number().int().min(1).max(50),
  banLimit: z.number().int().min(1).max(100),
  webhookCreateLimit: z.number().int().min(1).max(50),
  timeWindow: z.number().int().min(10).max(300),
  punitiveAction: z.enum(["strip", "ban"]),
  allowOwner: z.boolean()
});

const configSchema = z.object({
  logChannelId: z.string().optional(),
  raid: raidSchema,
  nuke: nukeSchema
});

router.get("/", (_req, res) => {
  res.json(getConfig());
});

router.post("/", requireManager, (req, res) => {
  const parsed = configSchema.safeParse(req.body);
  if (!parsed.success) {
    return res.status(400).json({ error: parsed.error.message });
  }
  const updated = updateConfig(parsed.data);
  res.json(updated);
});

export default router;
