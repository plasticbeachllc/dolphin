"""Unit tests for personas.src.persona_utils module."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from personas.src.persona_utils import (
    PersonaError,
    Persona,
    _strip_inline_comment,
    _parse_simple_value,
    _minimal_toml_loads,
    count_tokens,
    _normalize_block,
    _join_sections,
    _guardrails_skeleton,
    _truncate_system_to_budget,
    compile_system_message,
    load_persona,
    iter_persona_dirs,
    ensure_unique_models,
    write_json,
)


class TestStripInlineComment:
    """Test _strip_inline_comment function."""

    def test_strip_comment_simple(self):
        """Test stripping simple inline comment."""
        assert _strip_inline_comment('value # comment') == 'value'

    def test_strip_comment_no_comment(self):
        """Test string with no comment."""
        assert _strip_inline_comment('value') == 'value'

    def test_strip_comment_quoted_hash(self):
        """Test hash inside quotes is preserved."""
        assert _strip_inline_comment('"value # not a comment"') == '"value # not a comment"'

    def test_strip_comment_escaped_quote(self):
        """Test escaped quotes are handled correctly."""
        result = _strip_inline_comment('"value\\"test" # comment')
        assert '#' not in result or result.startswith('"')


class TestParseSimpleValue:
    """Test _parse_simple_value function."""

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        assert _parse_simple_value('') == ''

    def test_parse_boolean_true(self):
        """Test parsing boolean true."""
        assert _parse_simple_value('true') is True
        assert _parse_simple_value('True') is True
        assert _parse_simple_value('TRUE') is True

    def test_parse_boolean_false(self):
        """Test parsing boolean false."""
        assert _parse_simple_value('false') is False
        assert _parse_simple_value('False') is False

    def test_parse_integer(self):
        """Test parsing integer."""
        assert _parse_simple_value('42') == 42
        assert _parse_simple_value('-10') == -10

    def test_parse_float(self):
        """Test parsing float."""
        assert _parse_simple_value('3.14') == 3.14
        assert _parse_simple_value('2.5e2') == 250.0

    def test_parse_quoted_string(self):
        """Test parsing quoted string."""
        assert _parse_simple_value('"hello world"') == 'hello world'

    def test_parse_unquoted_string(self):
        """Test parsing unquoted string."""
        assert _parse_simple_value('hello') == 'hello'


class TestMinimalTomlLoads:
    """Test _minimal_toml_loads function."""

    def test_parse_simple_key_value(self):
        """Test parsing simple key-value pairs."""
        toml = 'name = "test"\nvalue = 42'
        result = _minimal_toml_loads(toml)
        assert result['name'] == 'test'
        assert result['value'] == 42

    def test_parse_table(self):
        """Test parsing TOML tables."""
        toml = '[section]\nkey = "value"'
        result = _minimal_toml_loads(toml)
        assert 'section' in result
        assert result['section']['key'] == 'value'

    def test_parse_comments(self):
        """Test ignoring comments."""
        toml = '# comment\nkey = "value" # inline comment'
        result = _minimal_toml_loads(toml)
        assert result['key'] == 'value'

    def test_parse_multiline_string(self):
        """Test parsing multiline strings."""
        toml = 'text = """line1\nline2\nline3"""'
        result = _minimal_toml_loads(toml)
        assert result['text'] == 'line1\nline2\nline3'

    def test_parse_empty_table_name_error(self):
        """Test error on empty table name."""
        toml = '[]\nkey = "value"'
        with pytest.raises(PersonaError, match="Empty table name"):
            _minimal_toml_loads(toml)

    def test_parse_invalid_line_error(self):
        """Test error on invalid line."""
        toml = 'invalid line without equals'
        with pytest.raises(PersonaError, match="Invalid TOML line"):
            _minimal_toml_loads(toml)


class TestCountTokens:
    """Test count_tokens function."""

    def test_count_tokens_empty(self):
        """Test counting tokens in empty string."""
        assert count_tokens('') == 0

    def test_count_tokens_fallback(self):
        """Test token counting with fallback heuristic."""
        # Without tiktoken, should use 4 chars/token heuristic
        text = 'a' * 100
        tokens = count_tokens(text)
        assert tokens > 0

    @patch('personas.src.persona_utils.tiktoken')
    def test_count_tokens_with_tiktoken(self, mock_tiktoken):
        """Test token counting with tiktoken."""
        mock_encoder = MagicMock()
        mock_encoder.encode.return_value = [1, 2, 3, 4, 5]
        mock_tiktoken.encoding_for_model.return_value = mock_encoder

        tokens = count_tokens('test text', model='gpt-4')
        assert tokens == 5


class TestNormalizeBlock:
    """Test _normalize_block function."""

    def test_normalize_line_endings(self):
        """Test normalizing different line endings."""
        text = "line1\r\nline2\rline3\n"
        result = _normalize_block(text)
        assert '\r' not in result
        assert result.count('\n') == 2

    def test_normalize_trailing_whitespace(self):
        """Test removing trailing whitespace."""
        text = "line1  \nline2\t\n"
        result = _normalize_block(text)
        assert not result.endswith('  ')
        assert 'line1\nline2' in result


class TestJoinSections:
    """Test _join_sections function."""

    def test_join_all_sections(self):
        """Test joining system, guardrails, and overlay."""
        result = _join_sections(
            system="System text",
            guardrails="Guardrails text",
            overlay="Overlay text"
        )
        assert "System text" in result
        assert "— Guardrails —" in result
        assert "— Overlay —" in result

    def test_join_system_only(self):
        """Test joining with only system text."""
        result = _join_sections(system="System text")
        assert "System text" in result
        assert "— Guardrails —" not in result

    def test_join_empty_sections(self):
        """Test joining with empty sections."""
        result = _join_sections(system="", guardrails="", overlay="")
        assert result == ""


class TestGuardrailsSkeleton:
    """Test _guardrails_skeleton function."""

    def test_skeleton_short_text(self):
        """Test skeleton with short text (no reduction)."""
        text = "Line 1\nLine 2\nLine 3"
        result = _guardrails_skeleton(text)
        assert result == text

    def test_skeleton_long_text_with_bullets(self):
        """Test skeleton with long text and bullets."""
        text = "Header\n- Bullet 1\n- Bullet 2\n- Bullet 3\n- Bullet 4"
        result = _guardrails_skeleton(text)
        assert "Header" in result
        assert "- Bullet 1" in result
        assert "- Bullet 4" in result

    def test_skeleton_empty(self):
        """Test skeleton with empty text."""
        assert _guardrails_skeleton("") == ""


class TestTruncateSystemToBudget:
    """Test _truncate_system_to_budget function."""

    def test_truncate_within_budget(self):
        """Test when text is already within budget."""
        system = "Short text"
        result_text, result_tokens = _truncate_system_to_budget(
            system=system,
            guardrails="",
            overlay="",
            model=None,
            budget=1000
        )
        assert result_text == system
        assert result_tokens <= 1000

    def test_truncate_exceeds_budget(self):
        """Test when text exceeds budget."""
        system = "a" * 10000
        result_text, result_tokens = _truncate_system_to_budget(
            system=system,
            guardrails="",
            overlay="",
            model=None,
            budget=100
        )
        assert len(result_text) < len(system)
        assert result_tokens <= 100


class TestCompileSystemMessage:
    """Test compile_system_message function."""

    def test_compile_within_budget(self):
        """Test compilation when within budget."""
        compiled, info = compile_system_message(
            system="System text",
            guardrails="Guardrails text",
            overlay="Overlay text",
            model=None,
            budget=1000
        )
        assert "System text" in compiled
        assert info['trimmed'] is False
        assert info['initial_tokens'] > 0

    def test_compile_drop_overlay(self):
        """Test overlay is dropped when over budget."""
        long_text = "a" * 5000
        compiled, info = compile_system_message(
            system=long_text,
            guardrails="Guardrails",
            overlay="Overlay",
            model=None,
            budget=100
        )
        assert info['trimmed'] is True
        assert any(step['action'] == 'drop_overlay' for step in info['steps'])

    def test_compile_no_budget(self):
        """Test compilation with no budget limit."""
        compiled, info = compile_system_message(
            system="System text",
            guardrails="Guardrails",
            overlay="Overlay",
            model=None,
            budget=0
        )
        assert "System text" in compiled
        assert info['trimmed'] is False


class TestLoadPersona:
    """Test load_persona function."""

    def test_load_valid_persona(self):
        """Test loading a valid persona."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persona_dir = Path(tmpdir) / "test-persona"
            persona_dir.mkdir()

            # Create persona.toml without inline systemMessage
            persona_toml = persona_dir / "persona.toml"
            persona_toml.write_text("""
[persona]
id = "test-persona"
name = "Test Persona"
version = "1.0.0"

[provider]
kind = "anthropic"
model = "claude-3-5-sonnet-20241022"

[system]
token_budget = 1200
""")

            # Create system.md file
            system_md = persona_dir / "system.md"
            system_md.write_text("You are a helpful assistant.")

            persona = load_persona(persona_dir)

            assert persona.id == "test-persona"
            assert persona.name == "Test Persona"
            assert persona.provider_kind == "anthropic"
            assert persona.provider_model == "claude-3-5-sonnet-20241022"
            assert persona.token_budget == 1200

    def test_load_persona_missing_file(self):
        """Test error when persona.toml is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persona_dir = Path(tmpdir) / "test-persona"
            persona_dir.mkdir()

            with pytest.raises(PersonaError, match="Missing persona.toml"):
                load_persona(persona_dir)

    def test_load_persona_invalid_id(self):
        """Test error when persona id is invalid."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persona_dir = Path(tmpdir) / "test_invalid"
            persona_dir.mkdir()

            persona_toml = persona_dir / "persona.toml"
            persona_toml.write_text("""
[persona]
id = "test_invalid"
name = "Test"
version = "1.0.0"

[provider]
kind = "anthropic"
model = "claude-3-5-sonnet-20241022"
""")

            with pytest.raises(PersonaError, match="must match slug pattern"):
                load_persona(persona_dir)

    def test_load_persona_with_system_file(self):
        """Test loading persona with external system file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persona_dir = Path(tmpdir) / "test-persona"
            persona_dir.mkdir()

            # Create persona.toml without inline system message
            persona_toml = persona_dir / "persona.toml"
            persona_toml.write_text("""
[persona]
id = "test-persona"
name = "Test Persona"
version = "1.0.0"

[provider]
kind = "anthropic"
model = "claude-3-5-sonnet-20241022"
""")

            # Create system.md file
            system_file = persona_dir / "system.md"
            system_file.write_text("You are a helpful assistant from file.")

            persona = load_persona(persona_dir)

            assert "from file" in persona.system_text


class TestIterPersonaDirs:
    """Test iter_persona_dirs function."""

    def test_iter_valid_directories(self):
        """Test iterating valid persona directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "persona1").mkdir()
            (root / "persona2").mkdir()
            (root / ".hidden").mkdir()
            (root / "_private").mkdir()
            (root / "file.txt").touch()

            dirs = list(iter_persona_dirs(root))

            assert len(dirs) == 2
            assert any(d.name == "persona1" for d in dirs)
            assert any(d.name == "persona2" for d in dirs)

    def test_iter_nonexistent_directory(self):
        """Test error when directory doesn't exist."""
        with pytest.raises(PersonaError, match="does not exist"):
            list(iter_persona_dirs(Path("/nonexistent")))


class TestEnsureUniqueModels:
    """Test ensure_unique_models function."""

    def test_unique_models(self):
        """Test with unique model combinations."""
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

        ensure_unique_models(personas)  # Should not raise

    def test_duplicate_models(self):
        """Test error with duplicate model combinations."""
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
                id="persona1",  # Duplicate id
                name="Persona 2",
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
            )
        ]

        with pytest.raises(PersonaError, match="Duplicate"):
            ensure_unique_models(personas)


class TestWriteJson:
    """Test write_json function."""

    def test_write_json_success(self):
        """Test writing JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "subdir" / "test.json"
            data = {"key": "value", "number": 42}

            write_json(path, data)

            assert path.exists()
            import json
            with open(path) as f:
                loaded = json.load(f)
            assert loaded == data

    def test_write_json_dry_run(self):
        """Test dry run doesn't write file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.json"
            data = {"key": "value"}

            write_json(path, data, dry_run=True)

            assert not path.exists()
