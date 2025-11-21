import express from "express";
import { getStats } from "../../db/database.js";

const router = express.Router();

router.get("/", (_req, res) => {
  res.json(getStats());
});

export default router;
