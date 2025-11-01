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
    compile_system_message,
    ensure_unique_models,
    iter_persona_dirs,
    load_persona,
    write_json,
)
from .continue_utils import (
    ContinueError,
    write_continue_config,
    validate_continue_config,
)
from .kilocode_utils import (
    KiloCodeError,
    write_kilocode_config,
    validate_kilocode_config,
)

app = typer.Typer(
    add_completion=False,
    help="Persona toolkit for previewing and generating Continue or KiloCode configs.",
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
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Path to write the configuration output (auto-determined if not specified).",
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
    kilocode: bool = typer.Option(
        False,
        "--kilocode",
        help="Generate KiloCode Custom Modes configuration.",
    ),
    continue_compat: bool = typer.Option(
        False,
        "--continue",
        help="Generate Continue configuration.",
    ),
    target_format: Optional[str] = typer.Option(
        None,
        "--target-format",
        help="Target format for output: 'kilocode' or 'continue' (alternative to --kilocode/--continue flags).",
    ),
) -> None:
    """Generate a Continue or KiloCode config from persona definitions."""

    personas_root = personas

    # Handle target_format option vs legacy flags
    if target_format is not None:
        # New --target-format option used
        if kilocode or continue_compat:
            typer.secho("error: --target-format cannot be used with --kilocode or --continue", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        
        if target_format not in ["kilocode", "continue"]:
            typer.secho("error: --target-format must be 'kilocode' or 'continue'", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        
        # Set the corresponding flags for backward compatibility with existing logic
        if target_format == "kilocode":
            kilocode = True
        else:
            continue_compat = True
    else:
        # Legacy flags used
        if not (kilocode or continue_compat):
            typer.secho("error: must specify either --kilocode, --continue, or --target-format", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        
        if kilocode and continue_compat:
            typer.secho("error: --kilocode and --continue are mutually exclusive", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2)
        
        # Set target_format based on flags
        target_format = "kilocode" if kilocode else "continue"
    
    # Determine output paths - Both formats output to private directories
    if out is None:
        if target_format == "kilocode":
            out = Path(".")  # Directory, will create .kilocode-config subdirectory
        else:  # continue
            out = Path(".")  # Directory, will create .continue-config subdirectory

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

    compiled_messages = {}  # Store compiled messages for both formats

    for persona in sorted(personas_list, key=lambda p: p.name.lower()):
        compiled, info = compile_system_message(
            system=persona.system_text,
            guardrails=shared_guardrails,  # Use the shared guardrails file
            overlay="",
            model=persona.provider_model,
            budget=persona.token_budget,
        )
        
        # Store compiled message for both generators
        compiled_messages[persona.id] = compiled

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

    # Generate configuration based on target format
    if target_format == "kilocode":
        # Generate KiloCode configuration
        try:
            result = write_kilocode_config(
                personas_list,
                compiled_messages,
                shared_guardrails,
                out.parent if out.parent != Path(".") else Path("."),
                dry_run=dry_run
            )
            
            if dry_run:
                typer.echo(f"(dry-run) Would generate KiloCode config with {result['modes_count']} modes")
                typer.echo(f"(dry-run) Would write to: {result['output_directory']}")
                for file_path in result['generated_files']:
                    typer.echo(f"  - {file_path}")
            else:
                typer.echo(f"Generated KiloCode config with {result['modes_count']} modes")
                typer.echo(f"Configuration written to: {result['output_directory']}")
                
                # Validate generated configurations
                validation_errors = []
                for persona in personas_list:
                    config_file = Path(result['output_directory']) / "modes" / f"{persona.id}.json"
                    errors = validate_kilocode_config(config_file)
                    validation_errors.extend(errors)
                
                if validation_errors:
                    typer.secho("Validation warnings:", fg=typer.colors.YELLOW)
                    for error in validation_errors:
                        typer.secho(f"  - {error}", fg=typer.colors.YELLOW)
                else:
                    typer.secho("✓ All generated configurations validated successfully", fg=typer.colors.GREEN)
            
            if manifest:
                # Create manifest entries with KiloCode-specific data
                manifest_entries = []
                for persona in personas_list:
                    manifest_entries.append({
                        "id": persona.id,
                        "name": persona.name,
                        "version": persona.version,
                        "provider": persona.provider_kind,
                        "model": persona.provider_model,
                        "token_budget": persona.token_budget,
                        "path": str(persona.path),
                        "target_format": "kilocode",
                        "config_file": f"modes/{persona.id}.json",
                        "instructions_file": f"instructions/{persona.id}-instructions.md"
                    })
                
                write_json(manifest, manifest_entries, dry_run=dry_run)
                
        except KiloCodeError as exc:
            typer.secho(f"error: KiloCode generation failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from exc
    
    elif target_format == "continue":
        # Generate Continue configuration
        try:
            target_dir = out.parent if out.parent != Path(".") else Path(".")
            if dry_run:
                result = write_continue_config(
                    personas_list,
                    compiled_messages,
                    target_dir,
                    manifest,
                    dry_run=True
                )
                typer.echo(yaml.safe_dump(result['config_payload'], sort_keys=False))
                typer.echo(f"(dry-run) Would write {result['models_count']} models to {result['output_file']}")
                if manifest:
                    typer.echo(f"(dry-run) Would write manifest to {manifest}")
            else:
                result = write_continue_config(
                    personas_list,
                    compiled_messages,
                    target_dir,
                    manifest,
                    dry_run=False
                )
                typer.echo(f"Wrote {result['models_count']} models to {result['output_file']}")
                if manifest and result['manifest_file']:
                    typer.echo(f"Wrote manifest to {result['manifest_file']}")
                
                # Validate generated configuration
                output_file = Path(result['output_file'])
                validation_errors = validate_continue_config(output_file)
                if validation_errors:
                    typer.secho("Validation warnings:", fg=typer.colors.YELLOW)
                    for error in validation_errors:
                        typer.secho(f"  - {error}", fg=typer.colors.YELLOW)
                else:
                    typer.secho("✓ Configuration validated successfully", fg=typer.colors.GREEN)
                    
        except ContinueError as exc:
            typer.secho(f"error: Continue generation failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=2) from exc


def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()
