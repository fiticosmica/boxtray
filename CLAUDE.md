# boxtray

Sincronización bidireccional de Box.com en Linux (Debian + KDE Plasma) usando
`rclone bisync`, con un ícono en la bandeja del sistema hecho en PyQt5.

## Estructura

- `src/boxsync.sh` → hace la sincronización (lock huérfano, excludes, logs, estado).
- `src/box-tray.py` → ícono de bandeja. Decide CUÁNDO sincronizar y muestra el estado.
  Toda la lógica de sync vive en `boxsync.sh`; el tray solo lo llama.
- `icons/*.svg` → íconos con `currentColor` (el tray lo reemplaza por `ICON_COLOR`).
- `install.sh` / `uninstall.sh` → instalación en la carpeta del usuario, sin root.

## Rutas en el sistema

- Programa instalado: `~/.local/share/box-tray/`
- Configuración: `~/.config/box-tray/box-tray.conf` (la leen el script y el tray)
- Estado, pausa e intervalo: `~/.config/box-tray/box-status`, `box-paused`, `box-interval`
- Logs: `~/.local/state/box-tray/logs/`
- Acceso de rclone: `~/.config/rclone/rclone.conf`

## Flujo de trabajo

- `install.sh` COPIA los archivos. Después de editar algo en el repo, hay que
  ejecutar `./install.sh` para que el tray instalado use los cambios.
- Verificar siempre con `bash -n`, `shellcheck` y `python3 -m py_compile` antes de dar algo por terminado.
- Para probar `boxsync.sh` sin tocar Box, usar un `rclone` falso en el PATH.
- Commits en español, cortos y descriptivos.

## Reglas importantes

- NUNCA ejecutar `boxsync --resync` ni borrar nada dentro de la carpeta sincronizada
  (`~/Box`) sin preguntarme antes: son mis archivos reales.
- NUNCA subir `rclone.conf` ni tokens al repo.
- rclone mínimo: 1.66 (por `--conflict-resolve` y `--recover`).

## Cómo quiero el código

- Fácil de entender antes que óptimo o liviano. No importan llaves de más ni
  saltos de línea extra si queda más claro.
- Nada de código espagueti: que se entienda de dónde viene cada cosa.
- Ordenado y bien indentado, con secciones separadas por comentarios
  (`# ---------- NOMBRE ----------`).
- Nombres descriptivos; el buen código se documenta solo. Comentarios solo
  donde explican el POR QUÉ.
- Comentarios, mensajes al usuario y README en español de Chile, sin voseo.

## Cómo quiero las respuestas

- Cortas, y dame opciones cuando haya más de un camino.
- Si algo tiene implicancias legales (licencias, marcas, etc.), menciónalo en una
  línea, sin sermón.
