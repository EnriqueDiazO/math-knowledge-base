#!/usr/bin/env bash
set -euo pipefail

# ChkTeX installer for Ubuntu/Debian
# Usage:
#   ./scripts/install_chktex.sh

chktex_path() {
  command -v chktex 2>/dev/null
}

chktex_version() {
  chktex --version 2>&1 | head -n 1
}

verify_chktex() {
  local bin
  local version

  if ! bin="$(chktex_path)"; then
    return 1
  fi

  if ! version="$(chktex_version)"; then
    return 1
  fi

  if [[ -z "$version" ]]; then
    return 1
  fi

  echo "Ruta: ${bin}"
  echo "Versión: ${version}"
}

if chktex_path >/dev/null 2>&1; then
  echo "ChkTeX ya está instalado."
  verify_chktex
  echo "Done."
  exit 0
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "Unsupported system: apt-get is not available."
  echo "This installer supports Ubuntu/Debian systems with apt-get."
  exit 1
fi

echo "Installing ChkTeX package (requires sudo)..."
sudo apt-get update -y
sudo apt-get install -y chktex

echo "Verifying installation..."
if ! verify_chktex; then
  echo "No se pudo verificar la instalación de ChkTeX."
  exit 1
fi

echo "ChkTeX instalado correctamente."
echo "Done."
