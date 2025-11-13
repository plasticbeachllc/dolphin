"""Tests for structured logger."""

import json
import logging
from io import StringIO

import pytest

from kb.logging.structured_logger import StructuredLogger, LogLevel


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
        handler.setFormatter(logging.Formatter('%(message)s'))

        # Clear any existing handlers and add our test handler
        logger.logger.handlers.clear()
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.DEBUG)

        # Attach output stream to logger for test access
        logger._test_output = log_output

        return logger

    def _get_log_entry(self, logger):
        """Get the last log entry as a dict."""
        output = logger._test_output.getvalue()
        lines = output.strip().split('\n')
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
        handler.setFormatter(logging.Formatter('%(message)s'))
        logger.logger.handlers.clear()
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.DEBUG)
        logger._test_output = log_output

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
        handler.setFormatter(logging.Formatter('%(message)s'))
        child.logger.handlers.clear()
        child.logger.addHandler(handler)
        child.logger.setLevel(logging.DEBUG)
        child._test_output = log_output

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
        handler.setFormatter(logging.Formatter('%(message)s'))
        parent.logger.handlers.clear()
        parent.logger.addHandler(handler)
        parent.logger.setLevel(logging.DEBUG)
        parent._test_output = log_output

        child = parent.create_child({"request_id": "xyz"})
        child.logger.handlers.clear()
        child.logger.addHandler(handler)
        child._test_output = log_output

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
        logger.info("Test", {
            "user": {
                "id": 123,
                "name": "Test User"
            },
            "metadata": {
                "tags": ["tag1", "tag2"]
            }
        })

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
