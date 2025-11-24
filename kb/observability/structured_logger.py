"""Structured logging for KB backend with OpenTelemetry integration.

This module provides structured JSON logging with:
- OpenTelemetry trace context integration (trace_id, span_id)
- PII sanitization (API keys, file paths, tokens)
- Circular reference detection
- Child logger pattern for context inheritance
- Feature parity with TypeScript observability stack
"""

import json
import logging
import re
import traceback
import unicodedata
from contextvars import ContextVar
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any
from urllib.parse import unquote

try:
    from opentelemetry import trace

    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False


# Global context variable for async request context
_request_context: ContextVar[dict[str, Any]] = ContextVar("request_context", default={})


class LogLevel(IntEnum):
    """Log severity levels."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class StructuredLogger:
    """Structured logger with JSON output, OpenTelemetry integration, and PII sanitization.

    Features:
    - JSON-formatted output for structured log aggregation
    - OpenTelemetry trace context (trace_id, span_id)
    - Automatic PII sanitization (API keys, tokens, file paths)
    - Circular reference detection
    - Child logger pattern for context inheritance
    - Exception tracking with full traceback
    """

    # PII patterns to redact
    _API_KEY_PATTERN = re.compile(
        r"\b(sk|api|key|token|secret|password|bearer)[-_][a-zA-Z0-9]{20,}\b",
        re.IGNORECASE,
    )
    _ANTHROPIC_KEY_PATTERN = re.compile(r"sk-ant-[a-zA-Z0-9-]{95,}")
    _OPENAI_KEY_PATTERN = re.compile(r"sk-[a-zA-Z0-9]{48,}")

    # Enhanced file path patterns - more comprehensive coverage
    _UNIX_HOME_PATTERN = re.compile(r"/(Users|home|root)/[^/\s]+")
    _UNIX_PATH_PATTERN = re.compile(r"/(usr/local|opt|var|tmp)/[^/\s]*")
    _WINDOWS_PATH_PATTERN = re.compile(r"C:\\(Users|Program Files|Windows)\\[^\\]+")
    # Generic Windows pattern - excludes known directories to prevent double-sanitization
    _WINDOWS_GENERIC_PATTERN = re.compile(r"[A-Z]:\\(?!Users\\|Program Files\\|Windows\\)[^\\]+")

    # JWT/Bearer tokens
    _JWT_PATTERN = re.compile(r"eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+")

    def __init__(self, name: str, default_context: dict[str, Any] | None = None):
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
            handler.setFormatter(logging.Formatter("%(message)s"))  # Raw JSON output
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def _extract_trace_context(self) -> dict[str, str]:
        """Extract OpenTelemetry trace context from current span.

        Returns:
            Dictionary with trace_id and span_id if available
        """
        if not OTEL_AVAILABLE:
            return {}

        try:
            span = trace.get_current_span()
            if span and span.is_recording():
                span_context = span.get_span_context()
                if span_context.is_valid:
                    return {
                        "trace_id": format(span_context.trace_id, "032x"),
                        "span_id": format(span_context.span_id, "016x"),
                    }
        except Exception:
            # Silently fail if trace extraction fails
            pass

        return {}

    def _extract_async_context(self) -> dict[str, Any]:
        """Extract async context from contextvars.

        Returns:
            Dictionary with request context (e.g., request_id, user_id, etc.)
        """
        try:
            ctx = _request_context.get()
            return dict(ctx) if ctx else {}
        except Exception:
            return {}

    def _sanitize_value(self, value: Any) -> Any:
        """Sanitize a single value for PII.

        Supported types:
        - str: Pattern-based redaction of API keys, tokens, and file paths
        - dict: Recursive sanitization with circular reference detection
        - list/tuple: Element-wise sanitization
        - Other types (int, float, bool, None, etc.): Returned as-is

        Args:
            value: Value to sanitize

        Returns:
            Sanitized value with PII redacted
        """
        if isinstance(value, str):
            # Normalize unicode to prevent homoglyph bypasses
            value = unicodedata.normalize("NFKC", value)

            # Decode URL encoding (single pass to avoid overhead)
            try:
                decoded = unquote(value)
                if decoded != value:
                    value = decoded
            except Exception:
                pass  # If decoding fails, use original value

            # Apply specific API key patterns FIRST to preserve key prefixes
            value = self._ANTHROPIC_KEY_PATTERN.sub("sk-ant-***", value)
            value = self._OPENAI_KEY_PATTERN.sub("sk-***", value)
            value = self._JWT_PATTERN.sub("eyJ***.eyJ***.***", value)
            # Apply generic pattern last (won't re-match already sanitized keys)
            value = self._API_KEY_PATTERN.sub(r"\1-***", value)

            # Redact file paths (remove username/sensitive portions)
            value = self._UNIX_HOME_PATTERN.sub(r"/\1/***", value)
            value = self._UNIX_PATH_PATTERN.sub(r"/***", value)
            value = self._WINDOWS_PATH_PATTERN.sub(r"C:\\\1\***", value)
            value = self._WINDOWS_GENERIC_PATTERN.sub(r"*:\***", value)

            return value
        elif isinstance(value, dict):
            return self._sanitize_dict(value)
        elif isinstance(value, (list, tuple)):
            return [self._sanitize_value(v) for v in value]
        else:
            return value

    def _sanitize_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Sanitize dictionary for PII with circular reference detection.

        Args:
            data: Dictionary to sanitize

        Returns:
            Sanitized dictionary with PII redacted
        """
        if not data:
            return {}

        # Detect circular references
        try:
            json.dumps(data)
        except (TypeError, ValueError):
            return {"error": "Failed to sanitize metadata - circular reference or non-serializable object"}

        sanitized = {}
        for key, value in data.items():
            # Apply pattern-based sanitization first
            sanitized_value = self._sanitize_value(value)

            # Then check if key name itself is sensitive
            if key.lower() in (
                "password",
                "passwd",
                "secret",
                "authorization",
                "apikey",
                "access_token",
                "auth_token",
            ):
                # These keys should be completely redacted
                sanitized[key] = "***"
            else:
                # For other keys (including api_key, token), use the sanitized value
                # which may have already been pattern-matched
                sanitized[key] = sanitized_value

        return sanitized

    def _log(
        self,
        level: LogLevel,
        message: str,
        context: dict[str, Any] | None = None,
        error: Exception | None = None,
    ):
        """Internal logging method with OpenTelemetry and PII sanitization.

        Args:
            level: Log level
            message: Log message
            context: Additional context fields
            error: Exception to log with traceback
        """
        # Build base entry with timestamp and level
        entry = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": level.name,
            "message": message,
        }

        # Add OpenTelemetry trace context
        trace_context = self._extract_trace_context()
        if trace_context:
            entry.update(trace_context)

        # Merge and sanitize context (async context + default + provided)
        async_context = self._extract_async_context()
        merged_context = {**async_context, **self.default_context, **(context or {})}
        entry["context"] = self._sanitize_dict(merged_context)

        # Add error information if provided
        if error:
            entry["error"] = {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            }

        # Log as JSON
        self.logger.log(level, json.dumps(entry))

    def debug(self, message: str, context: dict[str, Any] | None = None):
        """Log debug message (development/troubleshooting only).

        Args:
            message: Log message
            context: Additional context fields
        """
        self._log(LogLevel.DEBUG, message, context)

    def info(self, message: str, context: dict[str, Any] | None = None):
        """Log info message (important events worth monitoring).

        Args:
            message: Log message
            context: Additional context fields
        """
        self._log(LogLevel.INFO, message, context)

    def warning(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        error: Exception | None = None,
    ):
        """Log warning message (recoverable issues).

        Args:
            message: Log message
            context: Additional context fields
            error: Exception that triggered the warning
        """
        self._log(LogLevel.WARNING, message, context, error)

    def error(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        error: Exception | None = None,
    ):
        """Log error message (serious issues requiring attention).

        Args:
            message: Log message
            context: Additional context fields
            error: Exception that triggered the error
        """
        self._log(LogLevel.ERROR, message, context, error)

    def critical(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        error: Exception | None = None,
    ):
        """Log critical message (system-level failures).

        Args:
            message: Log message
            context: Additional context fields
            error: Exception that triggered the critical error
        """
        self._log(LogLevel.CRITICAL, message, context, error)

    def create_child(self, context: dict[str, Any]) -> "StructuredLogger":
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


# Helper functions for async context management


def set_request_context(**context: Any) -> None:
    """Set async request context that will be included in all log entries.

    This uses Python's contextvars to propagate context across async boundaries.

    Example:
        >>> set_request_context(request_id="req-123", user_id="user-456")
        >>> logger.info("Processing request")  # Will include request_id and user_id

    Args:
        **context: Key-value pairs to set in the request context
    """
    current = _request_context.get()
    updated = {**current, **context}
    _request_context.set(updated)


def clear_request_context() -> None:
    """Clear all async request context.

    Example:
        >>> clear_request_context()
    """
    _request_context.set({})


def get_request_context() -> dict[str, Any]:
    """Get the current async request context.

    Returns:
        Dictionary of current request context
    """
    return dict(_request_context.get())
