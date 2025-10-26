"""Tests for repository-specific chunking configuration."""

from pathlib import Path
import tempfile
import shutil

from pb_kb.chunkers import RepoChunkingConfig, load_repo_chunking_config


def run_test():
    """Test repository chunking configuration loading."""
    print("Testing RepoChunkingConfig...")
    
    # Test 1: Loading configuration from the dolphin repo (should exist)
    dolphin_path = Path(__file__).parent.parent
    config = load_repo_chunking_config(dolphin_path)
    
    assert config.repo_path == dolphin_path.resolve()
    assert config.default_window_size > 0, "Default window size must be positive"
    assert config.embedding_model in [
        "text-embedding-3-small",
        "text-embedding-3-large",
    ], f"Invalid embedding model: {config.embedding_model}"
    assert config.tokenizer_encoding == "cl100k_base", "Expected cl100k_base encoding"
    
    print(f"✓ Loaded config from {dolphin_path}")
    print(f"  - default_window_size: {config.default_window_size}")
    print(f"  - embedding_model: {config.embedding_model}")
    print(f"  - tokenizer_encoding: {config.tokenizer_encoding}")
    
    # Test 2: Per-language window sizes
    python_size = config.get_window_size_for_language("python")
    assert python_size > 0, "Python window size must be positive"
    print(f"  - python window size: {python_size}")
    
    typescript_size = config.get_window_size_for_language("typescript")
    assert typescript_size > 0, "TypeScript window size must be positive"
    print(f"  - typescript window size: {typescript_size}")
    
    # Test 3: Overlap calculation
    overlap = config.get_overlap_tokens(python_size)
    assert overlap >= 0, "Overlap must be non-negative"
    assert overlap < python_size, "Overlap must be less than window size"
    print(f"  - python overlap tokens: {overlap}")
    
    # Test 4: Missing config (should use defaults)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        default_config = load_repo_chunking_config(tmp_path)
        
        assert default_config.repo_path == tmp_path.resolve()
        assert default_config.default_window_size == 350, "Expected default window size 350"
        assert default_config.embedding_model == "text-embedding-3-small"
        print(f"✓ Default config works for repo without .dolphin/chunking_config.toml")
    
    # Test 5: Custom config file
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        config_dir = tmp_path / ".dolphin"
        config_dir.mkdir()
        
        config_file = config_dir / "chunking_config.toml"
        config_file.write_text("""
default_window_size = 512

[per_language]
rust = 600
python = 700

[embeddings]
model = "text-embedding-3-large"

[tokenizer]
encoding = "cl100k_base"
""")
        
        custom_config = load_repo_chunking_config(tmp_path)
        assert custom_config.default_window_size == 512
        assert custom_config.get_window_size_for_language("rust") == 600
        assert custom_config.get_window_size_for_language("python") == 700
        assert custom_config.embedding_model == "text-embedding-3-large"
        print(f"✓ Custom config loaded successfully")
    
    print("\n✅ All RepoChunkingConfig tests passed!")


if __name__ == "__main__":
    run_test()
