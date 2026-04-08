#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${CODEX_HOME:-$HOME/.codex}/skills/lanjie-thinking-skill"
rm -rf "$TARGET_DIR"

echo "Removed: $TARGET_DIR"
