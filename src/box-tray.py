#!/usr/bin/env python3
"""
box-tray.py
Ícono en la bandeja del sistema para sincronizar Box con rclone.

- Ejecuta boxsync.sh cada N segundos (según el intervalo elegido en el menú).
- Muestra el estado con un ícono: sincronizando, sincronizado, error o en pausa.
- Toda la lógica de sincronización vive en boxsync.sh; este programa solo
  decide CUÁNDO llamarlo y muestra el resultado.
"""

import glob
import os
import subprocess
import sys

from PyQt5.QtCore import QByteArray, QProcess, Qt, QTimer
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QMenu,
    QSystemTrayIcon,
)

# Está en la misma carpeta (APP_DIR); se agrega al principio del import
# porque necesitamos APP_DIR antes de poder importarlo normalmente.
sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from setup_wizard import SetupWizard, is_autostart_enabled, set_autostart_enabled  # noqa: E402


# ---------- RUTAS ----------
# Carpeta donde está instalado este archivo (funciona aunque se llame por symlink)
APP_DIR = os.path.dirname(os.path.realpath(__file__))
ICON_DIR = os.path.join(APP_DIR, "icons")
BOXSYNC_SCRIPT = os.path.join(APP_DIR, "boxsync.sh")
REPO_URL_FILE = os.path.join(APP_DIR, "repo-url")      # lo escribe install.sh

CFG_DIR = os.path.expanduser("~/.config/box-tray")
CONFIG_FILE = os.path.join(CFG_DIR, "box-tray.conf")
STATUS_FILE = os.path.join(CFG_DIR, "box-status")
INTERVAL_FILE = os.path.join(CFG_DIR, "box-interval")
PAUSE_FILE = os.path.join(CFG_DIR, "box-paused")
LOG_DIR = os.path.expanduser("~/.local/state/box-tray/logs")
AUTOSTART_DIR = os.path.expanduser("~/.config/autostart")

BOX_WEB = "https://app.box.com"


# ---------- OPCIONES ----------
INTERVALS = [10, 30, 60, 120, 300]    # en segundos
DEFAULT_INTERVAL = 30

ICON_FILES = {
    "syncing": "syncing.svg",
    "synced":  "synced.svg",
    "error":   "error.svg",
    "paused":  "paused.svg",
    "unknown": "synced.svg",
}

STATUS_LABELS = {
    "syncing": "Sincronizando...",
    "synced":  "Todo sincronizado",
    "error":   "Error al sincronizar",
    "paused":  "Sincronización en pausa",
    "unknown": "Esperando la primera sincronización",
}


# ---------- CONFIGURACIÓN ----------
def read_config():
    """
    Lee box-tray.conf (el mismo archivo que usa boxsync.sh).
    Formato: CLAVE="valor", una por línea. Las líneas con # se ignoran.
    """
    config = {
        "REMOTE": "box:",
        "LOCAL_DIR": "$HOME/Box",
        "ICON_COLOR": "#ffffff",
    }

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()

                if not line or line.startswith("#") or "=" not in line:
                    continue

                key, value = line.split("=", 1)
                config[key.strip()] = value.strip().strip('"').strip("'")

    config["LOCAL_DIR"] = os.path.expandvars(os.path.expanduser(config["LOCAL_DIR"]))
    return config


def read_interval():
    try:
        with open(INTERVAL_FILE) as f:
            value = int(f.read().strip())
        return value if value in INTERVALS else DEFAULT_INTERVAL
    except (FileNotFoundError, ValueError):
        return DEFAULT_INTERVAL


def write_interval(value):
    with open(INTERVAL_FILE, "w") as f:
        f.write(str(value))


def read_status():
    try:
        with open(STATUS_FILE) as f:
            return f.read().strip() or "unknown"
    except FileNotFoundError:
        return "unknown"


def write_status(status):
    try:
        with open(STATUS_FILE, "w") as f:
            f.write(status)
    except OSError:
        pass


def read_repo_url():
    try:
        with open(REPO_URL_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""


def is_paused():
    return os.path.exists(PAUSE_FILE)


def notify(message):
    subprocess.Popen(["notify-send", "Box", message])


# ---------- ÍCONOS ----------
def render_icon(svg_path, color):
    """Carga un SVG, reemplaza 'currentColor' por el color elegido y lo convierte en QIcon."""
    with open(svg_path, "r", encoding="utf-8") as f:
        svg = f.read().replace("currentColor", color)

    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    icon = QIcon(pixmap)
    if icon.isNull():
        print(f"[box-tray] AVISO: el ícono generado desde {svg_path} quedó vacío.", file=sys.stderr)

    return icon


# ---------- APLICACIÓN ----------
class BoxTray:

    def __init__(self, app):
        self.app = app
        self.config = read_config()
        self.sync_process = None
        self.current_status = None

        os.makedirs(CFG_DIR, exist_ok=True)
        if not os.path.exists(INTERVAL_FILE):
            write_interval(DEFAULT_INTERVAL)

        # Ícono de la bandeja
        self.tray = QSystemTrayIcon()
        self.build_menu()
        self.tray.activated.connect(self.on_activated)
        self.update_status()
        self.tray.show()

        # Refresca el ícono cada 2 s (también refleja syncs lanzadas desde la terminal)
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(2000)

        # Temporizador de la sincronización automática.
        # Es de un solo disparo: se vuelve a programar al terminar cada sync,
        # así nunca se juntan dos sincronizaciones.
        self.sync_timer = QTimer()
        self.sync_timer.setSingleShot(True)
        self.sync_timer.timeout.connect(self.auto_sync)

        # Primera sincronización al iniciar
        if not is_paused():
            self.run_sync()

    # ----- Menú -----

    def build_menu(self):
        menu = QMenu()
        menu.addAction("Sincronizar ahora", self.force_sync)
        menu.addAction("Abrir carpeta Box", self.open_folder)
        menu.addAction("Abrir Box en la web", self.open_web)
        menu.addAction("Ver registro (log)", self.open_log)
        menu.addSeparator()

        # Submenú de intervalo
        interval_menu = menu.addMenu("Intervalo de sincronización")
        self.interval_group = QActionGroup(self.app)
        self.interval_group.setExclusive(True)
        current_interval = read_interval()

        for seconds in INTERVALS:
            action = QAction(f"Cada {seconds} segundos", self.app, checkable=True)
            action.setChecked(seconds == current_interval)
            action.triggered.connect(lambda _checked, value=seconds: self.set_interval(value))
            self.interval_group.addAction(action)
            interval_menu.addAction(action)

        # Pausar / reanudar
        self.pause_action = QAction("Pausar sincronización automática", self.app, checkable=True)
        self.pause_action.setChecked(is_paused())
        self.pause_action.triggered.connect(self.toggle_pause)
        menu.addAction(self.pause_action)

        # Inicio automático al iniciar sesión en el sistema
        self.autostart_action = QAction(
            "Iniciar automáticamente al iniciar sesión", self.app, checkable=True
        )
        self.autostart_action.setChecked(is_autostart_enabled(AUTOSTART_DIR))
        self.autostart_action.triggered.connect(self.toggle_autostart)
        menu.addAction(self.autostart_action)

        menu.addSeparator()
        menu.addAction("Volver a iniciar sesión en Box", self.reconnect)

        # El link solo aparece si se instaló desde un repo clonado con git
        if read_repo_url():
            menu.addAction("Ver proyecto en GitHub", self.open_repo)

        menu.addSeparator()
        menu.addAction("Salir", self.app.quit)

        self.tray.setContextMenu(menu)

    def on_activated(self, reason):
        # Clic izquierdo sobre el ícono = sincronizar ahora
        if reason == QSystemTrayIcon.Trigger:
            self.force_sync()

    # ----- Sincronización -----

    def is_syncing(self):
        return self.sync_process is not None

    def schedule_next_sync(self):
        self.sync_timer.start(read_interval() * 1000)

    def auto_sync(self):
        # Si está en pausa no se reprograma; al reanudar se vuelve a activar.
        if is_paused():
            return
        self.run_sync()

    def force_sync(self):
        if is_paused():
            notify("La sincronización está en pausa")
            return
        if self.is_syncing():
            return

        self.sync_timer.stop()
        self.run_sync()

    def run_sync(self):
        if self.is_syncing():
            return

        self.sync_process = QProcess(self.app)
        # La salida ya queda en el log; no hace falta guardarla en memoria.
        self.sync_process.setStandardOutputFile(QProcess.nullDevice())
        self.sync_process.setStandardErrorFile(QProcess.nullDevice())
        self.sync_process.finished.connect(self.on_sync_finished)
        self.sync_process.errorOccurred.connect(self.on_sync_error)
        self.sync_process.start(BOXSYNC_SCRIPT, [])

        self.update_status()

    def on_sync_finished(self, _exit_code, exit_status):
        # boxsync.sh escribe su propio estado; solo corregimos si el proceso murió.
        if exit_status == QProcess.CrashExit:
            write_status("error")

        self.clear_process()
        self.update_status()

        if not is_paused():
            self.schedule_next_sync()

    def on_sync_error(self, error):
        # Si el script ni siquiera pudo arrancar, 'finished' nunca se emite.
        if error != QProcess.FailedToStart:
            return

        notify(f"No se pudo ejecutar {BOXSYNC_SCRIPT}")
        write_status("error")
        self.clear_process()
        self.update_status()

        if not is_paused():
            self.schedule_next_sync()

    def clear_process(self):
        if self.sync_process is not None:
            self.sync_process.deleteLater()
            self.sync_process = None

    # ----- Opciones del menú -----

    def set_interval(self, seconds):
        write_interval(seconds)

        # Si había una sync programada, se reprograma con el nuevo intervalo
        if self.sync_timer.isActive():
            self.schedule_next_sync()

    def toggle_pause(self):
        if is_paused():
            try:
                os.remove(PAUSE_FILE)
            except FileNotFoundError:
                pass
            self.run_sync()
        else:
            open(PAUSE_FILE, "w").close()
            self.sync_timer.stop()

        self.update_status()

    def toggle_autostart(self):
        set_autostart_enabled(APP_DIR, AUTOSTART_DIR, self.autostart_action.isChecked())

    def open_folder(self):
        subprocess.Popen(["xdg-open", self.config["LOCAL_DIR"]])

    def open_web(self):
        subprocess.Popen(["xdg-open", BOX_WEB])

    def open_repo(self):
        subprocess.Popen(["xdg-open", read_repo_url()])

    def reconnect(self):
        """
        Abre una terminal con 'rclone config reconnect', que vuelve a abrir
        el navegador para iniciar sesión. Útil si Box vence el acceso.
        """
        command = ["rclone", "config", "reconnect", self.config["REMOTE"]]

        try:
            subprocess.Popen(["x-terminal-emulator", "-e"] + command)
        except FileNotFoundError:
            notify("No encontré una terminal. Ejecuta: " + " ".join(command))

    def open_log(self):
        logs = sorted(glob.glob(os.path.join(LOG_DIR, "boxsync_*.log")))

        if logs:
            subprocess.Popen(["xdg-open", logs[-1]])    # el más reciente
        else:
            notify("Aún no hay registro disponible")

    # ----- Estado -----

    def update_status(self):
        status = "paused" if is_paused() else read_status()

        # Solo se redibuja el ícono si el estado cambió
        if status == self.current_status:
            return
        self.current_status = status

        icon_file = os.path.join(ICON_DIR, ICON_FILES.get(status, "synced.svg"))
        self.tray.setIcon(render_icon(icon_file, self.config["ICON_COLOR"]))
        self.tray.setToolTip(f"Box — {STATUS_LABELS.get(status, status)}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Primer arranque: todavía no existe box-tray.conf. Se muestra el
    # asistente antes de crear el ícono de bandeja. Se revisa si
    # box-tray.conf quedó guardado (no si el diálogo se "aceptó"): el
    # asistente lo escribe apenas se presiona "Finalizar", antes de la
    # primera sincronización, así que aunque se cierre la ventana después
    # de eso la configuración ya quedó lista y no hay que pedirla de nuevo.
    if not os.path.exists(CONFIG_FILE):
        wizard = SetupWizard(
            APP_DIR, CFG_DIR, CONFIG_FILE, INTERVAL_FILE, AUTOSTART_DIR,
            INTERVALS, DEFAULT_INTERVAL,
        )
        wizard.exec_()
        if not os.path.exists(CONFIG_FILE):
            sys.exit(0)

    tray = BoxTray(app)
    sys.exit(app.exec_())
