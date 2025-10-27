# Dolphin Configuration System Specification

## Overview

This document specifies the new configuration system for Dolphin that follows a clear precedence order and provides a unified approach to configuration management across the entire application.

## Configuration Precedence Order

The configuration system follows this precedence order (highest to lowest):

1. **Environment Variables** - For complex CLI or debugging
2. **Repository-specific** - Settings in `.dolphin/config.toml` within specific repos
3. **System-wide** - Settings in `~/.dolphin/config.toml`
4. **Defaults** - Mastered in `config/defaults.toml` within source code

## Architecture

### File Structure

```
dolphin/
├── config/
│   └── defaults.toml                    # Default configuration (lowest priority)
├── src/
│   └── dolphin/
│       └── config/
│           ├── __init__.py              # Configuration loading entry point
│           ├── loader.py                # Configuration merger and loader
│           ├── validator.py             # Configuration validation
│           └── environment.py           # Environment variable parsing
├── .dolphin/
│   └── config.toml                      # Repository-specific config
└── ~/.dolphin/
    └── config.toml                      # System-wide config
```

### Configuration Schema

#### defaults.toml (Source Code Defaults)

```toml
# Dolphin Default Configuration
# =============================

[storage]
store_root = "~/.dolphin/knowledge_store"
cache_dir = "~/.dolphin/cache"

[server]
endpoint = "127.0.0.1:7777"
max_connections = 10
timeout_seconds = 30

[chunking]
default_window_size = 350
overlap_pct = 0.10
max_chunk_size = 1000

[chunking.per_language]
python = 512
javascript = 350
typescript = 350
typescriptreact = 350
java = 512
cpp = 512
c = 512
go = 400
rust = 400
markdown = 256
text = 256
json = 128
toml = 128
yaml = 128

[embeddings]
model = "text-embedding-3-small"
default_embed_model = "small"
concurrency = 3
per_session_spend_cap_usd = 10.0

[tokenizer]
encoding = "cl100k_base"

[retrieval]
score_cutoff = 0.15
top_k = 8
max_snippet_tokens = 240

[personas]
default_persona = "deep-dive"
auto_switch = true

[ui]
theme = "dark"
compact_mode = false
show_token_counts = true

[logging]
level = "INFO"
format = "json"
enable_file_logging = false
log_file = "~/.dolphin/dolphin.log"

# Language mappings (existing from current config)
[languages]
# ... existing language mappings from current .dolphin/config.toml ...
```

### Environment Variable Mapping

Environment variables follow the pattern: `DOLPHIN_{SECTION}_{KEY}`

Examples:
- `DOLPHIN_SERVER_ENDPOINT=localhost:8888`
- `DOLPHIN_CHUNKING_DEFAULT_WINDOW_SIZE=400`
- `DOLPHIN_EMBEDDINGS_MODEL=text-embedding-3-large`
- `DOLPHIN_PERSONAS_DEFAULT_PERSONA=journalist`

## Implementation Plan

### Phase 1: Core Configuration Infrastructure

#### 1.1 Create Configuration Directory Structure
- Create `config/defaults.toml` with comprehensive defaults
- Create `src/dolphin/config/` package structure
- Migrate existing language mappings from current config

#### 1.2 Implement Configuration Loader
- Configuration merger with precedence logic
- Path resolution for system-wide and repo-specific configs
- Environment variable parsing integration

**Key Files:**
- `src/dolphin/config/loader.py` - Main configuration loading logic
- `src/dolphin/config/__init__.py` - Public API exports

#### 1.3 Create Configuration Validator
- Schema validation for all configuration sections
- Type checking for numeric values
- Path validation for directory settings

**Key Files:**
- `src/dolphin/config/validator.py` - Validation logic

### Phase 2: Environment Variable Integration

#### 2.1 Environment Variable Parser
- Parse `DOLPHIN_*` environment variables
- Convert to appropriate TOML structure
- Handle type conversion (string to int/bool)

**Key Files:**
- `src/dolphin/config/environment.py` - Environment variable parsing

#### 2.2 CLI Argument Support
- Command-line flag overrides
- Integration with existing Just commands
- Configuration validation at startup

### Phase 3: Backward Compatibility & Migration

#### 3.1 Migrate Existing Configuration
- Convert current `.dolphin/config.toml` to new schema
- Handle `chunking_config.toml` migration
- Provide deprecation warnings for old configuration files

#### 3.2 Update Existing Code
- Replace direct config file reading with new loader
- Update tests to use new configuration system
- Ensure all components use unified config

**Files to Update:**
- `src/pb_kb/chunkers/repo_config.py`
- `personas/scripts/persona_utils.py`
- All chunker implementations
- Test files

### Phase 4: Enhanced Features

#### 4.1 Advanced Configuration Features
- Configuration diff viewing
- Configuration template generation
- Configuration documentation generation
- Configuration validation at application startup

## Technical Implementation Details

### Configuration Loader Implementation

```python
# src/dolphin/config/loader.py
class ConfigLoader:
    def __init__(self):
        self.defaults_path = "config/defaults.toml"
        self.system_config_path = "~/.dolphin/config.toml"
        self.repo_config_path = ".dolphin/config.toml"
    
    def load_config(self, repo_path: Optional[Path] = None) -> Dict:
        # 1. Load defaults from source code
        config = self._load_defaults()
        
        # 2. Merge system-wide config
        config = self._merge_config(config, self._resolve_path(self.system_config_path))
        
        # 3. Merge repo-specific config
        if repo_path:
            repo_config = repo_path / self.repo_config_path
            config = self._merge_config(config, repo_config)
        
        # 4. Apply environment variables (highest priority)
        config = self._apply_env_vars(config)
        
        return config
    
    def _merge_config(self, base: Dict, overlay_path: Path) -> Dict:
        # Deep merge implementation preserving nested structures
        pass
```

### Environment Variable Parser

```python
# src/dolphin/config/environment.py
def parse_env_vars() -> Dict:
    env_config = {}
    for key, value in os.environ.items():
        if key.startswith("DOLPHIN_"):
            # Convert DOLPHIN_SERVER_ENDPOINT to server.endpoint
            path = key[8:].lower().split('_')
            current = env_config
            for part in path[:-1]:
                current = current.setdefault(part, {})
            current[path[-1]] = _convert_type(value)
    return env_config

def _convert_type(value: str) -> Any:
    # Handle type conversion for environment variables
    if value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value
```

### Public API

```python
# src/dolphin/config/__init__.py
from .loader import ConfigLoader

def get_config(repo_path: Optional[Path] = None) -> Dict:
    """Get merged configuration with proper precedence"""
    loader = ConfigLoader()
    return loader.load_config(repo_path)

def validate_config(config: Dict) -> bool:
    """Validate configuration against schema"""
    from .validator import ConfigValidator
    return ConfigValidator().validate(config)
```

## Migration Strategy

### Step 1: Parallel Operation
- New configuration system runs alongside existing
- Both systems active during transition period
- Log warnings when using deprecated config files

### Step 2: Gradual Migration
- Migrate components one by one to new system
- Update tests to use new configuration API
- Maintain backward compatibility wrappers

### Step 3: Cleanup
- Remove legacy configuration support
- Remove deprecated configuration files
- Update documentation to reflect new system

## Testing Strategy

### Unit Tests
- Configuration merging precedence tests
- Environment variable parsing tests
- Validation tests for configuration schema
- Path resolution tests

### Integration Tests
- End-to-end configuration loading tests
- Backward compatibility tests
- Migration path validation tests

### Test Files to Create
- `tests/test_config_loader.py`
- `tests/test_config_validator.py`
- `tests/test_environment_parser.py`
- `tests/test_config_migration.py`

## Backward Compatibility

### Deprecation Timeline
- **Phase 1**: Warn about deprecated config files but continue support
- **Phase 2**: Log warnings and suggest migration
- **Phase 3**: Remove support for old configuration files

### Migration Path
1. Existing `.dolphin/config.toml` will be automatically migrated
2. `chunking_config.toml` settings will be merged into new config
3. Environment variables will take precedence during migration

## File Touchpoints

### New Files to Create
- `config/defaults.toml`
- `src/dolphin/config/__init__.py`
- `src/dolphin/config/loader.py`
- `src/dolphin/config/validator.py`
- `src/dolphin/config/environment.py`

### Existing Files to Update
- `src/pb_kb/chunkers/repo_config.py` - Migrate to new config system
- `personas/scripts/persona_utils.py` - Use new config for persona defaults
- `tests/test_repo_config.py` - Update tests for new system
- All chunker implementations - Use unified config
- `Justfile` - Add configuration management commands

### Configuration Management Commands
```bash
# View current effective configuration
just config-show

# Validate configuration
just config-validate

# Generate configuration template
just config-template

# View configuration precedence
just config-precedence
```

## Success Criteria

- [ ] All configuration sources follow specified precedence order
- [ ] Backward compatibility maintained during migration
- [ ] All existing tests pass with new configuration system
- [ ] New configuration validation prevents invalid settings
- [ ] Environment variables properly override file-based config
- [ ] Performance of configuration loading meets requirements
- [ ] Comprehensive test coverage for configuration system
- [ ] Documentation updated to reflect new configuration approach

## Risk Mitigation

- Maintain rollback capability during migration
- Comprehensive testing before each phase
- Gradual rollout to catch issues early
- Clear error messages for configuration issues
- Automated validation of configuration changes

This specification provides a clear roadmap for implementing the new configuration system while maintaining backward compatibility and providing a clean migration path from the current implementation.