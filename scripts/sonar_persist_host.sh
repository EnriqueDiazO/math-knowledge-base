#!/usr/bin/env bash
# Apply only the missing persistent vm.max_map_count setting. Run with sudo.
set -euo pipefail
if [[ "${EUID}" -ne 0 ]]; then
  echo "Run: sudo bash scripts/sonar_persist_host.sh" >&2
  exit 1
fi
target=/etc/sysctl.d/90-mathmongo-sonar.conf
if [[ -e "$target" || -L "$target" ]]; then
  echo "Existing $target preserved; review it manually." >&2
  exit 1
fi
# Account for all persisted declarations, including vendor settings. A sufficient
# declaration needs operator review of ordering, rather than silently overwriting it.
shopt -s nullglob
configs=(/etc/sysctl.conf /etc/sysctl.d/*.conf /usr/lib/sysctl.d/*.conf /run/sysctl.d/*.conf)
if awk -F= '/^[[:space:]]*vm[.]max_map_count[[:space:]]*=/ {if ($2+0 >= 524288) found=1} END {exit !found}' \
  "${configs[@]}"; then
  echo "A sufficient persistent setting already exists; no file created."
  exit 0
fi
previous=$(sysctl -n vm.max_map_count)
(set -o noclobber; printf '# MathMongo SonarQube; previous live value: %s\nvm.max_map_count=524288\n' "$previous" > "$target")
chmod 644 "$target"
if (( previous < 524288 )); then
  sysctl -w vm.max_map_count=524288
fi
echo "Created $target; existing sufficient live values were preserved."
