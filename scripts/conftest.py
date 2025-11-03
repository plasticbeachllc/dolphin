"""Pytest configuration and fixtures for end-to-end tests."""
import pytest
from pathlib import Path
import tempfile
import socket


@pytest.fixture
def store_root():
    """Provide a temporary store root directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir) / "dolphin_store"


@pytest.fixture
def repo_path(store_root):
    """Provide a temporary repository path for tests."""
    repo_dir = store_root.parent / "test_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    yield repo_dir


@pytest.fixture
def port():
    """Provide a free port for API server testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port_num = s.getsockname()[1]
    yield port_num
