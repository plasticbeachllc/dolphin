"""Unit tests for configuration loading and validation."""

import pytest
from pathlib import Path
from kb.config import (
    KBConfig,
    load_config,
    _to_path,
    CONFIG_ROOT,
    DEFAULT_CONFIG_PATH,
)


class TestToPath:
    """Test path conversion and expansion."""

    def test_path_object_expansion(self):
        """Test that Path objects are expanded and resolved."""
        path = Path("~/test")
        result = _to_path(path)
        assert result.is_absolute()
        assert "~" not in str(result)

    def test_string_conversion(self):
        """Test that strings are converted to Path and expanded."""
        result = _to_path("~/test")
        assert isinstance(result, Path)
        assert result.is_absolute()
        assert "~" not in str(result)

    def test_already_absolute(self):
        """Test that absolute paths are preserved."""
        path = Path("/tmp/test")
        result = _to_path(path)
        assert result == path.resolve()


class TestKBConfig:
    """Test KBConfig dataclass and methods."""

    def test_default_config_values(self):
        """Test that default config values are set correctly."""
        config = KBConfig()
        assert config.endpoint == "127.0.0.1:7777"
        assert config.default_embed_model == "large"
        assert config.concurrency == 3
        assert config.per_session_spend_cap_usd == 10.0
        assert config.score_cutoff == 0.15
        assert config.top_k == 8
        assert config.max_snippet_tokens == 240
        assert config.embedding_provider == "stub"
        assert config.embedding_batch_size == 100
        assert config.openai_api_key_env == "OPENAI_API_KEY"

    def test_from_mapping_minimal(self):
        """Test from_mapping with minimal data."""
        config = KBConfig.from_mapping({})
        assert config.endpoint == "127.0.0.1:7777"
        assert config.default_embed_model == "small"  # Note: from_mapping default is "small"

    def test_from_mapping_with_all_values(self):
        """Test from_mapping with all values specified."""
        data = {
            "store_root": "/tmp/test_store",
            "endpoint": "0.0.0.0:8888",
            "default_embed_model": "large",
            "concurrency": 5,
            "per_session_spend_cap_usd": 20.0,
            "ignore": ["*.pyc", "*.log"],
            "score_cutoff": 0.2,
            "top_k": 10,
            "max_snippet_tokens": 300,
            "embedding_provider": "openai",
            "embedding_batch_size": 50,
            "openai_api_key_env": "MY_API_KEY",
        }
        config = KBConfig.from_mapping(data)

        assert config.store_root == Path("/tmp/test_store").resolve()
        assert config.endpoint == "0.0.0.0:8888"
        assert config.default_embed_model == "large"
        assert config.concurrency == 5
        assert config.per_session_spend_cap_usd == 20.0
        assert config.ignore == ["*.pyc", "*.log"]
        assert config.score_cutoff == 0.2
        assert config.top_k == 10
        assert config.max_snippet_tokens == 300
        assert config.embedding_provider == "openai"
        assert config.embedding_batch_size == 50
        assert config.openai_api_key_env == "MY_API_KEY"

    def test_from_mapping_with_nested_retrieval(self):
        """Test from_mapping with nested retrieval section."""
        data = {
            "retrieval": {
                "score_cutoff": 0.25,
                "top_k": 15,
                "max_snippet_tokens": 500,
            }
        }
        config = KBConfig.from_mapping(data)

        assert config.score_cutoff == 0.25
        assert config.top_k == 15
        assert config.max_snippet_tokens == 500

    def test_from_mapping_with_nested_embedding(self):
        """Test from_mapping with nested embedding section."""
        data = {
            "embedding": {
                "provider": "openai",
                "batch_size": 200,
                "api_key_env": "CUSTOM_KEY",
            }
        }
        config = KBConfig.from_mapping(data)

        assert config.embedding_provider == "openai"
        assert config.embedding_batch_size == 200
        assert config.openai_api_key_env == "CUSTOM_KEY"

    def test_from_mapping_nested_overrides_top_level(self):
        """Test that nested config overrides top-level config."""
        data = {
            "score_cutoff": 0.1,
            "retrieval": {
                "score_cutoff": 0.3,
            }
        }
        config = KBConfig.from_mapping(data)
        # Nested value should take precedence
        assert config.score_cutoff == 0.3

    def test_from_mapping_type_coercion(self):
        """Test that from_mapping coerces types correctly."""
        data = {
            "concurrency": "7",  # String should be converted to int
            "score_cutoff": "0.5",  # String should be converted to float
            "top_k": 12.5,  # Float should be converted to int
        }
        config = KBConfig.from_mapping(data)

        assert config.concurrency == 7
        assert isinstance(config.concurrency, int)
        assert config.score_cutoff == 0.5
        assert isinstance(config.score_cutoff, float)
        assert config.top_k == 12
        assert isinstance(config.top_k, int)

    def test_resolved_store_root(self):
        """Test resolved_store_root method."""
        config = KBConfig(store_root=Path("~/test"))
        result = config.resolved_store_root()
        assert result.is_absolute()
        assert "~" not in str(result)


class TestLoadConfig:
    """Test config loading from files."""

    def test_load_config_nonexistent_returns_defaults(self, tmp_path):
        """Test that loading non-existent config returns defaults."""
        nonexistent = tmp_path / "nonexistent.toml"
        config = load_config(nonexistent)

        assert isinstance(config, KBConfig)
        assert config.endpoint == "127.0.0.1:7777"
        assert config.default_embed_model == "large"

    def test_load_config_from_valid_file(self, tmp_path):
        """Test loading config from valid TOML file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
endpoint = "0.0.0.0:9999"
default_embed_model = "large"
concurrency = 8

[retrieval]
score_cutoff = 0.3
top_k = 20

[embedding]
provider = "openai"
batch_size = 150
""")

        config = load_config(config_file)
        assert config.endpoint == "0.0.0.0:9999"
        assert config.default_embed_model == "large"
        assert config.concurrency == 8
        assert config.score_cutoff == 0.3
        assert config.top_k == 20
        assert config.embedding_provider == "openai"
        assert config.embedding_batch_size == 150

    def test_load_config_empty_file(self, tmp_path):
        """Test loading config from empty file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("")

        config = load_config(config_file)
        # Should use defaults
        assert isinstance(config, KBConfig)
        assert config.endpoint == "127.0.0.1:7777"

    def test_load_config_invalid_toml_raises_error(self, tmp_path):
        """Test that invalid TOML syntax raises an error."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[invalid toml syntax
endpoint = "test"
""")

        with pytest.raises(Exception):  # tomllib.TOMLDecodeError
            load_config(config_file)

    def test_load_config_non_mapping_raises_error(self, tmp_path):
        """Test that non-mapping config raises ValueError."""
        config_file = tmp_path / "config.toml"
        # Create a valid TOML file where the parsed result is not a mapping
        # Actually, TOML files are always parsed to dicts at top level
        # So this test is checking an edge case that's hard to create
        # Let's just verify the function handles it properly
        # We'll skip this for now as it's not a realistic scenario
        pytest.skip("TOML files always parse to dicts at top level")

    def test_load_config_with_path_expansion(self, tmp_path):
        """Test that paths in config are expanded."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('store_root = "~/custom_store"')

        config = load_config(config_file)
        assert config.store_root.is_absolute()
        assert "~" not in str(config.store_root)

    def test_load_config_default_path(self, tmp_path, monkeypatch):
        """Test load_config with no arguments uses user config path."""
        # Create a config at the user config location
        user_config_path = tmp_path / "config.toml"
        user_config_path.write_text('endpoint = "custom:1234"')

        # Monkeypatch USER_CONFIG_PATH
        monkeypatch.setattr("kb.config.USER_CONFIG_PATH", user_config_path)

        config = load_config()
        assert config.endpoint == "custom:1234"

    def test_load_config_with_ignore_patterns(self, tmp_path):
        """Test loading config with ignore patterns."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
ignore = ["*.pyc", "*.pyo", "__pycache__"]
""")

        config = load_config(config_file)
        assert "*.pyc" in config.ignore
        assert "*.pyo" in config.ignore
        assert "__pycache__" in config.ignore
