import { describe, expect, it } from "bun:test";
import {
  getProviderDisplayName,
  getStatusHeadline,
  getStatusHint,
  getStatusIcon,
  getStatusTone,
  type ProviderAuthStatus,
} from "./auth-status-helpers";

describe("auth-status-helpers", () => {
  const baseStatus: ProviderAuthStatus = {
    provider: "anthropic",
    authenticated: true,
    mode: "subscription",
  };

  it("maps provider IDs to friendly names", () => {
    expect(getProviderDisplayName("anthropic")).toBe("Anthropic (Claude)");
    expect(getProviderDisplayName("openai")).toBe("OpenAI");
    expect(getProviderDisplayName("custom")).toBe("custom");
  });

  it("returns optimistic indicators for authenticated providers", () => {
    expect(getStatusIcon(baseStatus)).toBe("✅");
    expect(getStatusTone(baseStatus)).toBe("success");
    expect(getStatusHeadline(baseStatus)).toContain("subscription");
    expect(getStatusHint(baseStatus)).toContain("subscription");
  });

  it("surfaces warnings when provided", () => {
    const warningStatus: ProviderAuthStatus = {
      ...baseStatus,
      authenticated: false,
      warning: "Using fallback",
    };
    expect(getStatusIcon(warningStatus)).toBe("⚠️");
    expect(getStatusTone(warningStatus)).toBe("warning");
    expect(getStatusHint(warningStatus)).toContain("Using fallback");
  });

  it("shows errors when authentication is missing", () => {
    const errorStatus: ProviderAuthStatus = {
      provider: "openai",
      authenticated: false,
      mode: "api_key",
      error: "Missing key",
    };
    expect(getStatusIcon(errorStatus)).toBe("❌");
    expect(getStatusTone(errorStatus)).toBe("danger");
    expect(getStatusHeadline(errorStatus)).toBe("Missing key");
  });
});
