from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .persona_utils import Persona, count_tokens


class KiloCodeError(Exception):
    """Raised when KiloCode configuration generation fails."""


def map_provider_to_kilocode(persona_name: str, persona_config: Dict[str, Any]) -> Dict[str, Any]:
    """Map persona provider configuration to KiloCode format based on official documentation."""
    
    provider_kind = persona_config.get("provider", "").lower()
    provider_model = persona_config.get("model", "")
    api_key = persona_config.get("api_key", "")
    
    # Handle environment variable substitution
    if api_key.startswith("${") and api_key.endswith("}"):
        # Extract environment variable name
        env_var = api_key[2:-1]
        api_key = os.getenv(env_var, api_key)
    
    # Map provider types to KiloCode provider configurations
    if provider_kind == "anthropic":
        config = {
            "id": "default",
            "provider": "anthropic",
            "apiKey": api_key,
            "apiModelId": provider_model
        }
        # Add optional base URL if specified
        if "api_base" in persona_config:
            config["anthropicBaseUrl"] = persona_config["api_base"]
    
    elif provider_kind == "openai":
        # Check if this is actually a custom OpenAI-compatible provider
        base_url = persona_config.get("base_url") or persona_config.get("api_base")
        if base_url:
            config = {
                "id": "default",
                "provider": "openai-native",
                "openAiNativeApiKey": api_key,
                "apiModelId": provider_model,
                "openAiNativeBaseUrl": base_url
            }
        else:
            config = {
                "id": "default",
                "provider": "openai-native",
                "openAiNativeApiKey": api_key,
                "apiModelId": provider_model
            }
    
    elif provider_kind == "openrouter":
        config = {
            "id": "default",
            "provider": "openrouter",
            "openRouterApiKey": api_key,
            "openRouterModelId": provider_model
        }
    
    elif provider_kind == "groq":
        config = {
            "id": "default",
            "provider": "groq",
            "groqApiKey": api_key,
            "apiModelId": provider_model
        }
    
    elif provider_kind == "deepseek":
        config = {
            "id": "default",
            "provider": "deepseek",
            "deepSeekApiKey": api_key,
            "apiModelId": provider_model
        }
    
    elif provider_kind == "gemini":
        config = {
            "id": "default",
            "provider": "gemini",
            "geminiApiKey": api_key,
            "apiModelId": provider_model
        }
    
    elif provider_kind == "ollama":
        base_url = persona_config.get("base_url") or persona_config.get("api_base", "http://localhost:11434")
        config = {
            "id": "default",
            "provider": "ollama",
            "ollamaBaseUrl": base_url,
            "ollamaModelId": provider_model
        }
        # Add API key if specified
        if "api_key" in persona_config:
            config["ollamaApiKey"] = persona_config["api_key"]
    
    else:
        # Generic fallback for unknown providers
        config = {
            "id": "default",
            "provider": provider_kind,
            "apiModelId": provider_model
        }
        # Add common API key pattern
        if api_key:
            config["apiKey"] = api_key
        
        # Add base URL if specified
        base_url = persona_config.get("base_url") or persona_config.get("api_base")
        if base_url:
            config[f"{provider_kind}BaseUrl"] = base_url
    
    return config


def build_kilocode_mode_config(persona: Persona, system_message: str) -> Dict[str, Any]:
    """Build a KiloCode Custom Mode configuration from a persona."""
    
    # Convert persona to persona_config format for mapping
    persona_config = {
        "provider": persona.provider_kind,
        "model": persona.provider_model,
        "api_key": getattr(persona, 'api_key', ''),
    }
    
    # Add provider options if they exist
    if persona.provider_options:
        persona_config.update(persona.provider_options)
    
    # Map provider configuration
    provider_config = map_provider_to_kilocode(
        persona.id,
        persona_config
    )
    
    # Build completion parameters using the documented parameter names
    completion_params = {}
    param_mapping = {
        "temperature": "temperature",
        "top_p": "top_p",
        "topP": "top_p",
        "max_tokens": "max_tokens",
        "maxTokens": "max_tokens",
        "presence_penalty": "presence_penalty",
        "frequency_penalty": "frequency_penalty"
    }
    
    for key, value in persona.params.items():
        if value is not None and key in param_mapping:
            completion_params[param_mapping[key]] = value
    
    # Build the mode configuration following KiloCode Custom Modes format
    # The top level should be the provider configuration itself
    mode_config = provider_config.copy()
    
    # Add KiloCode Custom Mode specific fields
    mode_config.update(completion_params)
    mode_config.update({
        "name": persona.name,
        "slug": persona.id,
        "description": f"{persona.name} persona - {persona.provider_kind}:{persona.provider_model}",
        "version": persona.version,
        "instructions": system_message,  # Inline instructions
    })
    
    # Add provider options to metadata for reference (avoiding circular references)
    if persona.provider_options:
        # Create a clean copy of provider options without circular references
        clean_options = {}
        for key, value in persona.provider_options.items():
            # Skip self-referential keys
            if key != "provider_options" and not (isinstance(value, dict) and value is persona.provider_options):
                clean_options[key] = value
        mode_config["metadata"] = clean_options
    
    return mode_config


def generate_kilocode_instructions(
    system_text: str, 
    guardrails: str = "", 
    persona_name: str = ""
) -> str:
    """Generate KiloCode Custom Instructions from persona system text."""
    
    instructions = []
    
    # Add persona header
    if persona_name:
        instructions.append(f"# {persona_name} Mode")
        instructions.append("")
    
    # Add main system instructions
    if system_text:
        instructions.append(system_text.strip())
        instructions.append("")
    
    # Add guardrails as rules section
    if guardrails:
        instructions.append("## Global Guidelines")
        instructions.append("")
        instructions.append(guardrails.strip())
    
    return "\n".join(instructions)


def generate_kilocode_workflow(personas: List[Persona]) -> str:
    """Generate KiloCode workflow file with slash commands for persona switching."""
    
    workflow_content = [
        "# Persona Switching Workflows",
        "",
        "These slash commands allow quick switching between different persona modes.",
        ""
    ]
    
    for persona in sorted(personas, key=lambda p: p.name.lower()):
        workflow_content.extend([
            f"## /{persona.id}",
            f"Switch to {persona.name} mode ({persona.provider_kind}:{persona.provider_model})",
            "",
            f"**Usage**: `/{persona.id}`",
            f"**Description**: {persona.name} - AI assistant optimized for specific tasks",
            "",
            "```markdown",
            f"Please switch to {persona.name} mode and continue with these capabilities:",
            "",
            "- Provider: " + f"{persona.provider_kind}:{persona.provider_model}",
            "- Token Budget: " + str(persona.token_budget),
            "- Parameters: " + str(persona.params) if persona.params else "Default",
            "```",
            "",
            "---",
            ""
        ])
    
    return "\n".join(workflow_content)


def write_kilocode_config(
    personas: List[Persona],
    compiled_messages: Dict[str, str],
    guardrails: str,
    target_dir: Path,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Write KiloCode configuration files to private directory.
    
    Args:
        personas: List of personas to generate configs for
        compiled_messages: Compiled system messages by persona ID
        guardrails: Shared guardrails text
        target_dir: Target directory for config files (will create .kilocode-config subdirectory)
        dry_run: If True, don't write files
    """
    
    # Create .kilocode-config subdirectory within the target directory
    base_dir = target_dir / ".kilocode-config"
    modes_dir = base_dir / "modes"
    workflows_dir = base_dir / "workflows"
    
    if not dry_run:
        modes_dir.mkdir(parents=True, exist_ok=True)
        workflows_dir.mkdir(parents=True, exist_ok=True)
    
    generated_files = []
    
    # Generate individual mode configurations with inline instructions
    for persona in personas:
        system_message = compiled_messages.get(persona.id, "")
        
        # Generate mode config with inline instructions
        mode_config = build_kilocode_mode_config(persona, system_message)
        mode_file = modes_dir / f"{persona.id}.json"
        
        if not dry_run:
            mode_file.write_text(
                json.dumps(mode_config, indent=2) + "\n",
                encoding="utf-8"
            )
        generated_files.append(str(mode_file))
    
    # Generate workflows
    workflow_content = generate_kilocode_workflow(personas)
    workflow_file = workflows_dir / "persona-workflows.md"
    
    if not dry_run:
        workflow_file.write_text(workflow_content, encoding="utf-8")
    generated_files.append(str(workflow_file))
    
    # Generate global rules from guardrails
    if guardrails:
        rules_dir = base_dir / "rules"
        if not dry_run:
            rules_dir.mkdir(parents=True, exist_ok=True)
        
        global_rules = f"# Global Guardrails\n\n{guardrails}"
        rules_file = rules_dir / "global-guardrails.md"
        
        if not dry_run:
            rules_file.write_text(global_rules, encoding="utf-8")
        generated_files.append(str(rules_file))
    
    # Generate master configuration index for repository KiloCode setup
    master_config = {
        "name": "Dolphin Personas (KiloCode)",
        "version": "1.0.0",
        "description": "Migrated persona configurations for KiloCode Custom Modes",
        "type": "repository",
        "modes": [
            {
                "id": persona.id,
                "name": persona.name,
                "config_file": f"modes/{persona.id}.json"
            }
            for persona in personas
        ]
    }
    
    # Add workflows and rules only if they exist
    if not dry_run:
        workflow_path = base_dir / "workflows" / "persona-workflows.md"
        if workflow_path.exists():
            master_config["workflows"] = ["workflows/persona-workflows.md"]
        
        if guardrails:
            rules_path = base_dir / "rules" / "global-guardrails.md"
            if rules_path.exists():
                master_config["rules"] = ["rules/global-guardrails.md"]
    else:
        # For dry run, assume files would be created
        master_config["workflows"] = ["workflows/persona-workflows.md"]
        if guardrails:
            master_config["rules"] = ["rules/global-guardrails.md"]
    
    master_file = base_dir / "config.json"
    if not dry_run:
        master_file.write_text(
            json.dumps(master_config, indent=2) + "\n",
            encoding="utf-8"
        )
    generated_files.append(str(master_file))
    
    return {
        "generated_files": generated_files,
        "modes_count": len(personas),
        "output_directory": str(base_dir),
        "config_type": "repository"
    }


def validate_kilocode_config(config_or_path) -> List[str]:
    """Validate a KiloCode configuration file and return any issues.
    
    Args:
        config_or_path: Either a Path to a config file or a dict config object
    """
    
    issues = []
    
    # Handle both dict and Path inputs
    if isinstance(config_or_path, dict):
        config = config_or_path
        config_path = None
    else:
        config_path = config_or_path
        if not config_path.exists():
            issues.append(f"Configuration file not found: {config_path}")
            return issues
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            issues.append(f"Invalid JSON in {config_path}: {e}")
            return issues
        except Exception as e:
            issues.append(f"Error reading {config_path}: {e}")
            return issues
    
    # Validate required fields for KiloCode Custom Modes
    if not isinstance(config, dict):
        location = f"in {config_path}" if config_path else ""
        issues.append(f"Configuration must be a dictionary {location}")
        return issues
    
    # For dict validation, check basic required fields
    location = f" in {config_path}" if config_path else ""
    
    # Check if this is a basic provider config (flat structure) or full mode config
    # A flat provider config has id, provider, and apiModelId but no name/slug/instructions
    has_provider_fields = "id" in config and "provider" in config and "apiModelId" in config
    has_mode_fields = "name" in config or "slug" in config or "instructions" in config
    is_flat_provider = has_provider_fields and not has_mode_fields
    
    if is_flat_provider:
        # Validate flat provider configuration
        required_provider_fields = ["id", "provider", "apiModelId"]
        for field in required_provider_fields:
            if field not in config:
                raise KiloCodeError(f"Missing required field '{field}'{location}")
        
        # Check for provider-specific API key field
        provider = config.get("provider", "")
        api_key_fields = [key for key in config.keys() if key.endswith("ApiKey") or key == "apiKey"]
        
        # Some providers like ollama don't require API keys
        if provider not in ["ollama"]:
            if not api_key_fields:
                raise KiloCodeError(f"Missing required field 'apiKey'{location}")
            # Check that at least one API key field is not empty
            has_valid_key = any(config.get(key) for key in api_key_fields)
            if not has_valid_key:
                raise KiloCodeError(f"Missing required field 'apiKey'{location}")
    else:
        # Validate full mode configuration
        required_fields = ["name", "slug", "provider", "instructions"]
        for field in required_fields:
            if field not in config:
                issues.append(f"Missing required field '{field}'{location}")
        
        # Validate provider configuration if present
        if "provider" in config:
            provider = config["provider"]
            if isinstance(provider, dict):
                # Nested provider structure
                if "provider" not in provider:
                    raise KiloCodeError(f"Missing required provider field 'provider'{location}")
                if "apiModelId" not in provider:
                    raise KiloCodeError(f"Missing required provider field 'apiModelId'{location}")
        
        # Validate instructions are not empty
        if "instructions" in config and not config["instructions"].strip():
            issues.append(f"Empty instructions{location}")
        
        # Validate slug format (should be kebab-case)
        if "slug" in config:
            slug = config["slug"]
            if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
                issues.append(f"Invalid slug format '{slug}'{location}. Should be kebab-case.")
    
    return issues