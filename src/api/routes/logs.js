import express from "express";
import { getStats } from "../../db/database.js";

const router = express.Router();

router.get("/", (req, res) => {
  const { events } = getStats();
  const { type } = req.query;
  const filtered = type ? events.filter((evt) => evt.type === type) : events;
  res.json(filtered);
});

export default router;
