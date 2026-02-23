"""Defensive decorator and context manager for intentionally broad exception handlers.

Usage
-----
Use ``@defensive`` when you need to swallow exceptions deliberately — for
example, in background cleanup tasks or optional enrichment steps where failure
must not propagate.  It makes the intent explicit and ensures the exception is
always logged with a full traceback.

Examples::

    from kb.utils.defensive import defensive

    # As a function decorator (returns fallback on any exception):
    @defensive(fallback=[], log_level="warning")
    def load_optional_data() -> list[str]:
        ...

    # As a context manager (executes body; on exception logs and continues):
    with defensive(label="cache-warm", log_level="warning"):
        warm_cache()
"""

from __future__ import annotations

import functools
import logging
import types
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, TypeVar

_log = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


class _DefensiveContext(AbstractContextManager):
    """Context manager produced by :func:`defensive`."""

    def __init__(self, label: str, log_level: int, logger: logging.Logger) -> None:
        self._label = label
        self._log_level = log_level
        self._logger = logger

    def __enter__(self) -> _DefensiveContext:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> bool:
        if exc_type is None:
            return False
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            # Never swallow signals or interpreter exits.
            return False
        self._logger.log(
            self._log_level,
            "Suppressed exception in defensive block [%s]: %s",
            self._label,
            exc_val,
            exc_info=True,
        )
        return True  # Suppress the exception.


class _Defensive:
    """Callable that acts as both a decorator factory and context manager.

    When called with keyword-only arguments it returns itself configured for
    use as a ``with`` statement or as a ``@defensive(...)`` decorator.

    Parameters
    ----------
    fallback:
        Value returned by the decorated function when an exception is caught.
        Ignored when used as a context manager.
    log_level:
        Logging level name (``"debug"``, ``"info"``, ``"warning"``,
        ``"error"``, ``"critical"``).  Defaults to ``"warning"``.
    label:
        Short description used in the log message to identify the call site.
        Defaults to the decorated function's qualified name, or ``"<block>"``
        when used as a context manager without a label.
    logger:
        Logger instance to use.  Defaults to this module's logger.
    """

    def __call__(
        self,
        func_or_none: F | None = None,
        *,
        fallback: Any = None,
        log_level: str = "warning",
        label: str | None = None,
        logger: logging.Logger | None = None,
    ) -> Any:
        resolved_level = _LEVELS.get(log_level.lower(), logging.WARNING)
        resolved_logger = logger or _log

        # Used as a context manager: defensive(label="x")
        if func_or_none is None:
            return _DefensiveContext(
                label=label or "<block>",
                log_level=resolved_level,
                logger=resolved_logger,
            )

        # Used directly as a decorator without arguments: @defensive
        if callable(func_or_none):
            return self._wrap(
                func_or_none,
                fallback=fallback,
                log_level=resolved_level,
                label=label,
                logger=resolved_logger,
            )

        raise TypeError(f"defensive() first positional argument must be callable, got {type(func_or_none)!r}")

    @staticmethod
    def _wrap(func: F, *, fallback: Any, log_level: int, label: str | None, logger: logging.Logger) -> F:
        resolved_label = label or func.__qualname__

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as exc:
                logger.log(
                    log_level,
                    "Suppressed exception in @defensive [%s]: %s",
                    resolved_label,
                    exc,
                    exc_info=True,
                )
                return fallback

        return wrapper  # type: ignore[return-value]


defensive = _Defensive()
