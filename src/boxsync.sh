#!/bin/bash
#
# boxsync.sh
# Sincroniza una carpeta local con Box.com usando rclone bisync.
#
# - Lee la configuración desde ~/.config/box-tray/box-tray.conf
# - Limpia el lock huérfano si no hay otro rclone bisync corriendo.
# - Escribe el estado (syncing / synced / error) para que box-tray.py
#   muestre el ícono correcto.
#
# Uso:
#   boxsync              -> sync normal (incremental)
#   boxsync --resync     -> resync completo (obligatorio la primera vez en un equipo)
#   boxsync --force      -> sincroniza aunque el tray esté en pausa
#

set -euo pipefail


# ---------- RUTAS ----------
CFG_DIR="$HOME/.config/box-tray"
CONFIG_FILE="$CFG_DIR/box-tray.conf"
STATUS_FILE="$CFG_DIR/box-status"
PAUSE_FILE="$CFG_DIR/box-paused"

LOG_DIR="$HOME/.local/state/box-tray/logs"
LOG_FILE="$LOG_DIR/boxsync_$(date +%Y%m%d).log"
LOG_DAYS=14                                   # los logs más antiguos se borran solos


# ---------- CONFIGURACIÓN ----------
# Valores por defecto; box-tray.conf los sobrescribe si existe.
REMOTE="box:"
LOCAL_DIR="$HOME/Box"

if [ -f "$CONFIG_FILE" ]; then
  # shellcheck source=/dev/null
  source "$CONFIG_FILE"
fi

mkdir -p "$CFG_DIR" "$LOG_DIR"


# ---------- FUNCIONES ----------
usage() {
  echo "Uso: boxsync [--resync] [--force]"
  echo "  --resync   resync completo (obligatorio la primera vez en un equipo)"
  echo "  --force    sincroniza aunque la pausa esté activa"
}

log() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

write_status() {
  echo -n "$1" > "$STATUS_FILE" 2>/dev/null || true
}

# Convierte una ruta al formato que usa rclone para nombrar el lock.
# Ej: "/home/fiti/Box" -> "home_fiti_Box"   |   "box:" -> "box_"
lock_part() {
  local path="$1"
  path="${path#/}"          # quita el "/" inicial
  path="${path%/}"          # quita el "/" final, si lo hay
  path="${path//\//_}"      # "/" -> "_"
  path="${path//:/_}"       # ":" -> "_"
  echo "$path"
}


# ---------- ARGUMENTOS ----------
RESYNC=false
FORCE=false

for arg in "$@"; do
  case "$arg" in
    --resync)  RESYNC=true ;;
    --force)   FORCE=true ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Opción desconocida: $arg"
      usage
      exit 2
      ;;
  esac
done


# ---------- 1. Respetar la pausa del tray ----------
if [ -f "$PAUSE_FILE" ] && [ "$FORCE" = false ]; then
  echo "Sincronización en pausa. Usa --force para saltarte la pausa."
  exit 0
fi


# ---------- 2. ¿Hay un rclone bisync REALMENTE corriendo? ----------
if pgrep -f "rclone bisync $LOCAL_DIR" > /dev/null; then
  log "AVISO: ya hay un 'rclone bisync' corriendo para $LOCAL_DIR. Saliendo."
  exit 1
fi


# ---------- 3. Si no hay proceso pero existe el lock, es huérfano ----------
LOCK_FILE="$HOME/.cache/rclone/bisync/$(lock_part "$LOCAL_DIR")..$(lock_part "$REMOTE").lck"

if [ -f "$LOCK_FILE" ]; then
  log "Lock huérfano detectado (sin proceso activo). Borrando: $LOCK_FILE"
  rm -f "$LOCK_FILE"
fi


# ---------- 4. Limpiar logs antiguos ----------
find "$LOG_DIR" -name "boxsync_*.log" -mtime +"$LOG_DAYS" -delete 2>/dev/null || true


# ---------- 5. Ejecutar bisync ----------
RCLONE_ARGS=(
  bisync "$LOCAL_DIR" "$REMOTE"
  --resilient
  --recover
  --conflict-resolve newer
  # Archivos de bloqueo de LibreOffice/Office (causan "corrupted on transfer")
  --exclude ".~lock.*#"
  --exclude "~\$*"
  -v
)

if [ "$RESYNC" = true ]; then
  RCLONE_ARGS+=(--resync)
  log "Ejecutando RESYNC completo entre $LOCAL_DIR y $REMOTE ..."
else
  log "Ejecutando bisync incremental entre $LOCAL_DIR y $REMOTE ..."
fi

write_status "syncing"

# set +e: si rclone falla, queremos capturar el código y escribir "error",
# no que el script se corte y deje el ícono pegado en "sincronizando".
set +e
rclone "${RCLONE_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
STATUS=${PIPESTATUS[0]}
set -e

if [ "$STATUS" -eq 0 ]; then
  log "Bisync completado correctamente."
  write_status "synced"
else
  log "Bisync terminó con errores (código $STATUS). Revisa el log."
  write_status "error"
fi

exit "$STATUS"
