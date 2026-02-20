import packageJson = require("../../package.json");

export interface ExtensionPackageJson {
  contributes: {
    configuration: {
      properties: Record<
        string,
        {
          enum?: string[];
          default?: string | number | boolean | string[];
        }
      >;
    };
  };
}

export const extensionPackageJson = packageJson as ExtensionPackageJson;
