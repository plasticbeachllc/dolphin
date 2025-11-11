"""Pytest configuration for end-to-end tests."""

import pytest
import tempfile
from pathlib import Path
from typing import Generator

from kb.store import LanceDBStore, SQLiteMetadataStore
from kb.config import KBConfig
from kb.pipeline import IngestionPipeline


@pytest.fixture
def e2e_test_repo() -> Generator[Path, None, None]:
    """Create a test repository with sample code."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir)

        # Create sample Python files
        (repo_dir / "main.py").write_text("""
def authenticate_user(username, password):
    '''Authenticate user with credentials.'''
    if not username or not password:
        return False
    return True

def validate_email(email):
    '''Validate email address format.'''
    return '@' in email and '.' in email
""")

        (repo_dir / "api.py").write_text("""
def create_api_endpoint(route, handler):
    '''Create REST API endpoint.'''
    return {'route': route, 'handler': handler}

def handle_request(request):
    '''Handle incoming HTTP request.'''
    return {'status': 200, 'body': 'OK'}
""")

        (repo_dir / "utils.py").write_text("""
def hash_password(password):
    '''Hash password for storage.'''
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token():
    '''Generate authentication token.'''
    import secrets
    return secrets.token_hex(32)
""")

        # Create markdown documentation
        (repo_dir / "README.md").write_text("""
# Sample Project

This is a sample authentication project.

## Features

- User authentication
- Email validation
- Password hashing
- Token generation
""")

        yield repo_dir


@pytest.fixture
def e2e_kb_setup(e2e_test_repo: Path) -> Generator[dict, None, None]:
    """Set up complete KB infrastructure for E2E testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "kb.db"

        # Initialize stores
        metadata_store = SQLiteMetadataStore(db_path)
        metadata_store.initialize()

        lancedb_store = LanceDBStore("memory://e2e_test")

        # Create config
        config = KBConfig(
            default_embed_model="small",
            ignore=["*.pyc", "__pycache__/*", ".git/*"]
        )

        # Create pipeline
        pipeline = IngestionPipeline(config, lancedb_store, metadata_store)

        # Register repository
        metadata_store.record_repo(
            name="test-repo",
            path=e2e_test_repo,
            default_embed_model="small"
        )

        yield {
            'pipeline': pipeline,
            'metadata_store': metadata_store,
            'lancedb_store': lancedb_store,
            'config': config,
            'repo_path': e2e_test_repo,
            'repo_name': 'test-repo'
        }
