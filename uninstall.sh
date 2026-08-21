#!/usr/bin/env bash
set -e

INSTALL_DIR="$HOME/.local/share/gafoam"
BIN_FILE="$HOME/.local/bin/gafoam"
DESKTOP_FILE="$HOME/.local/share/applications/gafoam.desktop"

echo "==> Removing GAFoam..."
rm -rf "$INSTALL_DIR"
rm -f "$BIN_FILE"
rm -f "$DESKTOP_FILE"

echo "✓ GAFoam uninstalled successfully."
