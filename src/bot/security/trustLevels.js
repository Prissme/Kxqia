export const TRUST_LEVELS = {
  OWNER: "OWNER",
  TRUSTED_ADMIN: "TRUSTED_ADMIN",
  NORMAL_ADMIN: "NORMAL_ADMIN",
  DEFAULT_USER: "DEFAULT_USER"
};

export function isTrusted(userId, trustStore) {
  const level = trustStore[userId];
  return level === TRUST_LEVELS.OWNER || level === TRUST_LEVELS.TRUSTED_ADMIN;
}

export function describeTrust(userId, trustStore) {
  return trustStore[userId] || TRUST_LEVELS.DEFAULT_USER;
}
