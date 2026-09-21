#!/usr/bin/env python3
"""
setup_wizard.py
Asistente de primera configuración de Box Tray.

box-tray.py lo muestra una sola vez, al arrancar cuando todavía no existe
box-tray.conf. Acá el usuario:
  - Elige el remoto de rclone y la carpeta local a sincronizar.
  - Inicia sesión en Box (abre una terminal con 'rclone config create').
  - Elige el modo de sincronización. Por ahora solo existe "Sincronizar
    todo" (rclone bisync); "Streaming" (bajar cada archivo solo al
    abrirlo) queda deshabilitado como aviso de "próximamente": es una
    arquitectura distinta (rclone mount) que todavía no está implementada.
  - Elige el intervalo de sincronización automática.
  - Activa o no el inicio automático al iniciar sesión en el sistema.

Al presionar "Finalizar" se guarda box-tray.conf y box-interval, se deja
o se saca el acceso directo de autostart, y se ofrece hacer la primera
sincronización (--resync).

Las funciones is_autostart_enabled() / set_autostart_enabled() también
las usa box-tray.py, para el ítem del menú que prende o apaga el inicio
automático después de la instalación.
"""

import os
import subprocess

from PyQt5.QtCore import QProcess, QTimer
from PyQt5.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)


# ---------- ACCESO DIRECTO DE AUTOSTART ----------
# Vive acá (y no en box-tray.py) porque tanto el asistente como el ítem
# del menú "Iniciar automáticamente..." necesitan crear/borrar el mismo
# archivo con el mismo contenido.

def autostart_file(autostart_dir):
    return os.path.join(autostart_dir, "box-tray.desktop")


def is_autostart_enabled(autostart_dir):
    return os.path.exists(autostart_file(autostart_dir))


def set_autostart_enabled(app_dir, autostart_dir, enabled):
    os.makedirs(autostart_dir, exist_ok=True)
    path = autostart_file(autostart_dir)

    if enabled:
        entry = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Box Tray\n"
            "Comment=Sincronización de Box con rclone\n"
            f"Exec={os.path.join(app_dir, 'box-tray.py')}\n"
            f"Icon={os.path.join(app_dir, 'icons', 'synced.svg')}\n"
            "Terminal=false\n"
            "Categories=Utility;Network;\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(entry)
    else:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


# ---------- ASISTENTE ----------
class SetupWizard(QDialog):
    """
    Ventana modal de primera configuración.
    Si el usuario la cierra sin presionar "Finalizar", exec_() devuelve
    QDialog.Rejected y box-tray.py debe salir: sin box-tray.conf no hay
    nada que sincronizar.
    """

    def __init__(self, app_dir, cfg_dir, config_file, interval_file,
                 autostart_dir, intervals, default_interval):
        super().__init__()
        self.app_dir = app_dir
        self.cfg_dir = cfg_dir
        self.config_file = config_file
        self.interval_file = interval_file
        self.autostart_dir = autostart_dir
        self.intervals = intervals
        self.default_interval = default_interval
        self.boxsync_script = os.path.join(app_dir, "boxsync.sh")

        self.remote_connected = False
        self.login_started = False
        self.resync_process = None

        self.setWindowTitle("Configurar Box Tray")
        self.setMinimumWidth(440)
        self.build_ui()

        # Revisa la conexión cada 1.5 s (por si el usuario ya tenía el
        # remoto de una instalación anterior, o termina el login en la
        # terminal mientras esta ventana sigue abierta).
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.check_connection)
        self.poll_timer.start(1500)
        self.check_connection()

    # ----- Interfaz -----

    def build_ui(self):
        layout = QVBoxLayout(self)

        # ---------- Conexión a Box ----------
        connection_box = QGroupBox("Conexión a Box")
        connection_layout = QVBoxLayout(connection_box)

        remote_row = QHBoxLayout()
        remote_row.addWidget(QLabel("Nombre del remoto:"))
        self.remote_input = QLineEdit("box")
        remote_row.addWidget(self.remote_input)
        connection_layout.addLayout(remote_row)

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Carpeta local:"))
        self.folder_input = QLineEdit(os.path.expanduser("~/Box"))
        folder_row.addWidget(self.folder_input)
        browse_btn = QPushButton("Elegir...")
        browse_btn.clicked.connect(self.browse_folder)
        folder_row.addWidget(browse_btn)
        connection_layout.addLayout(folder_row)

        login_row = QHBoxLayout()
        self.login_btn = QPushButton("Iniciar sesión en Box")
        self.login_btn.clicked.connect(self.start_login)
        login_row.addWidget(self.login_btn)
        self.connection_label = QLabel("Sin conectar")
        login_row.addWidget(self.connection_label)
        login_row.addStretch()
        connection_layout.addLayout(login_row)

        layout.addWidget(connection_box)

        # ---------- Modo de sincronización ----------
        mode_box = QGroupBox("Modo de sincronización")
        mode_layout = QVBoxLayout(mode_box)

        self.mode_all = QRadioButton("Sincronizar todo (recomendado)")
        self.mode_all.setChecked(True)
        mode_layout.addWidget(self.mode_all)

        self.mode_streaming = QRadioButton(
            "Streaming: bajar cada archivo solo al abrirlo, subirlo al guardar (próximamente)"
        )
        self.mode_streaming.setEnabled(False)
        mode_layout.addWidget(self.mode_streaming)

        layout.addWidget(mode_box)

        # ---------- Intervalo ----------
        interval_box = QGroupBox("Intervalo de sincronización automática")
        interval_layout = QHBoxLayout(interval_box)
        self.interval_group = QButtonGroup(self)
        for seconds in self.intervals:
            radio = QRadioButton(f"{seconds}s")
            radio.setChecked(seconds == self.default_interval)
            self.interval_group.addButton(radio, seconds)
            interval_layout.addWidget(radio)
        layout.addWidget(interval_box)

        # ---------- Inicio automático ----------
        self.autostart_check = QCheckBox("Iniciar Box Tray automáticamente al iniciar sesión")
        self.autostart_check.setChecked(True)
        layout.addWidget(self.autostart_check)

        # ---------- Botones ----------
        buttons_row = QHBoxLayout()
        self.status_label = QLabel("")
        buttons_row.addWidget(self.status_label)
        buttons_row.addStretch()
        self.finish_btn = QPushButton("Finalizar")
        self.finish_btn.setEnabled(False)
        self.finish_btn.clicked.connect(self.finish)
        buttons_row.addWidget(self.finish_btn)
        layout.addLayout(buttons_row)

    # ----- Conexión a Box -----

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Elegir carpeta", self.folder_input.text())
        if folder:
            self.folder_input.setText(folder)

    def remote_name(self):
        return self.remote_input.text().strip() or "box"

    def remote_exists(self):
        try:
            result = subprocess.run(
                ["rclone", "listremotes"], capture_output=True, text=True, timeout=5, check=False
            )
            return f"{self.remote_name()}:" in result.stdout.splitlines()
        except (subprocess.SubprocessError, OSError):
            return False

    def start_login(self):
        self.login_started = True
        command = ["rclone", "config", "create", self.remote_name(), "box"]
        try:
            subprocess.Popen(["x-terminal-emulator", "-e"] + command)
        except FileNotFoundError:
            QMessageBox.warning(
                self,
                "No encontré una terminal",
                "Ejecuta esto a mano en una terminal:\n" + " ".join(command),
            )

    def check_connection(self):
        self.remote_connected = self.remote_exists()

        if self.remote_connected:
            self.connection_label.setText(f"✓ Conectado como '{self.remote_name()}'")
        elif self.login_started:
            self.connection_label.setText("Esperando confirmación en el navegador...")
        else:
            self.connection_label.setText("Sin conectar")

        self.finish_btn.setEnabled(self.remote_connected)

    # ----- Finalizar -----

    def finish(self):
        if not self.remote_connected:
            return

        local_dir = self.folder_input.text().strip() or os.path.expanduser("~/Box")
        os.makedirs(local_dir, exist_ok=True)

        self.write_config(self.remote_name(), local_dir)
        self.write_interval(self.interval_group.checkedId())
        set_autostart_enabled(self.app_dir, self.autostart_dir, self.autostart_check.isChecked())

        answer = QMessageBox.question(
            self,
            "Primera sincronización",
            f"Se juntará lo que haya en {local_dir} y en Box. No se borra nada.\n"
            "¿Hacerlo ahora? (puede tardar, sobre todo si hay muchos archivos)",
        )
        if answer == QMessageBox.Yes:
            self.run_first_sync()
        else:
            self.accept()

    def write_config(self, remote, local_dir):
        os.makedirs(self.cfg_dir, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            f.write(
                "# Configuración de box-tray (la leen boxsync.sh y box-tray.py)\n\n"
                "# Remoto de rclone (con los dos puntos al final)\n"
                f'REMOTE="{remote}:"\n\n'
                "# Carpeta local que se sincroniza\n"
                f'LOCAL_DIR="{local_dir}"\n\n'
                '# Color de los íconos: "#ffffff" para panel oscuro, "#000000" para panel claro\n'
                'ICON_COLOR="#ffffff"\n'
            )

    def write_interval(self, seconds):
        with open(self.interval_file, "w", encoding="utf-8") as f:
            f.write(str(seconds))

    def run_first_sync(self):
        self.finish_btn.setEnabled(False)
        self.login_btn.setEnabled(False)
        self.status_label.setText("Sincronizando por primera vez...")

        # QProcess (no bloquea la ventana) en vez de subprocess.run: el
        # resync puede tardar y no queremos congelar el asistente.
        self.resync_process = QProcess(self)
        self.resync_process.setStandardOutputFile(QProcess.nullDevice())
        self.resync_process.setStandardErrorFile(QProcess.nullDevice())
        self.resync_process.finished.connect(self.on_first_sync_finished)
        self.resync_process.start(self.boxsync_script, ["--resync", "--force"])

    def on_first_sync_finished(self, exit_code, _exit_status):
        if exit_code != 0:
            QMessageBox.warning(
                self,
                "Sincronización con errores",
                "El primer resync terminó con errores. Revisa el registro desde el "
                "menú de Box Tray ('Ver registro') y prueba 'Sincronizar ahora'.",
            )
        self.accept()
