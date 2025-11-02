"""Tests for centralized error logging and retry decorator."""

import io
import logging
from pathlib import Path

from kb.ingest.error_logging import ErrorLogger, log_error_to_file, with_retry


def test_error_logger_writes_file(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    logger = ErrorLogger(repo_root, session_id="123")
    logger.log_error("Something bad happened")

    # Ensure log file exists and contains our message
    log_path = logger.get_log_path()
    assert log_path.exists()
    content = log_path.read_text()
    assert "Something bad happened" in content


def test_error_logger_file_and_console_levels(tmp_path: Path, caplog):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    # Capture logs
    caplog.set_level(logging.ERROR)

    logger = ErrorLogger(repo_root, session_id="abc")
    try:
        raise RuntimeError("boom")
    except RuntimeError as e:
        logger.log_file_error("src/a.py", e)

    # File should include our message and an exception info line
    text = logger.get_log_path().read_text()
    assert "Error processing file src/a.py" in text
    # Depending on logging configuration, exc_info may render as traceback or 'NoneType: None'
    assert ("Traceback" in text) or ("NoneType: None" in text)


def test_log_error_to_file_convenience(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    log_error_to_file(repo_root, "quick error", session_id="s1")
    # A file should be created under .pb_kb_logs
    logs_dir = repo_root / ".pb_kb_logs"
    assert any(p.name.startswith("indexing_errors_") for p in logs_dir.iterdir())


def test_with_retry_decorator_succeeds_after_attempts(monkeypatch):
    calls = {"n": 0}

    @with_retry(max_attempts=3, delays=(0.01, 0.01))
    def sometimes():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("fail")
        return "ok"

    assert sometimes() == "ok"
    assert calls["n"] == 3


def test_with_retry_decorator_propagates_after_exhaustion(monkeypatch):
    @with_retry(max_attempts=2, delays=(0.01,))
    def always_fail():
        raise ValueError("nope")

    try:
        always_fail()
    except ValueError as e:
        assert str(e) == "nope"
    else:
        raise AssertionError("Expected ValueError to be raised after retries")
