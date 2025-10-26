# dolphin

Your personal AI companion.

---

## 🚀 Getting Started

### Prerequisites

*   just
*   Docker
*   Python >=3.13 (with `uv` installed)

### Installation & Setup

1.  Clone the repository:
    ```sh
    git clone <your-repo-url>
    cd dolphin
    ```
2.  Run the setup command:
    ```sh
    just setup
    ```

## 🤖 Usage

To start all services for the AI companion, run:
```sh
just run
```

This will launch OpenWebUI and the necessary backend MCP servers.

### Common Commands

*   `just run`: Starts all services.
*   `just stop`: Stops all services.
*   `just setup-openwebui`: Pulls the latest images and starts the web UI.
*   `just test`: Runs the project's test runner (tests.run_tests) which discovers test_*.py modules in the tests/ directory and executes their run_test() functions.

To see all available commands, run:
```sh
just list
```

### Running tests manually

You can also run the test runner directly (without just):

```sh
python -m tests.run_tests
```

Notes:
- Individual test modules now export `run_test()` with no parameters; the test runner imports each test_*.py module and calls run_test().
- If you prefer pytest, you can of course run any test file with `pytest tests/` (ensure pytest is installed).

## 🎭 Personas

The dolphin project includes a personas system that allows you to define and use different AI agent personalities with specific behaviors, guardrails, and configurations.

### Available Personas

- **Deep Dive**: Principal AI planner and systems architect who breaks work into ordered, testable increments, surfaces trade-offs and risks, and ensures production-ready patterns
- **Journalist**: Meticulous project documentarian who synthesizes repository state and changes, highlights gaps between plans and reality, and maintains accurate records
- **Little Ripper**: Junior software engineer who thrives on tight feedback cycles, follows specifications exactly, and implements small, verifiable changes
- **Fancy Slave**: Pragmatic cheap labor focused on conversation, efficiency, and adaptability
- **Popeye**: Senior engineer at Plastic Beach responsible for implementation and engineering on high-priority projects, writing thoughtful, elegant, and maintainable code

### Personas Commands

* `just personas-list`: List all available personas
* `just personas-preview --id <persona_id>`: Preview a specific persona's configuration and system message
* `just personas-generate`: Generate Continue config from all personas (writes to `.continue/agents/personas_config.yaml`)

### Persona Structure

Each persona is defined in its own directory under `personas/` with the following structure:

```
personas/
  ├── <persona-id>/
  │   ├── persona.toml    # Persona metadata and configuration
  │   ├── system.md       # System prompt and behavior definition
  │   └── guardrails.md   # Safety rules and constraints
```

### Creating a New Persona

1. Create a new directory under `personas/` with a slug-style name (e.g., `my-new-persona`)
2. Add the required files:
   - `persona.toml`: Define persona metadata, provider settings, and parameters
   - `system.md`: Write the system prompt that defines the persona's behavior
   - `guardrails.md`: (Optional) Add safety rules and constraints
3. Use `just personas-preview --id my-new-persona` to validate your persona
4. Run `just personas-generate` to include it in the Continue configuration

### Example: Previewing a Persona

```sh
just personas-preview --id journalist --verbose
```

This will show the compiled system message, token usage, and any trimming steps applied to fit within the token budget.

## Miscellaneous

### Failed Tool Fires (log for future system prompting)
- ```create_new_file failed with the message: `filepath` argument is required and must not be empty or whitespace-only. (type string)```
- ```failed because the arguments were invalid, with the following message: Tool  not found```
- ```create_new_file failed with the message: `filepath` argument is required and must not be empty or whitespace-only. (type string)```
- ``` failed because the arguments were invalid, with the following message: Tool  not found```
- ```multi_edit failed because the arguments were invalid, with the following message: invalid multi-edit args```
- ```edit_existing_file failed because the arguments were invalid, with the following message: Tool edit_existing_file not found```
- ```single_find_and_replace failed because the arguments were invalid, with the following message: Tool single_find_and_replace not found```
- ```create_new_file failed with the message: File scripts/security-scan-enhanced.sh already exists. Use the edit tool to edit this file```
- ```create_new_file failed with the message: File scripts/security-scan-enhanced.sh already exists. Use the edit tool to edit this file```
- Model uses absolute path when repo-relative path is correct
- ```multi_edit failed because the arguments were invalid, with the following message: invalid multi-edit args```
