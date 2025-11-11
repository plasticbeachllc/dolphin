"""Unit tests for personas.src.continue_utils module."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from personas.src.continue_utils import (
    ContinueError,
    build_continue_entry,
    write_continue_config,
    validate_continue_config,
)
from personas.src.persona_utils import Persona


@pytest.fixture
def mock_persona():
    """Create a mock persona for testing."""
    return Persona(
        path=Path("/test/persona"),
        id="test-persona",
        name="Test Persona",
        version="1.0.0",
        provider_kind="anthropic",
        provider_model="claude-3-5-sonnet-20241022",
        params={"temperature": 0.7, "max_tokens": 4000},
        token_budget=1200,
        trim_policy="tiered",
        system_text="You are a helpful assistant.",
        provider_options={"apiBase": "https://api.anthropic.com"},
        continue_extra={"contextLength": 8000},
        raw={"continue": {"roles": ["chat", "edit"]}},
        warnings=[]
    )


class TestBuildContinueEntry:
    """Test build_continue_entry function."""

    def test_build_basic_entry(self, mock_persona):
        """Test building basic Continue entry."""
        system_message = "Test system message"
        entry = build_continue_entry(mock_persona, system_message)

        assert entry["name"] == "Test Persona"
        assert entry["title"] == "Test Persona"
        assert entry["provider"] == "anthropic"
        assert entry["model"] == "claude-3-5-sonnet-20241022"
        assert entry["systemMessage"] == system_message
        assert entry["roles"] == ["chat", "edit"]

    def test_build_entry_with_completion_params(self, mock_persona):
        """Test building entry with completion parameters."""
        mock_persona.params = {
            "temperature": 0.8,
            "top_p": 0.9,
            "max_tokens": 5000,
            "presence_penalty": 0.1
        }

        entry = build_continue_entry(mock_persona, "Test message")

        assert "defaultCompletionOptions" in entry
        assert entry["defaultCompletionOptions"]["temperature"] == 0.8
        assert entry["defaultCompletionOptions"]["topP"] == 0.9
        assert entry["defaultCompletionOptions"]["maxTokens"] == 5000
        assert entry["defaultCompletionOptions"]["presencePenalty"] == 0.1

    def test_build_entry_default_roles(self):
        """Test default roles when not specified."""
        persona = Persona(
            path=Path("/test"),
            id="test",
            name="Test",
            version="1.0",
            provider_kind="openai",
            provider_model="gpt-4",
            params={},
            token_budget=1200,
            trim_policy="tiered",
            system_text="",
            provider_options={},
            continue_extra={},
            raw={},  # No continue section
            warnings=[]
        )

        entry = build_continue_entry(persona, "message")

        assert entry["roles"] == ["chat", "edit"]

    def test_build_entry_single_role_string(self):
        """Test when role is specified as a string."""
        persona = Persona(
            path=Path("/test"),
            id="test",
            name="Test",
            version="1.0",
            provider_kind="openai",
            provider_model="gpt-4",
            params={},
            token_budget=1200,
            trim_policy="tiered",
            system_text="",
            provider_options={},
            continue_extra={},
            raw={"continue": {"roles": "chat"}},
            warnings=[]
        )

        entry = build_continue_entry(persona, "message")

        assert entry["roles"] == ["chat"]

    @patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key-123'})
    def test_build_entry_anthropic_api_key(self, mock_persona):
        """Test Anthropic API key from environment."""
        entry = build_continue_entry(mock_persona, "message")

        assert entry["apiKey"] == "test-key-123"

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'openai-key-123'})
    def test_build_entry_openai_api_key(self):
        """Test OpenAI API key from environment."""
        persona = Persona(
            path=Path("/test"),
            id="test",
            name="Test",
            version="1.0",
            provider_kind="openai",
            provider_model="gpt-4",
            params={},
            token_budget=1200,
            trim_policy="tiered",
            system_text="",
            provider_options={},
            continue_extra={},
            raw={},
            warnings=[]
        )

        entry = build_continue_entry(persona, "message")

        assert entry["apiKey"] == "openai-key-123"

    @patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'deepseek-key-123'})
    def test_build_entry_deepseek_api_key(self):
        """Test DeepSeek API key from environment."""
        persona = Persona(
            path=Path("/test"),
            id="test",
            name="Test",
            version="1.0",
            provider_kind="openai",
            provider_model="deepseek-chat",
            params={},
            token_budget=1200,
            trim_policy="tiered",
            system_text="",
            provider_options={"apiBase": "https://api.deepseek.com"},
            continue_extra={},
            raw={},
            warnings=[]
        )

        entry = build_continue_entry(persona, "message")

        assert entry["apiKey"] == "deepseek-key-123"

    def test_build_entry_provider_options(self, mock_persona):
        """Test provider options are included."""
        entry = build_continue_entry(mock_persona, "message")

        assert entry["apiBase"] == "https://api.anthropic.com"

    def test_build_entry_continue_extra(self, mock_persona):
        """Test continue extra fields are included."""
        entry = build_continue_entry(mock_persona, "message")

        assert entry["contextLength"] == 8000


class TestWriteContinueConfig:
    """Test write_continue_config function."""

    def test_write_config_success(self, mock_persona):
        """Test writing Continue config successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir)
            compiled_messages = {"test-persona": "Test system message"}

            result = write_continue_config(
                personas=[mock_persona],
                compiled_messages=compiled_messages,
                target_dir=target_dir,
                dry_run=False
            )

            assert result["models_count"] >= 1
            assert result["config_type"] == "workspace"

            # Check config file was created
            config_file = target_dir / ".continue-config" / "personas_config.yaml"
            assert config_file.exists()

    def test_write_config_dry_run(self, mock_persona):
        """Test dry run doesn't create files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir)
            compiled_messages = {"test-persona": "Test system message"}

            result = write_continue_config(
                personas=[mock_persona],
                compiled_messages=compiled_messages,
                target_dir=target_dir,
                dry_run=True
            )

            assert result["models_count"] >= 1
            assert "config_payload" in result

            # Check no files were created
            config_file = target_dir / ".continue-config" / "personas_config.yaml"
            assert not config_file.exists()

    def test_write_config_multiple_personas(self):
        """Test writing config with multiple personas."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir)

            personas = [
                Persona(
                    path=Path("/test1"),
                    id="persona1",
                    name="Persona 1",
                    version="1.0",
                    provider_kind="anthropic",
                    provider_model="claude-3-5-sonnet-20241022",
                    params={},
                    token_budget=1200,
                    trim_policy="tiered",
                    system_text="",
                    provider_options={},
                    continue_extra={},
                    raw={},
                    warnings=[]
                ),
                Persona(
                    path=Path("/test2"),
                    id="persona2",
                    name="Persona 2",
                    version="1.0",
                    provider_kind="openai",
                    provider_model="gpt-4",
                    params={},
                    token_budget=1200,
                    trim_policy="tiered",
                    system_text="",
                    provider_options={},
                    continue_extra={},
                    raw={},
                    warnings=[]
                )
            ]

            compiled_messages = {
                "persona1": "Message 1",
                "persona2": "Message 2"
            }

            result = write_continue_config(
                personas=personas,
                compiled_messages=compiled_messages,
                target_dir=target_dir,
                dry_run=False
            )

            # Should have at least 2 personas + maybe autocomplete
            assert result["models_count"] >= 2

    def test_write_config_with_manifest(self, mock_persona):
        """Test writing config with manifest file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir)
            manifest_file = target_dir / "manifest.json"
            compiled_messages = {"test-persona": "Test message"}

            result = write_continue_config(
                personas=[mock_persona],
                compiled_messages=compiled_messages,
                target_dir=target_dir,
                manifest_file=manifest_file,
                dry_run=False
            )

            assert result["manifest_file"] == str(manifest_file)
            assert manifest_file.exists()

    def test_write_config_adds_autocomplete(self, mock_persona):
        """Test that qwen autocomplete model is added if not present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir)
            compiled_messages = {"test-persona": "Test message"}

            result = write_continue_config(
                personas=[mock_persona],
                compiled_messages=compiled_messages,
                target_dir=target_dir,
                dry_run=True
            )

            # Check config payload includes autocomplete model
            models = result["config_payload"]["models"]
            has_qwen = any(
                model.get("model") == "qwen2.5-coder:1.5b"
                for model in models
            )
            assert has_qwen


class TestValidateContinueConfig:
    """Test validate_continue_config function."""

    def test_validate_valid_config(self):
        """Test validation of valid config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("""
name: Test Config
version: 1.0
schema: v1
models:
  - name: test-model
    provider: anthropic
    model: claude-3-5-sonnet-20241022
    roles: [chat]
mcpServers: []
""")

            issues = validate_continue_config(config_file)

            assert len(issues) == 0

    def test_validate_missing_file(self):
        """Test validation of missing file."""
        issues = validate_continue_config(Path("/nonexistent/config.yaml"))

        assert len(issues) > 0
        assert any("not found" in issue for issue in issues)

    def test_validate_invalid_yaml(self):
        """Test validation of invalid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("invalid: yaml: content: [")

            issues = validate_continue_config(config_file)

            assert len(issues) > 0
            assert any("Invalid YAML" in issue for issue in issues)

    def test_validate_missing_models_field(self):
        """Test validation when models field is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("""
name: Test Config
version: 1.0
""")

            issues = validate_continue_config(config_file)

            assert len(issues) > 0
            assert any("Missing 'models'" in issue for issue in issues)

    def test_validate_models_not_list(self):
        """Test validation when models is not a list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("""
name: Test Config
models: not-a-list
""")

            issues = validate_continue_config(config_file)

            assert len(issues) > 0
            assert any("must be a list" in issue for issue in issues)

    def test_validate_model_missing_required_fields(self):
        """Test validation when model entries miss required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("""
name: Test Config
models:
  - name: test-model
    # Missing provider and model
""")

            issues = validate_continue_config(config_file)

            assert len(issues) > 0
            assert any("missing required field" in issue.lower() for issue in issues)

    def test_validate_model_not_dict(self):
        """Test validation when model entry is not a dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "config.yaml"
            config_file.write_text("""
name: Test Config
models:
  - just-a-string
""")

            issues = validate_continue_config(config_file)

            assert len(issues) > 0
            assert any("must be a dictionary" in issue for issue in issues)
