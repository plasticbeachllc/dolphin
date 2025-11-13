"""Structured logging for KB backend."""

import logging
import json
import traceback
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from enum import IntEnum


class LogLevel(IntEnum):
    """Log severity levels."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class StructuredLogger:
    """Structured logger with JSON output and correlation IDs."""

    def __init__(self, name: str, default_context: Optional[Dict[str, Any]] = None):
        """Initialize structured logger.

        Args:
            name: Logger name (typically module path like 'kb.api.search_backend')
            default_context: Default context fields to include in all log entries
        """
        self.logger = logging.getLogger(name)
        self.default_context = default_context or {}

        # Configure JSON formatter if not already configured
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(message)s'))  # Raw JSON output
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def _log(
        self,
        level: LogLevel,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ):
        """Internal logging method."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": level.name,
            "message": message,
            "context": {**self.default_context, **(context or {})},
        }

        if error:
            entry["error"] = {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            }

        # Log as JSON
        self.logger.log(level, json.dumps(entry))

    def debug(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log debug message (development/troubleshooting only)."""
        self._log(LogLevel.DEBUG, message, context)

    def info(self, message: str, context: Optional[Dict[str, Any]] = None):
        """Log info message (important events worth monitoring)."""
        self._log(LogLevel.INFO, message, context)

    def warning(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ):
        """Log warning message (recoverable issues)."""
        self._log(LogLevel.WARNING, message, context, error)

    def error(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ):
        """Log error message (serious issues requiring attention)."""
        self._log(LogLevel.ERROR, message, context, error)

    def critical(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        error: Optional[Exception] = None,
    ):
        """Log critical message (system-level failures)."""
        self._log(LogLevel.CRITICAL, message, context, error)

    def create_child(self, context: Dict[str, Any]) -> "StructuredLogger":
        """Create child logger with additional context.

        Args:
            context: Additional context fields to merge with parent context

        Returns:
            New StructuredLogger instance with merged context
        """
        return StructuredLogger(self.logger.name, {**self.default_context, **context})

    def set_level(self, level: LogLevel):
        """Set minimum log level for this logger.

        Args:
            level: Minimum log level to output
        """
        self.logger.setLevel(level)
