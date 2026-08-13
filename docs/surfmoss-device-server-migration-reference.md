# SURFMOSS Device Servers — Migration Reference

_Single source of truth for installing the SURFMOSS Tango device servers onto
the new Trixie NFS root (`/nfs/pi-trixie` on wolframite) and reconciling them at
the clean-DB cutover. Built from the Python-3 audit, the entry-point inventory,
and the dependency map._

_Last updated: 13-ago-2026_

---

## Estado (08-ago-2026): primera Pi validada en la red nueva

**pi-rackmossbauer arranca Debian 13 por netboot desde `/nfs/pi-trixie`, con
Tango 10, y el Starter lanza sus device servers.** Los únicos fallos restantes son
por hardware ausente (la Pi está en el despacho, no en el laboratorio).

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
- **WisselMCA/1** ✅ reactivado (13-ago-2026): devuelto a la raíz del repositorio y
  dado de alta en las tres listas del `pyproject.toml`, así que ya se instala y el
  Starter lo encontrará. Falta instalar sus dependencias en la raíz Trixie y
  probarlo contra un MCA real (ver _Dependencias de WisselMCA_ más abajo).
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
- Import test: **31/31 live servers import** with deps present. 6 GPIO servers
  (RaspberryButton, RaspberrySwitch, TempSensorDS18B20, Motor, SEAWaterflowmeter,
  WaterSwitch) only import on a real Pi — `RPi.GPIO` refuses to load on x86; this
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

Tally: **32 live · 8 inactive · 3 deprecated** (= 43 entry-point servers), plus
RaspberryButton_old (dead duplicate, remove) and PANIC (third-party, separate).

_(Era 31 · 9 hasta el 13-ago-2026, cuando WisselMCA pasó de inactivo a vivo. El
recuento del chroot de arriba, con fecha 30-jun-2026, es anterior a ese cambio: al
reinstalar deben salir 32 wrappers, no 31.)_

---

## Server inventory

### LIVE — install on the Trixie root (32)

Entry point in `[project.scripts]`, installed, registered in the new DB.

AGPolaritySwitch, AMLPGC1, ArduinoDAC, ArduinoMotor, ArduinoPt, MFC
(BronkhorstMFC), CryoCon32, ElmitecLEEM2k, ElmitecUview, FUGMCP, HuttingerPFGDC,
HuttingerPFGRF, Hygrometer, Itech6000C, CenterOneGauge (LeyboldCenterOne),
LeyboldIG3, MKSGauge, Motor, NetworkUPSTool, PfeifferHiscroll, PfeifferTC100,
PfeifferTU400, RaspberryButton, RaspberrySwitch, SEAWaterflowmeter, SRIlockin830,
TempSensorDS18B20, VarianTV301nav, WaterSwitch, Tti604, **PIDController**,
**WisselMCA**.

### INACTIVE — keep in repo, do NOT install (8)

Move to `inactive/`. Code present but hardware idle or work remains. Not in
`[project.scripts]`, not registered in the new DB until revived. See
`inactive/README.md` for per-server revival notes.

GammaIonPump, GammaVacuumSPCe, Keithley2100, MCC1208LS, PfeifferDCU002,
V4L2Camera, VSMControlDevice, WebCam.

_(WisselMCA salió de esta lista el 13-ago-2026 — reactivado, ver más abajo.)_

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
| python3-rpi.gpio | RPi.GPIO | RaspberryButton, RaspberrySwitch, TempSensorDS18B20, Motor, SEAWaterflowmeter, WaterSwitch |
| python3-nut | PyNUT | NetworkUPSTool |

```bash
apt update
apt install -y python3-tango python3-serial python3-rpi.gpio python3-nut
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

- **GPIO library**: `python3-rpi.gpio` exists, but RPi.GPIO has had Trixie-kernel
  compatibility issues; the ecosystem has moved toward `rpi-lgpio` (drop-in).
  Confirm RaspberryButton / RaspberrySwitch / TempSensorDS18B20 actually drive GPIO
  on a Pi booted off the Trixie root. **Validate this first** — three live servers
  depend on it.
- **w1thermsensor**: the kernel one-wire modules + overlay must be enabled on the
  Pi, independent of the pip package.

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

WisselMCA ✅ reactivado (13-ago-2026): ya está en la raíz del repositorio y en el
`pyproject.toml`, así que se instala y el Starter lo encontrará en `StartDsPath`.
Pendiente: sus dependencias en la raíz Trixie y la prueba contra un MCA real (ver
_Dependencias de WisselMCA_ más abajo).

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

| DS | propiedad | valor por defecto | puerto |
|---|---|---|---|
| ElmitecLEEM2k | `IP` | `tvips.lab` | 5566 |
| ElmitecUview | `UviewIP` | `tvips.lab` | 5570 |
| Itech6000C | `IP` | `PWSItech6000VSM.lab` | 30000 |

`tvips` es el ordenador del LEEM, que controla también la cámara TVIPS XFS216.

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

**Permisos**: el DS abre el dispositivo por VID/PID `0x0925:0x0035` a través de
`/dev/hidraw*`, accesible solo por root por defecto. Si el servidor corre como
usuario normal bajo el Starter hace falta una regla udev:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0925", ATTRS{idProduct}=="0035", MODE="0660", GROUP="plugdev"
```

y el usuario en `plugdev`. Es la causa más habitual de que uno de estos arranque
bien y falle al abrir el aparato.

Sigue **sin probar contra un MCA real** — era la advertencia de
`inactive/README.md` y continúa vigente.

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
   - [ ] Top-level `pyproject.toml` lists exactly the **32** live entry points
         (build-backend = `setuptools.build_meta`).
   - [ ] PIDController added as a live entry; its Makefile removed.
   - [ ] 3 dead → `deprecated/`, 8 paused → `inactive/`, both excluded in
         `packages.find`.
   - [ ] RaspberryButton_old removed.
   - [x] WisselMCA encoding fix committed, y el servidor reactivado el
         13-ago-2026: vive en la raíz y está en el `pyproject.toml` (32ª entrada).
2. **Trixie root install (in chroot, binds mounted)**
   - [ ] apt deps: `python3-tango python3-serial python3-rpi.gpio`,
         más `python3-numpy libhidapi-hidraw0` para WisselMCA.
   - [ ] pip deps: `simple-pid w1thermsensor` (`--break-system-packages`),
         más el binding HID de WisselMCA (ver sección de dependencias).
   - [ ] `pip install -e --no-deps --break-system-packages .` from repo root.
   - [ ] All 32 live wrappers present in `/usr/local/bin`; no parked ones.
   - [ ] `/etc/tangorc` = `TANGO_HOST=tangodb.lab:10000`.
   - [ ] **Unmount binds** (`/dev`, `/proc`, `/sys`) before any exportfs/rsync.
3. **Clean DB**
   - [ ] Build fresh DB with the 32 live servers only — parked ones never entered.
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
