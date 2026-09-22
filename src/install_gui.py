#!/usr/bin/env python3
"""
install_gui.py
Instalador gráfico de Box Tray.

install.sh solo hace lo mínimo indispensable para poder mostrar una
ventana (asegurar que exista Python3 + PyQt5) y le pasa la posta a este
programa. De acá para adelante todo es ventanas: nada de preguntas por
consola.

Pasos:
  1. Revisa/instala rclone (con pkexec: pide la clave en un diálogo
     gráfico, no en la terminal).
  2. Revisa/instala el resto de las dependencias del sistema
     (notify-send, xdg-open, curl).
  3. Copia los archivos del programa a ~/.local/share/box-tray.
  4. Crea los accesos directos: comandos 'boxsync'/'box-tray' y el menú
     de aplicaciones.
  5. Arranca box-tray.py. Si es la primera vez, box-tray.py muestra su
     propio asistente (setup_wizard.py) para el login a Box, la carpeta,
     el intervalo, etc.

Uso: install_gui.py <REPO_DIR>
"""

import glob
import os
import shutil
import subprocess
import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


RCLONE_MIN_VERSION = (1, 66, 0)

# comando -> paquete que lo provee
SYSTEM_PACKAGES = {
    "notify-send": "libnotify-bin",
    "xdg-open": "xdg-utils",
    "curl": "curl",
}


class Installer(QWidget):

    def __init__(self, repo_dir):
        super().__init__()
        self.repo_dir = repo_dir
        self.app_dir = os.path.expanduser("~/.local/share/box-tray")
        self.bin_dir = os.path.expanduser("~/.local/bin")
        self.apps_dir = os.path.expanduser("~/.local/share/applications")

        self.setWindowTitle("Instalando Box Tray")
        self.resize(520, 340)

        layout = QVBoxLayout(self)
        self.title_label = QLabel("Preparando la instalación...")
        layout.addWidget(self.title_label)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)

        self.close_btn = QPushButton("Cerrar")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)

        self.show()
        # Se arranca la instalación después de que la ventana ya se
        # terminó de dibujar, para que no se vea congelada desde el inicio.
        QTimer.singleShot(100, self.run_install)

    # ----- Utilidades de progreso -----

    def step(self, text):
        self.title_label.setText(text)
        self.log.appendPlainText(text)
        QApplication.processEvents()

    def run_privileged(self, description, shell_command):
        """Corre un comando como root con pkexec: pide la clave en un
        diálogo gráfico del sistema, nunca en esta ventana ni en una
        terminal."""
        self.step(description)
        try:
            result = subprocess.run(
                ["pkexec", "bash", "-c", shell_command],
                capture_output=True, text=True, check=False,
            )
        except FileNotFoundError:
            self.fail(
                "No encontré 'pkexec' (paquete policykit-1), necesario para "
                "instalar cosas como administrador desde una ventana.\n\n"
                "Instálalo con: sudo apt install policykit-1\n"
                "y vuelve a correr ./install.sh"
            )
            return False

        if result.stdout.strip():
            self.log.appendPlainText(result.stdout.strip())
        if result.returncode != 0:
            if result.stderr.strip():
                self.log.appendPlainText(result.stderr.strip())
            return False
        return True

    def fail(self, message):
        self.log.appendPlainText(f"ERROR: {message}")
        QMessageBox.critical(self, "No se pudo instalar", message)
        self.title_label.setText("La instalación falló.")
        self.close_btn.setEnabled(True)

    # ----- Pasos de la instalación -----

    def run_install(self):
        # Si el tray ya estaba corriendo (actualización), se cierra antes
        # de copiar archivos nuevos encima.
        subprocess.run(["pkill", "-f", "box-tray/box-tray.py"], check=False)

        if not self.ensure_rclone():
            return
        if not self.ensure_system_packages():
            return

        self.copy_files()
        self.create_shortcuts()

        self.step("Listo. Iniciando Box Tray...")
        self.launch_tray()

        self.title_label.setText("Instalación completada.")
        self.close_btn.setEnabled(True)

    def rclone_version(self):
        try:
            output = subprocess.run(
                ["rclone", "version"], capture_output=True, text=True, check=False
            ).stdout
            first_word = output.splitlines()[0].split()[1]    # "rclone v1.66.0"
            numbers = first_word.lstrip("v").split("-")[0]    # por si trae "-DEV"
            return tuple(int(n) for n in numbers.split("."))
        except (subprocess.SubprocessError, IndexError, ValueError, OSError):
            return (0, 0, 0)

    def ensure_rclone(self):
        self.step("Revisando rclone...")
        current = self.rclone_version()

        if current >= RCLONE_MIN_VERSION:
            self.log.appendPlainText(f"rclone {'.'.join(map(str, current))} ya está instalado.")
            return True

        if current == (0, 0, 0):
            self.log.appendPlainText("rclone no está instalado.")
        else:
            self.log.appendPlainText(
                f"rclone {'.'.join(map(str, current))} es muy antiguo "
                f"(se necesita {'.'.join(map(str, RCLONE_MIN_VERSION))} o superior)."
            )

        # La versión de apt suele ser vieja; se quita para que un futuro
        # 'apt upgrade' no la vuelva a instalar por encima de la nueva.
        command = (
            "dpkg -s rclone >/dev/null 2>&1 && apt-get remove -y rclone; "
            "curl -fsSL https://rclone.org/install.sh | bash"
        )
        self.run_privileged("Instalando rclone desde rclone.org...", command)

        current = self.rclone_version()
        if current < RCLONE_MIN_VERSION:
            self.fail("No se pudo instalar una versión compatible de rclone.")
            return False

        self.log.appendPlainText(f"rclone {'.'.join(map(str, current))} instalado.")
        return True

    def ensure_system_packages(self):
        self.step("Revisando dependencias del sistema...")
        missing = sorted({pkg for cmd, pkg in SYSTEM_PACKAGES.items() if not shutil.which(cmd)})

        if not missing:
            self.log.appendPlainText("Dependencias del sistema listas.")
            return True

        ok = self.run_privileged(
            f"Instalando: {', '.join(missing)}...",
            f"apt-get update && apt-get install -y {' '.join(missing)}",
        )
        if not ok:
            self.fail("No se pudieron instalar las dependencias del sistema.")
            return False
        return True

    def copy_files(self):
        self.step("Copiando archivos...")

        icons_dir = os.path.join(self.app_dir, "icons")
        os.makedirs(icons_dir, exist_ok=True)
        os.makedirs(self.bin_dir, exist_ok=True)

        for name in ("boxsync.sh", "box-tray.py", "setup_wizard.py"):
            src = os.path.join(self.repo_dir, "src", name)
            dst = os.path.join(self.app_dir, name)
            shutil.copyfile(src, dst)
            os.chmod(dst, 0o755)

        for icon in glob.glob(os.path.join(self.repo_dir, "icons", "*.svg")):
            shutil.copyfile(icon, os.path.join(icons_dir, os.path.basename(icon)))

        # URL del proyecto, tomada del 'git remote' del repo clonado.
        # Convierte git@github.com:usuario/repo.git -> https://github.com/usuario/repo
        repo_url = subprocess.run(
            ["git", "-C", self.repo_dir, "remote", "get-url", "origin"],
            capture_output=True, text=True, check=False,
        ).stdout.strip()
        if repo_url.endswith(".git"):
            repo_url = repo_url[:-len(".git")]
        repo_url = repo_url.replace("git@github.com:", "https://github.com/")
        with open(os.path.join(self.app_dir, "repo-url"), "w", encoding="utf-8") as f:
            f.write(repo_url)

    def create_shortcuts(self):
        self.step("Creando accesos...")

        # Comandos cortos 'boxsync' y 'box-tray'
        for link_name, target in (("boxsync", "boxsync.sh"), ("box-tray", "box-tray.py")):
            link_path = os.path.join(self.bin_dir, link_name)
            if os.path.islink(link_path) or os.path.exists(link_path):
                os.remove(link_path)
            os.symlink(os.path.join(self.app_dir, target), link_path)

        # Acceso en el menú de aplicaciones. El de autostart NO se crea
        # acá: lo maneja box-tray.py (asistente de primera vez + ítem del
        # menú "Iniciar automáticamente al iniciar sesión").
        os.makedirs(self.apps_dir, exist_ok=True)
        entry = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Box Tray\n"
            "Comment=Sincronización de Box con rclone\n"
            f"Exec={os.path.join(self.app_dir, 'box-tray.py')}\n"
            f"Icon={os.path.join(self.app_dir, 'icons', 'synced.svg')}\n"
            "Terminal=false\n"
            "Categories=Utility;Network;\n"
        )
        with open(os.path.join(self.apps_dir, "box-tray.desktop"), "w", encoding="utf-8") as f:
            f.write(entry)

        if self.bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
            self.log.appendPlainText(
                f"Aviso: {self.bin_dir} no está en tu PATH. Cierra sesión y "
                "vuelve a entrar para usar 'boxsync' desde la terminal."
            )

    def launch_tray(self):
        subprocess.Popen(
            [sys.executable, os.path.join(self.app_dir, "box-tray.py")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: install_gui.py <REPO_DIR>", file=sys.stderr)
        sys.exit(1)

    app = QApplication(sys.argv)
    installer = Installer(sys.argv[1])
    sys.exit(app.exec_())
