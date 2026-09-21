# boxtray

Sincronización bidireccional de Box.com en Linux usando `rclone bisync`, con un ícono en la bandeja del sistema.

- Sincroniza automáticamente cada 10 s, 30 s, 1 min, 2 min o 5 min (se elige desde el menú).
- Ícono con el estado: sincronizando, sincronizado, error o en pausa.
- Clic izquierdo: sincronizar ahora.
- Limpia solo los locks huérfanos de rclone.
- Ignora los archivos de bloqueo de LibreOffice/Office.

Probado en Debian con KDE Plasma.

## Instalación

```bash
git clone https://github.com/fiticosmica/boxtray.git
cd boxtray
./install.sh
```

El instalador:

1. Instala las dependencias que falten (`python3-pyqt5`, `libnotify-bin`, etc.).
2. Instala rclone desde rclone.org si no está o si es muy antiguo (se necesita 1.66 o superior; el de los repos de Debian no sirve).
3. Crea el acceso en el menú de aplicaciones.
4. Te pregunta si quieres iniciar Box Tray. La primera vez que se abre aparece
   una ventana de configuración (ver abajo).

## Primera configuración

Al abrir Box Tray por primera vez aparece una ventana donde eliges:

- **Nombre del remoto y carpeta local** a sincronizar.
- **Iniciar sesión en Box**: se abre una terminal con el navegador; entras a tu
  cuenta y presionas **Otorgar acceso a Box**. No hay que escribir usuario ni
  contraseña en ningún lado de Box Tray. rclone guarda el acceso en
  `~/.config/rclone/rclone.conf`.
- **Modo de sincronización**: por ahora solo está disponible "Sincronizar
  todo" (`rclone bisync`, baja y sube todo). "Streaming" (bajar cada archivo
  solo al abrirlo) va a llegar más adelante.
- **Intervalo de sincronización automática**.
- **Inicio automático al iniciar sesión** en el sistema (se puede cambiar
  después desde el menú del ícono).

Al terminar, se ofrece hacer la primera sincronización (`--resync`, obligatoria
la primera vez en cada equipo).

Si Box vence el acceso (pasa si el equipo queda más de 60 días sin sincronizar), usa **Volver a iniciar sesión en Box** en el menú del ícono.

## Actualizar

```bash
cd boxtray
git pull
./install.sh
```

Tu configuración se conserva.

## Desinstalar

```bash
./uninstall.sh
```

No borra tu carpeta sincronizada ni el remoto de rclone.

## Uso desde la terminal

```bash
boxsync             # sync normal
boxsync --resync    # resync completo
boxsync --force     # sincroniza aunque esté en pausa
```

## Archivos

| Qué                 | Dónde                                  |
|---------------------|----------------------------------------|
| Programa            | `~/.local/share/box-tray/`             |
| Configuración       | `~/.config/box-tray/box-tray.conf`     |
| Logs (14 días)      | `~/.local/state/box-tray/logs/`        |

## Importante

- **Cada equipo necesita su propio `rclone config`.** No copies `rclone.conf` entre equipos: Box renueva el token cada vez que se usa, así que dos equipos con el mismo token terminan desautorizándose entre sí.
- **Nunca subas tu `rclone.conf` a GitHub**: contiene el acceso a tu cuenta.
- Intervalos muy cortos (10 s) hacen muchas llamadas a la API de Box; si ves errores de límite de peticiones, sube el intervalo.
