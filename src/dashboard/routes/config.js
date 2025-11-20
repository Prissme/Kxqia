import { Router } from "express";
import { getConfig, updateConfig } from "../../db/database.js";

export default function configRouter(client) {
  const router = Router();

  router.get("/", (req, res) => {
    const config = getConfig();
    res.send(`
      <html><body>
        <h1>Configuration</h1>
        <form method="post" action="/dashboard/config">
          <h3>Logging</h3>
          <label>Log channel ID <input name="logChannelId" value="${config.logChannelId}" /></label><br/>
          <h3>Anti-raid</h3>
          <label>Join threshold (60s) <input type="number" name="joinThreshold" value="${config.raid.joinThreshold}" /></label><br/>
          <label>Min account age (days) <input type="number" name="accountAgeDays" value="${config.raid.accountAgeDays}" /></label><br/>
          <label>Lockdown on raid <input type="checkbox" name="lockdownOnRaid" ${config.raid.lockdownOnRaid ? "checked" : ""} /></label><br/>
          <label>Kick young accounts <input type="checkbox" name="kickYoungAccounts" ${config.raid.kickYoungAccounts ? "checked" : ""} /></label><br/>
          <label>Quarantine role ID <input name="quarantineRoleId" value="${config.raid.quarantineRoleId}" /></label><br/>
          <h3>Anti-nuke</h3>
          <label>Channel delete limit <input type="number" name="channelDeleteLimit" value="${config.nuke.channelDeleteLimit}" /></label><br/>
          <label>Role delete limit <input type="number" name="roleDeleteLimit" value="${config.nuke.roleDeleteLimit}" /></label><br/>
          <label>Ban limit <input type="number" name="banLimit" value="${config.nuke.banLimit}" /></label><br/>
          <label>Webhook create limit <input type="number" name="webhookCreateLimit" value="${config.nuke.webhookCreateLimit}" /></label><br/>
          <label>Time window (s) <input type="number" name="timeWindow" value="${config.nuke.timeWindow}" /></label><br/>
          <label>Punitive action
            <select name="punitiveAction">
              <option value="strip" ${config.nuke.punitiveAction === "strip" ? "selected" : ""}>Strip roles</option>
              <option value="ban" ${config.nuke.punitiveAction === "ban" ? "selected" : ""}>Ban</option>
            </select>
          </label><br/>
          <button type="submit">Save</button>
        </form>
        <p><a href="/dashboard">Back</a></p>
      </body></html>
    `);
  });

  router.post("/", (req, res) => {
    const body = req.body;
    const updated = updateConfig({
      logChannelId: body.logChannelId,
      raid: {
        joinThreshold: Number(body.joinThreshold),
        accountAgeDays: Number(body.accountAgeDays),
        lockdownOnRaid: body.lockdownOnRaid === "on",
        kickYoungAccounts: body.kickYoungAccounts === "on",
        quarantineRoleId: body.quarantineRoleId
      },
      nuke: {
        channelDeleteLimit: Number(body.channelDeleteLimit),
        roleDeleteLimit: Number(body.roleDeleteLimit),
        banLimit: Number(body.banLimit),
        webhookCreateLimit: Number(body.webhookCreateLimit),
        timeWindow: Number(body.timeWindow),
        punitiveAction: body.punitiveAction
      }
    });
    res.redirect("/dashboard/config");
  });

  return router;
}
