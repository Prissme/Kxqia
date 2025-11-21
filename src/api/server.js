import express from "express";
import cors from "cors";
import helmet from "helmet";
import cookieParser from "cookie-parser";
import rateLimit from "express-rate-limit";
import authRouter from "./routes/auth.js";
import configRouter from "./routes/config.js";
import statsRouter from "./routes/stats.js";
import whitelistRouter from "./routes/whitelist.js";
import logsRouter from "./routes/logs.js";
import guildsRouter from "./routes/guilds.js";
import { authMiddleware } from "./middlewares/auth.js";

const buildCors = () =>
  cors({
    origin: process.env.FRONTEND_URL || "http://localhost:5173",
    credentials: true
  });

const limiter = rateLimit({
  windowMs: 60 * 1000,
  max: 100,
  standardHeaders: "draft-7",
  legacyHeaders: false
});

export function startApiServer(client) {
  const app = express();
  const port = process.env.PORT || 8080;

  app.set("trust proxy", 1);
  app.use(helmet());
  app.use(buildCors());
  app.use(express.json());
  app.use(cookieParser());
  app.use(limiter);

  app.get("/health", (req, res) => {
    res.status(200).json({ status: "ok", uptime: process.uptime() });
  });

  app.use("/api/auth", authRouter(client));
  app.use("/api/config", authMiddleware, configRouter);
  app.use("/api/stats", authMiddleware, statsRouter);
  app.use("/api/whitelist", authMiddleware, whitelistRouter);
  app.use("/api/logs", authMiddleware, logsRouter);
  app.use("/api/guilds", authMiddleware, guildsRouter(client));

  app.use("/api/*", (req, res) => res.status(404).json({ error: "Not found" }));

  app.use((err, req, res, next) => {
    console.error("API error", err);
    res.status(err.status || 500).json({ error: err.message || "Internal error" });
  });

  app.listen(port, "0.0.0.0", () => {
    console.log(`API listening on port ${port}`);
  });
}
