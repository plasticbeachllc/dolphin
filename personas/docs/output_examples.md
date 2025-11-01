# Personas to KiloCode & Continue Migration Guide

This document shows what the generated KiloCode and Continue configuration files will look like after migration from persona TOML definitions.

## KiloCode Configuration (Global Only)

### Directory Structure
```
~/.kilocode/
├── config.json                           # Master configuration index
├── modes/
│   ├── smartest-guy.json                 # Custom Mode configurations (with inline instructions)
│   ├── journalist.json
│   ├── deep-dive.json
│   ├── popeye.json
│   └── big-balls.json
├── workflows/
│   └── persona-workflows.md              # Slash commands for mode switching
└── rules/
    └── global-guardrails.md              # Global rules from shared guardrails
```

**Key Changes from Previous Implementation:**
- Instructions are now embedded directly in mode configuration files
- Provider configurations match official KiloCode schema exactly
- Uses KiloCode Custom Modes format specification

### KiloCode Mode Examples

#### modes/smartest-guy.json (Anthropic Provider)
```json
{
  "name": "Smartest Guy",
  "slug": "smartest-guy",
  "description": "Smartest Guy persona - anthropic:claude-sonnet-4-5-20250929",
  "version": "0.1.0",
  "provider": {
    "id": "default",
    "provider": "anthropic",
    "apiKey": "${ANTHROPIC_API_KEY}",
    "apiModelId": "claude-sonnet-4-5-20250929"
  },
  "instructions": "You are **Smartest Guy**, the most senior software engineer on the team.\n\nYour mandate is to continuously elevate the codebase's **flexibility**, **performance**, and **maintainability** while guiding the team toward best‑practice solutions.\n\n— Guardrails —\n[Global guardrails content from personas/src/system.md]",
  "parameters": {},
  "metadata": {
    "token_budget": 1200,
    "trim_policy": "tiered",
    "original_persona_path": "personas/cast/smartest-guy"
  }
}
```

#### modes/journalist.json (OpenAI with Custom Base URL)
```json
{
  "name": "Journalist",
  "slug": "journalist", 
  "description": "Journalist persona - openai:deepseek-reasoner",
  "version": "0.1.0",
  "provider": {
    "id": "default",
    "provider": "openai-native",
    "openAiNativeApiKey": "${OPENAI_API_KEY}",
    "apiModelId": "deepseek-reasoner",
    "openAiNativeBaseUrl": "https://api.deepseek.com/v1"
  },
  "instructions": "You are a **Journalist** AI assistant specializing in research, fact-checking, and clear communication.\n\n— Guardrails —\n[Global guardrails content]",
  "parameters": {
    "temperature": 0,
    "top_p": 0.95,
    "max_tokens": 4096
  },
  "metadata": {
    "token_budget": 1400,
    "trim_policy": "tiered",
    "original_persona_path": "personas/cast/journalist",
    "provider_options": {
      "apiBase": "https://api.deepseek.com/v1"
    }
  }
}
```

#### modes/big-balls.json (Groq Provider)
```json
{
  "name": "Big Balls",
  "slug": "big-balls",
  "description": "Big Balls persona - groq:llama-3.3-70b-versatile", 
  "version": "0.1.0",
  "provider": {
    "id": "default",
    "provider": "groq",
    "groqApiKey": "${GROQ_API_KEY}",
    "apiModelId": "llama-3.3-70b-versatile"
  },
  "instructions": "You are **Big Balls**, a bold and confident AI assistant that takes decisive action.\n\n— Guardrails —\n[Global guardrails content]",
  "parameters": {
    "temperature": 0.8,
    "max_tokens": 2048
  },
  "metadata": {
    "token_budget": 1000,
    "trim_policy": "tiered",
    "original_persona_path": "personas/cast/big-balls"
  }
}
```

### config.json (Master Index)
```json
{
  "name": "Dolphin Personas (KiloCode)",
  "version": "1.0.0",
  "description": "Migrated persona configurations for KiloCode Custom Modes",
  "type": "global",
  "modes": [
    {
      "id": "big-balls",
      "name": "Big Balls",
      "config_file": "modes/big-balls.json"
    },
    {
      "id": "deep-dive",
      "name": "Deep Dive",
      "config_file": "modes/deep-dive.json"
    },
    {
      "id": "journalist", 
      "name": "Journalist",
      "config_file": "modes/journalist.json"
    },
    {
      "id": "smartest-guy",
      "name": "Smartest Guy", 
      "config_file": "modes/smartest-guy.json"
    }
  ],
  "workflows": ["workflows/persona-workflows.md"],
  "global_rules": ["rules/global-guardrails.md"]
}
```

## Continue Configuration

### Generated Continue Config Structure
The Continue configuration is generated as a single YAML file that can be placed in:
- Local workspace: `./continue-config.yaml`
- Global configuration: `~/.continue/config.yaml`

### Example Continue Configuration Output

#### continue-config.yaml
```yaml
models:
  - title: "Smartest Guy (claude-sonnet-4-5-20250929)"
    provider: anthropic
    model: claude-sonnet-4-5-20250929
    systemMessage: |
      You are **Smartest Guy**, the most senior software engineer on the team.
      
      Your mandate is to continuously elevate the codebase's **flexibility**, **performance**, and **maintainability** while guiding the team toward best‑practice solutions.
      
      — Guardrails —
      [Global guardrails content from personas/src/system.md]
    contextLength: 1200
    completionOptions:
      temperature: 0.7
    apiKey: "${ANTHROPIC_API_KEY}"

  - title: "Journalist (deepseek-reasoner)"  
    provider: openai
    model: deepseek-reasoner
    apiBase: "https://api.deepseek.com/v1"
    systemMessage: |
      You are a **Journalist** AI assistant specializing in research, fact-checking, and clear communication.
      
      — Guardrails —
      [Global guardrails content]
    contextLength: 1400
    completionOptions:
      temperature: 0
      top_p: 0.95
      max_tokens: 4096
    apiKey: "${OPENAI_API_KEY}"

  - title: "Big Balls (llama-3.3-70b-versatile)"
    provider: groq  
    model: llama-3.3-70b-versatile
    systemMessage: |
      You are **Big Balls**, a bold and confident AI assistant that takes decisive action.
      
      — Guardrails —
      [Global guardrails content]
    contextLength: 1000
    completionOptions:
      temperature: 0.8
      max_tokens: 2048
    apiKey: "${GROQ_API_KEY}"

  - title: "Deep Dive (claude-sonnet-4-5-20250929)"
    provider: anthropic
    model: claude-sonnet-4-5-20250929
    systemMessage: |
      You are **Deep Dive**, an AI assistant specialized in thorough analysis and comprehensive exploration.
      
      — Guardrails —
      [Global guardrails content]
    contextLength: 1500
    completionOptions: {}
    apiKey: "${ANTHROPIC_API_KEY}"
```

## Key Differences: KiloCode vs Continue

| Feature | KiloCode Custom Modes | Continue Models |
|---------|----------------------|-----------------|
| **Configuration Type** | Global only (`~/.kilocode/`) | Local or Global |
| **File Structure** | Multiple JSON files + workflows | Single YAML file |
| **Instructions** | Embedded inline in config | Embedded in YAML |
| **Provider Schema** | Official KiloCode schema | Continue provider format |
| **Validation** | Enhanced field validation | Basic YAML validation |
| **Workflows** | Built-in slash commands | Manual model switching |
| **Metadata** | Rich metadata tracking | Basic model info |

## Provider Mapping Comparison

### KiloCode Provider Configurations
```json
// Anthropic
{
  "provider": "anthropic",
  "apiKey": "${ANTHROPIC_API_KEY}",
  "apiModelId": "claude-sonnet-4-5-20250929"
}

// OpenAI with custom base
{
  "provider": "openai-native", 
  "openAiNativeApiKey": "${OPENAI_API_KEY}",
  "apiModelId": "deepseek-reasoner",
  "openAiNativeBaseUrl": "https://api.deepseek.com/v1"
}

// Groq
{
  "provider": "groq",
  "groqApiKey": "${GROQ_API_KEY}", 
  "apiModelId": "llama-3.3-70b-versatile"
}
```

### Continue Provider Configurations
```yaml
# Anthropic
provider: anthropic
model: claude-sonnet-4-5-20250929
apiKey: "${ANTHROPIC_API_KEY}"

# OpenAI with custom base
provider: openai
model: deepseek-reasoner
apiBase: "https://api.deepseek.com/v1"
apiKey: "${OPENAI_API_KEY}"

# Groq  
provider: groq
model: llama-3.3-70b-versatile
apiKey: "${GROQ_API_KEY}"
```

## Usage Instructions

### 1. Generate KiloCode Configuration  
```bash
# Generate KiloCode config (global configuration only)
uv run src.personas generate --kilocode --global

# Or with custom output location (must be global)
uv run src.personas generate --kilocode --global --out ~/.kilocode

# Dry run to preview what will be generated
uv run src.personas generate --kilocode --global --dry-run --verbose
```

### 2. Generate Continue Configuration
```bash
# Generate Continue config (local workspace)
uv run src.personas generate --continue

# Generate Continue config (global)
uv run src.personas generate --continue --global

# With custom output location
uv run src.personas generate --continue --out ./my-continue-config.yaml
```

### 3. Preview and Validation
```bash
# Preview specific persona compilation
uv run src.personas preview --id smartest-guy --verbose

# List all available personas
uv run src.personas preview --list

# Test with overlay for runtime customization
uv run src.personas preview --id journalist --overlay-text "Focus on technical accuracy"
```

## Migration Benefits

### Preserved Functionality
- ✅ All existing Continue generation works unchanged
- ✅ All persona definitions remain compatible
- ✅ Token budgeting and trimming preserved  
- ✅ Multiple provider support maintained
- ✅ Parameter mapping preserved across both formats

### New KiloCode Capabilities
- 🆕 Native KiloCode Custom Modes integration
- 🆕 Slash command workflows for mode switching
- 🆕 Provider configurations following official KiloCode schema
- 🆕 Enhanced validation and error checking
- 🆕 Global configuration management
- 🆕 Rich metadata tracking

### Enhanced Provider Support
- 🆕 **Anthropic**: Direct integration with proper field names
- 🆕 **OpenAI**: Support for both standard and custom base URLs
- 🆕 **Groq**: Native Groq provider configuration
- 🆕 **DeepSeek**: Dedicated DeepSeek provider support
- 🆕 **Ollama**: Local model support with base URL configuration
- 🆕 **Generic Fallback**: Automatic configuration for unknown providers

## Environment Variables Required

Both configurations rely on environment variables for API keys:

```bash
# Core providers
export ANTHROPIC_API_KEY="your-anthropic-key"
export OPENAI_API_KEY="your-openai-key"
export GROQ_API_KEY="your-groq-key"

# Additional providers
export DEEPSEEK_API_KEY="your-deepseek-key"
export GEMINI_API_KEY="your-gemini-key"
export OPENROUTER_API_KEY="your-openrouter-key"

# Usage examples
uv run src.personas generate --kilocode --global
uv run src.personas generate --continue
```

## Validation and Error Handling

### KiloCode Validation
- Validates required fields: `name`, `slug`, `provider`, `instructions`
- Checks provider configuration structure
- Validates slug format (kebab-case)
- Ensures proper KiloCode schema compliance

### Continue Validation  
- Validates YAML syntax
- Checks required model fields
- Validates provider configurations
- Ensures proper Continue schema format

## Future Enhancements
- 🔄 Real-time persona switching in KiloCode UI
- 🔄 Dynamic parameter adjustment
- 🔄 Advanced workflow automation
- 🔄 Integration with KiloCode's model management
- 🔄 Cross-platform persona synchronization