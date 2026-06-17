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

const slowModeTierSchema = z.object({
  threshold: z.number().min(1).max(500),
  seconds: z.number().int().min(0).max(21600)
});

const slowModeSchema = z.object({
  enabled: z.boolean(),
  windowSeconds: z.number().int().min(10).max(600),
  minUpdateIntervalSeconds: z.number().int().min(5).max(600),
  tiers: z.array(slowModeTierSchema).nonempty()
});

const nukeSchema = z.object({
  channelDeleteLimit: z.number().int().min(1).max(50),
  roleDeleteLimit: z.number().int().min(1).max(50),
  banLimit: z.number().int().min(1).max(100),
  webhookCreateLimit: z.number().int().min(1).max(50),
  channelUpdateLimit: z.number().int().min(1).max(50).default(3),
  globalActionLimit: z.number().int().min(1).max(100).default(4),
  botActionLimit: z.number().int().min(1).max(10).default(1),
  auditLogMaxAge: z.number().int().min(5).max(120).default(15),
  timeWindow: z.number().int().min(10).max(300),
  punitiveAction: z.enum(["strip", "ban"]),
  botPunitiveAction: z.enum(["strip", "ban"]).default("ban"),
  protectBots: z.boolean().default(true),
  allowOwner: z.boolean()
});

const configSchema = z.object({
  logChannelId: z.string().optional(),
  slowMode: slowModeSchema,
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
