"""Tests for knowledge base configuration."""
import pytest
from pathlib import Path
from kb.config import KBConfig, RetrievalConfig, RerankingConfig, load_config

class TestKBConfig:
    """Test cases for KBConfig."""

    def test_default_config_values(self):
        """Test that default config values are set correctly."""
        config = KBConfig()
        assert isinstance(config.retrieval, RetrievalConfig)
        assert config.retrieval.score_cutoff == 0.15
        assert config.retrieval.reranking.enabled is False

    def test_from_mapping_minimal(self):
        """Test from_mapping with minimal data."""
        config = KBConfig.from_mapping({})
        assert config.retrieval.top_k == 8
        assert config.default_embed_model == "large"

    def test_from_mapping_with_all_values(self):
        """Test from_mapping with all values specified."""
        data = {
            "retrieval": {
                "score_cutoff": 0.2,
                "top_k": 10,
                "reranking": {
                    "enabled": True,
                    "model": "bge-reranker-large",
                },
            },
            "embedding": {
                "provider": "openai",
                "default_embed_model": "large",
                "concurrency": 5,
            }
        }
        config = KBConfig.from_mapping(data)
        assert config.retrieval.score_cutoff == 0.2
        assert config.retrieval.top_k == 10
        assert config.retrieval.reranking.enabled is True
        assert config.retrieval.reranking.model == "bge-reranker-large"
        assert config.embedding_provider == "openai"
        assert config.default_embed_model == "large"
        assert config.concurrency == 5
        
    def test_from_mapping_type_coercion(self):
        """Test that from_mapping coerces types correctly."""
        data = {
            "embedding": {"concurrency": "7"},
            "retrieval": {"score_cutoff": "0.5", "top_k": 12.5},
        }
        config = KBConfig.from_mapping(data)
        assert isinstance(config.concurrency, int) and config.concurrency == 7
        assert isinstance(config.retrieval.score_cutoff, float) and config.retrieval.score_cutoff == 0.5
        assert isinstance(config.retrieval.top_k, int) and config.retrieval.top_k == 12

class TestLoadConfig:
    """Test cases for loading configuration from files."""

    def test_load_config_from_valid_file(self, tmp_path):
        """Test loading config from valid TOML file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""
[embedding]
concurrency = 8
[retrieval]
score_cutoff = 0.3
top_k = 20
""")
        config = load_config(config_file)
        assert config.concurrency == 8
        assert config.retrieval.score_cutoff == 0.3
        assert config.retrieval.top_k == 20