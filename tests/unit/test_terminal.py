"""Tests for terminal status rendering helpers."""

from kb.terminal import render_status_line


def test_render_status_line_sorts_context_keys() -> None:
    line = render_status_line(
        "Search backend ready.",
        level="success",
        context={"store": "/tmp/db", "provider": "stub"},
    )

    assert "[OK]" in line
    assert line.index("provider=stub") < line.index("store=/tmp/db")


def test_render_status_line_without_context() -> None:
    line = render_status_line("Initializing server.", level="step")

    assert line.startswith("[bold deep_sky_blue3][STEP][/bold deep_sky_blue3]")
    assert "Initializing server." in line
