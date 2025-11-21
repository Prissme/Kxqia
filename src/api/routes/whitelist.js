import express from "express";
import { z } from "zod";
import { getTrustLevels, setTrustLevel, removeTrust } from "../../db/database.js";
import { requireManager } from "../middlewares/permissions.js";

const router = express.Router();

const trustSchema = z.object({
  userId: z.string(),
  level: z.enum(["OWNER", "TRUSTED_ADMIN", "NORMAL_ADMIN", "DEFAULT_USER"])
});

router.get("/", (_req, res) => {
  res.json(getTrustLevels());
});

router.post("/", requireManager, (req, res) => {
  const parsed = trustSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: parsed.error.message });
  const trust = setTrustLevel(parsed.data.userId, parsed.data.level);
  res.json(trust);
});

router.put("/:userId", requireManager, (req, res) => {
  const parsed = trustSchema.safeParse({ userId: req.params.userId, level: req.body.level });
  if (!parsed.success) return res.status(400).json({ error: parsed.error.message });
  const trust = setTrustLevel(parsed.data.userId, parsed.data.level);
  res.json(trust);
});

router.delete("/:userId", requireManager, (req, res) => {
  const trust = removeTrust(req.params.userId);
  res.json(trust);
});

export default router;
