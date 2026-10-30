#!/bin/bash
set -e

# Usage: entrypoint.sh [bot|mcp]   (defaults to "bot")
COMMAND="${1:-bot}"

case "$COMMAND" in
  bot)
    uv run alembic upgrade head
    exec uv run agentic run
    ;;
  mcp)
    exec uv run agentic mcp run
    ;;
  *)
    # Unknown command: run it as-is
    exec "$@"
    ;;
esac
