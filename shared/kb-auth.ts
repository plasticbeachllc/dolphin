import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { randomBytes } from "crypto";

export interface KbAuthOptions {
  homeDir?: string;
}

function getEnvKey(): string | undefined {
  const key = process.env.DOLPHIN_API_KEY || process.env.DOLPHIN_KB_API_KEY;
  const trimmed = key?.trim();
  return trimmed ? trimmed : undefined;
}

export function getKbKeyPath(opts?: KbAuthOptions): string {
  const home = opts?.homeDir || os.homedir();
  return path.join(home, ".dolphin", "kb_api_key");
}

export function resolveKbApiKey(opts?: KbAuthOptions): string | undefined {
  const envKey = getEnvKey();
  if (envKey) {
    return envKey;
  }

  const keyPath = getKbKeyPath(opts);
  if (!fs.existsSync(keyPath)) {
    return undefined;
  }

  const data = fs.readFileSync(keyPath, "utf8").trim();
  return data || undefined;
}

export function getOrCreateKbApiKey(opts?: KbAuthOptions): string {
  const envKey = getEnvKey();
  if (envKey) {
    return envKey;
  }

  const keyPath = getKbKeyPath(opts);
  const dir = path.dirname(keyPath);
  fs.mkdirSync(dir, { recursive: true });

  if (fs.existsSync(keyPath)) {
    const contents = fs.readFileSync(keyPath, "utf8").trim();
    if (contents) {
      return contents;
    }
  }

  const key = randomBytes(32).toString("hex");

  try {
    const fd = fs.openSync(keyPath, "wx", 0o600);
    try {
      fs.writeFileSync(fd, key + "\n", { encoding: "utf8" });
    } finally {
      fs.closeSync(fd);
    }
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") {
      throw error;
    }
    const existing = fs.readFileSync(keyPath, "utf8").trim();
    return existing || key;
  }

  return key;
}
