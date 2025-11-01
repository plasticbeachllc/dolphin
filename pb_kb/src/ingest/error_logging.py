"""Centralized error logging for ingestion pipeline."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

# Track initialized loggers to avoid duplicate handlers across instances
_initialized_loggers: Dict[str, bool] = {}


class ErrorLogger:
    """Centralized error logging for ingestion pipeline operations."""

    def __init__(self, repo_root: Path, session_id: Optional[str] = None):
        """Initialize error logger for a repository.

        Args:
            repo_root: Root path of the repository being indexed
            session_id: Optional session identifier for grouping logs
        """
        self.repo_root = repo_root
        self.session_id = session_id

        # Log directory and file path (dir created lazily on first write)
        self.log_dir = repo_root / ".pb_kb_logs"

        # Generate log filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_suffix = f"_session_{session_id}" if session_id else ""
        self.log_file = self.log_dir / f"indexing_errors_{timestamp}{session_suffix}.log"

        # Lazy logger/file creation
        self._logger_name = f"pb_kb_ingest_{self.session_id or 'unknown'}"
        self.logger: Optional[logging.Logger] = None
        self._initialized = False
        self._had_errors = False

    def _setup_logging(self) -> None:
        """Configure logging to write to both file and console."""
        # Ensure directory exists only when we need to log
        self.log_dir.mkdir(exist_ok=True)

        logger = logging.getLogger(self._logger_name)
        logger.setLevel(logging.ERROR)

        if not _initialized_loggers.get(self._logger_name):
            # File handler
            file_handler = logging.FileHandler(self.log_file)
            file_handler.setLevel(logging.ERROR)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

            # Console handler (for critical errors only)
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.CRITICAL)
            console_formatter = logging.Formatter('%(levelname)s: %(message)s')
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

            _initialized_loggers[self._logger_name] = True
        self.logger = logger
        self._initialized = True

    def log_error(self, message: str, exc_info: bool = False) -> None:
        """Log an error message.

        Args:
            message: Error message to log
            exc_info: Whether to include exception info if available
        """
        if not self._initialized:
            self._setup_logging()
        self._had_errors = True
        assert self.logger is not None
        self.logger.error(message, exc_info=exc_info)

    def log_file_error(self, file_path: str, error: Exception) -> None:
        """Log an error for a specific file.

        Args:
            file_path: Path of the file that caused the error
            error: Exception that occurred
        """
        message = f"Error processing file {file_path}: {error}"
        self.log_error(message, exc_info=True)

    def log_embedding_error(self, model: str, error: Exception) -> None:
        """Log an embedding-related error.

        Args:
            model: Embedding model that caused the error
            error: Exception that occurred
        """
        message = f"Embedding error with model {model}: {error}"
        self.log_error(message, exc_info=True)

    def get_log_path(self) -> Path:
        """Return the path to the current log file."""
        return self.log_file

    def had_errors(self) -> bool:
        """Return True if any error has been logged during this session."""
        return self._had_errors


# Convenience function for quick error logging without full setup

def log_error_to_file(repo_root: Path, message: str, session_id: Optional[str] = None) -> None:
    """Quick convenience function to log an error without full ErrorLogger setup.

    Args:
        repo_root: Root path of the repository
        message: Error message to log
        session_id: Optional session identifier
    """
    logger = ErrorLogger(repo_root, session_id)
    logger.log_error(message)


# Retry decorator for network operations

def with_retry(max_attempts: int = 3, delays: tuple[float, ...] = (1.0, 2.0, 4.0)):
    """Decorator for retrying network operations with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        delays: Tuple of delay times in seconds for each attempt

    Usage:
        @with_retry()
        def embed_texts(model, texts):
            # embedding implementation
    """
    import time
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:  # Not the last attempt
                        delay = delays[attempt] if attempt < len(delays) else delays[-1]
                        time.sleep(delay)
                    else:
                        # Last attempt failed, re-raise the exception
                        raise last_exception
            # This should never be reached, but just in case
            raise last_exception
        return wrapper
    return decorator
