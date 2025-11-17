import * as assert from "assert";
import {
  MODEL_IDS_BY_PROVIDER,
  PROVIDER_IDS,
  DEFAULT_MODEL_BY_PROVIDER,
  type ProviderId,
} from "../../../../config/provider-options";
import { extensionPackageJson } from "../../../../config/extension-package";

describe("provider option definitions", () => {
  const properties = extensionPackageJson.contributes.configuration.properties;

  it("keeps provider enums in sync with package.json", () => {
    const providerProperty = properties["dolphin.llm.provider"];
    assert.ok(providerProperty, "Provider property must exist");
    assert.deepStrictEqual(providerProperty.enum, PROVIDER_IDS);
  });

  for (const provider of PROVIDER_IDS) {
    it(`keeps ${provider} models aligned with VS Code contributions`, () => {
      const key = `dolphin.llm.model.${provider}`;
      const property = properties[key];
      assert.ok(property, `Missing configuration property for ${key}`);
      assert.deepStrictEqual(property.enum, MODEL_IDS_BY_PROVIDER[provider as ProviderId]);
      assert.strictEqual(property.default, DEFAULT_MODEL_BY_PROVIDER[provider as ProviderId]);
    });
  }
});
