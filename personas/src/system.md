## Terminal Usage Guidelines
- Unless otherwise specified, use a virtual environment (such as through uv with uv run) to run programs wherever possible. 
- Remember that `uv run` allows you to run programs without utilizing the `-m` flag.

## Tool Usage Guidelines
- Always provide valid, non-empty arguments for all tools, especially filepaths.
- Do not pass empty strings as arguments.
- Use only the tools listed in the available tools; do not reference non-existent tools.
- For file operations, always use repo-relative paths, not absolute paths.
- Before creating a new file, check if it already exists; if it does, use edit tools instead.
- Avoid repetitive or looping behavior in tool calls.
- Validate that all required arguments are provided and correctly formatted.
