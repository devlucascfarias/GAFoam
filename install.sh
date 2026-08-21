#!/usr/bin/env bash
set -e

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/share/gafoam"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

echo "================================================="
echo "   GAFoam Installation"
echo "================================================="

# 1. Detect Python 3
PYTHON_BIN=""
for py in python3 python; do
    if command -v $py >/dev/null 2>&1; then
        PYTHON_BIN=$(command -v $py)
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "Error: Python 3 not found. Please install Python 3 before proceeding."
    exit 1
fi

echo "✓ Python detected: $PYTHON_BIN"

# 2. Create isolated virtual environment
echo "==> Creating dedicated virtual environment in $INSTALL_DIR/venv..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$BIN_DIR"
"$PYTHON_BIN" -m venv "$INSTALL_DIR/venv"

# 3. Install/upgrade pip and dependencies
echo "==> Installing dependencies and GAFoam package..."
"$INSTALL_DIR/venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$INSTALL_DIR/venv/bin/pip" install -e "$REPO_DIR"

# 4. Create executable wrapper in PATH (~/.local/bin/gafoam)
echo "==> Creating executable in $BIN_DIR/gafoam..."
cat << 'EOF' > "$BIN_DIR/gafoam"
#!/usr/bin/env bash
if command -v setxkbmap >/dev/null 2>&1; then
    setxkbmap -model abnt2 -layout br 2>/dev/null || true
fi
export VTK_DISABLE_SHM=1
exec "$HOME/.local/share/gafoam/venv/bin/gafoam" "$@"
EOF
chmod +x "$BIN_DIR/gafoam"

# 5. Ensure ~/.local/bin is in PATH (~/.bashrc)
export PATH="$BIN_DIR:$PATH"
if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
    if ! grep -q 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.bashrc" 2>/dev/null; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        echo "✓ Added ~/.local/bin to ~/.bashrc"
    fi
fi

# Try global /usr/local/bin link if writable
if [ -w /usr/local/bin ]; then
    ln -sf "$BIN_DIR/gafoam" /usr/local/bin/gafoam 2>/dev/null || true
fi

# 6. Create .desktop launcher entry (WSLg / Linux Desktop)
mkdir -p "$DESKTOP_DIR"
cat << EOF > "$DESKTOP_DIR/gafoam.desktop"
[Desktop Entry]
Name=GAFoam
Comment=OpenFOAM GUI & CFD Case Manager
Exec=$BIN_DIR/gafoam %F
Icon=$REPO_DIR/src/gafoam/icons/app_icon.svg
Terminal=false
Type=Application
Categories=Science;Engineering;
EOF
chmod +x "$DESKTOP_DIR/gafoam.desktop"

echo "================================================="
echo "  ✓ GAFoam installed successfully!"
echo "================================================="
echo "To use 'gafoam' in your current terminal session, run:"
echo "   source ~/.bashrc"
echo ""
echo "Then you can launch it anytime by typing:"
echo "   gafoam"
echo "Or open a case directly:"
echo "   gafoam /path/to/case"
echo "================================================="
