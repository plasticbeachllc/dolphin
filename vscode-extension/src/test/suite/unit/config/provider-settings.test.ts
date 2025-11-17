import * as assert from "assert";
import {
  resolveProviderSettings,
  DEFAULT_MODELS,
} from "../../../../config/provider-settings";

describe("resolveProviderSettings", () => {
  it("defaults to anthropic when provider is missing", () => {
    const result = resolveProviderSettings({});
    assert.strictEqual(result.provider, "anthropic");
    assert.strictEqual(result.model, DEFAULT_MODELS.anthropic);
    assert.deepStrictEqual(result.warnings, []);
  });

  it("returns configured openai model when valid", () => {
    const result = resolveProviderSettings({
      provider: "openai",
      openaiModel: "gpt-5.1",
    });
    assert.strictEqual(result.provider, "openai");
    assert.strictEqual(result.model, "gpt-5.1");
    assert.deepStrictEqual(result.warnings, []);
  });

  it("returns configured anthropic model when valid", () => {
    const result = resolveProviderSettings({
      provider: "anthropic",
      anthropicModel: "claude-haiku-4-5",
    });
    assert.strictEqual(result.provider, "anthropic");
    assert.strictEqual(result.model, "claude-haiku-4-5");
    assert.deepStrictEqual(result.warnings, []);
  });

  it("falls back and warns on invalid model", () => {
    const result = resolveProviderSettings({
      provider: "openai",
      openaiModel: "bogus",
    });
    assert.strictEqual(result.model, DEFAULT_MODELS.openai);
    assert.ok(result.warnings.some((warning) => warning.includes("bogus")));
  });

  it("warns when provider is unknown", () => {
    const result = resolveProviderSettings({ provider: "foo" });
    assert.strictEqual(result.provider, "anthropic");
    assert.ok(result.warnings.some((warning) => warning.includes("Unknown provider")));
  });
});
