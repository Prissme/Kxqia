import express from "express";
import session from "express-session";
import { getStats, getConfig, updateConfig, getTrustLevels, setTrustLevel, removeTrust } from "../db/database.js";
import dashboardRouter from "./routes/index.js";
import configRouter from "./routes/config.js";
import whitelistRouter from "./routes/whitelist.js";

export function startDashboard(client) {
  const app = express();
  const port = process.env.DASHBOARD_PORT || 3000;

  app.use(express.urlencoded({ extended: true }));
  app.use(
    session({
      secret: process.env.SESSION_SECRET || "dev_secret",
      resave: false,
      saveUninitialized: false
    })
  );

  app.use((req, res, next) => {
    res.locals.authenticated = req.session.authenticated;
    next();
  });

  app.get("/login", (req, res) => {
    res.send(`
      <html><body>
      <h2>Security Dashboard Login</h2>
      <form method="post" action="/login">
        <input type="password" name="password" placeholder="Admin password" />
        <button type="submit">Login</button>
      </form>
      </body></html>
    `);
  });

  app.post("/login", (req, res) => {
    const { password } = req.body;
    if (password === process.env.ADMIN_PASSWORD) {
      req.session.authenticated = true;
      res.redirect("/dashboard");
    } else {
      res.status(401).send("Invalid password");
    }
  });

  app.use((req, res, next) => {
    if (req.path.startsWith("/dashboard") && !req.session.authenticated) {
      return res.redirect("/login");
    }
    next();
  });

  app.use("/dashboard", dashboardRouter(client));
  app.use("/dashboard/config", configRouter(client));
  app.use("/dashboard/whitelist", whitelistRouter(client));

  app.listen(port, () => console.log(`Dashboard listening on http://localhost:${port}`));
}
