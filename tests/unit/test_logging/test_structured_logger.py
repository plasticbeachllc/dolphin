"""Tests for structured logger with OpenTelemetry and PII sanitization."""

import json
import logging
from io import StringIO
from unittest.mock import Mock, patch

import pytest

from kb.logging.structured_logger import LogLevel, StructuredLogger


class TestStructuredLogger:
    """Test suite for StructuredLogger."""

    @pytest.fixture
    def logger(self):
        """Create a test logger with captured output."""
        # Create logger
        logger = StructuredLogger("test.logger")

        # Capture output
        log_output = StringIO()
        handler = logging.StreamHandler(log_output)
        handler.setFormatter(logging.Formatter("%(message)s"))

        # Clear any existing handlers and add our test handler
        logger.logger.handlers.clear()
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.DEBUG)

        # Attach output stream to logger for test access
        logger._test_output = log_output  # type: ignore[attr-defined]

        return logger

    def _get_log_entry(self, logger):
        """Get the last log entry as a dict."""
        output = logger._test_output.getvalue()
        lines = output.strip().split("\n")
        if lines and lines[-1]:
            return json.loads(lines[-1])
        return None

    def test_debug_logging(self, logger):
        """Test debug level logging."""
        logger.debug("Debug message", {"key": "value"})

        entry = self._get_log_entry(logger)
        assert entry is not None
        assert entry["level"] == "DEBUG"
        assert entry["message"] == "Debug message"
        assert entry["context"]["key"] == "value"
        assert "timestamp" in entry

    def test_info_logging(self, logger):
        """Test info level logging."""
        logger.info("Info message", {"count": 42})

        entry = self._get_log_entry(logger)
        assert entry is not None
        assert entry["level"] == "INFO"
        assert entry["message"] == "Info message"
        assert entry["context"]["count"] == 42

    def test_warning_logging(self, logger):
        """Test warning level logging."""
        logger.warning("Warning message", {"issue": "something"})

        entry = self._get_log_entry(logger)
        assert entry is not None
        assert entry["level"] == "WARNING"
        assert entry["message"] == "Warning message"
        assert entry["context"]["issue"] == "something"

    def test_warning_with_error(self, logger):
        """Test warning logging with exception."""
        try:
            raise ValueError("Test error")
        except ValueError as e:
            logger.warning("Warning with error", error=e)

        entry = self._get_log_entry(logger)
        assert entry is not None
        assert entry["level"] == "WARNING"
        assert "error" in entry
        assert entry["error"]["type"] == "ValueError"
        assert entry["error"]["message"] == "Test error"
        assert "traceback" in entry["error"]

    def test_error_logging(self, logger):
        """Test error level logging."""
        try:
            raise RuntimeError("Critical error")
        except RuntimeError as e:
            logger.error("Error occurred", error=e)

        entry = self._get_log_entry(logger)
        assert entry is not None
        assert entry["level"] == "ERROR"
        assert entry["message"] == "Error occurred"
        assert entry["error"]["type"] == "RuntimeError"
        assert entry["error"]["message"] == "Critical error"

    def test_critical_logging(self, logger):
        """Test critical level logging."""
        logger.critical("System failure", {"component": "database"})

        entry = self._get_log_entry(logger)
        assert entry is not None
        assert entry["level"] == "CRITICAL"
        assert entry["message"] == "System failure"
        assert entry["context"]["component"] == "database"

    def test_default_context(self):
        """Test logger with default context."""
        logger = StructuredLogger("test.context", {"service": "test-service", "version": "1.0"})

        # Capture output
        log_output = StringIO()
        handler = logging.StreamHandler(log_output)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.logger.handlers.clear()
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.DEBUG)
        logger._test_output = log_output  # type: ignore[attr-defined]

        logger.info("Test message")

        entry = self._get_log_entry(logger)
        assert entry is not None
        assert entry["context"]["service"] == "test-service"
        assert entry["context"]["version"] == "1.0"

    def test_create_child(self, logger):
        """Test creating child logger with additional context."""
        child = logger.create_child({"request_id": "abc123", "user_id": "user456"})

        # Capture child output
        log_output = StringIO()
        handler = logging.StreamHandler(log_output)
        handler.setFormatter(logging.Formatter("%(message)s"))
        child.logger.handlers.clear()
        child.logger.addHandler(handler)
        child.logger.setLevel(logging.DEBUG)
        child._test_output = log_output  # type: ignore[attr-defined]

        child.info("Child message", {"extra": "data"})

        entry = self._get_log_entry(child)
        assert entry is not None
        assert entry["context"]["request_id"] == "abc123"
        assert entry["context"]["user_id"] == "user456"
        assert entry["context"]["extra"] == "data"

    def test_context_merging(self):
        """Test that child context merges with parent context."""
        parent = StructuredLogger("test.parent", {"service": "api", "env": "test"})

        # Capture output
        log_output = StringIO()
        handler = logging.StreamHandler(log_output)
        handler.setFormatter(logging.Formatter("%(message)s"))
        parent.logger.handlers.clear()
        parent.logger.addHandler(handler)
        parent.logger.setLevel(logging.DEBUG)
        parent._test_output = log_output  # type: ignore[attr-defined]

        child = parent.create_child({"request_id": "xyz"})
        child.logger.handlers.clear()
        child.logger.addHandler(handler)
        child._test_output = log_output  # type: ignore[attr-defined]

        child.info("Test")

        entry = self._get_log_entry(child)
        assert entry["context"]["service"] == "api"
        assert entry["context"]["env"] == "test"
        assert entry["context"]["request_id"] == "xyz"

    def test_set_level(self, logger):
        """Test setting log level."""
        logger.set_level(LogLevel.WARNING)

        # Debug and info should not be logged
        logger.debug("Debug message")
        logger.info("Info message")

        output = logger._test_output.getvalue()
        assert output.strip() == ""

        # Warning should be logged
        logger.warning("Warning message")

        entry = self._get_log_entry(logger)
        assert entry is not None
        assert entry["level"] == "WARNING"

    def test_json_output_format(self, logger):
        """Test that output is valid JSON."""
        logger.info("Test message", {"key": "value"})

        output = logger._test_output.getvalue().strip()
        # Should be parseable as JSON
        entry = json.loads(output)

        assert isinstance(entry, dict)
        assert "timestamp" in entry
        assert "level" in entry
        assert "message" in entry
        assert "context" in entry

    def test_timestamp_format(self, logger):
        """Test timestamp is in ISO format with Z suffix."""
        logger.info("Test")

        entry = self._get_log_entry(logger)
        assert entry["timestamp"].endswith("Z")

        # Should be parseable as ISO format
        from datetime import datetime

        ts = datetime.fromisoformat(entry["timestamp"].rstrip("Z"))
        assert ts is not None

    def test_context_with_nested_dict(self, logger):
        """Test logging with nested context dict."""
        logger.info(
            "Test",
            {
                "user": {"id": 123, "name": "Test User"},
                "metadata": {"tags": ["tag1", "tag2"]},
            },
        )

        entry = self._get_log_entry(logger)
        assert entry["context"]["user"]["id"] == 123
        assert entry["context"]["user"]["name"] == "Test User"
        assert entry["context"]["metadata"]["tags"] == ["tag1", "tag2"]

    def test_context_with_list(self, logger):
        """Test logging with list in context."""
        logger.info("Test", {"items": [1, 2, 3, 4, 5]})

        entry = self._get_log_entry(logger)
        assert entry["context"]["items"] == [1, 2, 3, 4, 5]

    def test_context_with_none(self, logger):
        """Test logging with None context."""
        logger.info("Test without context")

        entry = self._get_log_entry(logger)
        assert entry is not None
        assert entry["message"] == "Test without context"
        assert isinstance(entry["context"], dict)

    # OpenTelemetry integration tests

    @patch("kb.logging.structured_logger.OTEL_AVAILABLE", True)
    @patch("kb.logging.structured_logger.trace")
    def test_otel_trace_context_extraction(self, mock_trace, logger):
        """Test OpenTelemetry trace context extraction."""
        # Mock span with valid context
        mock_span = Mock()
        mock_span.is_recording.return_value = True
        mock_span_context = Mock()
        mock_span_context.is_valid = True
        mock_span_context.trace_id = 123456789012345678901234567890123456
        mock_span_context.span_id = 1234567890123456
        mock_span.get_span_context.return_value = mock_span_context
        mock_trace.get_current_span.return_value = mock_span

        logger.info("Test with trace")

        entry = self._get_log_entry(logger)
        assert "trace_id" in entry
        assert "span_id" in entry
        assert len(entry["trace_id"]) == 32  # 128-bit trace ID as hex
        assert len(entry["span_id"]) == 16  # 64-bit span ID as hex

    @patch("kb.logging.structured_logger.OTEL_AVAILABLE", True)
    @patch("kb.logging.structured_logger.trace")
    def test_otel_no_active_span(self, mock_trace, logger):
        """Test logging when no active span exists."""
        mock_trace.get_current_span.return_value = None

        logger.info("Test without span")

        entry = self._get_log_entry(logger)
        assert "trace_id" not in entry
        assert "span_id" not in entry

    # PII sanitization tests

    def test_pii_sanitization_anthropic_key(self, logger):
        """Test Anthropic API key sanitization."""
        logger.info("Test", {"api_key": "sk-ant-api03-" + "a" * 95})

        entry = self._get_log_entry(logger)
        assert "sk-ant-***" in entry["context"]["api_key"]
        assert "sk-ant-api03" not in entry["context"]["api_key"]

    def test_pii_sanitization_openai_key(self, logger):
        """Test OpenAI API key sanitization."""
        logger.info("Test", {"key": "sk-" + "a" * 48})

        entry = self._get_log_entry(logger)
        assert entry["context"]["key"] == "sk-***"

    def test_pii_sanitization_generic_token(self, logger):
        """Test generic token sanitization."""
        logger.info("Test", {"auth": "Bearer token_abc123xyz456789012345"})

        entry = self._get_log_entry(logger)
        assert "token_abc123xyz456789012345" not in entry["context"]["auth"]
        assert "token-***" in entry["context"]["auth"]

    def test_pii_sanitization_file_paths_unix(self, logger):
        """Test Unix file path sanitization."""
        logger.info("Test", {"path": "/Users/john/documents/secret.txt"})

        entry = self._get_log_entry(logger)
        assert "/Users/***" in entry["context"]["path"]
        assert "john" not in entry["context"]["path"]

    def test_pii_sanitization_file_paths_windows(self, logger):
        """Test Windows file path sanitization."""
        logger.info("Test", {"path": r"C:\Users\jane\documents\file.txt"})

        entry = self._get_log_entry(logger)
        assert r"C:\Users\***" in entry["context"]["path"]
        assert "jane" not in entry["context"]["path"]

    def test_pii_sanitization_sensitive_keys(self, logger):
        """Test that sensitive keys are completely redacted."""
        logger.info(
            "Test",
            {
                "password": "super_secret",
                "api_key": "sk-" + "a" * 48,
                "token": "token_abc123xyz456789012345",
                "secret": "confidential",
            },
        )

        entry = self._get_log_entry(logger)
        assert entry["context"]["password"] == "***"
        assert entry["context"]["api_key"] == "sk-***"  # Pattern-based sanitization
        assert "token-***" in entry["context"]["token"]  # Pattern-based sanitization
        assert entry["context"]["secret"] == "***"  # Key-based redaction

    def test_pii_sanitization_nested_values(self, logger):
        """Test PII sanitization in nested structures."""
        logger.info(
            "Test",
            {
                "user": {
                    "name": "John",
                    "api_key": "sk-" + "a" * 48,
                    "home": "/Users/john/workspace",
                },
                "config": {
                    "tokens": [
                        "token_abc123xyz456789012345",
                        "another_token_xyz789012345678",
                    ]
                },
            },
        )

        entry = self._get_log_entry(logger)
        assert entry["context"]["user"]["name"] == "John"
        assert entry["context"]["user"]["api_key"] == "sk-***"
        assert "/Users/***" in entry["context"]["user"]["home"]
        assert "token-***" in entry["context"]["config"]["tokens"][0]

    # Circular reference detection tests

    def test_circular_reference_detection(self, logger):
        """Test that circular references are detected and handled."""
        circular = {"key": "value"}
        circular["self"] = circular

        logger.info("Test", circular)

        entry = self._get_log_entry(logger)
        assert "error" in entry["context"]
        assert "circular reference" in entry["context"]["error"].lower()

    def test_non_serializable_object(self, logger):
        """Test handling of non-serializable objects."""

        class CustomObject:
            pass

        logger.info("Test", {"obj": CustomObject()})

        entry = self._get_log_entry(logger)
        assert "error" in entry["context"]

    # Integration test

    def test_full_feature_integration(self, logger):
        """Test all features working together."""
        with (
            patch("kb.logging.structured_logger.OTEL_AVAILABLE", True),
            patch("kb.logging.structured_logger.trace") as mock_trace,
        ):
            # Setup OpenTelemetry mock
            mock_span = Mock()
            mock_span.is_recording.return_value = True
            mock_span_context = Mock()
            mock_span_context.is_valid = True
            mock_span_context.trace_id = 123456789012345678901234567890123456
            mock_span_context.span_id = 1234567890123456
            mock_span.get_span_context.return_value = mock_span_context
            mock_trace.get_current_span.return_value = mock_span

            # Log with PII
            try:
                raise ValueError("Test error")
            except ValueError as e:
                logger.error(
                    "Error with PII",
                    {
                        "api_key": "sk-" + "a" * 48,
                        "path": "/Users/john/file.txt",
                        "data": {"nested": "value"},
                    },
                    error=e,
                )

            entry = self._get_log_entry(logger)

            # Check all features
            assert "trace_id" in entry  # OpenTelemetry
            assert "span_id" in entry
            assert entry["context"]["api_key"] == "sk-***"  # PII sanitization
            assert "/Users/***" in entry["context"]["path"]
            assert entry["error"]["type"] == "ValueError"  # Error tracking
            assert entry["context"]["data"]["nested"] == "value"  # Nested context
