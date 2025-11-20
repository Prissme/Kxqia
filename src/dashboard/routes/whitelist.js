import { Router } from "express";
import { getTrustLevels, setTrustLevel, removeTrust } from "../../db/database.js";
import { TRUST_LEVELS } from "../../bot/security/trustLevels.js";

export default function whitelistRouter(client) {
  const router = Router();

  router.get("/", (req, res) => {
    const trust = getTrustLevels();
    const rows = Object.entries(trust)
      .map(([id, level]) => `<li>${id} - ${level} <a href="/dashboard/whitelist/remove?id=${id}">Remove</a></li>`)
      .join("") || "<li>No trusted users</li>";

    res.send(`
      <html><body>
        <h1>Whitelist / Trust Levels</h1>
        <ul>${rows}</ul>
        <form method="post" action="/dashboard/whitelist">
          <input name="userId" placeholder="User ID" />
          <select name="level">
            ${Object.values(TRUST_LEVELS)
              .map((lvl) => `<option value="${lvl}">${lvl}</option>`)
              .join("")}
          </select>
          <button type="submit">Add/Update</button>
        </form>
        <p><a href="/dashboard">Back</a></p>
      </body></html>
    `);
  });

  router.post("/", (req, res) => {
    const { userId, level } = req.body;
    if (userId && level) setTrustLevel(userId, level);
    res.redirect("/dashboard/whitelist");
  });

  router.get("/remove", (req, res) => {
    const { id } = req.query;
    if (id) removeTrust(id);
    res.redirect("/dashboard/whitelist");
  });

  return router;
}
