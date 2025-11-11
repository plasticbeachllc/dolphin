#!/bin/bash

# Dolphin Server Startup Script
# This script ensures environment variables are loaded from .env file

# Change to the project directory
cd "$(dirname "$0")"

# Load environment variables from .env file
if [ -f .env ]; then
    echo "📄 Loading environment variables from .env file..."
    # Export variables from .env file (proper shell format)
    set -a  # automatically export all variables
    source .env
    set +a  # stop auto-export
else
    echo "⚠️  No .env file found. Make sure to set OPENAI_API_KEY environment variable."
fi

# Display key environment variables (masked for security)
if [ ! -z "$OPENAI_API_KEY" ]; then
    echo "✅ OPENAI_API_KEY is set (key starts with: ${OPENAI_API_KEY:0:15}...)"
else
    echo "❌ OPENAI_API_KEY is not set"
fi

# Start the Dolphin server
echo "🚀 Starting Dolphin server..."
echo "================================================================"

# Use uv run to ensure proper virtual environment
uv run dolphin serve