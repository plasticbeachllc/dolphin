// vscode-extension/src/utils/logger.ts
import * as vscode from "vscode";

export enum LogLevel {
  ERROR = 0,
  WARN = 1,
  INFO = 2,
  DEBUG = 3,
}

export class Logger {
  private static logLevelMap: Record<string, LogLevel> = {
    error: LogLevel.ERROR,
    warn: LogLevel.WARN,
    info: LogLevel.INFO,
    debug: LogLevel.DEBUG,
  };

  constructor(
    private readonly channel: vscode.OutputChannel,
    private readonly category: string
  ) {}

  private getLogLevel(): LogLevel {
    try {
      const config = vscode.workspace.getConfiguration("dolphin");
      const levelStr = config.get<string>("logLevel", "info");
      return Logger.logLevelMap[levelStr] ?? LogLevel.INFO;
    } catch {
      // Config not ready yet (e.g., during test initialization)
      return LogLevel.INFO;
    }
  }

  private shouldLog(level: LogLevel): boolean {
    return level <= this.getLogLevel();
  }

  private formatMessage(level: string, message: string): string {
    const timestamp = new Date().toISOString();
    return `[${timestamp}] [${level}] [${this.category}] ${message}`;
  }

  error(message: string): void {
    if (this.shouldLog(LogLevel.ERROR)) {
      this.channel.appendLine(this.formatMessage("ERROR", message));
    }
  }

  warn(message: string): void {
    if (this.shouldLog(LogLevel.WARN)) {
      this.channel.appendLine(this.formatMessage("WARN", message));
    }
  }

  info(message: string): void {
    if (this.shouldLog(LogLevel.INFO)) {
      this.channel.appendLine(this.formatMessage("INFO", message));
    }
  }

  debug(message: string): void {
    if (this.shouldLog(LogLevel.DEBUG)) {
      this.channel.appendLine(this.formatMessage("DEBUG", message));
    }
  }
}
