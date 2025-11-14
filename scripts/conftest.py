"""Pytest configuration and fixtures for end-to-end tests."""

import pytest
from pathlib import Path
import tempfile
import socket


@pytest.fixture
def store_root():
    """Provide a temporary store root directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        store_path = Path(temp_dir) / "dolphin_store"
        store_path.mkdir(parents=True, exist_ok=True)
        yield store_path


@pytest.fixture
def repo_path():
    """Provide a temporary repository path for tests that self-cleans."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_dir = Path(temp_dir) / "test_repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        yield repo_dir


@pytest.fixture
def port():
    """Provide a free port for API server testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        s.listen(1)
        port_num = s.getsockname()[1]
    yield port_num
