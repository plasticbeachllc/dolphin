#!/bin/bash
# Quick start script for Dolphin Observability Stack
# This is a convenience wrapper around manage.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/manage.sh" start
