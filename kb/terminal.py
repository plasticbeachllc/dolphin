"""Shared terminal rendering helpers for CLI and server status output."""

from __future__ import annotations

from typing import Any, Literal

from rich.console import Console

StatusLevel = Literal["step", "info", "success", "warn", "error"]

_STDOUT_CONSOLE = Console(stderr=False, highlight=False, soft_wrap=True)
_STDERR_CONSOLE = Console(stderr=True, highlight=False, soft_wrap=True)

_LEVEL_META: dict[StatusLevel, tuple[str, str]] = {
    "step": ("bright_blue", "STEP"),
    "info": ("cyan", "INFO"),
    "success": ("green", "OK"),
    "warn": ("yellow", "WARN"),
    "error": ("red", "ERROR"),
}


def _normalize_context(context: dict[str, Any] | None) -> str:
    if not context:
        return ""
    pairs: list[str] = []
    for key in sorted(context):
        value = context[key]
        if value is None or value == "":
            continue
        pairs.append(f"{key}={value}")
    return "  ".join(pairs)


def render_status_line(
    message: str,
    *,
    level: StatusLevel = "info",
    context: dict[str, Any] | None = None,
) -> str:
    """Build a consistently styled terminal status line."""
    color, label = _LEVEL_META[level]
    prefix = f"[bold {color}][{label}][/bold {color}]"
    details = _normalize_context(context)
    if details:
        return f"{prefix} {message} [dim]{details}[/dim]"
    return f"{prefix} {message}"


def print_status(
    message: str,
    *,
    level: StatusLevel = "info",
    context: dict[str, Any] | None = None,
    stderr: bool = False,
) -> None:
    """Print a consistently styled status line."""
    console = _STDERR_CONSOLE if stderr else _STDOUT_CONSOLE
    console.print(render_status_line(message, level=level, context=context))


def print_hint(message: str, *, stderr: bool = False) -> None:
    """Print a muted follow-up hint line."""
    console = _STDERR_CONSOLE if stderr else _STDOUT_CONSOLE
    console.print(f"[dim]Hint:[/dim] {message}")

