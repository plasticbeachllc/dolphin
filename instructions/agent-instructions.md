# AI Assistant Onboarding Guide for Dolphin Project

## Overview

The dolphin project is a personal AI companion system that integrates multiple MCP (Model Context Protocol) servers with OpenWebUI to provide a customizable AI assistant experience. The core feature is a personas system that allows different AI agent personalities with specific behaviors and configurations.

## Repository Structure

```
dolphin/
├── personas/                 # Persona definitions and configurations
│   ├── deep-dive/           # Principal planner and systems architect
│   ├── journalist/          # Project documentarian and status tracker
│   ├── little-ripper/       # Junior engineer for precise implementation
│   ├── fancy-slave/         # Senior engineer for rapid local deployment
│   ├── popeye/              # High-priority project engineer
│   └── scripts/             # Persona management utilities
├── .continue/               # Continue configuration files
├── instructions/            # Documentation and guides (this file)
└── Justfile                 # Task runner configuration
```

## Prerequisites & Setup

### Required Tools
- **just**: Task runner for project commands
- **Docker**: Containerization for services
- **Python ≥3.13**: With `uv` package manager
- **Git**: Version control

### Initial Setup
1. Clone the repository:
   ```sh
   git clone <repository-url>
   cd dolphin
   ```

2. Run the setup command:
   ```sh
   just setup
   ```
   This will:
   - Create environment configuration from template
   - Validate required environment variables
   - Set up necessary dependencies

3. Configure environment variables in `.env`:
   - `GITHUB_PERSONAL_ACCESS_TOKEN`: For GitHub integrations
   - `OPENAI_API_KEY`: For AI model access

## Core Components

### Personas System

The personas system defines different AI agent personalities with specific behaviors, guardrails, and configurations. Each persona consists of:

- `persona.toml`: Metadata, provider settings, and parameters
- `system.md`: System prompt defining behavior and capabilities
- `guardrails.md`: Safety rules and constraints (optional)

#### Available Personas

- **Deep Dive**: Principal AI planner and systems architect who breaks work into ordered, testable increments, surfaces trade-offs and risks, and ensures production-ready patterns
- **Journalist**: Meticulous project documentarian who synthesizes repository state and changes, highlights gaps between plans and reality, and maintains accurate records
- **Little Ripper**: Junior software engineer who thrives on tight feedback cycles, follows specifications exactly, and implements small, verifiable changes
- **Fancy Slave**: Pragmatic senior engineer focused on rapidly shipping reliable features for local/offline deployments, optimizing for resource-constrained environments
- **Popeye**: Senior engineer at Plastic Beach responsible for implementation and engineering on high-priority projects, writing thoughtful, elegant, and maintainable code

### Personas Management Commands

- `just personas-list`: List all available personas
- `just personas-preview --id <persona_id>`: Preview a specific persona's configuration
- `just personas-generate`: Generate Continue config from all personas

Example usage:
```sh
just personas-preview --id journalist --verbose
```

## Development Workflow

### Testing

We use a custom test harness in `tests/run_tests.py` which runs all `test_*.py` tests in the `tests/` dir. Each test must implement a run_test() method which should use `assert` to ensure tested modules / functionalities work as expected across all input surface areas.

### Running Services

Start all services:
```sh
just run
```

This launches:
- OpenWebUI interface
- Backend MCP servers
- Personas configurations

### Common Development Commands

- `just run`: Start all services
- `just stop`: Stop all services
- `just setup-openwebui`: Pull latest images and start web UI
- `just test`: Run tests for all MCP servers
- `just list`: Show all available Just commands

### Making Changes

1. **Code Changes**: Modify files in the appropriate directories
2. **Persona Updates**: Edit persona files in `personas/<persona-id>/`
3. **Testing**: Use `just test` to verify changes
4. **Configuration**: Update `.continue/` files for Continue integration

### Creating New Personas

1. Create a new directory under `personas/` with slug-style name:
   ```sh
   mkdir personas/my-new-persona
   ```

2. Add required files:
   - `persona.toml`: Define metadata and configuration
   - `system.md`: Write system prompt and behavior definition
   - `guardrails.md`: Add safety rules (optional)

3. Validate the persona:
   ```sh
   just personas-preview --id my-new-persona
   ```

4. Generate updated configuration:
   ```sh
   just personas-generate
   ```

## Key Files and Their Purposes

### Configuration Files
- `Justfile`: Task definitions and project commands
- `pyproject.toml`: Python project configuration and dependencies
- `.env`: Environment variables (create from `.env.example`)

### Persona Files
- `persona.toml`: Persona metadata, provider settings, token budgets
- `system.md`: Core behavior definition and capabilities
- `guardrails.md`: Constraints and safety rules

### Scripts
- `personas/scripts/personas.py`: CLI for persona management
- `personas/scripts/persona_utils.py`: Utilities for persona loading and validation

## AI Assistant Best Practices

### When Answering Questions
1. Reference specific files or code sections when possible
2. Use the personas system context to provide appropriate responses
3. Suggest relevant Just commands for common tasks
4. Consider the user's current context (open files, recent changes)

### When Making Changes
1. Use the multi_edit tool for multiple changes to a single file
2. Follow existing code patterns and conventions
3. Test changes with `just test` when appropriate
4. Update documentation if functionality changes

### When Developing Plans
1. Break down complex tasks into smaller, testable increments
2. Consider which persona might be best suited for the task
3. Surface trade-offs, risks, and unknowns
4. Provide implementation steps with verification criteria

## Troubleshooting Common Issues

### Environment Setup
- Ensure all prerequisites are installed and accessible
- Verify `.env` file exists with required variables
- Check Docker is running for containerized services

### Persona Issues
- Use `just personas-preview` to validate persona configurations
- Check for syntax errors in TOML files
- Verify token budgets are within 200-8000 range

### Service Problems
- Use `just stop` and `just run` to restart services
- Check Docker container status if services fail to start
- Verify network connectivity for external dependencies

## Integration Points

### OpenWebUI
- Primary user interface for AI interactions
- Configures personas as available models
- Manages conversation history and context

### MCP Servers
- Provide context and tools to AI models
- Handle specific domains (filesystem, GitHub, etc.)
- Extend core AI capabilities

### Continue Configuration
- Defines available models and their behaviors
- Maps personas to specific provider configurations
- Manages roles and capabilities for each persona

This guide should enable AI assistants to effectively understand, navigate, and contribute to the dolphin project while providing accurate assistance to users.