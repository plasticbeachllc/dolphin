import * as assert from 'assert';
import * as vscode from 'vscode';

describe('Configuration Schema Tests', () => {
  let config: vscode.WorkspaceConfiguration;

  beforeEach(() => {
    config = vscode.workspace.getConfiguration('dolphin');
  });

  describe('Configuration Properties', () => {
    it('Should have dolphin.model configuration', () => {
      const model = config.get('model');
      assert.ok(model !== undefined, 'dolphin.model should exist');
    });

    it('Should have default value for model', () => {
      const model = config.get('model', 'default-fallback');
      // The default should be claude-sonnet-4-5-20250929 or fall back to our test default
      assert.ok(model, 'Model should have a value');
      assert.strictEqual(typeof model, 'string', 'Model should be a string');
    });

    it('Should have dolphin.maxTokens configuration', () => {
      const maxTokens = config.get('maxTokens');
      assert.ok(maxTokens !== undefined, 'dolphin.maxTokens should exist');
    });

    it('Should have default value for maxTokens', () => {
      const maxTokens = config.get<number>('maxTokens', 8192);
      assert.strictEqual(typeof maxTokens, 'number', 'maxTokens should be a number');
      assert.ok(maxTokens > 0, 'maxTokens should be positive');
    });

    it('Should have dolphin.temperature configuration', () => {
      const temperature = config.get('temperature');
      assert.ok(temperature !== undefined, 'dolphin.temperature should exist');
    });

    it('Should have default value for temperature', () => {
      const temperature = config.get<number>('temperature', 1.0);
      assert.strictEqual(typeof temperature, 'number', 'temperature should be a number');
      assert.ok(temperature >= 0 && temperature <= 1, 'temperature should be between 0 and 1');
    });

    it('Should have dolphin.useTools configuration', () => {
      const useTools = config.get('useTools');
      assert.ok(useTools !== undefined, 'dolphin.useTools should exist');
    });

    it('Should have default value for useTools', () => {
      const useTools = config.get<boolean>('useTools', true);
      assert.strictEqual(typeof useTools, 'boolean', 'useTools should be a boolean');
    });

    it('Should have dolphin.enableTelemetry configuration', () => {
      const enableTelemetry = config.get('enableTelemetry');
      assert.ok(enableTelemetry !== undefined, 'dolphin.enableTelemetry should exist');
    });

    it('Should have default value for enableTelemetry as false', () => {
      const enableTelemetry = config.get<boolean>('enableTelemetry', false);
      assert.strictEqual(typeof enableTelemetry, 'boolean', 'enableTelemetry should be a boolean');
      // Default should be false for privacy
      assert.strictEqual(enableTelemetry, false, 'enableTelemetry should default to false');
    });

    it('Should have dolphin.logLevel configuration', () => {
      const logLevel = config.get('logLevel');
      assert.ok(logLevel !== undefined, 'dolphin.logLevel should exist');
    });

    it('Should have default value for logLevel', () => {
      const logLevel = config.get<string>('logLevel', 'info');
      assert.strictEqual(typeof logLevel, 'string', 'logLevel should be a string');
      const validLevels = ['error', 'warn', 'info', 'debug'];
      assert.ok(validLevels.includes(logLevel), 'logLevel should be a valid level');
    });
  });

  describe('Configuration Updates', () => {
    it('Should allow updating model configuration', async () => {
      const testModel = 'claude-opus-4-20250514';
      await config.update('model', testModel, vscode.ConfigurationTarget.Global);

      const updatedConfig = vscode.workspace.getConfiguration('dolphin');
      const model = updatedConfig.get<string>('model');

      assert.strictEqual(model, testModel, 'Model should be updated');

      // Reset to default
      await config.update('model', undefined, vscode.ConfigurationTarget.Global);
    });

    it('Should allow updating maxTokens configuration', async () => {
      const testMaxTokens = 4096;
      await config.update('maxTokens', testMaxTokens, vscode.ConfigurationTarget.Global);

      const updatedConfig = vscode.workspace.getConfiguration('dolphin');
      const maxTokens = updatedConfig.get<number>('maxTokens');

      assert.strictEqual(maxTokens, testMaxTokens, 'maxTokens should be updated');

      // Reset to default
      await config.update('maxTokens', undefined, vscode.ConfigurationTarget.Global);
    });

    it('Should allow updating temperature configuration', async () => {
      const testTemperature = 0.7;
      await config.update('temperature', testTemperature, vscode.ConfigurationTarget.Global);

      const updatedConfig = vscode.workspace.getConfiguration('dolphin');
      const temperature = updatedConfig.get<number>('temperature');

      assert.strictEqual(temperature, testTemperature, 'temperature should be updated');

      // Reset to default
      await config.update('temperature', undefined, vscode.ConfigurationTarget.Global);
    });

    it('Should allow updating useTools configuration', async () => {
      const testUseTools = false;
      await config.update('useTools', testUseTools, vscode.ConfigurationTarget.Global);

      const updatedConfig = vscode.workspace.getConfiguration('dolphin');
      const useTools = updatedConfig.get<boolean>('useTools');

      assert.strictEqual(useTools, testUseTools, 'useTools should be updated');

      // Reset to default
      await config.update('useTools', undefined, vscode.ConfigurationTarget.Global);
    });

    it('Should allow updating enableTelemetry configuration', async () => {
      const testEnableTelemetry = true;
      await config.update('enableTelemetry', testEnableTelemetry, vscode.ConfigurationTarget.Global);

      const updatedConfig = vscode.workspace.getConfiguration('dolphin');
      const enableTelemetry = updatedConfig.get<boolean>('enableTelemetry');

      assert.strictEqual(enableTelemetry, testEnableTelemetry, 'enableTelemetry should be updated');

      // Reset to default
      await config.update('enableTelemetry', undefined, vscode.ConfigurationTarget.Global);
    });

    it('Should allow updating logLevel configuration', async () => {
      const testLogLevel = 'debug';
      await config.update('logLevel', testLogLevel, vscode.ConfigurationTarget.Global);

      const updatedConfig = vscode.workspace.getConfiguration('dolphin');
      const logLevel = updatedConfig.get<string>('logLevel');

      assert.strictEqual(logLevel, testLogLevel, 'logLevel should be updated');

      // Reset to default
      await config.update('logLevel', undefined, vscode.ConfigurationTarget.Global);
    });
  });

  describe('Configuration Inspection', () => {
    it('Should provide configuration details for model', () => {
      const inspection = config.inspect('model');
      assert.ok(inspection, 'Model configuration should be inspectable');
      assert.ok(inspection?.defaultValue !== undefined, 'Model should have a default value');
    });

    it('Should provide configuration details for logLevel', () => {
      const inspection = config.inspect('logLevel');
      assert.ok(inspection, 'LogLevel configuration should be inspectable');
      assert.ok(inspection?.defaultValue !== undefined, 'LogLevel should have a default value');
    });
  });
});
