#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/skill/lanjie-thinking-skill"
TARGET_DIR="${CODEX_HOME:-$HOME/.codex}/skills/lanjie-thinking-skill"

mkdir -p "$(dirname "$TARGET_DIR")"
rm -rf "$TARGET_DIR"
cp -R "$SRC_DIR" "$TARGET_DIR"

echo "Installed: $TARGET_DIR"
