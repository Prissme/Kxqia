import fs from "fs";
import path from "path";
import defaultConfig from "../../config/defaultConfig.js";

function resolveDataPath() {
  if (process.env.DATA_PATH) return process.env.DATA_PATH;

  const persistentDir = path.join(path.sep, "data");
  try {
    fs.mkdirSync(persistentDir, { recursive: true });
    fs.accessSync(persistentDir, fs.constants.W_OK);
    return path.join(persistentDir, "data.json");
  } catch {
    // ignore and fallback below
  }

  const fallbackDir = path.join(process.cwd(), "data");
  fs.mkdirSync(fallbackDir, { recursive: true });
  return path.join(fallbackDir, "data.json");
}

const dataPath = resolveDataPath();

const defaultData = {
  config: defaultConfig,
  trust: {},
  stats: {
    raidAlerts: 0,
    nukeAlerts: 0,
    events: []
  }
};

function ensureFile() {
  if (!fs.existsSync(dataPath)) {
    fs.mkdirSync(path.dirname(dataPath), { recursive: true });
    fs.writeFileSync(dataPath, JSON.stringify(defaultData, null, 2));
  }
}

function read() {
  ensureFile();
  const raw = fs.readFileSync(dataPath, "utf8");
  const parsed = JSON.parse(raw || "{}");
  return {
    ...defaultData,
    ...parsed,
    config: { ...defaultData.config, ...(parsed.config || {}) },
    trust: parsed.trust || {},
    stats: {
      ...defaultData.stats,
      ...(parsed.stats || {}),
      events: parsed.stats?.events || []
    }
  };
}

function write(data) {
  fs.writeFileSync(dataPath, JSON.stringify(data, null, 2));
}

export function getConfig() {
  return read().config;
}

export function updateConfig(patch) {
  const data = read();
  data.config = { ...data.config, ...patch };
  write(data);
  return data.config;
}

export function getTrustLevels() {
  return read().trust;
}

export function setTrustLevel(userId, level) {
  const data = read();
  data.trust[userId] = level;
  write(data);
  return data.trust;
}

export function removeTrust(userId) {
  const data = read();
  delete data.trust[userId];
  write(data);
  return data.trust;
}

export function recordStat(key) {
  const data = read();
  if (key === "raidAlerts") data.stats.raidAlerts += 1;
  if (key === "nukeAlerts") data.stats.nukeAlerts += 1;
  write(data);
}

export function pushEvent(event) {
  const data = read();
  data.stats.events.unshift({ ...event, at: new Date().toISOString() });
  data.stats.events = data.stats.events.slice(0, 50);
  write(data);
}

export function getStats() {
  return read().stats;
}

export function resetStats() {
  const data = read();
  data.stats = { ...defaultData.stats };
  write(data);
}
