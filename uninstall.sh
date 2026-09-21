#!/bin/bash
#
# uninstall.sh — Desinstala box-tray
#
# NO toca tu carpeta sincronizada ni la configuración de rclone.
#

set -euo pipefail

APP_DIR="$HOME/.local/share/box-tray"
BIN_DIR="$HOME/.local/bin"
CFG_DIR="$HOME/.config/box-tray"
STATE_DIR="$HOME/.local/state/box-tray"

echo "Cerrando Box Tray..."
pkill -f "box-tray/box-tray.py" 2> /dev/null || true

echo "Borrando programa y accesos..."
rm -f  "$BIN_DIR/boxsync" "$BIN_DIR/box-tray"
rm -f  "$HOME/.config/autostart/box-tray.desktop"
rm -f  "$HOME/.local/share/applications/box-tray.desktop"
rm -rf "$APP_DIR"

read -r -p "¿Borrar también la configuración y los logs? [s/N] " answer
if [[ "$answer" =~ ^[sSyY]$ ]]; then
  rm -rf "$CFG_DIR" "$STATE_DIR"
  echo "Configuración y logs borrados."
fi

echo "Listo. Tu carpeta sincronizada y el remoto de rclone siguen intactos."
