import * as assert from 'assert';
import * as vscode from 'vscode';
import { Logger, LogLevel } from '../../utils/logger';

describe('Logger Unit Tests', () => {
  let outputChannel: vscode.OutputChannel;
  let logger: Logger;
  let loggedMessages: string[];

  beforeEach(() => {
    loggedMessages = [];

    // Create a mock output channel
    outputChannel = {
      name: 'TestChannel',
      appendLine: (message: string) => {
        loggedMessages.push(message);
      },
      append: () => {},
      clear: () => {},
      show: () => {},
      hide: () => {},
      dispose: () => {},
      replace: () => {},
    } as vscode.OutputChannel;

    logger = new Logger(outputChannel, 'TestCategory');
  });

  describe('Log Level Filtering', () => {
    it('Should log ERROR messages when level is ERROR', () => {
      // Mock configuration to return 'error'
      const originalGet = vscode.workspace.getConfiguration;
      vscode.workspace.getConfiguration = () => ({
        get: (key: string, defaultValue?: any) => key === 'logLevel' ? 'error' : defaultValue,
      } as any);

      logger.error('Error message');
      logger.warn('Warning message');
      logger.info('Info message');
      logger.debug('Debug message');

      assert.strictEqual(loggedMessages.length, 1, 'Should only log ERROR messages');
      assert.ok(loggedMessages[0].includes('[ERROR]'), 'Message should have ERROR tag');
      assert.ok(loggedMessages[0].includes('Error message'), 'Message should contain the error text');

      vscode.workspace.getConfiguration = originalGet;
    });

    it('Should log ERROR and WARN when level is WARN', () => {
      const originalGet = vscode.workspace.getConfiguration;
      vscode.workspace.getConfiguration = () => ({
        get: (key: string, defaultValue?: any) => key === 'logLevel' ? 'warn' : defaultValue,
      } as any);

      logger.error('Error message');
      logger.warn('Warning message');
      logger.info('Info message');
      logger.debug('Debug message');

      assert.strictEqual(loggedMessages.length, 2, 'Should log ERROR and WARN messages');
      assert.ok(loggedMessages[0].includes('[ERROR]'), 'First message should be ERROR');
      assert.ok(loggedMessages[1].includes('[WARN]'), 'Second message should be WARN');

      vscode.workspace.getConfiguration = originalGet;
    });

    it('Should log ERROR, WARN, and INFO when level is INFO', () => {
      const originalGet = vscode.workspace.getConfiguration;
      vscode.workspace.getConfiguration = () => ({
        get: (key: string, defaultValue?: any) => key === 'logLevel' ? 'info' : defaultValue,
      } as any);

      logger.error('Error message');
      logger.warn('Warning message');
      logger.info('Info message');
      logger.debug('Debug message');

      assert.strictEqual(loggedMessages.length, 3, 'Should log ERROR, WARN, and INFO messages');
      assert.ok(loggedMessages[0].includes('[ERROR]'));
      assert.ok(loggedMessages[1].includes('[WARN]'));
      assert.ok(loggedMessages[2].includes('[INFO]'));

      vscode.workspace.getConfiguration = originalGet;
    });

    it('Should log all messages when level is DEBUG', () => {
      const originalGet = vscode.workspace.getConfiguration;
      vscode.workspace.getConfiguration = () => ({
        get: (key: string, defaultValue?: any) => key === 'logLevel' ? 'debug' : defaultValue,
      } as any);

      logger.error('Error message');
      logger.warn('Warning message');
      logger.info('Info message');
      logger.debug('Debug message');

      assert.strictEqual(loggedMessages.length, 4, 'Should log all messages at DEBUG level');
      assert.ok(loggedMessages[0].includes('[ERROR]'));
      assert.ok(loggedMessages[1].includes('[WARN]'));
      assert.ok(loggedMessages[2].includes('[INFO]'));
      assert.ok(loggedMessages[3].includes('[DEBUG]'));

      vscode.workspace.getConfiguration = originalGet;
    });

    it('Should default to INFO level when config is invalid', () => {
      const originalGet = vscode.workspace.getConfiguration;
      vscode.workspace.getConfiguration = () => ({
        get: (key: string, defaultValue?: any) => key === 'logLevel' ? 'invalid' : defaultValue,
      } as any);

      logger.error('Error message');
      logger.warn('Warning message');
      logger.info('Info message');
      logger.debug('Debug message');

      assert.strictEqual(loggedMessages.length, 3, 'Should default to INFO level');

      vscode.workspace.getConfiguration = originalGet;
    });
  });

  describe('Message Formatting', () => {
    it('Should include category in log messages', () => {
      const originalGet = vscode.workspace.getConfiguration;
      vscode.workspace.getConfiguration = () => ({
        get: (key: string, defaultValue?: any) => key === 'logLevel' ? 'debug' : defaultValue,
      } as any);

      logger.info('Test message');

      assert.ok(loggedMessages[0].includes('[TestCategory]'), 'Message should include category');

      vscode.workspace.getConfiguration = originalGet;
    });

    it('Should include timestamp in log messages', () => {
      const originalGet = vscode.workspace.getConfiguration;
      vscode.workspace.getConfiguration = () => ({
        get: (key: string, defaultValue?: any) => key === 'logLevel' ? 'debug' : defaultValue,
      } as any);

      logger.info('Test message');

      // Check for ISO timestamp format (starts with year)
      assert.ok(/\[20\d{2}-/.test(loggedMessages[0]), 'Message should include ISO timestamp');

      vscode.workspace.getConfiguration = originalGet;
    });

    it('Should format messages with level, timestamp, category, and content', () => {
      const originalGet = vscode.workspace.getConfiguration;
      vscode.workspace.getConfiguration = () => ({
        get: (key: string, defaultValue?: any) => key === 'logLevel' ? 'debug' : defaultValue,
      } as any);

      logger.error('Error occurred');

      const message = loggedMessages[0];
      assert.ok(message.includes('[ERROR]'), 'Should include level');
      assert.ok(message.includes('[TestCategory]'), 'Should include category');
      assert.ok(message.includes('Error occurred'), 'Should include message content');
      assert.ok(/\[20\d{2}-/.test(message), 'Should include timestamp');

      vscode.workspace.getConfiguration = originalGet;
    });
  });

  describe('Different Log Levels', () => {
    beforeEach(() => {
      const originalGet = vscode.workspace.getConfiguration;
      vscode.workspace.getConfiguration = () => ({
        get: (key: string, defaultValue?: any) => key === 'logLevel' ? 'debug' : defaultValue,
      } as any);
    });

    it('Should log error messages', () => {
      logger.error('Test error');
      assert.strictEqual(loggedMessages.length, 1);
      assert.ok(loggedMessages[0].includes('[ERROR]'));
      assert.ok(loggedMessages[0].includes('Test error'));
    });

    it('Should log warning messages', () => {
      logger.warn('Test warning');
      assert.strictEqual(loggedMessages.length, 1);
      assert.ok(loggedMessages[0].includes('[WARN]'));
      assert.ok(loggedMessages[0].includes('Test warning'));
    });

    it('Should log info messages', () => {
      logger.info('Test info');
      assert.strictEqual(loggedMessages.length, 1);
      assert.ok(loggedMessages[0].includes('[INFO]'));
      assert.ok(loggedMessages[0].includes('Test info'));
    });

    it('Should log debug messages', () => {
      logger.debug('Test debug');
      assert.strictEqual(loggedMessages.length, 1);
      assert.ok(loggedMessages[0].includes('[DEBUG]'));
      assert.ok(loggedMessages[0].includes('Test debug'));
    });
  });

  describe('Multiple Logger Instances', () => {
    it('Should maintain separate categories for different loggers', () => {
      const originalGet = vscode.workspace.getConfiguration;
      vscode.workspace.getConfiguration = () => ({
        get: (key: string, defaultValue?: any) => key === 'logLevel' ? 'debug' : defaultValue,
      } as any);

      const logger1 = new Logger(outputChannel, 'Category1');
      const logger2 = new Logger(outputChannel, 'Category2');

      logger1.info('Message from logger 1');
      logger2.info('Message from logger 2');

      assert.strictEqual(loggedMessages.length, 2);
      assert.ok(loggedMessages[0].includes('[Category1]'));
      assert.ok(loggedMessages[1].includes('[Category2]'));

      vscode.workspace.getConfiguration = originalGet;
    });
  });
});
