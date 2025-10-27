from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

try:
    import yaml
except ModuleNotFoundError as exc:  # pragma: no cover - should be in deps
    raise RuntimeError("PyYAML is required. Install with `uv pip install pyyaml`." ) from exc

from .persona_utils import (
    Persona,
    PersonaError,
    build_continue_entry,
    compile_system_message,
    ensure_unique_models,
    iter_persona_dirs,
    load_persona,
    write_json,
)

app = typer.Typer(
    add_completion=False,
    help="Persona toolkit for previewing and generating Continue configs.",
)

PERSONAS_SUBDIR = 'cast'
SRC_SUBDIR = 'src'


def _read_overlay(overlay: Optional[Path], overlay_text: Optional[str]) -> str:
    if overlay and overlay_text:
        raise PersonaError("Use either --overlay or --overlay-text, not both")

    if overlay_text:
        return overlay_text

    if overlay:
        if not overlay.exists():
            raise PersonaError(f"Overlay file '{overlay}' does not exist")
        if not overlay.is_file():
            raise PersonaError(f"Overlay path '{overlay}' is not a file")
        return overlay.read_text(encoding="utf-8")

    return ""


def _load_guardrails(personas_root: Path) -> str:
    guardrails_path = personas_root / SRC_SUBDIR / "system.md"
    if not guardrails_path.exists():
        raise PersonaError(f"guardrails file '{guardrails_path}' not found")
    if not guardrails_path.is_file():
        raise PersonaError(f"guardrails path '{guardrails_path}' is not a file")
    return guardrails_path.read_text(encoding="utf-8")


def _list_personas(personas_root: Path) -> List[Persona]:
    try:
        directories = list(iter_persona_dirs(personas_root / PERSONAS_SUBDIR))
    except PersonaError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    personas: List[Persona] = []

    if not directories:
        typer.echo(f"No personas found in {personas_root}")
        return personas

    typer.echo(f"Personas in {personas_root}:")
    for directory in directories:
        if directory.name.startswith(".") or directory.name.startswith('_'):
            continue
        try:
            persona = load_persona(directory)
        except PersonaError as exc:
            typer.echo(f"  - {directory.name}: error ({exc})", err=True)
            continue
        personas.append(persona)
        typer.echo(
            f"  - {persona.id}: {persona.name}"
            f" [{persona.provider_kind}:{persona.provider_model}]"
        )

    return personas


@app.command()
def preview(
    personas: Path = typer.Option(
        Path("personas"),
        "--personas",
        "-p",
        help="Path to the personas root directory.",
    ),
    persona_id: Optional[str] = typer.Option(
        None,
        "--id",
        "-i",
        help="Persona id (directory name) to preview.",
    ),
    overlay: Optional[Path] = typer.Option(
        None,
        "--overlay",
        help="Path to an overlay file appended after guardrails.",
    ),
    overlay_text: Optional[str] = typer.Option(
        None,
        "--overlay-text",
        help="Inline overlay text appended after guardrails.",
    ),
    list_only: bool = typer.Option(
        False,
        "--list",
        help="List available personas and exit.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Print the compiled systemMessage after the summary.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat validation warnings as errors.",
    ),
) -> None:
    """Preview the compiled systemMessage for a persona."""

    personas_root = personas

    if list_only:
        _list_personas(personas_root)
        raise typer.Exit()

    if not persona_id:
        typer.secho("error: --id is required unless --list is used", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    persona_dir = personas_root / PERSONAS_SUBDIR / persona_id

    try:
        persona = load_persona(persona_dir)
    except PersonaError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    if persona.warnings:
        for warning in persona.warnings:
            typer.secho(f"warning: {warning}", fg=typer.colors.YELLOW, err=True)
        if strict:
            raise typer.Exit(code=2)

    try:
        overlay_content = _read_overlay(overlay, overlay_text)
    except PersonaError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    try:
        shared_guardrails = _load_guardrails(personas_root)
    except PersonaError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    compiled, info = compile_system_message(
        system=persona.system_text,
        guardrails=shared_guardrails,
        overlay=overlay_content,
        model=persona.provider_model,
        budget=persona.token_budget,
    )

    typer.echo(
        f"Persona: {persona.name} ({persona.id})\n"
        f"Provider: {persona.provider_kind}:{persona.provider_model}\n"
        f"Token budget: {persona.token_budget}\n"
        f"Initial tokens: {info['initial_tokens']}\n"
        f"Final tokens: {info['final_tokens']}\n"
    )

    if info["steps"]:
        typer.echo("Trim steps:")
        for step in info["steps"]:
            typer.echo(f"  - {step['action']}: {step['tokens']} tokens")
    else:
        typer.echo("Trim steps: none")

    if verbose:
        typer.echo("\nCompiled systemMessage:\n")
        typer.echo(compiled)


@app.command()
def generate(
    personas: Path = typer.Option(
        Path("personas"),
        "--personas",
        "-p",
        help="Path to the personas root directory.",
    ),
    out: Path = typer.Option(
        Path(".continue/agents/personas_config.yaml"),
        "--out",
        "-o",
        help="Path to write the Continue config YAML output.",
    ),
    manifest: Optional[Path] = typer.Option(
        None,
        "--manifest",
        "-m",
        help="Optional path to write a manifest JSON file.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Parse and report without writing any files.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat validation warnings as errors.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Print compiled systemMessage text for each persona.",
    ),
) -> None:
    """Generate a Continue config from persona definitions."""

    personas_root = personas

    personas_list: List[Persona] = []
    warnings: List[str] = []

    try:
        directories = list(iter_persona_dirs(personas_root / PERSONAS_SUBDIR))
    except PersonaError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    if not directories:
        typer.secho(f"error: no personas found in {personas_root}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    # Load the shared guardrails file once
    try:
        shared_guardrails = _load_guardrails(personas_root)
    except PersonaError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    for directory in directories:
        try:
            persona = load_persona(directory)
        except PersonaError as exc:
            typer.secho(
                f"error: failed to load persona '{directory.name}': {exc}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=2) from exc
        personas_list.append(persona)
        for warning in persona.warnings:
            message = f"warning ({persona.id}): {warning}"
            warnings.append(message)
            typer.secho(message, fg=typer.colors.YELLOW, err=True)

    if warnings and strict:
        raise typer.Exit(code=2)

    try:
        ensure_unique_models(personas_list)
    except PersonaError as exc:
        typer.secho(f"error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    models = []
    manifest_entries = []

    for persona in sorted(personas_list, key=lambda p: p.name.lower()):
        compiled, info = compile_system_message(
            system=persona.system_text,
            guardrails=shared_guardrails,  # Use the shared guardrails file
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
        typer.echo(summary)

        if verbose:
            typer.echo("--- compiled systemMessage ---")
            typer.echo(compiled)
            typer.echo("--- end systemMessage ---\n")

    has_qwen_autocomplete = any(
        ("autocomplete" in (entry.get("roles") or []))
        or entry.get("model") == "qwen2.5-coder:1.5b"
        for entry in models
    )

    if not has_qwen_autocomplete:
        models.append(
            {
                "name": "qwen2.5-coder:1.5b",
                "title": "qwen2.5-coder:1.5b",
                "provider": "ollama",
                "model": "qwen2.5-coder:1.5b",
                "roles": ["autocomplete", "chat"],
            }
        )

    config_payload = {
        "name": "Dolphin Personas",
        "version": "0.1.1",
        "schema": "v1",
        "models": models,
        "mcpServers": [],
    }
    if dry_run:
        typer.echo(yaml.safe_dump(config_payload, sort_keys=False))
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()
        out.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")
    if manifest:
        write_json(manifest, manifest_entries, dry_run=dry_run)

    if dry_run:
        typer.echo(f"(dry-run) Would write {len(models)} models to {out}")
        if manifest:
            typer.echo(f"(dry-run) Would write manifest to {manifest}")
    else:
        typer.echo(f"Wrote {len(models)} models to {out}")
        if manifest:
            typer.echo(f"Wrote manifest to {manifest}")


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    app()
