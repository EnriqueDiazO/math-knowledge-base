#!/usr/bin/env bash
set -euo pipefail

# Quarto installer for Ubuntu/Debian
# Usage:
#   ./install_quarto.sh
#   QUARTO_VERSION=1.8.26 ./install_quarto.sh
#   QUARTO_VERSION=1.8.26 QUARTO_SHA256=<sha> ./install_quarto.sh

QUARTO_VERSION="${QUARTO_VERSION:-1.8.26}"
QUARTO_SHA256="${QUARTO_SHA256:-}"

ARCH="$(dpkg --print-architecture)"
case "$ARCH" in
  amd64|arm64) ;;
  *)
    echo "Unsupported architecture: $ARCH"
    echo "Supported: amd64, arm64"
    exit 1
    ;;
esac

DEB="quarto-${QUARTO_VERSION}-linux-${ARCH}.deb"
URL="https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/${DEB}"

TMP_DIR="$(mktemp -d)"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

echo "Quarto version: ${QUARTO_VERSION}"
echo "Arch: ${ARCH}"
echo "Downloading: ${URL}"

cd "$TMP_DIR"
if command -v curl >/dev/null 2>&1; then
  curl -fL -o "$DEB" "$URL"
elif command -v wget >/dev/null 2>&1; then
  wget -O "$DEB" "$URL"
else
  echo "Neither curl nor wget is available. Install one and retry."
  exit 1
fi

if [[ -n "$QUARTO_SHA256" ]]; then
  echo "${QUARTO_SHA256}  ${DEB}" | sha256sum -c -
else
  echo "SHA256 not provided; skipping checksum verification."
  echo "Tip: set QUARTO_SHA256=<value> to verify the download."
fi

echo "Installing .deb (requires sudo)..."
sudo dpkg -i "$DEB" || true

echo "Fixing dependencies (if any)..."
sudo apt-get update -y
sudo apt-get -f install -y

echo "Verifying installation..."
quarto --version
quarto check || true

echo "Done."
