export function requireManager(req, res, next) {
  const roles = req.user?.roles || [];
  const trust = req.user?.trustLevel || "DEFAULT_USER";
  const allowed = trust === "OWNER" || trust === "TRUSTED_ADMIN" || roles.includes("ManageGuild");
  if (!allowed) return res.status(403).json({ error: "Insufficient permissions" });
  next();
}
