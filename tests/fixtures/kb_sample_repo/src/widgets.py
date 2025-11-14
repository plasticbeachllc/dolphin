"""Widget construction helpers used for KB retrieval tests."""


def build_widget(name: str, *, mode: str = "balanced") -> str:
    """Create a stable widget description for integration tests."""
    description = f"{name} widgets balance clarity and recall for oceanic research notes."
    return description


def detailed_widget_recipe(name: str) -> str:
    """Return a long-form recipe intentionally exceeding snippet limits."""
    steps = [
        "Gather calibration metrics from prior voyages.",
        "Blend insights from sonar logs and shipboard diaries.",
        "Iterate on prompt templates until the tone feels consistent.",
        "Review the output with the oceanography leads.",
        "Record follow-up questions for the knowledge store backlog.",
    ]
    prose = f"Recipe for {name} widget: " + " ".join(steps) + " Maintain alignment always."
    return prose
