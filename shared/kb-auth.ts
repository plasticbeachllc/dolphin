import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import { randomBytes } from "crypto";

export interface KbAuthOptions {
  /** Custom home directory override (mainly for tests) */
  homeDir?: string;
  /** If true, never create the key file (read-only mode) */
  readOnly?: boolean;
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

/**
 * Resolve KB API key in read-only mode (never creates the file).
 *
 * Precedence:
 *   1) DOLPHIN_API_KEY env var
 *   2) DOLPHIN_KB_API_KEY env var
 *   3) ~/.dolphin/kb_api_key (if exists)
 *
 * @returns The resolved key, or undefined if not found
 */
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
