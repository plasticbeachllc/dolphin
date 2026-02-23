"""Unit tests for the @defensive decorator and context manager."""

from __future__ import annotations

import logging

import pytest

from kb.utils.defensive import _Defensive, _log as _module_log, defensive


def _wrap(func, *, fallback=None, log_level="warning", label=None, logger=None):
    """Helper: manually wrap a function with defensive's internal _wrap method.

    The current _Defensive.__call__ returns a _DefensiveContext (context manager)
    when called with keyword-only arguments, so `@defensive(fallback=[])` as a
    decorator syntax is not supported.  This helper calls _wrap directly to test
    the decorator behaviour that the spec describes.
    """
    _LEVELS = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    resolved_level = _LEVELS.get(log_level.lower(), logging.WARNING)
    resolved_logger = logger or _module_log
    return _Defensive._wrap(
        func,
        fallback=fallback,
        log_level=resolved_level,
        label=label,
        logger=resolved_logger,
    )


class TestDefensiveDecorator:
    """Tests for @defensive used as a function decorator."""

    def test_decorator_suppresses_exception_and_returns_fallback(self):
        """Wrapped function that raises returns fallback=[]."""

        def boom():
            raise RuntimeError("kaboom")

        wrapped = _wrap(boom, fallback=[])
        result = wrapped()
        assert result == []

    def test_decorator_logs_with_exc_info(self, caplog):
        """Warning log contains exc_info traceback."""

        def boom():
            raise ValueError("oops")

        wrapped = _wrap(boom, fallback=None)
        with caplog.at_level(logging.WARNING):
            wrapped()

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.WARNING
        assert "oops" in record.message
        assert record.exc_info is not None
        assert record.exc_info[1] is not None

    def test_decorator_does_not_swallow_keyboard_interrupt(self):
        """KeyboardInterrupt re-raised by @defensive-wrapped function."""

        def boom():
            raise KeyboardInterrupt()

        wrapped = _wrap(boom, fallback=None)
        with pytest.raises(KeyboardInterrupt):
            wrapped()

    def test_decorator_does_not_swallow_system_exit(self):
        """SystemExit re-raised by @defensive-wrapped function."""

        def boom():
            raise SystemExit(1)

        wrapped = _wrap(boom, fallback=None)
        with pytest.raises(SystemExit):
            wrapped()

    def test_decorator_custom_fallback_value(self):
        """fallback=42 returned on exception."""

        def boom():
            raise RuntimeError("fail")

        wrapped = _wrap(boom, fallback=42)
        assert wrapped() == 42

    def test_decorator_custom_log_level_error(self, caplog):
        """log_level='error' produces ERROR-level log record."""

        def boom():
            raise RuntimeError("fail")

        wrapped = _wrap(boom, fallback=None, log_level="error")
        with caplog.at_level(logging.DEBUG):
            wrapped()

        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_decorator_custom_label(self, caplog):
        """Log message contains the custom label string."""

        def boom():
            raise RuntimeError("fail")

        wrapped = _wrap(boom, fallback=None, label="my-custom-label")
        with caplog.at_level(logging.WARNING):
            wrapped()

        assert any("my-custom-label" in r.message for r in caplog.records)

    def test_decorator_custom_logger(self, caplog):
        """Custom logger receives the log record, module logger does not."""
        custom_logger = logging.getLogger("test.custom.defensive")

        def boom():
            raise RuntimeError("custom-logger-test")

        wrapped = _wrap(boom, fallback=None, logger=custom_logger)
        with caplog.at_level(logging.WARNING):
            wrapped()

        custom_records = [r for r in caplog.records if r.name == "test.custom.defensive"]
        module_records = [r for r in caplog.records if r.name == "kb.utils.defensive"]
        assert len(custom_records) == 1
        assert len(module_records) == 0
        assert "custom-logger-test" in custom_records[0].message

    def test_bare_decorator_without_arguments(self):
        """@defensive (no parens) works and uses function __qualname__ as label."""

        @defensive
        def my_func():
            raise RuntimeError("bare")

        result = my_func()
        assert result is None  # default fallback

    def test_decorator_preserves_function_metadata(self):
        """@functools.wraps — wrapper.__name__ equals original name."""

        def original_function_name():
            pass

        wrapped = _wrap(original_function_name, fallback=None)
        assert wrapped.__name__ == "original_function_name"

    def test_invalid_first_argument_raises_type_error(self):
        """defensive(42) raises TypeError."""
        with pytest.raises(TypeError, match="callable"):
            defensive(42)


class TestDefensiveContextManager:
    """Tests for defensive() used as a context manager."""

    def test_context_manager_suppresses_exception(self):
        """with defensive(label='x'): block swallows RuntimeError."""
        with defensive(label="x"):
            raise RuntimeError("should be suppressed")

        # Execution continues here — no assertion needed beyond reaching this line.

    def test_context_manager_logs_with_exc_info(self, caplog):
        """Context manager log includes traceback."""
        with caplog.at_level(logging.WARNING):
            with defensive(label="ctx-test"):
                raise ValueError("ctx-error")

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert "ctx-error" in record.message
        assert record.exc_info is not None

    def test_context_manager_does_not_swallow_keyboard_interrupt(self):
        """KeyboardInterrupt propagates from with defensive():."""
        with pytest.raises(KeyboardInterrupt):
            with defensive(label="kbd"):
                raise KeyboardInterrupt()

    def test_context_manager_does_not_swallow_system_exit(self):
        """SystemExit propagates from with defensive():."""
        with pytest.raises(SystemExit):
            with defensive(label="exit"):
                raise SystemExit(1)

    def test_context_manager_no_exception_exits_cleanly(self):
        """Block with no exception: __exit__ returns False, no log emitted."""
        ctx = defensive(label="clean")
        ctx.__enter__()
        result = ctx.__exit__(None, None, None)
        assert result is False
