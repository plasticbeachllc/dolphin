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
*   `just test`: Runs tests for all MCP servers.

To see all available commands, run:
```sh
just list
