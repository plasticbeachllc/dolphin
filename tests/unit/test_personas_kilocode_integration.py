"""Unit tests for personas <> KiloCode integration.

Tests the integration between personas system and KiloCode Custom Modes,
including provider mapping, configuration generation, and validation.
"""

import tempfile
import json
from pathlib import Path
from unittest.mock import patch, mock_open
import pytest

from personas.src.kilocode_utils import (
    KiloCodeError,
    map_provider_to_kilocode,
    build_kilocode_mode_config,
    write_kilocode_config,
    validate_kilocode_config,
)
from personas.src.persona_utils import PersonaError
import tomllib


class TestProviderMapping:
    """Test provider field mapping to KiloCode schema."""

    def test_anthropic_mapping(self):
        """Test Anthropic provider mapping to KiloCode schema."""
        persona_config = {
            "provider": "anthropic",
            "api_key": "sk-ant-test123",
            "model": "claude-3-5-sonnet-20241022",
            "temperature": 0.7,
            "max_tokens": 4000,
        }
        
        config = map_provider_to_kilocode("test-persona", persona_config)
        
        assert config["provider"] == "anthropic"
        assert config["apiKey"] == "sk-ant-test123"  # Direct value now
        assert config["apiModelId"] == "claude-3-5-sonnet-20241022"
        assert "anthropicBaseUrl" not in config  # Should not be present when not specified
        assert "kilocodeToken" not in config
        assert "openAiNativeApiKey" not in config

    def test_openai_mapping(self):
        """Test OpenAI provider mapping to KiloCode schema."""
        persona_config = {
            "provider": "openai",
            "api_key": "sk-test123",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 4000,
        }
        
        config = map_provider_to_kilocode("test-persona", persona_config)
        
        assert config["provider"] == "openai-native"
        assert config["openAiNativeApiKey"] == "sk-test123"  # Direct value now
        assert config["apiModelId"] == "gpt-4o"
        assert "openAiNativeBaseUrl" not in config  # Should not be present when not specified
        assert "openAiApiKey" not in config

    def test_openai_with_custom_base_url(self):
        """Test OpenAI with custom base URL."""
        persona_config = {
            "provider": "openai",
            "api_key": "sk-test123",
            "model": "gpt-4o",
            "base_url": "https://custom.openai.ai/v1",
        }
        
        config = map_provider_to_kilocode("test-persona", persona_config)
        
        assert config["provider"] == "openai-native"
        assert config["openAiNativeApiKey"] == "sk-test123"
        assert config["apiModelId"] == "gpt-4o"
        assert config["openAiNativeBaseUrl"] == "https://custom.openai.ai/v1"

    def test_groq_mapping(self):
        """Test Groq provider mapping to KiloCode schema."""
        persona_config = {
            "provider": "groq",
            "api_key": "gsk_test123",
            "model": "llama-3.3-70b-versatile",
        }
        
        config = map_provider_to_kilocode("test-persona", persona_config)
        
        assert config["provider"] == "groq"
        assert config["groqApiKey"] == "gsk_test123"
        assert config["apiModelId"] == "llama-3.3-70b-versatile"

    def test_deepseek_mapping(self):
        """Test DeepSeek provider mapping to KiloCode schema."""
        persona_config = {
            "provider": "deepseek",
            "api_key": "sk-deepseek123",
            "model": "deepseek-chat",
        }
        
        config = map_provider_to_kilocode("test-persona", persona_config)
        
        assert config["provider"] == "deepseek"
        assert config["deepSeekApiKey"] == "sk-deepseek123"
        assert config["apiModelId"] == "deepseek-chat"

    def test_gemini_mapping(self):
        """Test Gemini provider mapping to KiloCode schema."""
        persona_config = {
            "provider": "gemini",
            "api_key": "AIza_test123",
            "model": "gemini-2.5-flash-preview-04-17",
        }
        
        config = map_provider_to_kilocode("test-persona", persona_config)
        
        assert config["provider"] == "gemini"
        assert config["geminiApiKey"] == "AIza_test123"
        assert config["apiModelId"] == "gemini-2.5-flash-preview-04-17"
        assert "googleGeminiBaseUrl" not in config

    def test_ollama_mapping(self):
        """Test Ollama provider mapping to KiloCode schema."""
        persona_config = {
            "provider": "ollama",
            "model": "llama3.2",
            "base_url": "http://localhost:11434",
        }
        
        config = map_provider_to_kilocode("test-persona", persona_config)
        
        assert config["provider"] == "ollama"
        assert config["ollamaModelId"] == "llama3.2"
        assert config["ollamaBaseUrl"] == "http://localhost:11434"

    def test_unknown_provider_fallback(self):
        """Test fallback mapping for unknown providers."""
        persona_config = {
            "provider": "unknown_provider",
            "api_key": "test-key",
            "model": "test-model",
        }
        
        config = map_provider_to_kilocode("test-persona", persona_config)
        
        assert config["provider"] == "unknown_provider"
        assert config["apiKey"] == "test-key"
        assert config["apiModelId"] == "test-model"

    def test_environment_variable_substitution(self):
        """Test environment variable substitution in API keys."""
        persona_config = {
            "provider": "anthropic",
            "api_key": "${ANTHROPIC_API_KEY}",
            "model": "claude-3-5-sonnet-20241022",
        }
        
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-sk-ant-123"}):
            config = map_provider_to_kilocode("test-persona", persona_config)
            
            assert config["apiKey"] == "env-sk-ant-123"

    def test_missing_environment_variable(self):
        """Test handling of missing environment variables."""
        persona_config = {
            "provider": "anthropic",
            "api_key": "${MISSING_API_KEY}",
            "model": "claude-3-5-sonnet-20241022",
        }
        
        with patch.dict("os.environ", {}, clear=True):
            config = map_provider_to_kilocode("test-persona", persona_config)
            
            # Should keep the placeholder if env var is missing
            assert config["apiKey"] == "${MISSING_API_KEY}"


class TestConfigurationGeneration:
    """Test KiloCode mode configuration generation."""

    def test_build_minimal_config(self):
        """Test building minimal KiloCode configuration."""
        persona_config = {
            "provider": "anthropic",
            "api_key": "sk-ant-test123",
            "model": "claude-3-5-sonnet-20241022",
        }
        
        config = build_kilocode_mode_config(
            slug="test-persona",
            display_name="Test Persona",
            persona_config=persona_config,
            instructions="Test instructions",
        )
        
        assert config["slug"] == "test-persona"
        assert config["displayName"] == "Test Persona"
        assert config["description"] == "Test instructions"
        assert "provider" in config
        assert config["provider"]["provider"] == "anthropic"
        assert config["provider"]["apiKey"] == "sk-ant-test123"
        assert config["provider"]["apiModelId"] == "claude-3-5-sonnet-20241022"

    def test_build_config_with_parameters(self):
        """Test building config with temperature and max_tokens."""
        persona_config = {
            "provider": "anthropic",
            "api_key": "sk-ant-test123",
            "model": "claude-3-5-sonnet-20241022",
            "temperature": 0.8,
            "max_tokens": 6000,
        }
        
        config = build_kilocode_mode_config(
            slug="test-persona",
            display_name="Test Persona",
            persona_config=persona_config,
            instructions="Test instructions",
        )
        
        assert config["provider"]["temperature"] == 0.8
        assert config["provider"]["maxTokens"] == 6000

    def test_build_config_with_system_prompt(self):
        """Test building config with system prompt content."""
        persona_config = {
            "provider": "anthropic",
            "api_key": "sk-ant-test123",
            "model": "claude-3-5-sonnet-20241022",
        }
        
        system_content = "You are a helpful coding assistant."
        
        config = build_kilocode_mode_config(
            slug="test-persona",
            display_name="Test Persona",
            persona_config=persona_config,
            instructions="Test instructions",
            system_content=system_content,
        )
        
        assert config["systemPrompt"] == "You are a helpful coding assistant."

    def test_slug_validation(self):
        """Test slug format validation."""
        persona_config = {
            "provider": "anthropic",
            "api_key": "sk-ant-test123",
            "model": "claude-3-5-sonnet-20241022",
        }
        
        # Valid slug
        config = build_kilocode_mode_config(
            slug="valid-slug",
            display_name="Test",
            persona_config=persona_config,
            instructions="Test",
        )
        assert config["slug"] == "valid-slug"
        
        # Invalid slug should raise error
        with pytest.raises(KiloCodeError, match="Invalid slug format"):
            build_kilocode_mode_config(
                slug="Invalid Slug!",
                display_name="Test",
                persona_config=persona_config,
                instructions="Test",
            )


class TestConfigurationValidation:
    """Test KiloCode configuration validation."""

    def test_valid_config_validation(self):
        """Test validation of valid configuration."""
        config = {
            "id": "default",
            "provider": "anthropic",
            "apiKey": "sk-ant-test123",
            "apiModelId": "claude-3-5-sonnet-20241022",
        }
        
        validate_kilocode_config(config)  # Should not raise

    def test_missing_required_fields(self):
        """Test validation catches missing required fields."""
        config = {
            "id": "default",
            "provider": "anthropic",
            # Missing apiKey
            "apiModelId": "claude-3-5-sonnet-20241022",
        }
        
        with pytest.raises(KiloCodeError, match="Missing required field"):
            validate_kilocode_config(config)

    def test_invalid_provider_structure(self):
        """Test validation catches invalid provider structure."""
        config = {
            "id": "default",
            "provider": {
                "provider": "anthropic",
                "apiKey": "sk-ant-test123",
                # Missing apiModelId
            },
        }
        
        with pytest.raises(KiloCodeError, match="Missing required provider field"):
            validate_kilocode_config(config)


class TestConfigurationWriting:
    """Test writing KiloCode configuration files."""

    def test_write_global_config(self):
        """Test writing configuration to global location."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                config_dir = Path(tmpdir) / ".kilocode" / "custom-modes"
                config_dir.mkdir(parents=True)
                
                config = {
                    "slug": "test-persona",
                    "displayName": "Test Persona",
                    "description": "Test description",
                    "provider": {
                        "provider": "anthropic",
                        "apiKey": "sk-ant-test123",
                        "apiModelId": "claude-3-5-sonnet-20241022",
                    },
                }
                
                output_path = write_kilocode_config(
                    persona_name="test-persona",
                    persona_config=config,
                    global_config=True,
                )
                
                assert output_path == config_dir / "test-persona.json"
                assert output_path.exists()
                
                # Verify file content
                with open(output_path) as f:
                    written_config = json.load(f)
                    assert written_config["slug"] == "test-persona"
                    assert written_config["provider"]["apiKey"] == "sk-ant-test123"

    def test_write_workspace_config_fails(self):
        """Test that writing workspace config fails as expected."""
        persona_config = {
            "provider": "anthropic",
            "api_key": "sk-ant-test123",
            "model": "claude-3-5-sonnet-20241022",
        }
        
        with pytest.raises(KiloCodeError, match="Global configuration required"):
            write_kilocode_config(
                persona_name="test-persona",
                persona_config=persona_config,
                global_config=False,  # This should fail
            )

    def test_directory_creation(self):
        """Test that directories are created if they don't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                # Directory doesn't exist initially
                config_dir = Path(tmpdir) / ".kilocode" / "custom-modes"
                assert not config_dir.exists()
                
                config = {
                    "slug": "test-persona",
                    "displayName": "Test Persona",
                    "description": "Test description",
                    "provider": {
                        "provider": "anthropic",
                        "apiKey": "sk-ant-test123",
                        "apiModelId": "claude-3-5-sonnet-20241022",
                    },
                }
                
                output_path = write_kilocode_config(
                    persona_name="test-persona",
                    persona_config=config,
                    global_config=True,
                )
                
                assert config_dir.exists()
                assert config_dir.is_dir()
                assert output_path.exists()


class TestPersonaCLIIntegration:
    """Test persona CLI integration with KiloCode."""

    def test_cli_requires_global_flag(self):
        """Test that CLI requires --global flag for KiloCode operations."""
        # Test without --global flag
        with pytest.raises(SystemExit):
            with patch("sys.argv", ["personas", "export", "kilocode", "test-persona"]):
                personas_main()

    def test_cli_with_global_flag(self):
        """Test that CLI works with --global flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("pathlib.Path.home", return_value=Path(tmpdir)):
                with patch("sys.argv", [
                    "personas", "export", "kilocode", "test-persona", "--global"
                ]):
                    with patch("personas.src.persona_utils.get_persona_path") as mock_get_path:
                        # Mock persona file
                        persona_toml = """
[persona]
name = "Test Persona"
provider = "anthropic"
api_key = "sk-ant-test123"
model = "claude-3-5-sonnet-20241022"

[system]
content = "You are a test persona."
"""
                        
                        persona_path = Path(tmpdir) / "test-persona" / "persona.toml"
                        persona_path.parent.mkdir()
                        persona_path.write_text(persona_toml)
                        
                        mock_get_path.return_value = persona_path
                        
                        # Should not raise
                        personas_main()


class TestLegacyMigrationCompatibility:
    """Test compatibility with existing persona configurations."""

    def test_old_toml_format_parsing(self):
        """Test parsing old TOML format with sections."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persona_path = Path(tmpdir) / "test-persona" / "persona.toml"
            persona_path.parent.mkdir()
            
            # Write old format
            persona_content = """
[persona]
name = "Test Persona"
provider = "anthropic"
api_key = "sk-ant-test123"
model = "claude-3-5-sonnet-20241022"
temperature = 0.7

[system]
content = "You are a test persona."

[prompt]
file = "prompt.md"
"""
            persona_path.write_text(persona_content)
            
            # Read and parse
            with open(persona_path, "rb") as f:
                data = tomllib.load(f)
            
            # Should have both persona and system sections
            assert "persona" in data
            assert "system" in data
            assert data["persona"]["provider"] == "anthropic"
            assert data["system"]["content"] == "You are a test persona."

    def test_new_inline_format_parsing(self):
        """Test parsing new inline format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persona_path = Path(tmpdir) / "test-persona" / "persona.toml"
            persona_path.parent.mkdir()
            
            # Write new format
            persona_content = """
name = "Test Persona"
provider = "anthropic"
api_key = "sk-ant-test123"
model = "claude-3-5-sonnet-20241022"
system_content = "You are a test persona."
"""
            persona_path.write_text(persona_content)
            
            # Read and parse
            with open(persona_path, "rb") as f:
                data = tomllib.load(f)
            
            # Should be flat structure
            assert "name" in data
            assert data["name"] == "Test Persona"
            assert data["provider"] == "anthropic"
            assert data["system_content"] == "You are a test persona."


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_invalid_persona_file(self):
        """Test handling of invalid persona TOML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persona_path = Path(tmpdir) / "test-persona" / "persona.toml"
            persona_path.parent.mkdir()
            persona_path.write_text("invalid toml content {{")
            
            with pytest.raises(PersonaError, match="Failed to parse persona file"):
                map_provider_to_kilocode("test-persona", {"provider": "anthropic"})

    def test_missing_required_persona_fields(self):
        """Test handling of missing required persona fields."""
        persona_config = {
            "provider": "anthropic",
            # Missing api_key
            "model": "claude-3-5-sonnet-20241022",
        }
        
        with pytest.raises(KiloCodeError, match="Missing required field"):
            map_provider_to_kilocode("test-persona", persona_config)

    def test_malformed_environment_variable(self):
        """Test handling of malformed environment variable syntax."""
        persona_config = {
            "provider": "anthropic",
            "api_key": "${malformed",
            "model": "claude-3-5-sonnet-20241022",
        }
        
        # Should not crash, just pass through the malformed value
        config = map_provider_to_kilocode("test-persona", persona_config)
        assert config["apiKey"] == "${malformed"


if __name__ == "__main__":
    pytest.main([__file__])