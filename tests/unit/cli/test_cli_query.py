"""
Additional CLI tests for query and health commands

Tests remaining CLI commands to improve coverage
"""

import pytest
from typer.testing import CliRunner
from kb.cli import app

runner = CliRunner()


def test_help_command():
    """Test help command."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
