#!/bin/bash
#
# install.sh — Arranca el instalador gráfico de Box Tray
#
# Lo único que hace este script es asegurarse de que exista Python3 +
# PyQt5: lo mínimo indispensable para poder mostrar una ventana. Si
# falta, se instala con pkexec, que pide la clave de administrador en un
# diálogo GRÁFICO del sistema (no hay que escribirla en la terminal).
#
# De ahí para adelante todo el instalador es ventanas: ver
# src/install_gui.py, que revisa/instala rclone y el resto de las
# dependencias, copia los archivos y deja Box Tray corriendo.
#
# También sirve para ACTUALIZAR: git pull && ./install.sh
#

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ "$EUID" -eq 0 ]; then
  echo "No ejecutes el instalador como root: se instala en tu usuario."
  exit 1
fi

if ! python3 -c "import PyQt5.QtSvg" 2> /dev/null; then
  if ! command -v pkexec &> /dev/null; then
    echo "Necesito 'pkexec' (paquete policykit-1) para instalar PyQt5 sin pedir la"
    echo "clave por terminal. Instálalo con: sudo apt install policykit-1"
    echo "y vuelve a correr ./install.sh"
    exit 1
  fi

  echo "Instalando Python3 y PyQt5 (te va a pedir la clave en una ventana)..."
  pkexec bash -c "apt-get update && apt-get install -y python3 python3-pyqt5 python3-pyqt5.qtsvg"
fi

exec python3 "$REPO_DIR/src/install_gui.py" "$REPO_DIR"
