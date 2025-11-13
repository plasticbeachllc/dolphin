"""Tests for repository-specific chunking configuration."""

import tempfile
from pathlib import Path

from kb.chunkers import RepoChunkingConfig, load_repo_chunking_config


def test_load_dolphin_repo_config():
    """Test loading configuration from the dolphin repo."""
    dolphin_path = Path(__file__).parent.parent.parent
    config = load_repo_chunking_config(dolphin_path)

    assert config.repo_path == dolphin_path.resolve()
    assert config.default_window_size > 0, "Default window size must be positive"
    assert config.embedding_model in [
        "text-embedding-3-small",
        "text-embedding-3-large",
    ], f"Invalid embedding model: {config.embedding_model}"
    assert config.tokenizer_encoding == "cl100k_base", "Expected cl100k_base encoding"


def test_per_language_window_sizes():
    """Test per-language window size configuration."""
    dolphin_path = Path(__file__).parent.parent.parent
    config = load_repo_chunking_config(dolphin_path)

    python_size = config.get_window_size_for_language("python")
    assert python_size > 0, "Python window size must be positive"

    typescript_size = config.get_window_size_for_language("typescript")
    assert typescript_size > 0, "TypeScript window size must be positive"


def test_overlap_calculation():
    """Test overlap token calculation."""
    dolphin_path = Path(__file__).parent.parent.parent
    config = load_repo_chunking_config(dolphin_path)

    python_size = config.get_window_size_for_language("python")
    overlap = config.get_overlap_tokens(python_size)
    assert overlap >= 0, "Overlap must be non-negative"
    assert overlap < python_size, "Overlap must be less than window size"


def test_missing_config_uses_defaults():
    """Test that missing config file uses sensible defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        default_config = load_repo_chunking_config(tmp_path)

        assert default_config.repo_path == tmp_path.resolve()
        assert (
            default_config.default_window_size == 350
        ), "Expected default window size 350"
        assert default_config.embedding_model == "text-embedding-3-small"


def test_custom_config_file():
    """Test loading custom configuration from TOML file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()

        config_file = config_dir / "chunking_config.toml"
        config_file.write_text(
            """
default_window_size = 512

[per_language]
rust = 600
python = 700

[embeddings]
model = "text-embedding-3-large"

[tokenizer]
encoding = "cl100k_base"
"""
        )

        custom_config = load_repo_chunking_config(tmp_path)
        assert custom_config.default_window_size == 512
        assert custom_config.get_window_size_for_language("rust") == 600
        assert custom_config.get_window_size_for_language("python") == 700
        assert custom_config.embedding_model == "text-embedding-3-large"
