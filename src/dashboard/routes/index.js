import { Router } from "express";
import { getStats } from "../../db/database.js";

export default function dashboardRouter(client) {
  const router = Router();

  router.get("/", (req, res) => {
    const stats = getStats();
    const recent = stats.events
      .map((e) => `<li>[${e.type}] ${e.message} @ ${e.at}</li>`)
      .join("") || "<li>No events yet</li>";
    res.send(`
      <html><body>
        <h1>Security Dashboard</h1>
        <p>Raid alerts: ${stats.raidAlerts}</p>
        <p>Nuke alerts: ${stats.nukeAlerts}</p>
        <h3>Recent events</h3>
        <ul>${recent}</ul>
        <p><a href="/dashboard/config">Config</a> | <a href="/dashboard/whitelist">Whitelist</a></p>
      </body></html>
    `);
  });

  return router;
}
