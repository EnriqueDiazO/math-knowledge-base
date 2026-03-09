#!/usr/bin/env bash
set -euo pipefail

# --- Pick Desktop folder automatically ---
if [[ -d "$HOME/Desktop" ]]; then
  DESKTOP_DIR="$HOME/Desktop"
elif [[ -d "$HOME/Escritorio" ]]; then
  DESKTOP_DIR="$HOME/Escritorio"
else
  DESKTOP_DIR="$HOME/Desktop"
  mkdir -p "$DESKTOP_DIR"
fi

FILE_NAME="mathmongodb-run.desktop"
FILE_PATH="$DESKTOP_DIR/$FILE_NAME"

# Repo root = where you run this script from
REPO_ROOT="$(pwd)"

cat > "$FILE_PATH" <<EOF
[Desktop Entry]
Type=Application
Name=MathMongoDB (run)
Comment=Streamlit: make start && make run
Terminal=true
Path=$REPO_ROOT
Exec=bash -lc 'make start && make run'
Icon=utilities-terminal
Categories=Development;
EOF

# GNOME-friendly permissions
chmod 755 "$FILE_PATH"
chmod go-w "$FILE_PATH"

echo "✅ Creado: $FILE_PATH"
echo "📌 Path apuntando a: $REPO_ROOT"
echo ""
echo "Si GNOME no te deja lanzarlo aún:"
echo "  - Click derecho → 'Allow Launching / Permitir lanzar'"
