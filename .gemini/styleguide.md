# Dolphin Code Review Guide for Gemini

Use this guide when reviewing or suggesting code changes in the Dolphin repository.
Keep reviews focused, architecture-aware, and test-driven.

## 1. Overall Review Principles

- When uncertain about intent or behavior, surface the ambiguity explicitly instead of guessing.
- Prefer concrete, actionable suggestions (what to change and why) over high-level criticism.
- Provide feedback on the overall architecture and code quality from the perspective of flexibility, performance, maintainability, and correctness.
- Ensure all documentation is aligned with the current state of the codebase.

## 2. Repository-Specific Rules

- Always follow `AGENTS.md` at the repo root; do not contradict its instructions.
- Python: use `uv run` for all commands (tests, tools, scripts); never suggest plain `python` or `pytest`.
- TypeScript/Bun: use `bun test`, `bun run lint`, and existing scripts; do not introduce alternate toolchains.
- Do not create new documentation files unless the user explicitly requests it; otherwise, suggest updates to existing docs.
- Preserve the documented architecture in `docs/ARCHITECTURE.md` and related plans; call out when a change deviates from it.

## 3. Testing and Quality Expectations

- For bug fixes, require a regression test that fails before the fix and passes after.
- For new features, require unit tests and, when appropriate, integration tests in the existing suites.
- Prefer to run the narrowest relevant test commands first (e.g., file- or directory-level) before full suites.
- Reject or flag changes that significantly reduce test coverage or remove important assertions without justification.=

## 4. Change Review Checklist

For each change, verify:

- **Correctness:** Logic matches the described behavior and edge cases are handled or called out.
- **Consistency:** Code style and patterns match nearby code and the language-specific guidelines in `AGENTS.md`.
- **Tests:** Relevant tests are added or updated, and test commands are clearly indicated for the user to run.
- **Safety:** Input validation, error handling, and resource usage are appropriate for the change.
- **Scope:** The change set is focused; unrelated modifications are either removed or clearly justified.

## 5. Review Communication Style

- Be direct and unambiguous; prefer concise, numbered lists or bullets over long paragraphs.
- Separate **must-fix** issues (correctness, tests, security, major regressions) from **nice-to-have** improvements.
- When suggesting non-trivial refactors, describe the target structure and risks in detail.
