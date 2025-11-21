import jwt from "jsonwebtoken";

function getToken(req) {
  const header = req.headers.authorization;
  if (header?.startsWith("Bearer ")) return header.slice(7);
  if (req.cookies?.token) return req.cookies.token;
  return null;
}

export function issueToken(payload, options = {}) {
  const secret = process.env.JWT_SECRET || "dev_secret";
  const expiresIn = options.expiresIn || "1h";
  return jwt.sign(payload, secret, { expiresIn });
}

export function authMiddleware(req, res, next) {
  try {
    const token = getToken(req);
    if (!token) return res.status(401).json({ error: "Authentication required" });
    const secret = process.env.JWT_SECRET || "dev_secret";
    const decoded = jwt.verify(token, secret);
    req.user = decoded;
    next();
  } catch (err) {
    return res.status(401).json({ error: "Invalid or expired token" });
  }
}
