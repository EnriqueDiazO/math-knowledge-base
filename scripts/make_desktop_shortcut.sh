#!/usr/bin/env bash
set -euo pipefail

# Backwards-compatible entry point; all implementation lives in the installed package.
if command -v mathmongo-desktop >/dev/null 2>&1; then
  exec mathmongo-desktop "$@"
fi

exec python3 -m mathmongo.desktop "$@"
