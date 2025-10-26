from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from persona_utils import (
    Persona,
    PersonaError,
    build_continue_entry,
    compile_system_message,
    ensure_unique_models,
    iter_persona_dirs,
    load_persona,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Continue config from persona definitions",
    )
    parser.add_argument(
        "--personas",
        default="personas",
        help="Path to the personas root directory (default: personas)",
    )
    parser.add_argument(
        "--out",
        default=".continue/config.json",
        help="Continue config output path (default: .continue/config.json)",
    )
    parser.add_argument(
        "--manifest",
        help="Optional manifest output path (JSON)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without writing output files",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat validation warnings as errors",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print compiled systemMessage text for each persona",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    personas_root = Path(args.personas)

    personas: List[Persona] = []
    warnings: List[str] = []

    try:
        directories = list(iter_persona_dirs(personas_root))
    except PersonaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    if not directories:
        print(f"error: no personas found in {personas_root}", file=sys.stderr)
        sys.exit(2)

    for directory in directories:
        try:
            persona = load_persona(directory)
        except PersonaError as exc:
            print(f"error: failed to load persona '{directory.name}': {exc}", file=sys.stderr)
            sys.exit(2)
        personas.append(persona)
        for warning in persona.warnings:
            message = f"warning ({persona.id}): {warning}"
            warnings.append(message)
            print(message, file=sys.stderr)

    if warnings and args.strict:
        sys.exit(2)

    try:
        ensure_unique_models(personas)
    except PersonaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    models = []
    manifest_entries = []

    for persona in sorted(personas, key=lambda p: p.name.lower()):
        compiled, info = compile_system_message(
            system=persona.system_text,
            guardrails=persona.guardrails_text,
            overlay="",
            model=persona.provider_model,
            budget=persona.token_budget,
        )
        entry = build_continue_entry(persona, compiled)
        models.append(entry)

        manifest_entries.append(
            {
                "id": persona.id,
                "name": persona.name,
                "version": persona.version,
                "provider": persona.provider_kind,
                "model": persona.provider_model,
                "token_budget": persona.token_budget,
                "path": str(persona.path),
                "trimmed": info["trimmed"],
            }
        )

        summary = (
            f"[{persona.id}] {persona.name} -> {persona.provider_kind}:{persona.provider_model} "
            f"{info['final_tokens']}/{persona.token_budget} tokens"
        )
        if info["steps"]:
            actions = ", ".join(step["action"] for step in info["steps"])
            summary += f" (trimmed: {actions})"
        print(summary)

        if args.verbose:
            print("--- compiled systemMessage ---")
            print(compiled)
            print("--- end systemMessage ---\n")

    config_payload = {"models": models}
    write_json(Path(args.out), config_payload, dry_run=args.dry_run)
    if args.manifest:
        write_json(Path(args.manifest), manifest_entries, dry_run=args.dry_run)

    action = "(dry-run) " if args.dry_run else ""
    print(f"{action}Wrote {len(models)} models to {args.out}")
    if args.manifest:
        print(f"{action}Wrote manifest to {args.manifest}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
