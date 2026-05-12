#!/usr/bin/env bash
#
# multi-agent-connector — one-line installer.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/sparkdeath324/multi-agent-connector/main/install.sh | bash
#
# Or with a custom repo / install location:
#   MAC_CONNECTOR_REPO=https://github.com/me/fork.git bash install.sh
#   MAC_CONNECTOR_INSTALL_DIR=/opt/mac-connector bash install.sh
#
# What it does:
#   1. git-clones (or `git pull`s) the plugin into ~/.claude/plugins/multi-agent-connector/
#   2. Runs the plugin's `setup` script, which wires settings.json and runs a smoke test.
#
# Exits non-zero on any failure. Safe to re-run.

set -euo pipefail

REPO_URL="${MAC_CONNECTOR_REPO:-https://github.com/sparkdeath324/multi-agent-connector.git}"
INSTALL_DIR="${MAC_CONNECTOR_INSTALL_DIR:-$HOME/.claude/plugins/multi-agent-connector}"
BRANCH="${MAC_CONNECTOR_BRANCH:-main}"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "[err] required command not found: $1" >&2
    exit 2
  }
}

require git
require python3

mkdir -p "$(dirname "$INSTALL_DIR")"

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "[info] plugin already cloned at $INSTALL_DIR — pulling latest from $BRANCH"
  git -C "$INSTALL_DIR" fetch --depth 1 origin "$BRANCH"
  git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
elif [ -e "$INSTALL_DIR" ]; then
  echo "[err] $INSTALL_DIR exists but is not a git checkout." >&2
  echo "      Move or remove it and rerun." >&2
  exit 2
else
  echo "[info] cloning $REPO_URL -> $INSTALL_DIR"
  git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi

chmod +x "$INSTALL_DIR/setup" 2>/dev/null || true
exec "$INSTALL_DIR/setup"
