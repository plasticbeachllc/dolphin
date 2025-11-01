from __future__ import annotations

import json
import math
import re
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # Python 3.11+
    import tomllib as _toml_module  # type: ignore[attr-defined]

    def toml_loads(data: str) -> Dict[str, Any]:
        return _toml_module.loads(data)

except ModuleNotFoundError:  # pragma: no cover - fallback for <3.11
    try:
        import tomli as _toml_module  # type: ignore

        def toml_loads(data: str) -> Dict[str, Any]:
            return _toml_module.loads(data)

    except ModuleNotFoundError:

        def toml_loads(data: str) -> Dict[str, Any]:  # type: ignore[misc]
            return _minimal_toml_loads(data)

try:
    import tiktoken  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    tiktoken = None  # type: ignore

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_TOP_LEVEL_KEYS = {
    "persona",
    "provider",
    "params",
    "system",
    "files",
    "continue",
}


class PersonaError(Exception):
    """Raised when a persona definition is invalid."""


@dataclass
class Persona:
    path: Path
    id: str
    name: str
    version: str
    provider_kind: str
    provider_model: str
    params: Dict[str, Any]
    token_budget: int
    trim_policy: str
    system_text: str
    provider_options: Dict[str, Any]
    continue_extra: Dict[str, Any]
    raw: Dict[str, Any]
    warnings: List[str]


def _strip_inline_comment(value: str) -> str:
    result: List[str] = []
    in_quote = False
    escape = False
    for ch in value:
        if escape:
            result.append(ch)
            escape = False
            continue
        if ch == "\\":
            result.append(ch)
            escape = True
            continue
        if ch == '"':
            in_quote = not in_quote
            result.append(ch)
            continue
        if ch == "#" and not in_quote:
            break
        result.append(ch)
    return "".join(result).strip()


def _parse_simple_value(value: str) -> Any:
    if not value:
        return ""

    lowered = value.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"

    if value.startswith('"') and value.endswith('"') and len(value) >= 2:
        inner = value[1:-1]
        return bytes(inner, "utf-8").decode("unicode_escape")

    try:
        if any(c in value for c in (".", "e", "E")):
            return float(value)
        return int(value)
    except ValueError:
        return value


def _minimal_toml_loads(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    current_table: Dict[str, Any] = result

    lines = text.splitlines()
    idx = 0
    total = len(lines)

    while idx < total:
        raw_line = lines[idx]
        idx += 1
        stripped = raw_line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("[") and stripped.endswith("]"):
            table_name = stripped[1:-1].strip()
            if not table_name:
                raise PersonaError("Empty table name in TOML content")
            current_table = result.setdefault(table_name, {})
            if not isinstance(current_table, dict):
                raise PersonaError(f"Table '{table_name}' redefined as non-table")
            continue

        if "=" not in stripped:
            raise PersonaError(f"Invalid TOML line: {raw_line}")

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()

        if value.startswith('"""'):
            multiline = value[3:]
            lines_buffer: List[str] = []
            terminator = '"""'

            if multiline.endswith(terminator) and not multiline.endswith("\\" + terminator):
                multiline = multiline[:-3]
                if multiline:
                    lines_buffer.append(multiline)
            else:
                if multiline:
                    lines_buffer.append(multiline)
                finished = False
                while idx < total:
                    next_line = lines[idx]
                    idx += 1
                    if next_line.endswith(terminator) and not next_line.endswith("\\" + terminator):
                        lines_buffer.append(next_line[:-3])
                        finished = True
                        break
                    lines_buffer.append(next_line)
                if not finished:
                    raise PersonaError("Unterminated multi-line string in TOML content")
            parsed_value = "\n".join(lines_buffer)
        else:
            value = _strip_inline_comment(value)
            parsed_value = _parse_simple_value(value)

        current_table[key] = parsed_value

    return result


def count_tokens(text: str, model: Optional[str] = None) -> int:
    """Estimate token count for the given text and optional model identifier."""

    if not text:
        return 0

    if tiktoken and model:
        try:
            encoder = tiktoken.encoding_for_model(model)
        except Exception:
            try:
                encoder = tiktoken.get_encoding("cl100k_base")
            except Exception:
                encoder = None
        if encoder:
            return len(encoder.encode(text))

    # Fallback heuristic: ~4 characters per token
    return math.ceil(len(text) / 4)


def _normalize_block(text: str) -> str:
    """Normalize line endings and trailing whitespace while preserving blank lines."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    cleaned = [line.rstrip() for line in lines]
    return "\n".join(cleaned).strip("\n")


def _join_sections(system: str, guardrails: str = "", overlay: str = "") -> str:
    parts: List[str] = []
    if system:
        parts.append(system.strip())
    if guardrails:
        parts.append("— Guardrails —\n" + guardrails.strip())
    if overlay:
        parts.append("— Overlay —\n" + overlay.strip())
    compiled = "\n\n".join(parts).strip()
    return (compiled + "\n") if compiled else ""


def _guardrails_skeleton(guardrails: str) -> str:
    """Reduce guardrails content to a compact skeleton (first + key bullet + last)."""

    if not guardrails:
        return guardrails

    lines = [ln for ln in guardrails.splitlines() if ln.strip()]
    if len(lines) <= 3:
        return guardrails

    header = lines[0]
    bullet_lines = [ln for ln in lines[1:] if ln.lstrip().startswith("-")]
    skeleton: List[str] = [header]

    if bullet_lines:
        skeleton.append(bullet_lines[0])
        if len(bullet_lines) > 1:
            skeleton.append(bullet_lines[-1])
    else:
        skeleton.append(lines[-1])

    return "\n".join(dict.fromkeys(skeleton))


def _truncate_system_to_budget(
    system: str,
    guardrails: str,
    overlay: str,
    model: Optional[str],
    budget: int,
) -> Tuple[str, int]:
    """Binary search over character count to fit within the budget."""

    low, high = 0, len(system)
    best_text = system
    best_tokens = count_tokens(_join_sections(system, guardrails, overlay), model)

    while low <= high:
        mid = (low + high) // 2
        candidate = system[:mid].rstrip()
        compiled = _join_sections(candidate, guardrails, overlay)
        tokens = count_tokens(compiled, model)
        if tokens <= budget:
            best_text = candidate
            best_tokens = tokens
            low = mid + 1
        else:
            high = mid - 1

    return best_text, best_tokens


def compile_system_message(
    *,
    system: str,
    guardrails: str,
    overlay: str,
    model: Optional[str],
    budget: int,
) -> Tuple[str, Dict[str, Any]]:
    """Compile the final systemMessage applying trim tiers as needed."""

    system_norm = _normalize_block(system)
    guardrails_norm = _normalize_block(guardrails) if guardrails else ""
    overlay_norm = _normalize_block(overlay) if overlay else ""

    compiled = _join_sections(system_norm, guardrails_norm, overlay_norm)
    tokens = count_tokens(compiled, model)

    info: Dict[str, Any] = {
        "initial_tokens": tokens,
        "final_tokens": tokens,
        "trimmed": False,
        "steps": [],
        "sections": {
            "guardrails": "full" if guardrails_norm else "absent",
            "overlay": "present" if overlay_norm else "absent",
        },
    }

    if budget <= 0:
        return compiled, info

    current_guardrails = guardrails_norm
    current_overlay = overlay_norm
    current_system = system_norm
    current_tokens = tokens

    if current_tokens > budget:
        info["trimmed"] = True

        if current_overlay:
            current_overlay = ""
            compiled = _join_sections(current_system, current_guardrails, current_overlay)
            current_tokens = count_tokens(compiled, model)
            info["steps"].append({"action": "drop_overlay", "tokens": current_tokens})
            info["sections"]["overlay"] = "dropped"

        if current_tokens > budget and current_guardrails:
            skeleton = _guardrails_skeleton(current_guardrails)
            if skeleton != current_guardrails:
                current_guardrails = skeleton
                compiled = _join_sections(current_system, current_guardrails, current_overlay)
                current_tokens = count_tokens(compiled, model)
                info["steps"].append({"action": "guardrails_skeleton", "tokens": current_tokens})
                info["sections"]["guardrails"] = "skeleton"

        if current_tokens > budget:
            truncated_system, truncated_tokens = _truncate_system_to_budget(
                current_system,
                current_guardrails,
                current_overlay,
                model,
                budget,
            )
            current_system = truncated_system
            compiled = _join_sections(current_system, current_guardrails, current_overlay)
            current_tokens = truncated_tokens
            info["steps"].append({"action": "truncate_system", "tokens": current_tokens})

    info["final_tokens"] = current_tokens
    return compiled, info


def load_persona(persona_dir: Path) -> Persona:
    persona_path = persona_dir / "persona.toml"
    if not persona_path.exists():
        raise PersonaError(f"Missing persona.toml in {persona_dir}")

    try:
        data = toml_loads(persona_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PersonaError(f"Failed to parse {persona_path}: {exc}") from exc

    warnings: List[str] = []

    unknown_keys = set(data.keys()) - ALLOWED_TOP_LEVEL_KEYS
    if unknown_keys:
        warnings.append(
            f"Unknown top-level keys in {persona_path.name}: {', '.join(sorted(unknown_keys))}"
        )

    persona_meta = data.get("persona") or {}
    persona_id = persona_meta.get("id")
    if not persona_id:
        raise PersonaError(f"[persona] id is required in {persona_path}")
    if not SLUG_RE.fullmatch(persona_id):
        raise PersonaError(f"[persona] id '{persona_id}' must match slug pattern {SLUG_RE.pattern}")
    if persona_dir.name != persona_id:
        raise PersonaError(
            f"Persona directory '{persona_dir.name}' must match persona id '{persona_id}'"
        )

    name = persona_meta.get("name")
    if not name:
        raise PersonaError(f"[persona] name is required for {persona_id}")

    version = persona_meta.get("version")
    if not version:
        raise PersonaError(f"[persona] version is required for {persona_id}")

    provider = data.get("provider") or {}
    provider_kind = provider.get("kind")
    provider_model = provider.get("model")
    if not provider_kind or not provider_model:
        raise PersonaError(f"[provider] kind and model are required for {persona_id}")

    provider_options = provider.get("options") or {}
    if not isinstance(provider_options, dict):  # pragma: no cover - defensive
        raise PersonaError(f"[provider.options] must be a table for {persona_id}")

    params = data.get("params") or {}
    if not isinstance(params, dict):  # pragma: no cover - defensive
        raise PersonaError(f"[params] must be a table for {persona_id}")

    system_table = data.get("system") or {}
    token_budget = system_table.get("token_budget", 1200)
    trim_policy = system_table.get("trim_policy", "tiered")
    if token_budget < 200 or token_budget > 8000:
        warnings.append(
            f"token_budget {token_budget} for persona '{persona_id}' is outside 200-8000"
        )

    files = data.get("files") or {}
    system_inline = system_table.get("systemMessage")

    if system_inline and files.get("system"):
        warnings.append(
            f"Persona '{persona_id}' defines both systemMessage and files.system; using inline text"
        )

    if system_inline:
        system_text = str(system_inline)
    else:
        system_file = files.get("system")
        
        # If no specific system file specified, check for common variants
        if not system_file:
            # Try system.md first, then prompt.md
            system_path = persona_dir / "system.md"
            if system_path.exists():
                system_file = "system.md"
            else:
                prompt_path = persona_dir / "prompt.md"
                if prompt_path.exists():
                    system_file = "prompt.md"
                else:
                    raise PersonaError(
                        f"Persona '{persona_id}' system file not found in {persona_dir}. "
                        f"Expected 'system.md' or 'prompt.md'"
                    )
        
    system_path = persona_dir / system_file
    
    # If the explicitly specified file doesn't exist, raise error
    if not system_path.exists():
        raise PersonaError(
            f"Persona '{persona_id}' system file '{system_file}' not found in {persona_dir}"
        )
    
    system_text = system_path.read_text(encoding="utf-8")

    continue_table = data.get("continue") or {}
    continue_extra = continue_table.get("extra") or {}
    if not isinstance(continue_extra, dict):  # pragma: no cover - defensive
        raise PersonaError(f"[continue.extra] must be a table for {persona_id}")

    return Persona(
        path=persona_dir,
        id=persona_id,
        name=name,
        version=version,
        provider_kind=provider_kind,
        provider_model=provider_model,
        params=params,
        token_budget=token_budget,
        trim_policy=trim_policy,
        system_text=system_text,
        provider_options=provider_options,
        continue_extra=continue_extra,
        raw=data,
        warnings=warnings,
    )


def iter_persona_dirs(personas_root: Path) -> Iterable[Path]:
    if not personas_root.exists():
        raise PersonaError(f"Personas root '{personas_root}' does not exist")
    if not personas_root.is_dir():
        raise PersonaError(f"Personas root '{personas_root}' is not a diraectory")
    for candidate in sorted(personas_root.iterdir()):
        if not candidate.is_dir():
            continue
        if candidate.name.startswith(".") or candidate.name.startswith("_"):
            continue
        yield candidate

def ensure_unique_models(personas: Iterable[Persona]) -> None:
    seen: Dict[Tuple[str, str, str], Persona] = {}
    for persona in personas:
        key = (persona.provider_kind, persona.provider_model, persona.id)
        if key in seen:
            raise PersonaError(
                "Duplicate provider/model/id combination for personas "
                f"'{persona.id}' and '{seen[key].id}'"
            )
        seen[key] = persona


# build_continue_entry moved to continue_utils.py


def write_json(path: Path, payload: Any, *, dry_run: bool = False) -> None:
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
