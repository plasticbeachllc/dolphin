from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - should be in deps
    raise RuntimeError("PyYAML is required. Install with `uv pip install pyyaml`.") from exc

from .persona_utils import Persona, write_json


class ContinueError(Exception):
    """Raised when Continue configuration generation fails."""


def build_continue_entry(persona: Persona, system_message: str) -> Dict[str, Any]:
    """Build a Continue model entry from a persona."""
    roles = persona.raw.get("continue", {}).get("roles")
    if not roles:
        roles = ["chat", "edit"]
    elif isinstance(roles, str):
        roles = [roles]
    
    entry: Dict[str, Any] = {
        "name": persona.name,
        "title": persona.name,
        "provider": persona.provider_kind,
        "model": persona.provider_model,
        "roles": roles,
        "systemMessage": system_message,
    }

    completion_map = {
        "temperature": "temperature",
        "top_p": "topP",
        "topP": "topP",
        "max_tokens": "maxTokens",
        "maxTokens": "maxTokens",
        "presence_penalty": "presencePenalty",
        "frequency_penalty": "frequencyPenalty",
    }
    default_completion: Dict[str, Any] = {}

    for key, value in persona.params.items():
        if value is None:
            continue
        mapped = completion_map.get(key)
        if mapped:
            default_completion[mapped] = value
        else:
            entry[key] = value

    if default_completion:
        entry["defaultCompletionOptions"] = default_completion

    entry.update(persona.provider_options)
    entry.update(persona.continue_extra)

    if persona.provider_kind.lower() == "openai":
        api_base = str(persona.provider_options.get("apiBase", "")).lower()
        if "deepseek" in api_base:
            api_key = os.getenv("DEEPSEEK_API_KEY")
        else:
            api_key = os.getenv("OPENAI_API_KEY")
    elif persona.provider_kind.lower() == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
    else:
        api_key = None
    
    if api_key is not None:
        entry.setdefault("apiKey", api_key)

    return entry


def write_continue_config(
    personas: List[Persona],
    compiled_messages: Dict[str, str],
    target_dir: Path,
    manifest_file: Path = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """Write Continue configuration files to private directory.
    
    Args:
        personas: List of personas to generate configs for
        compiled_messages: Compiled system messages by persona ID
        target_dir: Target directory for config files (will create .continue-config subdirectory)
        manifest_file: Optional manifest file path
        dry_run: If True, don't write files
    """
    
    # Create .continue-config subdirectory within the target directory
    base_dir = target_dir / ".continue-config"
    output_file = base_dir / "personas_config.yaml"
    
    models = []
    manifest_entries = []

    for persona in sorted(personas, key=lambda p: p.name.lower()):
        system_message = compiled_messages.get(persona.id, "")
        
        # Build Continue entry
        entry = build_continue_entry(persona, system_message)
        models.append(entry)

        manifest_entries.append({
            "id": persona.id,
            "name": persona.name,
            "version": persona.version,
            "provider": persona.provider_kind,
            "model": persona.provider_model,
            "token_budget": persona.token_budget,
            "path": str(persona.path),
            "target_format": "continue"
        })

    # Add default autocomplete model if not present
    has_qwen_autocomplete = any(
        ("autocomplete" in (entry.get("roles") or []))
        or entry.get("model") == "qwen2.5-coder:1.5b"
        for entry in models
    )

    if not has_qwen_autocomplete:
        models.append({
            "name": "qwen2.5-coder:1.5b",
            "title": "qwen2.5-coder:1.5b",
            "provider": "ollama",
            "model": "qwen2.5-coder:1.5b",
            "roles": ["autocomplete", "chat"],
        })

    config_payload = {
        "name": "Dolphin Personas",
        "version": "0.1.1",
        "schema": "v1",
        "models": models,
        "mcpServers": [],
    }
    
    if dry_run:
        return {
            "config_payload": config_payload,
            "manifest_entries": manifest_entries,
            "models_count": len(models),
            "output_file": str(output_file)
        }
    else:
        # Ensure .continue-config directory exists
        base_dir.mkdir(parents=True, exist_ok=True)
        if output_file.exists():
            output_file.unlink()
        output_file.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")
        
        if manifest_file:
            write_json(manifest_file, manifest_entries, dry_run=dry_run)
        
        return {
            "models_count": len(models),
            "output_file": str(output_file),
            "manifest_file": str(manifest_file) if manifest_file else None,
            "config_type": "workspace"
        }


def validate_continue_config(config_path: Path) -> List[str]:
    """Validate a Continue configuration file and return any issues."""
    
    issues = []
    
    if not config_path.exists():
        issues.append(f"Configuration file not found: {config_path}")
        return issues
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        issues.append(f"Invalid YAML in {config_path}: {e}")
        return issues
    except Exception as e:
        issues.append(f"Error reading {config_path}: {e}")
        return issues
    
    # Validate required fields
    if not isinstance(config, dict):
        issues.append(f"Configuration must be a dictionary in {config_path}")
        return issues
        
    if "models" not in config:
        issues.append(f"Missing 'models' field in {config_path}")
        return issues
    
    if not isinstance(config["models"], list):
        issues.append(f"'models' must be a list in {config_path}")
        return issues
    
    # Validate model entries
    for i, model in enumerate(config["models"]):
        if not isinstance(model, dict):
            issues.append(f"Model {i} must be a dictionary in {config_path}")
            continue
            
        required_fields = ["name", "provider", "model"]
        for field in required_fields:
            if field not in model:
                issues.append(f"Model {i} missing required field '{field}' in {config_path}")
    
    return issues