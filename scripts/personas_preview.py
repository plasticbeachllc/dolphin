from __future__ import annotations

import argparse
import sys
from pathlib import Path

from persona_utils import (
    PersonaError,
    compile_system_message,
    iter_persona_dirs,
    load_persona,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview compiled systemMessage output for a persona",
    )
    parser.add_argument(
        "--personas",
        default="personas",
        help="Path to the personas root directory (default: personas)",
    )
    parser.add_argument(
        "--id",
        help="Persona id (folder name) to preview",
    )
    parser.add_argument(
        "--overlay",
        help="Optional path to an overlay file appended after guardrails",
    )
    parser.add_argument(
        "--overlay-text",
        help="Inline overlay text appended after guardrails (mutually exclusive with --overlay)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available personas and exit",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the compiled systemMessage after the summary",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat validation warnings as errors",
    )
    return parser.parse_args()


def read_overlay(args: argparse.Namespace) -> str:
    if args.overlay and args.overlay_text:
        raise PersonaError("Use either --overlay or --overlay-text, not both")

    if args.overlay_text:
        return args.overlay_text

    if args.overlay:
        path = Path(args.overlay)
        if not path.exists():
            raise PersonaError(f"Overlay file '{path}' does not exist")
        if not path.is_file():
            raise PersonaError(f"Overlay path '{path}' is not a file")
        return path.read_text(encoding="utf-8")

    return ""


def list_personas(root: Path) -> None:
    try:
        dirs = list(iter_persona_dirs(root))
    except PersonaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    if not dirs:
        print(f"No personas found in {root}")
        return

    print(f"Personas in {root}:")
    for directory in dirs:
        try:
            persona = load_persona(directory)
        except PersonaError as exc:
            print(f"  - {directory.name}: error ({exc})")
            continue
        print(
            f"  - {persona.id}: {persona.name}"
            f" [{persona.provider_kind}:{persona.provider_model}]"
        )


def main() -> None:
    args = parse_args()
    personas_root = Path(args.personas)

    if args.list:
        list_personas(personas_root)
        return

    if not args.id:
        print("error: --id is required unless --list is used", file=sys.stderr)
        sys.exit(2)

    persona_dir = personas_root / args.id

    try:
        persona = load_persona(persona_dir)
    except PersonaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    if persona.warnings:
        for warning in persona.warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if args.strict:
            sys.exit(2)

    try:
        overlay = read_overlay(args)
    except PersonaError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)

    compiled, info = compile_system_message(
        system=persona.system_text,
        guardrails=persona.guardrails_text,
        overlay=overlay,
        model=persona.provider_model,
        budget=persona.token_budget,
    )

    print(
        f"Persona: {persona.name} ({persona.id})\n"
        f"Provider: {persona.provider_kind}:{persona.provider_model}\n"
        f"Token budget: {persona.token_budget}\n"
        f"Initial tokens: {info['initial_tokens']}\n"
        f"Final tokens: {info['final_tokens']}\n"
    )

    if info["steps"]:
        print("Trim steps:")
        for step in info["steps"]:
            print(f"  - {step['action']}: {step['tokens']} tokens")
    else:
        print("Trim steps: none")

    if args.verbose:
        print("\nCompiled systemMessage:\n")
        print(compiled)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
