"""Tests for knowledge base configuration."""

from kb.config import KBConfig, RetrievalConfig, load_config


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
        # This test is now invalid - all config must come from file
        # Minimal config requires all required fields
        minimal_data = {
            "storage": {"store_root": "/tmp/test"},
            "server": {"endpoint": "127.0.0.1:7777"},
            "embedding": {"provider": "stub", "default_embed_model": "large"},
            "retrieval": {
                "score_cutoff": 0.15,
                "top_k": 8,
                "max_snippet_tokens": 240,
                "mmr_enabled": True,
                "mmr_lambda": 0.7,
                "reranking": {
                    "enabled": False,
                    "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
                    "batch_size": 32,
                    "candidate_multiplier": 4,
                    "score_threshold": 0.3,
                },
                "hybrid_search": {
                    "enabled": True,
                    "fusion_method": "rrf",
                    "fusion_k": 60,
                },
                "ann": {
                    "strategy": "adaptive",
                    "metric": "cosine",
                    "estimated_dataset_size": 100000,
                    "default_query_type": "concept",
                },
            },
        }
        config = KBConfig.from_mapping(minimal_data)
        assert config.retrieval.top_k == 8
        assert config.default_embed_model == "large"

    def test_from_mapping_with_all_values(self):
        """Test from_mapping with all values specified."""
        data = {
            "storage": {"store_root": "/tmp/test"},
            "server": {"endpoint": "127.0.0.1:7777"},
            "retrieval": {
                "score_cutoff": 0.2,
                "top_k": 10,
                "max_snippet_tokens": 240,
                "mmr_enabled": True,
                "mmr_lambda": 0.7,
                "reranking": {
                    "enabled": True,
                    "model": "bge-reranker-large",
                    "batch_size": 32,
                    "candidate_multiplier": 4,
                    "score_threshold": 0.3,
                },
                "hybrid_search": {
                    "enabled": True,
                    "fusion_method": "rrf",
                    "fusion_k": 60,
                },
                "ann": {
                    "strategy": "adaptive",
                    "metric": "cosine",
                    "estimated_dataset_size": 100000,
                    "default_query_type": "concept",
                },
            },
            "embedding": {
                "provider": "openai",
                "default_embed_model": "large",
                "concurrency": 5,
            },
        }
        config = KBConfig.from_mapping(data)
        assert config.retrieval.score_cutoff == 0.2
        assert config.retrieval.top_k == 10
        assert config.retrieval.reranking.enabled is True
        assert config.retrieval.reranking.model == "bge-reranker-large"
        assert config.embedding_provider == "openai"
        assert config.default_embed_model == "large"
        assert config.concurrency == 5

    def test_from_mapping_api_and_graph(self):
        """Test API and graph config parsing from mapping."""
        data = {
            "storage": {"store_root": "/tmp/test"},
            "server": {"endpoint": "127.0.0.1:7777"},
            "api": {
                "max_top_k": 64,
                "max_snippet_tokens": 500,
                "max_context_lines": 8,
                "include_graph_context": False,
                "context_lines_before": 1,
                "context_lines_after": 2,
            },
            "graph": {"max_related_nodes": 3, "max_edges_per_node": 2},
        }

        config = KBConfig.from_mapping(data)

        assert config.api.max_top_k == 64
        assert config.api.max_snippet_tokens == 500
        assert config.api.max_context_lines == 8
        assert config.api.include_graph_context is False
        assert config.api.context_lines_before == 1
        assert config.api.context_lines_after == 2
        assert config.graph.max_related_nodes == 3
        assert config.graph.max_edges_per_node == 2

    def test_from_mapping_type_coercion(self):
        """Test that from_mapping coerces types correctly."""
        data = {
            "storage": {"store_root": "/tmp/test"},
            "server": {"endpoint": "127.0.0.1:7777"},
            "embedding": {
                "provider": "stub",
                "default_embed_model": "large",
                "concurrency": "7",
            },
            "retrieval": {
                "score_cutoff": "0.5",
                "top_k": 12.5,
                "max_snippet_tokens": 240,
                "mmr_enabled": True,
                "mmr_lambda": 0.7,
                "reranking": {
                    "enabled": False,
                    "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
                    "batch_size": 32,
                    "candidate_multiplier": 4,
                    "score_threshold": 0.3,
                },
                "hybrid_search": {
                    "enabled": True,
                    "fusion_method": "rrf",
                    "fusion_k": 60,
                },
                "ann": {
                    "strategy": "adaptive",
                    "metric": "cosine",
                    "estimated_dataset_size": 100000,
                    "default_query_type": "concept",
                },
            },
        }
        config = KBConfig.from_mapping(data)
        assert isinstance(config.concurrency, int) and config.concurrency == 7
        assert isinstance(config.retrieval.score_cutoff, float) and config.retrieval.score_cutoff == 0.5
        assert isinstance(config.retrieval.top_k, int) and config.retrieval.top_k == 12

    def test_config_ignore_exceptions_field(self):
        """Test that ignore_exceptions field is properly initialized and used."""
        config_data = {
            "storage": {"store_root": "/tmp/test"},
            "server": {"endpoint": "127.0.0.1:7777"},
            "embedding": {"provider": "stub", "default_embed_model": "large"},
            "retrieval": {
                "score_cutoff": 0.15,
                "top_k": 8,
                "max_snippet_tokens": 240,
                "mmr_enabled": True,
                "mmr_lambda": 0.7,
                "reranking": {
                    "enabled": False,
                    "model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
                    "batch_size": 32,
                    "candidate_multiplier": 4,
                    "score_threshold": 0.3,
                },
                "hybrid_search": {
                    "enabled": True,
                    "fusion_method": "rrf",
                    "fusion_k": 60,
                },
                "ann": {
                    "strategy": "adaptive",
                    "metric": "cosine",
                    "estimated_dataset_size": 100000,
                    "default_query_type": "concept",
                },
            },
            "ignore": [".env", "*.log"],
            "ignore_exceptions": [".env.example", "config.log"],
        }

        config = KBConfig.from_mapping(config_data)

        assert ".env" in config.ignore
        assert "*.log" in config.ignore
        assert ".env.example" in config.ignore_exceptions
        assert "config.log" in config.ignore_exceptions

        # Test that build_ignore_set works with config exceptions
        from kb.ignores import build_ignore_set

        result = build_ignore_set(config.ignore, config.ignore_exceptions)

        # Basic patterns should be there
        assert ".env" in result
        assert "*.log" in result

        # Exceptions should be excluded
        assert ".env.example" not in result
        assert "config.log" not in result


class TestLoadConfig:
    """Test cases for loading configuration from files."""

    def test_load_config_from_valid_file(self, tmp_path):
        """Test loading config from valid TOML file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            """
[storage]
store_root = "/tmp/test"

[server]
endpoint = "127.0.0.1:7777"

[embedding]
provider = "stub"
default_embed_model = "large"
concurrency = 8

[retrieval]
score_cutoff = 0.3
top_k = 20
max_snippet_tokens = 240
mmr_enabled = true
mmr_lambda = 0.7

[retrieval.reranking]
enabled = false
model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
batch_size = 32
candidate_multiplier = 4
score_threshold = 0.3

[retrieval.hybrid_search]
enabled = true
fusion_method = "rrf"
fusion_k = 60

[retrieval.ann]
strategy = "adaptive"
metric = "cosine"
estimated_dataset_size = 100000
default_query_type = "concept"
"""
        )
        config = load_config(config_file)
        assert config.concurrency == 8
        assert config.retrieval.score_cutoff == 0.3
        assert config.retrieval.top_k == 20

    def test_load_config_merges_repo_over_global(self, tmp_path, monkeypatch):
        """Test repo config overrides are merged over global config."""
        base_config = tmp_path / "global.toml"
        base_config.write_text(
            """
[storage]
store_root = "/tmp/test"

[retrieval]
score_cutoff = 0.2
top_k = 7

[api]
max_top_k = 50
include_graph_context = true
"""
        )
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        repo_cfg_dir = repo_dir / ".dolphin"
        repo_cfg_dir.mkdir()
        (repo_cfg_dir / "config.toml").write_text(
            """
ignore = ["node_modules/**"]
"""
        )

        monkeypatch.setenv("DOLPHIN_CONFIG_PATH", str(base_config))

        config = load_config(repo_path=repo_dir)

        assert config.retrieval.top_k == 7
        assert config.api.max_top_k == 50
        assert "node_modules/**" in config.ignore
