# SURFMOSS Device Servers — Migration Reference

_Single source of truth for installing the SURFMOSS Tango device servers onto
the new Trixie NFS root (`/nfs/pi-trixie` on wolframite) and reconciling them at
the clean-DB cutover. Built from the Python-3 audit, the entry-point inventory,
and the dependency map._

_Last updated: 18-ago-2026_

---

## Estado (08-ago-2026): primera Pi validada en la red nueva

**pi-rackmossbauer arranca Debian 13 por netboot desde `/nfs/pi-trixie`, con
Tango 10, y el Starter lanza sus device servers.** Los únicos fallos restantes son
por hardware ausente (la Pi está en el despacho, no en el laboratorio).

> Corrección del 17-ago-2026: eso no era del todo cierto. Con el hardware presente,
> TempSensorDS18B20 y WisselMCA seguían fallando por defectos del propio código
> (ver sus secciones más abajo). «Falla solo por hardware ausente» era una hipótesis,
> no una comprobación.

Cadena validada de punta a punta: DHCP → TFTP → NFS → sistema → DNS `.lab` → NTP
→ Tango DB → Starter → device servers.

### Tres problemas resueltos ese día (los tres bloqueaban el arranque de DS)

**1. Collations de MariaDB — la causa principal, y la más difícil de ver.**
La base importada del servidor viejo tenía todas las tablas en
`utf8mb4_general_ci`, mientras la base en MariaDB 11 (Debian 13) usaba por defecto
`utf8mb4_uca1400_ai_ci`. Los **procedimientos almacenados** (`ds_start`,
`import_device`…) comparan parámetros con columnas y fallaban con
`ERROR 1267: Illegal mix of collations`. Su `EXIT HANDLER` lo convertía en un
genérico `MySQL Error`, y el Databaseds lo traducía a
**"The device server X is not defined in database. Exiting!"** — mensaje engañoso
que costó todo un día de diagnóstico.

Síntoma característico: las consultas de lectura funcionan (listar instancias,
`--check-server`, `import_device` desde PyTango), pero **arrancar** cualquier device
server falla. Falla igual con Tango 9 y con Tango 10, desde cualquier máquina, por
nombre o por IP. No es problema de versiones ni de red.

Diagnóstico: llamar al procedimiento a mano revela el fallo enmascarado.
```bash
sudo mysql tango -e "CALL ds_start('Starter/pi-rackmossbauer','pi-rackmossbauer',@res); SELECT @res;"
# -> MySQL Error
```
Para ver el error real hay que recrear el procedimiento sin su `EXIT HANDLER`.

Solución:
```bash
sudo mysql -e "ALTER DATABASE tango CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
sudo mysql tango < /usr/share/tango-db/stored_proc.sql   # recrear: conservan el collation de creación
```
⚠️ **Crítico para la reimportación limpia**: si se vuelve a cargar el volcado viejo,
el problema reaparece. El procedimiento debe incluir siempre el ajuste de collation
y la recreación de los procedimientos almacenados.

**2. `argv[0]` con ruta absoluta en los device servers Python.**
Los wrappers que genera `pip install -e` dejan la ruta completa en `sys.argv[0]`
(`/usr/local/bin/ElmitecLEEM2k`). PyTango 10 usa `argv[0]` como nombre de servidor,
y en la DB está registrado como `ElmitecLEEM2k` a secas → no casa.
(El antiguo `setup.py install` usaba `EASY-INSTALL-ENTRY-SCRIPT`, que sí dejaba el
nombre simple; por eso funcionaba antes.)

Solución aplicada a los 41 servidores (31 vivos + inactivos), dentro de la región
protegida de POGO:
```python
sys.argv[0] = os.path.basename(sys.argv[0])
```
Nota: 40 de 41 ficheros **no importaban ni `os` ni `sys`**; hubo que añadir ambos.

**3. Databaseds publicando `0.0.0.0`.**
`/etc/tangorc` tenía `TANGO_HOST=0.0.0.0:10000` (arreglo previo para que escuchara
en todas las interfaces). Sirve para escuchar, pero el IOR publicado lleva
`0.0.0.0` y los clientes remotos no pueden reconectar → `TRANSIENT_CallTimedout` al
pedir `sys/database/2`.

Solución — drop-in `/etc/systemd/system/tango-db.service.d/endpoint.conf`:
```
[Service]
ExecStart=
ExecStart=/usr/lib/tango/Databaseds 2 -ORBendPoint giop:tcp:0.0.0.0:10000 -ORBendPointPublish giop:tcp:10.43.88.3:10000
```

### Otros ajustes de la raíz Trixie (afectan a todas las Pis, es compartida)

- **Firmware de arranque**: la copia inicial solo trajo la partición p2, sin
  `/boot/firmware`. Se obtuvo con `apt install --reinstall raspi-firmware
  linux-image-rpi-v8` dentro del chroot, y se copió a `/tftpboot/<serial>/`.
  (`mkinitramfs` falla en chroot y en raíz NFS — es esperable y **no hace falta**:
  con `root=/dev/nfs` + `ip=dhcp` el kernel monta la raíz sin initrd.)
- **`config.txt`** necesita `arm_64bit=1` (la raíz es arm64, las Pi son 3B+).
  Conservar `dtoverlay=w1-gpio,gpiopin=4` (TempSensorDS18B20). Verificado que el bus
  1-Wire se activa en Trixie (`/sys/bus/w1/devices/` existe).
- **`/etc/resolv.conf`** venía copiado del chroot con los DNS de la red vieja.
  Corregido a `nameserver 10.43.88.3` + `domain lab`.
- **`/etc/systemd/timesyncd.conf`** → `NTP=tangodb.lab`. timesyncd **ignora** la
  opción NTP del DHCP, hay que ponerlo explícito.
- **Usuario**: la imagen RaspiOS trae `pi` con `/usr/sbin/nologin` y `!` en shadow;
  se completa con el asistente de primer arranque (o a mano desde wolframite).
- **`tango-starter`** no venía instalado; su unidad systemd tiene
  `Requires=tango-db.service`, que no existe en la Pi. Hay que copiar la unidad a
  `/etc/systemd/system/` y borrar esa línea (un drop-in con `Requires=` vacío **no**
  la anula).
- ⚠️ El `ExecStartPre=tango-starter-register-helper` **crea registros automáticamente**
  en la DB tomando el nombre de `TANGO_HOST` (creó un espurio `Starter/tangodb.lab`).
  Vigilar en cada Pi nueva.

### Pendiente en esta Pi

- Devolverla al laboratorio y validar LeyboldIG3 (puerto serie) y TempSensorDS18B20
  (sensor 1-Wire). Ambos fallan ahora solo por hardware ausente.
- **WisselMCA/1** ✅ reactivado (13-ago-2026) y **probado contra el MCA real**
  (17-ago-2026): protocolo HID verificado, cuatro defectos corregidos. Falta
  arrancarlo bajo el Starter con el código corregido (ver
  _Dependencias de WisselMCA_ más abajo).
- **TempSensorDS18B20/1** ya no falla por hardware ausente: el sensor
  `28-3cd5f649fc87` responde. Moría al arrancar por un defecto del servidor,
  corregido el 17-ago-2026 (ver _TempSensorDS18B20_ más abajo).
- La ruta serie de LeyboldIG3 (`/dev/serial/by-path/platform-3f980000.usb-...`)
  codifica el puerto USB físico: si se cambia de conector, hay que actualizar la
  propiedad.

### Inventario de asignaciones recuperado

`~/tango-server-assignments.txt` en wolframite contiene la salida de
`SELECT name, host, level FROM server ORDER BY host, level` — 64 filas con qué
servidor corre en qué máquina y con qué nivel de arranque. Es la fuente para
rellenar los "TBD" de la sección _Host → server assignments_ más abajo.

Ojo: los hosts figuran con el dominio viejo `.labo` (`pi-leem.labo`,
`sputtering.labo`…). La red nueva usa `.lab`.

### Servidores de pi-rackmossbauer (confirmado desde la DB)

`LeyboldIG3/1`, `TempSensorDS18B20/1`, `WisselMCA/1`.

---

## Status del chroot (30-jun-2026)

**Trixie root device-server install: COMPLETE and verified (30-jun-2026).**
On `/nfs/pi-trixie` (ARM64 chroot on wolframite):
- Deps installed — apt: `python3-tango` (10.0.2), `python3-serial`, `python3-rpi.gpio`;
  pip `--break-system-packages`: `simple-pid`, `w1thermsensor`.
- `pip install -e --no-deps --break-system-packages .` from repo root succeeded
  (editable wheel built clean).
- **31 live wrappers** present in `/usr/local/bin`; **zero parked servers** present
  (deprecated/inactive exclusion confirmed via grep).
- Import test: **31/31 live servers import** with deps present. 4 GPIO servers
  (RaspberryButton, RaspberrySwitch, SEAWaterflowmeter, WaterSwitch) only
  import on a real Pi — `RPi.GPIO` refuses to load on x86; this
  is expected, validate on hardware.
- Package structure fixed: explicit `[tool.setuptools.packages]` +
  `[tool.setuptools.package-dir]` mapping each name → inner `Name/Name` dir
  (auto-discovery was mapping to empty outer dirs → "unknown location").
  `__init__.py` re-exports `main`; inner `release.py` tracked (was hidden by
  `.gitignore __*`).
- `/etc/tangorc` = `TANGO_HOST=tangodb.lab:10000`.
- ⚠️ Unmount binds (`/dev`, `/proc`, `/sys`) before any exportfs/rsync of this tree.

Imports passing certifies load-time correctness only — NOT runtime behavior on
hardware. Per-server bring-up on a test Pi remains the authoritative test (blocked
behind the `enp6s0f1` VLAN port / IT).

Repo restructure committed and pushed (Mac reference → GitHub → chroot pull).

---

## The reconciliation principle

A device server has presence in **three** places, and at cutover all three must
list the **same** set of live servers. Most silent failures come from these
drifting apart:

1. **Installed entry points** — `[project.scripts]` in the top-level
   `pyproject.toml` → the `/usr/local/bin/<Server>` wrappers the Starter launches
   by bare name.
2. **Starter control lists** — which servers each Pi's Starter is assigned to
   launch (edited via Astor / the Starter's startup-level properties).
3. **Tango DB registrations** — the server/class/device entries (Jive).

A server missing from (1) but present in (2)+(3) → Starter tries to launch a
non-existent executable → red in Astor.
A server in (1)+(3) but referencing an uninstalled module → wrapper exists but
import fails at launch.

**The live-server list below is what all three must agree on.**

Tally: **32 live · 7 inactive · 4 deprecated** (= 43 entry-point servers), plus
RaspberryButton_old (dead duplicate, remove) and PANIC (third-party, separate).

_(Era 31 · 9 hasta el 13-ago-2026, cuando WisselMCA y GammaVacuumSPCe pasaron de
inactivos a vivos, y 33 · 7 · 3 hasta el 18-ago-2026, cuando Motor pasó a
deprecated. El recuento del chroot de arriba, con fecha 30-jun-2026, es anterior a
ambos cambios: al reinstalar deben salir 32 wrappers, no 31.)_

---

## Server inventory

### LIVE — install on the Trixie root (32)

Entry point in `[project.scripts]`, installed, registered in the new DB.

AGPolaritySwitch, AMLPGC1, ArduinoDAC, ArduinoMotor, ArduinoPt, MFC
(BronkhorstMFC), CryoCon32, ElmitecLEEM2k, ElmitecUview, FUGMCP, HuttingerPFGDC,
HuttingerPFGRF, Hygrometer, Itech6000C, CenterOneGauge (LeyboldCenterOne),
LeyboldIG3, MKSGauge, NetworkUPSTool, PfeifferHiscroll, PfeifferTC100,
PfeifferTU400, RaspberryButton, RaspberrySwitch, SEAWaterflowmeter, SRIlockin830,
TempSensorDS18B20, VarianTV301nav, WaterSwitch, Tti604, **PIDController**,
**WisselMCA**, **GammaVacuumSPCe**.

### INACTIVE — keep in repo, do NOT install (7)

Move to `inactive/`. Code present but hardware idle or work remains. Not in
`[project.scripts]`, not registered in the new DB until revived. See
`inactive/README.md` for per-server revival notes.

GammaIonPump, Keithley2100, MCC1208LS, PfeifferDCU002,
V4L2Camera, VSMControlDevice, WebCam.

_(WisselMCA y GammaVacuumSPCe salieron de esta lista el 13-ago-2026 —
reactivados, ver más abajo.)_

### DEPRECATED — dead hardware, remove from install set permanently (3)

Move to `deprecated/`. **Death by omission**: never entered in the new DB. See
`deprecated/README.md`.

MitutoyoPostable, SpecsXRC1000, VarianMultiGauge.

### Special cases

- **RaspberryButton_old** — dead duplicate of RaspberryButton (forced the TOML
  dedup). Remove from repo.
- **PANIC (PyAlarm)** — third-party Alba alarm system, still Python 2 + Qt5. Not a
  SURFMOSS server; installed separately if/when converted. No entry point in this
  repo's pyproject.

---

## Dependency matrix (live servers only)

Install strategy: **apt for everything Debian packages** (precompiled arm64, no
PEP 668 fight, no emulated builds); **pip `--break-system-packages` only for the
gaps**. Install the servers with
`pip install -e --no-deps --break-system-packages .` so the editable install does
NOT pull PyPI versions over the system packages.

### apt (in the chroot)

| Debian package | PyPI name | Needed by |
|---|---|---|
| python3-tango | pytango | ALL (already installed, 10.0.2-1) |
| python3-serial | pyserial | most serial-instrument servers |
| python3-rpi-lgpio | RPi.GPIO (shim) | RaspberryButton, RaspberrySwitch, SEAWaterflowmeter, WaterSwitch — ver _GPIO en Trixie_ |
| python3-nut | PyNUT | NetworkUPSTool |

```bash
apt update
apt install -y python3-tango python3-serial python3-rpi-lgpio python3-nut
```

### pip (not packaged in Trixie)

| PyPI name | Needed by | Notes |
|---|---|---|
| simple-pid | PIDController | pure Python, trivial |
| w1thermsensor | TempSensorDS18B20 | also needs w1-gpio / w1-therm kernel modules + DS18B20 device-tree overlay (a Pi boot-config item, separate from the package) |

```bash
pip install --break-system-packages simple-pid w1thermsensor
```

### Dropped entirely (no live server needs them)

- **usbtmc** — only Keithley2100 (now inactive). Also dropped its `python3-usb` /
  libusb chain.
- **numpy / python3-numpy** — ElmitecUview's `import numpy` was orphaned (only use
  was `numpy.frombuffer` in a commented-out, unfinished `ImageData_read` stub); the
  import was removed. No live server imports numpy (grep-verified). Re-add
  `python3-numpy` if/when ElmitecUview's ImageData attribute is implemented.
- **matplotlib** — ElmitecUview corrected to need neither numpy nor matplotlib; the
  other user (VSMControlDevice) is inactive. ⚠️ El «no live server imports numpy»
  de arriba dejó de ser cierto al reactivar WisselMCA, que sí lo usa.
- **opencv / python3-opencv** — only V4L2Camera (inactive).
- **usb_1208LS / Linux_Drivers source build** — only MCC1208LS (inactive). The
  single nastiest install, gone.

Net pip footprint: **two pure-Python packages.** The entire compiled/ARM-painful
dependency set has been eliminated by omission.

### Verify on real hardware (cannot be tested in the x86 chroot)

- **GPIO library**: confirmado el 18-ago-2026 — RPi.GPIO **no sirve** en Trixie.
  Ver _GPIO en Trixie_ más abajo. Falta comprobar en hardware RaspberryButton,
  RaspberrySwitch y WaterSwitch con el shim ya puesto. TempSensorDS18B20 salió de
  esta lista el 17-ago-2026 (el pin lo lleva el overlay w1-gpio del kernel) y Motor
  el 18-ago-2026 (a `deprecated/`).
- **w1thermsensor**: the kernel one-wire modules + overlay must be enabled on the
  Pi, independent of the pip package. ✅ Verificado el 17-ago-2026 en
  pi-rackmossbauer: `w1_gpio`/`w1_therm` cargados y el sensor enumera, aunque el bus
  va ruidoso (ver _TempSensorDS18B20_).

---

## Host → server assignments

All three of (entry points / Starter list / DB) reconcile per-host. Populate each
Pi's list from its Starter's controlled-servers in Astor.

### pi-leem (.10, /nfs/leem) — from Astor

Controlled servers (all live): AMLPGC1/1, ElmitecLEEM2k/1, ElmitecUview/1,
FUGMCP/1·2·3, NetworkUPSTool/1, PIDController/1·2·3, RaspberrySwitch/2.

Removed at clean import: **VarianMultiGauge/1** (deprecated — was red in Astor).

### pi-rackmossbauer (.11) — CONFIRMADO desde la DB (08-ago-2026)

`LeyboldIG3/1`, `TempSensorDS18B20/1`, `WisselMCA/1`.

WisselMCA ✅ reactivado (13-ago-2026) y probado contra el MCA real (17-ago-2026):
ya está en la raíz del repositorio y en el `pyproject.toml`, así que se instala y el
Starter lo encontrará en `StartDsPath`. Pendiente: arrancarlo bajo el Starter con el
código corregido (ver _Dependencias de WisselMCA_ más abajo).

Ya migrada a `/nfs/pi-trixie` (Debian 13). Los otros dos servidores arrancan y
fallan solo por hardware ausente.

### pi-vsm (.12, /nfs/vsm) — TBD

_Populate from this Pi's Starter in Astor. Note VSMControlDevice is inactive —
confirm whether this host still needs it before reviving._

### Other Pis (pi-xps, pi-mossbauer, pi-hvleem, ender, …) — TBD

_Populate per host from Astor as each is migrated._

---

## ✅ IPs hardcodeadas en los device servers — RESUELTO

Tres DS se conectaban a su instrumento **por red** con la dirección IP escrita en
el propio código, no en una propiedad de Tango: **Itech6000C, ElmitecUview y
ElmitecLEEM2k**.

Eso bloqueaba la migración: las IPs eran de la red vieja (`10.10.99.x`), así que en
cuanto el instrumento cambiaba de VLAN el DS dejaba de encontrarlo.

**Actualizadas en la Fase 2** (los tres instrumentos están en el LEEM / VSM).

**Externalizadas a propiedades de device el 13-ago-2026** (commits `2d749c8` y
`eba613b`). Los tres DS ya declaraban las propiedades y tenían la línea correcta
escrita justo encima de la literal, comentada — es decir, lo que hubiera en la
base de datos se estaba ignorando. Ahora manda la BD:

**Nombres unificados el 13-ago-2026**: los cuatro DS de red usan ahora `IP` y
`Port`. ElmitecUview los tenía como `UviewIP` / `UviewPort` y GammaVacuumSPCe
llamaba `Host` al suyo.

| DS | propiedad | valor por defecto | `Port` |
|---|---|---|---|
| ElmitecLEEM2k | `IP` | `tvips.lab` | 5566 |
| ElmitecUview | `IP` | `tvips.lab` | 5570 |
| Itech6000C | `IP` | `PWSItech6000VSM.lab` | 30000 |
| GammaVacuumSPCe | `IP` | **sin default — hay que ponerlo en la BD** | 23 |

`tvips` es el ordenador del LEEM, que controla también la cámara TVIPS XFS216.

⚠️ El renombrado tiene un efecto en la base de datos: un valor guardado bajo
`UviewIP`, `UviewPort` o `Host` queda huérfano y el DS no lo verá. Si algún
dispositivo los tenía puestos, hay que reescribirlos con el nombre nuevo.

Los defaults se pusieron a la dirección real, así que una propiedad sin poner en
la BD da el comportamiento correcto. ⚠️ Al revés sí hay riesgo: si un dispositivo
tiene ya `IP` o `UviewIP` escrita en la base de datos con un valor obsoleto, ahora
manda esa y el DS fallará al reiniciar. Comprobar en Jive antes del arranque.

Tres detalles que salieron al hacerlo:

- **ElmitecUview tenía tres direcciones distintas apuntadas**: `leem.labo` en el
  código, `leemPC.labo` como default del `.py` y `10.10.99.29` en el `.xmi`.
  Unificadas.
- **ElmitecLEEM2k no tenía default ninguno.** Con la propiedad sin poner,
  `self.IP` habría salido cadena vacía y el `connect()` habría fallado en
  silencio — el `except` desnudo se lo traga y deja el DS en FAULT.
- No hay más DS de red: el resto es serie, USB o GPIB. El
  `grep -rn '10\.10\.99'` sobre los device servers ya da vacío.

Nota: los DS de puerto serie tienen un problema análogo pero distinto — la ruta
`/dev/serial/by-path/...` codifica el conector USB físico. No cambia con la red,
pero sí si se enchufa el conversor en otro puerto de la Pi.

---

## Dependencias de WisselMCA (reactivado 13-ago-2026)

El servidor volvió a la raíz del repositorio y es la **32ª entrada** del
`pyproject.toml` (`[project.scripts]`, `[tool.setuptools.packages]` y
`[tool.setuptools.package-dir]`). El arreglo de `argv[0]` ya lo tenía, porque la
pasada de los 41 servidores cubrió también los inactivos.

Necesita **numpy** y un binding HID. Y ahí está la trampa: el código llama a

```python
dev = hid.device()          # minúscula
```

Esa API es la de **cython-hidapi**, que en PyPI se publica como **`hidapi`**. El
paquete de PyPI llamado literalmente `hid` es otro proyecto distinto: expone
`hid.Device()` con mayúscula y daría `AttributeError` al abrir el aparato. Los dos
ocupan el mismo nombre de módulo al importar, así que el error solo se ve en
ejecución, no al instalar.

En la raíz Trixie:

```bash
apt install python3-numpy libhidapi-hidraw0
apt install python3-hid        # comprobar cuál es, ver abajo
```

Comprobación que zanja la duda:

```bash
python3 -c "import hid; print(hid.__file__, hasattr(hid,'device'), hasattr(hid,'Device'))"
```

Tiene que salir `device=True`. Si sale `Device=True`, es el paquete equivocado y
hay que usar `pip install hidapi --break-system-packages`.

`libhidapi-hidraw0` es la biblioteca C que el binding carga en ejecución; sin ella
el `import` falla aunque el paquete Python esté instalado.

⚠️ Esto rompe el «net pip footprint: two pure-Python packages» de la sección de
dependencias: cython-hidapi es una extensión compilada. En ARM64 hay rueda o se
compila contra `libhidapi-dev`, por eso conviene el paquete de apt si sirve.

**Permisos: hacen falta DOS reglas udev, no una.** El DS abre el aparato por
VID/PID `0x0925:0x0035`. Con `hidraw` sola no basta:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0925", ATTRS{idProduct}=="0035", MODE="0660", GROUP="plugdev"
SUBSYSTEM=="usb",    ATTR{idVendor}=="0925",  ATTR{idProduct}=="0035",  MODE="0660", GROUP="plugdev"
```

Ojo a la diferencia `ATTRS` (atributos del padre, para hidraw) frente a `ATTR`
(atributos propios, para usb). El binding instalado usa el **backend libusb**, que
accede por `/dev/bus/usb/BBB/DDD` (`crw-rw-r-- root root`) y **desconecta el driver
hidraw del kernel al abrir**, con lo que el nodo `/dev/hidraw*` desaparece. Sin la
segunda regla el `open()` sigue dando `OSError: open failed` aunque la primera esté
puesta y el usuario esté en `plugdev`. Diagnosticado así en pi-rackmossbauer el
17-ago-2026.

El usuario que corre el DS (`tango`) tiene que estar en `plugdev`. Los grupos se
heredan al crear el proceso, así que **hay que reiniciar el Starter**, no solo el
device server, tras un `usermod -aG`.

### Probado contra el MCA real (17-ago-2026)

Ya no está sin probar: el protocolo se ha ejercitado contra la tarjeta (número de
serie `2007 61 122`). Tres defectos encontrados y corregidos, todos ellos invisibles
en un chroot:

1. **Reensamblado de reports HID.** `readpage` pedía `dev.read(131)`, pero el manual
   (`WisselMCA/CMCA 550_Newprotokoll Remotr Control.pdf`, página 1) dice
   "HID-Device, 64 bytes package". hidapi devolvía solo el primer report — 62 bytes
   útiles de 128 — y dejaba los otros dos **encolados**, con lo que cada comando
   posterior leía las sobras del anterior y respondía "wrong count". `read_response()`
   acumula reports hasta completar la respuesta y `drain()`, llamado en `open()`,
   descarta lo que dejara una sesión desincronizada previa.
2. **Errores enmascarados.** Doce sitios hacían `(t, r) = self.c.X()` e ignoraban el
   flag. Al fallar, `r` era la cadena de error; `r[2] * 10000` es repetición de
   cadena (legal) y solo reventaba en la división, con un
   `TypeError: unsupported operand type(s) for /: 'str' and 'int'` a cientos de
   líneas del origen. Ahora pasan por `checked()`, que lanza una excepción Tango con
   el mensaje real del aparato.
3. **Desbordamiento uint16 con NumPy 2.** Los tres lectores de la ventana hacían
   `float(r[n] * 10000 / 16383)` sobre un `numpy.uint16` de `frombuffer`. Con NumPy 2
   (NEP 50) el escalar conserva su dtype, así que la multiplicación **desborda módulo
   65536 antes de dividir**: ULD=819 se leía como 3.88 mV en vez de 499.91. Como el
   wrap no es monótono, cambiar un límite parecía no afectar a la lectura. El `float()`
   tiene que ir **antes** de la aritmética. Es el único DS del repositorio expuesto a
   esto — los demás `uint16` son declaraciones de atributos Tango, no escalares numpy.

**Y una inconsistencia de diseño**, también corregida: `setPHAmode` e `init_device`
derivaban la longitud del espectro del límite superior de la ventana con
`lastchannel = round(upper_mV * 16383 / 10000)`, que es la conversión mV → **valor
crudo de 14 bits**, no a canales. Los límites son tensiones de entrada (página 4:
"16383 = 0x3FFF = 10 Volts"), y el resultado excedía el hardware: una ventana de 10 V
daba 16383 "canales" en una tarjeta de 8192 como máximo, con lo que `Spectrum` leía
más allá del final de los datos, en las páginas 256-1023 que el manual reserva para
DFG.

**El mapeo correcto, medido en la tarjeta:** con `Res=0` y `ULD1 = 1310` (800 mV), el
último canal con cuentas es **655 = 1310 >> 1, exacto**. Es decir, el valor de 14 bits
de la ventana cubre el mismo margen 0-10 V que los canales, así que

```
canal = ULD >> (1 + Res)          # la mitad del crudo con 13 bit
canales totales = 8192 >> Res     # Res[1:0], bits 2-3 del byte 1 del General Setup
```

Era justo lo que buscaba el autor original: su expresión daba el crudo, que es **el
doble** del canal. `phalastchannel()` lo calcula, acotado a la resolución, y lo usan
`init_device`, `setPHAmode` y `write_Upper_Window_Limit` — mover el nivel superior
mueve dónde se acaban las cuentas, así que la longitud lo sigue.

Leer los 8192 canales enteros no aporta nada y cuesta: la suma es idéntica (216013
cuentas en ambos casos, porque los pulsos por encima del nivel superior se rechazan),
pero tarda **2.05 s frente a 0.17 s**. Y 2 s está incómodamente cerca del timeout de
cliente por defecto de Tango (3 s), lo que habría hecho `Spectrum` inestable para quien
no lo suba.

### Estado verificado a través del device server (17-ago-2026)

```
Configuration : 0x0000  -> OS=0  Res=0  -> 13 bit -> 8192 canales
Model         : 2007 61 122
Mode          : 3 (PHA)   ModeByte 0x03 (parado)
ventana       : 200.21 - 800.22 mV
Spectrum      : 672 canales en 0.17 s, suma 216013, 491 canales no vacíos
```

Escribir y volver a leer los límites: 2000/5000/8000 mV → crudo 3277/8192/13106 →
2000.24/5000.31/7999.76 mV. Los valores originales quedaron restaurados.

Nota: `ReadLastChannel` es un comando **sin `dtype_out`** — no devuelve nada, actualiza
`lastchannel` con lo que diga la tarjeta (último canal no nulo + 1). Devolver `None` es
su comportamiento correcto, no un fallo. Y la tarjeta redondea ese valor al final de la
página: con datos hasta el canal 655 informa 671 (página 20 = canales 640-671).

---

## GPIO en Trixie: RPi.GPIO no vale, hay que usar rpi-lgpio (18-ago-2026)

La advertencia de _Verify on real hardware_ se ha confirmado, y de la peor manera:
**falla en ejecución, no al importar**, así que el chroot no lo detecta y el
servidor arranca hasta que toca el pin.

`SEAWaterflowmeter/4` no arrancaba en pi-vsm:

```
File ".../SEAWaterflowmeter.py", line 154, in init_device
    GPIO.add_event_detect(i, GPIO.RISING, callback=my_callback)
RuntimeError: Failed to add edge detection
```

Reproducido en dos líneas como usuario `pi` (que está en `gpio`, así que **no es de
permisos**), en una Pi 3B+ con kernel 6.18.39 y `python3-rpi.gpio` 0.7.1a4:

```
GPIO.setup(17, GPIO.IN)            -> OK, GPIO.input(17) -> 0
GPIO.add_event_detect(17, RISING)  -> RuntimeError: Failed to add edge detection
```

`setup`, `input` y `output` **siguen funcionando**; lo que se rompe es solo la
**detección de flancos**, que es lo único que RPi.GPIO hace todavía por el interfaz
`sysfs` antiguo. Por eso SEAWaterflowmeter fue el primero en notarlo: es el único
servidor del repositorio que usa `add_event_detect`.

**Remedio: `python3-rpi-lgpio`**, un shim que reimplementa la API de RPi.GPIO sobre
`lgpio`, que habla con `/dev/gpiochip*`. Está en el archivo de raspberrypi.com para
Trixie (0.6) y su dependencia `python3-lgpio` ya venía instalada.

```
Package:   python3-rpi-lgpio
Depends:   python3-lgpio, python3:any
Conflicts: python3-rpi.gpio
Provides:  python3-rpi.gpio
```

⚠️ **Sustituye a `python3-rpi.gpio`, y la raíz NFS es compartida**: se instala en el
chroot de wolframite y afecta a **todas las Pis y a todos los DS de GPIO a la vez**.

Verificado sin tocar la raíz, descargando el .deb y extrayéndolo en `/tmp` con
`PYTHONPATH` por delante:

```
pin 6:  setup + add_event_detect OK, lectura 1
pin 13: setup + add_event_detect OK, lectura 0
```

y con el servidor real (instancia 4, canales 6,13 según la BD):

```
estado: ON | Measurement thread is running     channel0 = 0.0   channel1 = 0.0
```

Qué usa cada servidor vivo de la API, para saber qué revisar tras el cambio:

| Servidor | Usa | Riesgo |
|---|---|---|
| SEAWaterflowmeter | `add_event_detect` | Es el que se arregla |
| RaspberrySwitch | `setup`, `input`, `PUD_UP/DOWN` | Bajo |
| WaterSwitch | `setup`, `input`, `PUD_UP` | Bajo |
| RaspberryButton | `setup`, `output` | Bajo |

`rpi-lgpio` documenta diferencias de comportamiento en detalles como el *bouncetime*
de los eventos y en **PWM**. El único servidor que usaba PWM era Motor, que pasó a
`deprecated/` el 18-ago-2026 al sustituirlo por un Arduino con un DRV8825, así que
ese riesgo **ya no existe**.

Nota: los `time` y `calibration` vacíos de `vsm/safety/water` en la BD no son un
problema — tienen `default_value` en el código (1.0 y 7.5).

---

## TempSensorDS18B20 (corregido 17-ago-2026)

Moría al arrancar, y **no era por hardware ausente**: el sensor
`28-3cd5f649fc87` está conectado y lee. `init_device` llamaba a
`w1thermsensor.W1ThermSensor()` sin protección, y al lanzar `NoSensorFoundError`
PyTango **terminaba el proceso entero** — en `/var/tmp/ds.log/TempSensorDS18B20_1.log`:
`Exiting: Server exited with tango.DevFailed … Exited`. El Starter lo marca FAULT y no
lo vuelve a levantar.

Corregido: FAULT con el mensaje real en vez de morir; el hilo de control reintenta
adquirir el sensor y recupera a ON solo; ya no muere en un `get_temperature()` fallido
(que antes dejaba `Temperature` congelada en el último valor **para siempre**); FAULT
tras tres fallos seguidos y `ATTR_INVALID` cuando no hay sensor, para no servir un
valor viejo como fresco. El hilo es daemon y espera en un `Event`, e `init_device` para
el anterior, así un `Init` desde Astor no deja dos hilos escribiendo `self.temp`.

⚠️ **El bus 1-Wire de esta Pi está ruidoso.** Reporta un esclavo fantasma en casi cada
búsqueda:

```
w1_master_driver w1_bus_master1: Family 0 for 00.b3c800000000.12 is not registered.
```

153 de esos en el buffer de `dmesg`, uno cada ~45-60 s. Con ese ruido el esclavo real
puede desaparecer de `/sys/bus/w1/devices` y volver — lo que el software ahora tolera,
pero **no cura**. Merece una revisión del cableado (longitud, pull-up de 4.7 kΩ,
apantallamiento).

También **dejó de importar `RPi.GPIO`**: el pin lo maneja el overlay `w1-gpio` del
kernel, configurado en `config.txt`, no el servidor. La propiedad `GPIOPin` se queda,
documentada como informativa, para no dejar huérfanos los valores de la BD.

---

## Desplegar código en las Pis: la raíz NFS es de solo lectura desde el cliente

Verificado el 17-ago-2026 en pi-rackmossbauer: **`git pull` en el propio Pi no
funciona**. Su raíz es `10.43.88.3:/nfs/pi-trixie` por NFSv4 y, aunque el cliente la
monta `rw`, toda escritura da `EROFS` — `/opt/tango/SURFMOSS_TangoDS`, e incluso
`/home/pi`, también con `sudo`. Solo `/tmp` es escribible (tmpfs). `/var` sí lo es,
por su propio export: `10.43.88.3:/nfs/clients/pi-rackmossbauer/var` (de ahí que los
logs del Starter en `/var/tmp/ds.log/` sí se escriban).

Antes de llegar al motivo real aparecen dos errores de git que despistan:
`fatal: detected dubious ownership` (el repo es de `root`, uno entra como `pi`) y
luego, con `sudo`, `cannot open '.git/FETCH_HEAD': Read-only file system`.

El pull tiene que hacerse **donde `/nfs/pi-trixie` sea escribible** (wolframite), y
luego reiniciar el DS en el Pi con el Starter.

**Para probar un parche contra el hardware sin desplegar**: `scp` del módulo a `/tmp`
y ejercitarlo con `importlib.util.spec_from_file_location`. Para un device server
completo, `-nodb` evita tocar la base de datos:

```bash
python3 /tmp/mods.py test -nodb -dlist test/temp/1 -ORBendPoint giop:tcp:127.0.0.1:12988
python3 -c 'import tango; print(tango.DeviceProxy("tango://127.0.0.1:12988/test/temp/1#dbase=no").state())'
```

Con `-nodb` las propiedades toman su `default_value`. Ojo: hay que fijar el endpoint a
`127.0.0.1`, porque el nombre corto `pi-rackmossbauer` **no resuelve en el propio Pi**
(se ve también como `sudo: unable to resolve host`) y el IOR publicado queda
inalcanzable.

---

## GammaVacuumSPCe (reactivado 13-ago-2026)

Fuente de la bomba iónica DIGITEL SPCe de Gamma Vacuum, por Telnet sobre TCP
(puerto 23 por defecto). Devuelto a la raíz y dado de alta como **33ª entrada** del
`pyproject.toml`. El arreglo de `argv[0]` ya lo tenía.

Sin dependencias nuevas: solo `socket` y `struct`, de la biblioteca estándar.

Dos cosas que lo distinguen del resto:

- **No tiene `.xmi`.** Es el único device server del repositorio en esa situación
  — se escribió a mano, no con POGO. Consecuencia práctica: **POGO no puede
  regenerarlo ni editarlo**. POGO trabaja desde el `.xmi`, no desde el `.py`, así
  que añadir regiones protegidas al código no basta; habría que reconstruir el
  modelo declarando atributos, comandos y propiedades, y volver a generar.
- **Nunca se ha probado contra el controlador real.** Era la nota de
  `inactive/README.md`. Que ahora se instale no cambia eso.

La propiedad `IP` **no tiene valor por defecto** a propósito: no hay una dirección
conocida que poner. Hay que fijarla en la base de datos al registrar el
dispositivo, o el `connect()` fallará con cadena vacía.

---

## Handling deprecated/inactive servers in the repo

A server installs only if it is **both** discovered by `packages.find` **and**
listed in `[project.scripts]`. Removing from both, via directory move:

1. `git mv <Server>/ deprecated/<Server>/` (dead) or `inactive/<Server>/`
   (paused) — preserves history; the directory name is the flag.
2. Exclude both dirs in `[tool.setuptools.packages.find]`:
   ```toml
   [tool.setuptools.packages.find]
   where = ["."]
   exclude = ["scripts*", "synoptics*", "*.egg-info*", "deprecated*", "inactive*"]
   ```
3. Ensure none appear in `[project.scripts]` (automatic if built from the live
   list).
4. `deprecated/README.md` and `inactive/README.md` document why each is out and
   what reviving requires.

**Verify** after install that no parked server's wrapper appears:
```bash
ls /usr/local/bin/ | grep -iE 'Mitutoyo|Specs|VarianMultiGauge|Gamma|Keithley|MCC1208|DCU002|Camera|WebCam|VSMControl|Wissel'
# should return nothing
```

---

## Cutover checklist

1. **Repo**
   - [ ] Top-level `pyproject.toml` lists exactly the **33** live entry points
         (build-backend = `setuptools.build_meta`).
   - [ ] PIDController added as a live entry; its Makefile removed.
   - [ ] 3 dead → `deprecated/`, 7 paused → `inactive/`, both excluded in
         `packages.find`.
   - [ ] RaspberryButton_old removed.
   - [x] WisselMCA encoding fix committed, y el servidor reactivado el
         13-ago-2026: vive en la raíz y está en el `pyproject.toml` (32ª entrada).
   - [x] GammaVacuumSPCe reactivado el 13-ago-2026 (33ª entrada). Sin `.xmi` y
         sin probar contra el controlador; su propiedad `IP` no tiene default y
         hay que fijarla en la BD al registrar el dispositivo.
   - [x] Los cuatro DS de red usan `IP` / `Port` con el mismo nombre. Ojo a los
         valores huérfanos en la BD bajo `UviewIP`, `UviewPort` y `Host`.
2. **Trixie root install (in chroot, binds mounted)**
   - [ ] apt deps: `python3-tango python3-serial python3-rpi-lgpio`,
         más `python3-numpy libhidapi-hidraw0` para WisselMCA.
   - [ ] pip deps: `simple-pid w1thermsensor` (`--break-system-packages`),
         más el binding HID de WisselMCA (ver sección de dependencias).
   - [ ] `pip install -e --no-deps --break-system-packages .` from repo root.
   - [ ] All 33 live wrappers present in `/usr/local/bin`; no parked ones.
   - [ ] `/etc/tangorc` = `TANGO_HOST=tangodb.lab:10000`.
   - [ ] **Unmount binds** (`/dev`, `/proc`, `/sys`) before any exportfs/rsync.
3. **Clean DB**
   - [ ] Build fresh DB with the 33 live servers only — parked ones never entered.
   - [ ] Each Pi's Starter control list matches its live-server set.
   - [ ] Disable wolframite's own Starter (DB host, runs no instrument servers).
   - [x] **IPs hardcodeadas** externalizadas a propiedades (13-ago-2026). Queda
         verificar en Jive que ningún dispositivo arrastra un valor obsoleto en
         `IP` / `UviewIP`, que ahora sí manda (ver sección arriba).
4. **Per-server validation (on a test Pi booted off Trixie root)**
   - [ ] Bring servers up **one at a time** under the Starter.
   - [ ] Hardware/serial servers last, when the instrument is free.
   - [ ] GPIO + w1thermsensor servers: confirm on real hardware (do GPIO first).
   - [ ] PIDController: confirm it reaches its input/output device proxies over
         the new VLAN (intra-subnet dynamic Tango ports); FAULT = can't reach them.

> **Note**: the Python-3 audit (`py_compile` clean) certifies no py2 *syntax*
> remains. It does NOT certify runtime behavior — bytes-vs-str on serial reads,
> integer division, dict-view changes. Per-server bring-up on real hardware
> remains the authoritative test, especially for serial/instrument servers.

---

## Plan de migración por lotes (agrupación por switch)

Los puertos se cambian por switch, no de uno en uno, así que **todas las máquinas
de un switch cambian de red a la vez**.

### ✅ CLAVE (8-ago-2026): las Pis viejas SÍ funcionan contra wolframite

**Comprobado con pi-rackmossbauer arrancando su raíz Debian 10 (Tango 9.2.5)
contra wolframite (Tango 10): arranca y sus device servers levantan
correctamente** (los únicos fallos son por hardware ausente). WisselMCA arranca
sin problema.

Esto **elimina el cuello de botella** del plan original. Ya NO hace falta migrar
todas las Pis a Trixie antes de mover los puertos. La secuencia pasa a ser:

1. Pedir a IT el cambio de **todos** los puertos a la red nueva.
2. El laboratorio sigue operando con las Pis viejas (Debian 10) contra wolframite.
3. Migrar cada Pi a Trixie cuando convenga, sin ventanas de mantenimiento.

_Nota histórica: durante horas se creyó que las Pis viejas eran incompatibles con
el Databaseds 10. Era falso: el fallo real era el conflicto de collations de
MariaDB, que afectaba por igual a Tango 9 y 10. Corregido eso, la
retrocompatibilidad funciona._

### Requisito previo al cambio de puertos

Los dos PCs Debian 10 (sputtering, vsm) también corren device servers. Hay que
verificar que funcionan contra wolframite antes de mover su switch. **vsm** es el
urgente (va en el paso 1); **sputtering** puede esperar al paso 3.

### Secuencia de migración por fases (según `traslado_red_laboratorio.md`)

El orden protege lo que está en uso: XPS y Mössbauer siguen midiendo hasta el
final. Y la primera fase sirvió de banco de pruebas real, con poco en juego.

#### ✅ Fase 1 — COMPLETADA (10-ago-2026)

Nave 409 (VSM et al): VLAN 303 Talleres, puerto #01 Gi1/0/2.

| Equipo | MAC | IP nueva | Estado |
|---|---|---|---|
| vsm (PC Debian 10) | `00:15:17:50:bd:77` | `10.43.88.30` | ✅ device servers OK contra wolframite |
| pi-vsm (netboot) | `b8:27:eb:ec:95:5a` | `10.43.88.12` | ✅ arranca y DS OK |
| fuente ITech | `8c:c8:f4:41:bd:f4` | `10.43.88.40` | |
| 3dprinter (ender) | `b8:27:eb:26:ba:05` | `10.43.88.16` | |

**Resultado clave**: valida que **tanto las Pis netboot como los PCs Debian 10**
funcionan sin cambios contra wolframite (Tango 10). Nada bloquea las fases
siguientes.

#### ✅ Fase 2 — COMPLETADA — Nave 408 (LEEM et al)

Rocasolano Talleres, VLAN 13; puertos #4 Gi1/0/4, #5 Gi1/0/17.

leempc (`18:66:da:3d:88:2c`), tvips (`10:b6:76:49:fc:ad`),
ferberite (`10:ff:e0:63:02:ca`), Quadera mass spec (`00:50:c2:66:85:11`),
pi-leem (`b8:27:eb:71:00:ad`), pi-uleem (`b8:27:eb:86:01:9e`),
pi-hvleem (`b8:27:eb:56:e6:91`).

El instrumento con la lista de DS más larga, funcionando. Se actualizaron también
las IPs hardcodeadas de Itech6000C, ElmitecUview y ElmitecLEEM2k.

#### ✅ Fase 2a — COMPLETADA — hematite

Trasladado a `10.43.88.2` con **IP estática** (configurada por IT/IQF, no por
DHCP), manteniendo acceso IQF y VPN. El nombre se sirve desde `/etc/hosts` de
wolframite.

⚠️ Hasta la Fase 4, XPS y Mössbauer **no tienen acceso al almacenamiento**: deben
guardar espectros localmente.

Con hematite en la red nueva, el salto intermedio por wolframite deja de ser
necesario para llegar a las Pis desde la VPN.

#### ✅ Fase 3 — COMPLETADA — XPS upper floor (despachos)

Rocasolano-XPS, sala 500B y despachos 500C–500G. Incluye magnetite
(`40:b0:76:0f:67:f3`), fortytwo (Mac de Juan, `a0:ce:c8:ff:9d:b0`), impresora
Kyocera y equipos personales del grupo.

Los puertos omitidos se quedan en la **red IQF**, no en la red vieja del
laboratorio, así que seguirán funcionando tras la Fase 4.

#### ✅ Fase 4 — COMPLETADA — XPS + Mössbauer (CUTOVER REAL)

Rocasolano-XPS, puerto #17 Gi2/0/17, y **localsurfmoss apagado** (puerto #18
Gi4/0/18).

localsurfmoss, specs (`40:b0:76:0f:68:08`), mossbauer (`00:24:8c:e8:8f:25`),
pi-xps (`b8:27:eb:36:cf:2f`), pi-mossbauer (`b8:27:eb:eb:87:7b`),
pi-rackmossbauer (`b8:27:eb:a9:82:05`), sputtering (`00:15:17:24:e6:4e`),
CANbox XPS (`00:50:c2:4a:23:0c`).

**La red vieja `10.10.99.0/24` ha desaparecido.** Wolframite queda single-homed
(`enp6s0f0` comentada) y es el único servidor: DHCP, DNS, TFTP, NFS, NTP y Tango DB.

**Banco de pruebas**: dos puertos en la red nueva (despacho de Juan +
wolframite). Permite bajar una Pi, validarla y devolverla a su switch. Sigue
siendo útil para preparar migraciones a Trixie.

Como todas las Pis de producción son **3B+**, la raíz Trixie compartida vale para
todas.

### Trabajo pendiente por tipo de máquina

- **3 Pis netboot** (pi-leem, pi-rackmossbauer, pi-vsm): ya tienen directorio
  TFTP; para migrar a Trixie basta apuntar a `/nfs/pi-trixie` y copiar el firmware
  nuevo (ver `netboot-pi-raiz-compartida.md`).
- **4 Pis con microSD** (pi-xps, pi-mossbauer, pi-hvleem, ender): **convertir a
  netboot** (decidido). Crear su `/tftpboot/<serial>/` y anotar su MAC. Ya no
  urge: pueden seguir con su SD en la red nueva mientras tanto.
- **2 PCs Debian 10** (sputtering, vsm): verificar si funcionan contra wolframite.
  Repos muertos → hay que reinstalar o actualizar a Debian 13 con Tango 10.

### Por qué migrar igualmente

Debian 10 tiene los repos muertos (no se puede instalar ni `git` sin recurrir a
`archive.debian.org`). La migración sigue siendo necesaria, pero ahora es
**desacoplada del cambio de red**: se puede hacer con calma, máquina a máquina.

---

## Acceso remoto

**Tras la Fase 3** (despachos ya en la red nueva):

- Desde fortytwo u otro equipo migrado: **wolframite es `10.43.88.3`**, directo.
  La dirección vieja `10.10.99.25` ya no es alcanzable desde la red nueva.
- Desde fuera, por VPN: `hematite.iqf.csic.es` (`10.43.88.2`) → cualquier equipo de
  la red nueva. Ya no hace falta el salto intermedio por wolframite.

Conviene un `~/.ssh/config` con `ProxyJump` por hematite para el acceso desde casa.

La interfaz `enp6s0f0` de wolframite (red vieja, `10.10.99.25`) sigue activa hasta
la Fase 4; después puede retirarse.

**Tailscale no funciona en la red nueva**: el FortiGate (`FG101FTK21000170`) hace
inspección TLS y re-firma el certificado de `controlplane.tailscale.com`. Tailscale
hace pinning y lo rechaza por diseño. Además `UDP: false` y solo un DERP alcanzable
(Bengaluru). No es una regla que se pueda quitar sin excluir el dominio de la
inspección TLS. Descartado.
