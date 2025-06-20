# justfile for building and running OpenWebUI and MCP servers with Python, Docker, and uv

# Variables
OPENWEBUI_DIR := "/openwebui"
MCP_DIR := "/mcp"
OPENWEBUI_PORT := "3010"
OPENWEBUI_DOCKER_PORT := "8080"
MCP_PORT := "8010"

# Pull OpenWebUI Docker image to the openwebui directory
pull-openwebui:
    docker pull ghcr.io/open-webui/open-webui:main

# start OpenWebui (assumes Dockerfile built)
start-openwebui:
    docker run -d -p {{OPENWEBUI_PORT}}:{{OPENWEBUI_DOCKER_PORT}} -e WEBUI_AUTH=False -v open-webui:/app/backend/data --name open-webui ghcr.io/open-webui/open-webui:main
    @echo {{GREEN}}"OpenWebUI started on port {{OPENWEBUI_PORT}}"

# stop OpenWebUI container if running
stop-openwebui:
    docker stop open-webui || true
    docker rm open-webui || true

# set up open webui (pull, build, start)
setup-openwebui: stop-openwebui pull-openwebui start-openwebui

# reset installation settings
clean-openwebui:
    docker image rm ghcr.io/open-webui/open-webui:main || true
    docker volume rm open-webui || true

# # Run MCP server
setup-openwebui-mcp:
    uvx mcpo --config ./mcpo_config.json
#     cd {{MCP_DIR}} && source venv/bin/activate && python main.py

# # # Build all
# # build-all: build-openwebui build-mcp

# # # Run all (in parallel)
# # run-all:
# #     just run-mcp &
# #     just run-openwebui

# # # Clean OpenWebUI
# # clean-openwebui:
# #     cd {{OPENWEBUI_DIR}} && docker image rm openwebui-local || true

# # # Clean MCP
# # clean-mcp:
# #     cd {{MCP_DIR}} && rm -rf venv __pycache__

# # # Clean all
# # clean-all: clean-openwebui clean-mcp