# Python Version Requirement

This project requires **Python 3.12** specifically because of the `tree_sitter_languages` dependency.

## Why Python 3.12?

- `tree_sitter_languages` v1.10.2 provides prebuilt wheels for:
  - `cp311` (Python 3.11)
  - `cp312` (Python 3.12)
- **No wheels for Python 3.13** (`cp313`) are currently available
- Building from source requires complex C toolchains
- Using Python 3.12 ensures reliable installation via `uv`

## Version Management

If you need to switch Python versions:

```bash
# Install Python 3.12 if not available
uv python install 3.12

# Set as default for this project
uv python pin 3.12

# Sync dependencies
uv sync
```

## Future Considerations

- Monitor `tree_sitter_languages` releases for Python 3.13 support
- Consider building from source if Python 3.13 is required
- Alternative: vendor the grammars and use `tree_sitter` directly

## Current Dependencies

- `tree_sitter_languages==1.10.2` (requires Python 3.11 or 3.12)
- `tree_sitter` (supports all Python versions)
- `markdown-it-py` (supports all Python versions)

This constraint will be re-evaluated when `tree_sitter_languages` adds Python 3.13 wheels.
