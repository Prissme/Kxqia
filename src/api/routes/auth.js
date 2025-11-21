import express from "express";
import { authMiddleware, issueToken } from "../middlewares/auth.js";
import { getCurrentUser } from "../controllers/discord.js";

const router = express.Router();

export default function authRouter(client) {
  router.post("/login/discord", async (req, res) => {
    const { code, userId, guilds } = req.body;
    if (!code && !userId) {
      return res.status(400).json({ error: "Missing authorization code or userId" });
    }

    const tokenPayload = {
      userId: userId || "demo-user",
      guilds: guilds || [],
      trustLevel: "TRUSTED_ADMIN"
    };
    const token = issueToken(tokenPayload, { expiresIn: "1h" });
    res
      .cookie("token", token, {
        httpOnly: true,
        sameSite: "lax",
        secure: process.env.NODE_ENV === "production",
        maxAge: 60 * 60 * 1000
      })
      .json({ token });
  });

  router.post("/refresh", (req, res) => {
    const { refreshToken } = req.body;
    if (!refreshToken) return res.status(400).json({ error: "Missing refresh token" });
    const token = issueToken({ userId: "demo-user" }, { expiresIn: "1h" });
    res.json({ token });
  });

  router.get("/me", authMiddleware, async (req, res) => {
    const user = await getCurrentUser(client, req.user?.userId);
    res.json({ user });
  });

  return router;
}
