#!/usr/bin/env bash
# Copy agent-kit skills + slash commands into .claude/ so they become loadable.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/agent-kit"
DEST="$ROOT/.claude"
mkdir -p "$DEST/skills" "$DEST/commands"
if [ -d "$SRC/skills" ]; then cp -R "$SRC/skills/." "$DEST/skills/"; fi
if [ -d "$SRC/commands" ]; then cp -R "$SRC/commands/." "$DEST/commands/"; fi
echo "installed agent-kit into .claude/"
