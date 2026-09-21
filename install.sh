#!/bin/bash
#
# install.sh — Instalador de box-tray
#
# Instala todo en la carpeta del usuario (no necesita root, salvo para
# instalar dependencias con apt). También sirve para ACTUALIZAR:
#   git pull && ./install.sh
#

set -euo pipefail


# ---------- RUTAS ----------
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

APP_DIR="$HOME/.local/share/box-tray"
BIN_DIR="$HOME/.local/bin"
CFG_DIR="$HOME/.config/box-tray"
CONFIG_FILE="$CFG_DIR/box-tray.conf"
AUTOSTART_DIR="$HOME/.config/autostart"
APPS_DIR="$HOME/.local/share/applications"

RCLONE_MIN_VERSION="1.66.0"     # necesaria para --conflict-resolve y --recover


# ---------- UTILIDADES ----------
info() { echo -e "\n\e[1;34m==>\e[0m $1"; }
ok()   { echo -e " \e[1;32m✓\e[0m $1"; }
warn() { echo -e " \e[1;33m!\e[0m $1"; }

# ask "pregunta" -> verdadero si responde s/S o solo Enter
ask() {
  local answer
  read -r -p "   $1 [S/n] " answer
  [[ -z "$answer" || "$answer" =~ ^[sSyY]$ ]]
}

# Versión instalada de rclone, o 0.0.0 si no está
rclone_version() {
  rclone version 2>/dev/null | head -n1 | grep -oP 'v\K[0-9]+\.[0-9]+\.[0-9]+' || echo "0.0.0"
}

# version_ok ACTUAL MINIMA -> verdadero si ACTUAL >= MINIMA
version_ok() {
  local lowest
  lowest="$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -n1)"
  [ "$lowest" = "$2" ]
}


if [ "$EUID" -eq 0 ]; then
  echo "No ejecutes el instalador como root: se instala en tu usuario."
  exit 1
fi


# ---------- 1. Dependencias del sistema ----------
info "Revisando dependencias..."

MISSING_PKGS=()
command -v python3     > /dev/null || MISSING_PKGS+=(python3)
python3 -c "import PyQt5.QtSvg" 2> /dev/null || MISSING_PKGS+=(python3-pyqt5 python3-pyqt5.qtsvg)
command -v notify-send > /dev/null || MISSING_PKGS+=(libnotify-bin)
command -v xdg-open    > /dev/null || MISSING_PKGS+=(xdg-utils)
command -v curl        > /dev/null || MISSING_PKGS+=(curl)

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
  warn "Faltan paquetes: ${MISSING_PKGS[*]}"
  if ask "¿Instalarlos con apt? (pide sudo)"; then
    sudo apt update
    sudo apt install -y "${MISSING_PKGS[@]}"
  else
    echo "   Instálalos a mano y vuelve a ejecutar ./install.sh"
    exit 1
  fi
fi
ok "Dependencias del sistema listas."


# ---------- 2. rclone ----------
info "Revisando rclone..."

CURRENT_VERSION="$(rclone_version)"

if ! version_ok "$CURRENT_VERSION" "$RCLONE_MIN_VERSION"; then
  if [ "$CURRENT_VERSION" = "0.0.0" ]; then
    warn "rclone no está instalado."
  else
    warn "rclone $CURRENT_VERSION es muy antiguo (se necesita $RCLONE_MIN_VERSION o superior)."
  fi

  if ask "¿Instalar la última versión desde rclone.org? (pide sudo)"; then
    # La versión de apt es vieja; se quita para que un 'apt upgrade' no la pise.
    if dpkg -s rclone &> /dev/null; then
      sudo apt remove -y rclone
    fi
    # El instalador oficial sale con código 3 si ya está al día; no es error.
    curl -fsSL https://rclone.org/install.sh | sudo bash || true
  else
    echo "   Instala rclone $RCLONE_MIN_VERSION o superior y vuelve a ejecutar ./install.sh"
    exit 1
  fi

  CURRENT_VERSION="$(rclone_version)"
  if ! version_ok "$CURRENT_VERSION" "$RCLONE_MIN_VERSION"; then
    echo "   No se pudo instalar una versión compatible de rclone."
    exit 1
  fi
fi
ok "rclone $CURRENT_VERSION"


# ---------- 3. Copiar archivos ----------
info "Instalando archivos en $APP_DIR ..."

# Si el tray ya estaba corriendo (actualización), se cierra antes de copiar
pkill -f "box-tray/box-tray.py" 2> /dev/null || true

mkdir -p "$APP_DIR/icons" "$BIN_DIR"
install -m 755 "$REPO_DIR/src/boxsync.sh"  "$APP_DIR/boxsync.sh"
install -m 755 "$REPO_DIR/src/box-tray.py" "$APP_DIR/box-tray.py"
install -m 644 "$REPO_DIR"/icons/*.svg     "$APP_DIR/icons/"

# Comandos cortos: 'boxsync' y 'box-tray'
ln -sf "$APP_DIR/boxsync.sh"  "$BIN_DIR/boxsync"
ln -sf "$APP_DIR/box-tray.py" "$BIN_DIR/box-tray"
# URL del proyecto, tomada del 'git remote' del repo clonado.
# Convierte git@github.com:usuario/repo.git -> https://github.com/usuario/repo
REPO_URL="$(git -C "$REPO_DIR" remote get-url origin 2> /dev/null || true)"
REPO_URL="${REPO_URL%.git}"
REPO_URL="${REPO_URL/git@github.com:/https://github.com/}"
echo -n "$REPO_URL" > "$APP_DIR/repo-url"

ok "Archivos instalados."

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  warn "$BIN_DIR no está en tu PATH. Cierra sesión y vuelve a entrar para usar 'boxsync' directo."
fi


# ---------- 4. Configuración ----------
info "Configuración..."

if [ -f "$CONFIG_FILE" ]; then
  ok "Ya existe $CONFIG_FILE (no se modifica)."
else
  read -r -p "   Nombre del remoto de rclone [box]: " REMOTE_NAME
  REMOTE_NAME="${REMOTE_NAME:-box}"

  read -r -p "   Carpeta local a sincronizar [$HOME/Box]: " LOCAL_DIR
  LOCAL_DIR="${LOCAL_DIR:-$HOME/Box}"
  LOCAL_DIR="${LOCAL_DIR/#\~/$HOME}"      # por si escribes ~/algo

  mkdir -p "$CFG_DIR"
  cat > "$CONFIG_FILE" << EOF
# Configuración de box-tray (la leen boxsync.sh y box-tray.py)

# Remoto de rclone (con los dos puntos al final)
REMOTE="${REMOTE_NAME}:"

# Carpeta local que se sincroniza
LOCAL_DIR="${LOCAL_DIR}"

# Color de los íconos: "#ffffff" para panel oscuro, "#000000" para panel claro
ICON_COLOR="#ffffff"
EOF
  ok "Configuración creada en $CONFIG_FILE"
fi

# shellcheck source=/dev/null
source "$CONFIG_FILE"
mkdir -p "$LOCAL_DIR"


# ---------- 5. Remoto de rclone ----------
info "Revisando el remoto '$REMOTE' en rclone..."

REMOTE_NAME="${REMOTE%%:*}"

remote_exists() {
  rclone listremotes 2> /dev/null | grep -qx "${REMOTE_NAME}:"
}

if ! remote_exists; then
  warn "Todavía no has iniciado sesión en Box en este equipo."
  echo "   Se abrirá el navegador: entra a tu cuenta de Box y presiona"
  echo "   'Otorgar acceso a Box'. Luego vuelve a esta terminal."
  if ask "¿Iniciar sesión ahora?"; then
    rclone config create "$REMOTE_NAME" box || warn "No se completó el inicio de sesión."
  fi
fi

REMOTE_READY=false
if remote_exists; then
  REMOTE_READY=true
  ok "Remoto '${REMOTE_NAME}' encontrado."
else
  warn "Sin remoto no se puede sincronizar. Configúralo y vuelve a ejecutar ./install.sh"
fi


# ---------- 6. Primera sincronización ----------
if [ "$REMOTE_READY" = true ]; then
  info "Primera sincronización"
  echo "   La primera vez en cada equipo hay que hacer un --resync."
  echo "   No borra nada: junta lo que haya en $LOCAL_DIR y en Box."
  if ask "¿Hacer el resync ahora? (puede tardar)"; then
    "$APP_DIR/boxsync.sh" --resync --force || warn "El resync terminó con errores. Revisa el log con: box-tray → Ver registro."
  fi
fi


# ---------- 7. Menú de aplicaciones e inicio automático ----------
info "Creando accesos..."

mkdir -p "$AUTOSTART_DIR" "$APPS_DIR"

DESKTOP_ENTRY="[Desktop Entry]
Type=Application
Name=Box Tray
Comment=Sincronización de Box con rclone
Exec=$APP_DIR/box-tray.py
Icon=$APP_DIR/icons/synced.svg
Terminal=false
Categories=Utility;Network;
X-GNOME-Autostart-enabled=true"

echo "$DESKTOP_ENTRY" > "$APPS_DIR/box-tray.desktop"
echo "$DESKTOP_ENTRY" > "$AUTOSTART_DIR/box-tray.desktop"
ok "Box Tray arrancará solo al iniciar sesión."


# ---------- 8. Iniciar ----------
if [ "$REMOTE_READY" = true ] && ask "¿Iniciar Box Tray ahora?"; then
  nohup "$APP_DIR/box-tray.py" > /dev/null 2>&1 &
  disown
  ok "Box Tray iniciado."
fi

echo -e "\n\e[1;32mListo.\e[0m"
