# SURFMOSS Device Servers — Migration Reference

_Single source of truth for installing the SURFMOSS Tango device servers onto
the new Trixie NFS root (`/nfs/pi-trixie` on wolframite) and reconciling them at
the clean-DB cutover. Built from the Python-3 audit, the entry-point inventory,
and the dependency map._

_Last updated: 27-Aug-2026_

---

## Status (27-Aug-2026): two servers meeting their hardware for the first time

### CenterOneGauge: the state could only ever move to OFF (`ef1d1e1`)

It read pressure correctly and reported OFF. `read_Pressure` set OFF when an
exchange failed, and nothing anywhere set ON again — `init_device` set it once
at start-up and that was the only path to it. One transient bad exchange left
the device measuring perfectly and reporting OFF for ever. Found on
`leem/vacuum/gaugeEvap` at 3.6 mbar, ATTR_VALID, state OFF, and ON again the
moment it was restarted.

Every path sets the state now, in both directions. A failed read returned 0.0,
which on a pressure gauge reads as perfect vacuum; those paths return
ATTR_INVALID, as `eb90aba` did for LeyboldIG3. The measurement status field was
being parsed and discarded: confirmed against the gauge, `PR1` answers `\x06`
and `ENQ` answers `0, 3.6000E+00`, and 0 is the only value of that field meaning
the number beside it is a reading. The port also finally got `timeout=1`,
without which a silent gauge blocked in `read_until` rather than failing and
none of the new error handling could ever run.

### GammaVacuumDigitel: written to the serial packet, run over Telnet (`0a016bc`)

_Renamed from `GammaVacuumSPCe` on 27-Aug-2026 (`6ffce36`), when it grew to serve
the QPC as well; the old name appears below only in dated entries._

The server the repository had flagged as *never tested against the real
controller*. Pointed at the LEEM column ion pump, it connected and reported
nothing correctly. One root cause behind all of it.

The manual is explicit that over Telnet, "unlike the serial command protocol, no
opening tilde, **no address field, and no checksum** are required". The serial
reply is `<ADDRESS> <STATUS> <CODE> [data] <CHECKSUM>` and the code read it that
way — STATUS at `parts[1]`, first data field at `parts[3]`. Over Telnet the
reply is `OK 00 2.2E-09 MBA`, so every field was read one place to the right.
That is why `_connect` tested `parts[3] == 'YES'` against a three-field reply,
always fell through, and reported OFF while the pump ran with its HV on.

The reply also ends CR CR LF and then a `>` prompt:

```
spc 0b\r\n  ->  b'OK 00 2.2E-09 MBA\r\r\n>'
```

The reader stopped at the first CR and consumed one more byte, leaving the rest
in the socket: every exchange returned the *previous* command's reply with an
empty read between, and the lag grew by one per call. Asking six times for the
pressure returned a voltage, nothing, a status, nothing, a pressure, nothing.
It reads to the prompt now and drains anything stale before writing.

Two things the hardware settled that the manual has wrong:

- **The unit is `MBA`.** The manual documents `Torr`, `MBR` or `PA`. `MBA` was
  in neither the manual nor the conversion table, and an unknown unit fell back
  to 1.0 — right by luck for mbar, a silent 1.33x error had the pump been in
  Torr. Unknown units are refused now instead of guessed.
- **`3C GET SETPOINT` answers two values, not five.** The manual documents
  `N, E, X.XE-XX, Y.YE-YY, O`; this unit answers `9.0E-08,2.0E-07`. There is one
  setpoint — `3C 2` gives `ER 08 *ERROR: PARAMETER 1: ILLEGAL RANGE (1 - 1)`.

Also: `_HV_OFF_CURRENT` and `_HV_OFF_PRESSURE` were defined and used nowhere,
so an HV-off pump served its `0.1E-10` marker as a reading of 1e-11 mbar — an
outstanding vacuum. And a command the controller will not run still answers
`OK`, with the complaint in the data (`OK 00 *ERROR: COMMAND DISABLED`), so
STATUS alone never said whether there was a reading.

**Pressure interlock** (`109cc90`): `SetpointOn` and `SetpointOff`, in mbar —
9e-08 and 2e-07 on this pump. The relay's own state is **not** exposed: it is
not readable over the protocol on this unit, and deriving it from the pressure
would be a guess, since the manual has the relay latching once active and also
turning on for error conditions. Reading pin 11 of J1 (*setpoint logic output*)
with a Pi GPIO would give the real state if it is ever wanted. An Off Point of
`0.1E-10` is the same literal as the HV-off marker with a different meaning —
the manual says the setpoint then latches on — and is reported INVALID rather
than as a 1e-11 mbar threshold.

Verified against the pump: ON, 2.2e-09 mbar, 7.9e-07 A, -3500 V, RUNNING,
9e-08 / 2e-07 setpoints, all ATTR_VALID, with repeated rounds returning their
own values rather than each other's.

---

## Status (26-Aug-2026): the three Pfeiffer servers, and what is still open

All three are running against real pumps:

| Device | Server | Pi | Port | Address | Reading |
|---|---|---|---|---|---|
| `xps/vacuum/turboPCH` | PfeifferTC100/1 | pi-xps | `…usb-0:1.2:1.0-port0` | 001 `TC100` | 990 Hz, 0.17 A |
| `leem/vacuum/turboPCH` | PfeifferTU400/1 | pi-uleem | `…usb-0:1.1.2:1.0-port0` | 001 `TC 400` | 1000 Hz, 0.53 A |
| `leem/vacuum/scrollPump` | PfeifferHiscroll/1 | pi-uleem | `…usb-0:1.2.3:1.0-port0` | 002 `HiScrl` | 1557 rpm, 0.41 A |

Four separate faults were behind "the server dies seconds after the Starter
launches it". Only the first was a Python 3 problem, and even that one was not
really about Python.

### Fixed: `read_until()` lost its keyword in pyserial 3 (f018f5b)

```python
resp = self.ser.read_until(terminator=b"\r")     # pyserial 2.x
TypeError: SerialBase.read_until() got an unexpected keyword argument 'terminator'
```

3.x calls the argument `expected`. The call is **older than the migration** and
worked on the pyserial 2.x that Python 2 used; what moved underneath it was the
library, not the language. It was in PfeifferTU400, PfeifferHiscroll,
PfeifferTC100, CenterOneGauge and MKSGauge.

Now passed positionally, `read_until(b"\r")`, which both versions accept.

**Why it survived the migration:** db0bca9 was checked with `python3 -m
py_compile` ("All 40 DS Python files now pass"), and a wrong keyword argument
compiles perfectly. `tools/audit_serial_api.py` is that gap closed.

**Why it killed the server rather than one attribute:** the call sits in
`init_device`, and an exception escaping `init_device` makes PyTango exit the
whole process — the Starter then leaves it for dead. All three now catch and go
FAULT with the reason in the status, as LeyboldIG3 does. `sendcommand()` also
checks the reply before indexing it (length, announced against actual,
checksum, parameter echo) and clears the input buffer before writing;
PfeifferHiscroll additionally had no `timeout=`, so a silent pump hung
`init_device` for ever instead of failing.

### Fixed: PfeifferHiscroll reported watts as degrees (be3b186)

`read_TemperatureFinalStage` asked for **P316**, which is what `read_Power`
already asks for. It showed as `168.0 °C` next to `168 W` on the running pump.
The power stage temperature is **P324**: read back 56, next to P326
(electronics) 55 and P346 (motor) 54.

No framing check could have caught this — the pump answers P316 correctly. It
was asking the wrong question, and only live hardware showed it.

### Fixed: a converter with a vendor PID gets no `/dev` entry, silently

PfeifferTU400 could not open its port although the property was right and the
cable was in. On pi-leem, `1-1.1.2` was enumerated with **no driver bound**:

```
1-1.1.2    0403:daf1  drv=NONE  tty=none  Delphin USB Serial Converter 09QC4001
```

An FTDI part (vendor `0403`) reflashed with a vendor product id that is not in
the `ftdi_sio` table. Nothing is logged as an error; the port is simply absent.
Fixed with a udev rule now on the shared root — see
`docs/netboot-shared-root.md` for the rule and how to test it from `/run`.

### Not a fault: the servers were being looked for on the wrong Pi

`PfeifferTU400/1` and `PfeifferHiscroll/1` belong to **pi-uleem**, not pi-leem.
pi-leem's USB tree is numbered so much like pi-uleem's that both `SerialPort`
properties named paths that *existed* there, with entirely different adapters on
them — so the symptom was silence, not an error, and it looked like stale
properties or dead pumps. The properties were correct all along.

The remaining silence on the TU400 was the RS-485 converter itself; it answered
as soon as it was reconnected by hand. `tools/pfeiffer_probe.py` is what
distinguishes these cases: a pump that is off and a property pointing at the
wrong port are both silence, and only a name coming back tells them apart.

### Still open

- ✅ **PfeifferHiscroll's `TemperatureFinalStage`** — fixed in `be3b186`,
  deployed and restarted 26-Aug-2026; it reads ~56 °C instead of the drive
  power.
- ⚠️ **`inactive/PfeifferDCU002` and `inactive/GammaIonPump` still carry
  `read_until(terminator=…)`.** They are not installed, so they break nothing
  today, but they will die on first use. `tools/audit_serial_api.py` reports
  both.
- ✅ **CenterOneGauge** — it got `timeout=1` along with its own fix in
  `ef1d1e1`; see the 27-Aug-2026 section below.
- ⚠️ **pi-leem's FTDI on `1.2.3` (`AB0JP499`) logs real USB faults** —
  `failed to set flow control: -71`, `urb stopped: -32`. That adapter or its
  cabling looks independently bad.
- The `0403:daf1` Delphin converter on pi-leem's `1.1.2` belongs to something
  else on that Pi; no Pfeiffer answers on it. The udev rule is still needed
  there, just not for the TU400. **Unidentified.**
- 2.x camelCase spellings (`inWaiting`, `flushInput`) remain in AMLPGC1,
  Hygrometer and Tti604. They work in pyserial 3.5 and are deprecated, nothing
  more.

### Tools added for this (d906b33)

```
python3 tools/audit_serial_api.py           # every DS, against the pyserial API
python3 tools/pfeiffer_probe.py             # on a Pi: who is on which port
python3 tools/<either> --self-test          # both check their own method first
```

`audit_serial_api.py` reads the servers with `ast` and checks each call on a
pyserial object against what pyserial 3.5 accepts. Its table is frozen from the
Pi and `--self-test` compares it against the installed pyserial wherever
pyserial can be imported; the regression fixture is this repository's own
history (the five files must report at `f018f5b^` and must not at `f018f5b`).

`pfeiffer_probe.py` is read-only — action `00` only, never `10` — because
aiming `Start` or `SetRotSpeed` at whatever happens to be on a port is how a
vacuum system gets damaged. **Stop the device server before probing its port:**
the port is not locked, and two openers on one bus read each other's replies.

---

## Status (08-Aug-2026): first Pi validated on the new network

**pi-rackmossbauer boots Debian 13 by netboot from `/nfs/pi-trixie`, with Tango
10, and the Starter launches its device servers.** The only remaining failures
are from absent hardware (the Pi is in the office, not in the lab).

> Correction of 17-Aug-2026: that was not quite true. With the hardware present,
> TempSensorDS18B20 and WisselMCA still failed, through defects in their own code
> (see their sections below). "It only fails because the hardware is absent" was
> a hypothesis, not a check.

Chain validated end to end: DHCP → TFTP → NFS → system → DNS `.lab` → NTP →
Tango DB → Starter → device servers.

### Three problems solved that day (all three blocked DS start-up)

**1. MariaDB collations — the main cause, and the hardest to see.**
The database imported from the old server had every table in
`utf8mb4_general_ci`, while the database on MariaDB 11 (Debian 13) defaulted to
`utf8mb4_uca1400_ai_ci`. The **stored procedures** (`ds_start`,
`import_device`…) compare parameters against columns and failed with
`ERROR 1267: Illegal mix of collations`. Their `EXIT HANDLER` turned that into a
generic `MySQL Error`, and Databaseds translated it into
**"The device server X is not defined in database. Exiting!"** — a misleading
message that cost a whole day of diagnosis.

Characteristic symptom: read queries work (listing instances, `--check-server`,
`import_device` from PyTango), but **starting** any device server fails. It fails
identically with Tango 9 and Tango 10, from any machine, by name or by IP. It is
neither a version nor a network problem.

Diagnosis: calling the procedure by hand reveals the masked failure.
```bash
sudo mysql tango -e "CALL ds_start('Starter/pi-rackmossbauer','pi-rackmossbauer',@res); SELECT @res;"
# -> MySQL Error
```
To see the real error, the procedure has to be recreated without its `EXIT HANDLER`.

Fix:
```bash
sudo mysql -e "ALTER DATABASE tango CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
sudo mysql tango < /usr/share/tango-db/stored_proc.sql   # recreate: they keep the collation they were created with
```
⚠️ **Critical for the clean reimport**: if the old dump is loaded again, the
problem comes back. The procedure must always include the collation change and
the recreation of the stored procedures.

**2. `argv[0]` with an absolute path in the Python device servers.**
The wrappers `pip install -e` generates leave the full path in `sys.argv[0]`
(`/usr/local/bin/ElmitecLEEM2k`). PyTango 10 uses `argv[0]` as the server name,
and the DB has it registered as plain `ElmitecLEEM2k` → no match.
(The old `setup.py install` used `EASY-INSTALL-ENTRY-SCRIPT`, which did leave
the bare name; that is why it used to work.)

Fix applied to all 41 servers (31 live plus inactive), inside the POGO protected
region:
```python
sys.argv[0] = os.path.basename(sys.argv[0])
```
Note: 40 of the 41 files **imported neither `os` nor `sys`**; both had to be added.

**3. Databaseds publishing `0.0.0.0`.**
`/etc/tangorc` had `TANGO_HOST=0.0.0.0:10000` (an earlier fix so it would listen
on every interface). That works for listening, but the published IOR then carries
`0.0.0.0` and remote clients cannot reconnect → `TRANSIENT_CallTimedout` when
asking for `sys/database/2`.

Fix — drop-in `/etc/systemd/system/tango-db.service.d/endpoint.conf`:
```
[Service]
ExecStart=
ExecStart=/usr/lib/tango/Databaseds 2 -ORBendPoint giop:tcp:0.0.0.0:10000 -ORBendPointPublish giop:tcp:10.43.88.3:10000
```

### Other adjustments to the Trixie root (they affect every Pi, it is shared)

- **Boot firmware**: the initial copy brought only partition p2, without
  `/boot/firmware`. It was obtained with `apt install --reinstall raspi-firmware
  linux-image-rpi-v8` inside the chroot, and copied to `/tftpboot/<serial>/`.
  (`mkinitramfs` fails in a chroot and on an NFS root — that is expected and
  **not needed**: with `root=/dev/nfs` + `ip=dhcp` the kernel mounts the root
  without an initrd.)
- **`config.txt`** needs `arm_64bit=1` (the root is arm64, the Pis are 3B+).
  Keep `dtoverlay=w1-gpio,gpiopin=4` (TempSensorDS18B20). Verified that the
  1-Wire bus comes up on Trixie (`/sys/bus/w1/devices/` exists).
- **`/etc/resolv.conf`** had been copied from the chroot with the old network's
  DNS. Corrected to `nameserver 10.43.88.3` + `domain lab`.
- **`/etc/systemd/timesyncd.conf`** → `NTP=tangodb.lab`. timesyncd **ignores**
  the DHCP NTP option; it has to be set explicitly.
- **User**: the RaspiOS image ships `pi` with `/usr/sbin/nologin` and `!` in
  shadow; complete it with the first-boot wizard (or by hand from wolframite).
- **`tango-starter`** was not installed; its systemd unit has
  `Requires=tango-db.service`, which does not exist on the Pi. The unit has to be
  copied to `/etc/systemd/system/` and that line deleted (a drop-in with an empty
  `Requires=` does **not** cancel it).
- ⚠️ `ExecStartPre=tango-starter-register-helper` **creates records automatically**
  in the DB, taking the name from `TANGO_HOST` (it created a spurious
  `Starter/tangodb.lab`). Watch for it on every new Pi.

### Pending on this Pi

- Return it to the lab and validate LeyboldIG3 (serial port) and
  TempSensorDS18B20 (1-Wire sensor). Both now fail only through absent hardware.
- **WisselMCA/1** ✅ reactivated (13-Aug-2026) and **tested against the real MCA**
  (17-Aug-2026): HID protocol verified, four defects corrected. Still to do:
  start it under the Starter with the corrected code (see
  _WisselMCA dependencies_ below).
- **TempSensorDS18B20/1** no longer fails through absent hardware: the sensor
  `28-3cd5f649fc87` answers. It died at start-up through a defect in the server,
  corrected on 17-Aug-2026 (see _TempSensorDS18B20_ below).
- LeyboldIG3's serial path (`/dev/serial/by-path/platform-3f980000.usb-...`)
  encodes the physical USB port: if it is moved to another connector, the
  property has to be updated.

### Recovered assignment inventory

`~/tango-server-assignments.txt` on wolframite holds the output of
`SELECT name, host, level FROM server ORDER BY host, level` — 64 rows of which
server runs on which machine and at which start level. It is the source for
filling in the "TBD"s of the _Host → server assignments_ section below.

Careful: the hosts appear with the old domain `.labo` (`pi-leem.labo`,
`sputtering.labo`…). The new network uses `.lab`.

### pi-rackmossbauer's servers (confirmed from the DB)

`LeyboldIG3/1`, `TempSensorDS18B20/1`, `WisselMCA/1`.

---

## Chroot status (30-Jun-2026)

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

## ⛔ Do not run POGO's *Generate* on an existing server (20-Aug-2026)

**POGO 9.10.6 cannot regenerate these servers.** Tried on SEAWaterflowmeter: the
file it produced **does not even compile**. Three kinds of damage, independent of
one another:

1. **SyntaxError — repeated `label`.** For every attribute it emits `label`
   twice, once from the name and once from the model's `<properties>` block:
   ```python
   @attribute(label='channel0', dtype='DevDouble', label="channel0", ...)
   #                                               ^^^^^ keyword repetido
   ```
   `SyntaxError: keyword argument repeated: label`.

2. **NameError — it modernises the header but not the regions.** It changes
   `import PyTango` to `import tango`, and copies the protected regions
   literally, with their `PyTango.DevState`, `PyTango.Except.throw_exception` and
   `PyTango.AttrQuality.ATTR_INVALID` still inside. Eight references to a name
   that is no longer bound. **40 files in the repository** have that pattern.

3. **Silent changes of behaviour.** `polling_period=3000` appears on the
   attributes, out of the `polledPeriod` that had sat in the model for years with
   no effect — the server starts polling on its own. It adds scaffolding that
   does not match the implementation (`self._channel0 = 0.0` against the real
   `self.channeldata`), renames the read methods, creates a `__main__.py`, and
   **deletes any comments outside the protected regions**.

On top of that, opening a model strips the `<states>` it declares. Of the 107 in
the repository, 96 have an empty description and nothing is lost; the **11 with a
real description** are in CryoCon32, ElmitecUview, NetworkUPSTool and
VarianTV301nav, and there it does cost something
(`STANDBY = running on battery power`).

### What did work

**The protected regions survive intact**, including helper methods put in
`class_variable`. What does not fit is everything POGO generates around them. And
POGO **is still good for creating new servers from scratch**: the MFC generated
clean came out correct.

### The decision (option A′)

The `.xmi` is **documentation of the interface**: good for Jive, for documenting,
and for reviewing what a server exposes. **Not** for generating. It is kept in
step by hand — POGO has been confirmed to accept a hand-edited `.xmi` without
complaint, even with whole `<attributes>` blocks added — and POGO is used only to
read the model.

The safety net is **`tools/check_xmi.py`**, which compares model against code
across all 44 servers and fails if they diverge. Worth running before committing
an interface change:

```bash
python3 tools/check_xmi.py            # 0 if everything matches, 1 if there are divergences
```

State at the time of writing: 41 in sync, 0 divergences, 3 with no model
(AnalogInterlock, GammaVacuumDigitel and GranvillePhillips350 — all three
written by hand rather than with POGO) and 1 not comparable (PIDController, an
old template using `DeviceClass`).

⚠️ And if *Generate* is ever run by mistake, the wreckage shows up at once:
`python3 -m compileall` fails, because the file does not compile.

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

Tally: **34 live · 7 inactive · 4 deprecated** (= 45 entry-point servers).

_RaspberryButton_old and PANIC used to be counted here as special cases; neither
is in the repository any more. See the note below._

_(It was 31 · 9 until 13-Aug-2026, when WisselMCA and GammaVacuumDigitel (then
GammaVacuumSPCe) went from inactive to live, and 33 · 7 · 3 until 18-Aug-2026, when Motor went to
deprecated. The chroot tally above, dated 30-Jun-2026, predates both changes:
a reinstall should produce 32 wrappers, not 31.)_

---

## Server inventory

### LIVE — install on the Trixie root (34)

Entry point in `[project.scripts]`, installed, registered in the new DB.

AGPolaritySwitch, AMLPGC1, **AnalogInterlock**, ArduinoDAC, ArduinoMotor, ArduinoPt, MFC
(BronkhorstMFC), CryoCon32, ElmitecLEEM2k, ElmitecUview, FUGMCP, HuttingerPFGDC,
HuttingerPFGRF, Hygrometer, Itech6000C, CenterOneGauge (LeyboldCenterOne),
LeyboldIG3, MKSGauge, NetworkUPSTool, PfeifferHiscroll, PfeifferTC100,
PfeifferTU400, RaspberryButton, RaspberrySwitch, SEAWaterflowmeter, SRIlockin830,
TempSensorDS18B20, VarianTV301nav, WaterSwitch, Tti604, **PIDController**,
**WisselMCA**, **GammaVacuumDigitel**, **GranvillePhillips350**.

### INACTIVE — keep in repo, do NOT install (7)

Move to `inactive/`. Code present but hardware idle or work remains. Not in
`[project.scripts]`, not registered in the new DB until revived. See
`inactive/README.md` for per-server revival notes.

GammaIonPump, Keithley2100, MCC1208LS, PfeifferDCU002,
V4L2Camera, VSMControlDevice, WebCam.

_(WisselMCA and GammaVacuumDigitel, then GammaVacuumSPCe, left this list on
13-Aug-2026 — reactivated,
see below.)_

### DEPRECATED — dead hardware, remove from install set permanently (4)

Move to `deprecated/`. **Death by omission**: never entered in the new DB. See
`deprecated/README.md`.

MitutoyoPostable, **Motor**, SpecsXRC1000, VarianMultiGauge.

_(Motor came here on 18-Aug-2026, replaced by an Arduino with a DRV8825; its
replacement is `ArduinoMotor`. Checked on 23-Aug-2026 that nothing of it is left
in the DB — not as a server, not as a class, and with no devices.)_

### ⏳ Written but never run against its instrument

- **GranvillePhillips350** — added 27-Aug-2026 for the Granville Phillips 350
  ion gauge on pi-leem, over a USB-serial adapter and a null modem cable. It is
  in the install set, but the instrument was disconnected the day it was
  written, so only its parsing has been exercised (over a stub, against the
  real methods). The framing, the cable and DCD are all unverified. Run
  `tools/gp350_probe.py` on pi-leem before registering it: nothing in the
  protocol reports the baud rate or byte framing, which are DIP switches, so
  the probe walks the manual's 8 x 8 table and prints the properties to set.
  See `GranvillePhillips350/README.md`.

### Special cases

- **RaspberryButton_old** — ✅ no longer exists. It was a dead duplicate of
  RaspberryButton that forced the TOML deduplication. Checked on 23-Aug-2026: it
  is not at the root, nor in `inactive/`, nor in `deprecated/`.
- **PANIC (PyAlarm)** — ✅ removed from the tree on 21-Aug-2026. ALBA's alarm
  system, third-party code, Python 2 + Qt5, with no port planned. It never had an
  entry point here. What it watched over is in
  [`alarms-panic-legacy.md`](alarms-panic-legacy.md), recovered from the old
  network's DB; the code is at the `panic-final` tag and at
  https://github.com/ALBA-Synchrotron/panic

- **AnalogInterlock** — ✅ installed from 27-Aug-2026. It was deliberately held
  out of `[project.scripts]` and `packages` while pi-xps still booted from its
  own microSD and shared no software with the root, which is why the directory
  and installable counts used to differ. pi-xps netboots now, and both of its
  prerequisites are in the repository: `SEAWaterflowmeter`'s `UpdateCount` and
  `channelnames`, and `RaspberryButton`'s `Keepalive` / `DeadmanTimeout`.
  Installing it does **not** register or start it — see `AnalogInterlock/README.md`
  for the properties, which must be set before its first start, and for the
  commissioning sequence.

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
| python3-rpi-lgpio | RPi.GPIO (shim) | RaspberryButton, RaspberrySwitch, SEAWaterflowmeter, WaterSwitch — see _GPIO on Trixie_ |
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
  other user (VSMControlDevice) is inactive. ⚠️ The "no live server imports numpy"
  above stopped being true when WisselMCA was reactivated, as it does use it.
- **opencv / python3-opencv** — only V4L2Camera (inactive).
- **usb_1208LS / Linux_Drivers source build** — only MCC1208LS (inactive). The
  single nastiest install, gone.

Net pip footprint: **two pure-Python packages.** The entire compiled/ARM-painful
dependency set has been eliminated by omission.

### Verify on real hardware (cannot be tested in the x86 chroot)

- **GPIO library**: ✅ resolved on 18-Aug-2026 — RPi.GPIO **does not work** on
  Trixie, `python3-rpi-lgpio` has to be used, and two further workarounds are
  needed. See _GPIO on Trixie_ below, which already records the hardware
  verification of `SEAWaterflowmeter/4` (pi-vsm) and `RaspberrySwitch/2`
  (pi-leem). `RaspberryButton` runs only on pi-xps, which is still on microSD, so
  its turn has not come; `WaterSwitch` is not registered anywhere.
  TempSensorDS18B20 left this list on 17-Aug-2026 (its pin is handled by the
  kernel's w1-gpio overlay) and Motor on 18-Aug-2026 (to `deprecated/`).
- **w1thermsensor**: the kernel one-wire modules + overlay must be enabled on the
  Pi, independent of the pip package. ✅ Verified on 17-Aug-2026 on
  pi-rackmossbauer: `w1_gpio`/`w1_therm` loaded and the sensor enumerates, though
  the bus is noisy (see _TempSensorDS18B20_).

---

## Host → server assignments

All three of (entry points / Starter list / DB) reconcile per-host. Populate each
Pi's list from its Starter's controlled-servers in Astor.

### pi-leem (.10, /nfs/leem) — from Astor

Controlled servers (all live): AMLPGC1/1, ElmitecLEEM2k/1, ElmitecUview/1,
FUGMCP/1·2·3, NetworkUPSTool/1, PIDController/1·2·3, RaspberrySwitch/2.

Removed at clean import: **VarianMultiGauge/1** (deprecated — was red in Astor).

### pi-rackmossbauer (.11) — CONFIRMED from the DB (08-Aug-2026)

`LeyboldIG3/1`, `TempSensorDS18B20/1`, `WisselMCA/1`.

WisselMCA ✅ reactivated (13-Aug-2026) and tested against the real MCA
(17-Aug-2026): it is now at the repository root and in `pyproject.toml`, so it
installs and the Starter will find it in `StartDsPath`. Pending: start it under
the Starter with the corrected code (see _WisselMCA dependencies_ below).

Already migrated to `/nfs/pi-trixie` (Debian 13). The other two servers start and
fail only through absent hardware.

### pi-vsm (.12) — CONFIRMED from the Starter (18-Aug-2026)

`AGPolaritySwitch/1`, `Itech6000C/1`, `SEAWaterflowmeter/4`, `SRIlockin830/1`,
`Tti604/1`. Todos ON el 18-ago-2026.

Already migrated to netboot from `/nfs/pi-trixie`. VSMControlDevice is still in
`inactive/` and is **not** registered here; confirm whether it is needed before
reviving it.

⚠️ **`pi-vsm.lab` has no record in the lab DNS** (18-Aug-2026), and it is the only
one missing: `pi-leem`, `pi-xps`, `pi-uleem`, `pi-mossbauer`, `sputtering` and
`tangodb` do resolve. It has to be reached by IP (`10.43.88.12`), and that is the
cause of that Pi's `sudo: unable to resolve host`.

### Other Pis (pi-xps, pi-mossbauer, pi-hvleem, ender, …) — partially known

From the DB, GPIO servers (18-Aug-2026): pi-xps runs `RaspberryButton/1` and
`SEAWaterflowmeter/3`; pi-uleem, `RaspberrySwitch/1` and `SEAWaterflowmeter/1`;
pi-mossbauer, `SEAWaterflowmeter/2`; sputtering, `ArduinoMotor/1`. **The first
three were still booting from microSD** rather than netboot — see _Netboot versus
microSD_. (Out of date: see the update below.)

_Fill in per host from Astor as they are migrated._

#### Update (26-Aug-2026): read from the DB, not from Astor

`db.get_host_server_list()` is the authority — `tango/admin/<host>`'s `Servers`
property is empty on every host here, so the assignment lives in the per-server
record (`db.get_server_info()` → `host`, `mode`, `level`) and is what the
Starter acts on. Confirmed:

```
pi-leem.lab   AMLPGC1/1, ElmitecLEEM2k/1, ElmitecUview/1, FUGMCP/1·2·3,
              NetworkUPSTool/1, PIDController/1·2·3, RaspberrySwitch/2
pi-uleem.lab  CenterOneGauge/1, Hygrometer/3, PfeifferHiscroll/1,
              PfeifferTU400/1, RaspberrySwitch/1, SEAWaterflowmeter/1,
              TempSensorDS18B20/2
pi-xps.lab    PfeifferTC100/1  (+ RaspberryButton/1, SEAWaterflowmeter/3)
```

**The two LEEM pumps belong to pi-uleem**, and neither appears under pi-leem.
An Astor window left open from before the change keeps showing them under
pi-leem in red; refresh it.

**pi-uleem netboots now** (resolved 26-Aug-2026), so the note above about the
first three still running from microSD is out of date: **pi-hvleem is the only
Pi left on microSD.** See `docs/netboot-shared-root.md`.

#### Update (27-Aug-2026): pi-laser

```
pi-laser      GammaVacuumDigitel/1  (leem/vacuum/IonPumpColumns)
```

The first **Pi 4** in production, netbooting from the shared root. It was
missing from this section entirely. Its server's `IP` property is
`leemColumnsIonPump.lab` (`10.43.88.43`); `Port` is unset, so it takes the
default 23.

---

## ✅ Hardcoded IPs in the device servers — RESOLVED

Three DS connected to their instrument **over the network** with the IP address
written into the code itself, not into a Tango property: **Itech6000C,
ElmitecUview and ElmitecLEEM2k**.

That blocked the migration: the IPs belonged to the old network (`10.10.99.x`),
so as soon as the instrument changed VLAN the DS stopped finding it.

**Updated in Phase 2** (all three instruments are on the LEEM / VSM).

**Externalised into device properties on 13-Aug-2026** (commits `2d749c8` and
`eba613b`). All three DS already declared the properties and had the correct line
written just above the literal, commented out — that is, whatever was in the
database was being ignored. Now the DB is what counts:

**Names unified on 13-Aug-2026**: the four networked DS now use `IP` and `Port`.
ElmitecUview had them as `UviewIP` / `UviewPort`, and GammaVacuumDigitel called its
own `Host`.

| DS | property | default value | `Port` |
|---|---|---|---|
| ElmitecLEEM2k | `IP` | `tvips.lab` | 5566 |
| ElmitecUview | `IP` | `tvips.lab` | 5570 |
| Itech6000C | `IP` | `PWSItech6000VSM.lab` | 30000 |
| GammaVacuumDigitel | `IP` | **no default — it has to be set in the DB** | 23 |

`tvips` is the LEEM computer, which also controls the TVIPS XFS216 camera.

⚠️ The rename has an effect on the database: a value stored under `UviewIP`,
`UviewPort` or `Host` is left orphaned and the DS will not see it. If any device
had them set, they have to be rewritten under the new name.

The defaults were set to the real address, so a property left unset in the DB
gives the correct behaviour. ⚠️ The other way round there is a risk: if a device
already has `IP` or `UviewIP` written in the database with a stale value, that is
now what counts and the DS will fail on restart. Check in Jive before starting.

Three details that came out of doing this:

- **ElmitecUview had three different addresses noted**: `leem.labo` in the code,
  `leemPC.labo` as the `.py` default and `10.10.99.29` in the `.xmi`. Unified.
- **ElmitecLEEM2k had no default at all.** With the property unset, `self.IP`
  would have come out as an empty string and `connect()` would have failed
  silently — the bare `except` swallows it and leaves the DS in FAULT.
- There are no further networked DS: the rest are serial, USB or GPIB.
  `grep -rn '10\.10\.99'` over the device servers now comes back empty.

Note: the serial-port DS have an analogous but different problem — the
`/dev/serial/by-path/...` path encodes the physical USB connector. It does not
change with the network, but it does if the converter is plugged into another
port on the Pi.

---

## WisselMCA dependencies (reactivated 13-Aug-2026)

The server came back to the repository root and is the **32nd entry** of
`pyproject.toml` (`[project.scripts]`, `[tool.setuptools.packages]` and
`[tool.setuptools.package-dir]`). It already had the `argv[0]` fix, because the
pass over the 41 servers covered the inactive ones too.

It needs **numpy** and an HID binding. And there is the trap: the code calls

```python
dev = hid.device()          # lower case
```

That API is **cython-hidapi**'s, which PyPI publishes as **`hidapi`**. The PyPI
package literally named `hid` is a different project: it exposes `hid.Device()`
with a capital, and would raise `AttributeError` on opening the device. Both
occupy the same module name on import, so the error only shows at run time, not
at install time.

On the Trixie root:

```bash
apt install python3-numpy libhidapi-hidraw0
apt install python3-hid        # check which one it is, see below
```

The check that settles it:

```bash
python3 -c "import hid; print(hid.__file__, hasattr(hid,'device'), hasattr(hid,'Device'))"
```

It has to come out `device=True`. If it comes out `Device=True`, it is the wrong
package and `pip install hidapi --break-system-packages` is needed.

`libhidapi-hidraw0` is the C library the binding loads at run time; without it
the `import` fails even with the Python package installed.

⚠️ This breaks the "net pip footprint: two pure-Python packages" of the
dependency section: cython-hidapi is a compiled extension. On ARM64 there is
either a wheel or a build against `libhidapi-dev`, which is why the apt package
is preferable if it works.

**Permissions: TWO udev rules are needed, not one.** The DS opens the device by
VID/PID `0x0925:0x0035`. `hidraw` alone is not enough:

```
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="0925", ATTRS{idProduct}=="0035", MODE="0660", GROUP="plugdev"
SUBSYSTEM=="usb",    ATTR{idVendor}=="0925",  ATTR{idProduct}=="0035",  MODE="0660", GROUP="plugdev"
```

Mind the difference between `ATTRS` (the parent's attributes, for hidraw) and
`ATTR` (the device's own, for usb). The installed binding uses the **libusb
backend**, which goes through `/dev/bus/usb/BBB/DDD` (`crw-rw-r-- root root`) and
**detaches the kernel's hidraw driver on open**, so the `/dev/hidraw*` node
disappears. Without the second rule, `open()` still gives `OSError: open failed`
even with the first one in place and the user in `plugdev`. Diagnosed this way on
pi-rackmossbauer on 17-Aug-2026.

The user running the DS (`tango`) has to be in `plugdev`. Groups are inherited
when the process is created, so **the Starter has to be restarted**, not just the
device server, after a `usermod -aG`.

### Tested against the real MCA (17-Aug-2026)

It is no longer untested: the protocol has been exercised against the card
(serial number `2007 61 122`). Three defects found and corrected, all of them
invisible in a chroot:

1. **HID report reassembly.** `readpage` asked for `dev.read(131)`, but the
   manual (`WisselMCA/CMCA 550_Newprotokoll Remotr Control.pdf`, page 1) says
   "HID-Device, 64 bytes package". hidapi returned only the first report — 62
   useful bytes out of 128 — and left the other two **queued**, so every later
   command read the leftovers of the previous one and answered "wrong count".
   `read_response()` accumulates reports until the answer is complete, and
   `drain()`, called in `open()`, discards whatever a previously desynchronised
   session may have left.
2. **Masked errors.** Twelve places did `(t, r) = self.c.X()` and ignored the
   flag. On failure, `r` was the error string; `r[2] * 10000` is string
   repetition (legal) and only blew up at the division, with a
   `TypeError: unsupported operand type(s) for /: 'str' and 'int'` hundreds of
   lines away from the origin. They now go through `checked()`, which raises a
   Tango exception carrying the device's real message.
3. **uint16 overflow with NumPy 2.** The three window readers did
   `float(r[n] * 10000 / 16383)` on a `numpy.uint16` from `frombuffer`. With
   NumPy 2 (NEP 50) the scalar keeps its dtype, so the multiplication
   **overflows modulo 65536 before dividing**: ULD=819 read as 3.88 mV instead of
   499.91. Since the wrap is not monotonic, changing a limit appeared not to
   affect the reading. The `float()` has to come **before** the arithmetic. It is
   the only DS in the repository exposed to this — the other `uint16`s are Tango
   attribute declarations, not numpy scalars.

**And a design inconsistency**, also corrected: `setPHAmode` and `init_device`
derived the spectrum length from the window's upper limit with
`lastchannel = round(upper_mV * 16383 / 10000)`, which is the mV → **raw 14-bit
value** conversion, not to channels. The limits are input voltages (page 4:
"16383 = 0x3FFF = 10 Volts"), and the result exceeded the hardware: a 10 V window
gave 16383 "channels" on a card of 8192 at most, so `Spectrum` read past the end
of the data, into pages 256-1023 that the manual reserves for DFG.

**The correct mapping, measured on the card:** with `Res=0` and `ULD1 = 1310`
(800 mV), the last channel with counts is **655 = 1310 >> 1, exactly**. That is,
the window's 14-bit value covers the same 0-10 V range as the channels, so

```
channel      = ULD >> (1 + Res)   # half the raw value at 13 bit
total channels = 8192 >> Res      # Res[1:0], bits 2-3 of byte 1 of the General Setup
```

That was exactly what the original author was after: their expression gave the
raw value, which is **twice** the channel. `phalastchannel()` computes it,
clamped to the resolution, and it is used by `init_device`, `setPHAmode` and
`write_Upper_Window_Limit` — moving the upper level moves where the counts end,
so the length follows it.

Reading all 8192 channels adds nothing and costs: the sum is identical (216013
counts either way, because pulses above the upper level are rejected), but it
takes **2.05 s against 0.17 s**. And 2 s is uncomfortably close to Tango's
default client timeout (3 s), which would have made `Spectrum` unreliable for
anyone who does not raise it.

### State verified through the device server (17-Aug-2026)

```
Configuration : 0x0000  -> OS=0  Res=0  -> 13 bit -> 8192 channels
Model         : 2007 61 122
Mode          : 3 (PHA)   ModeByte 0x03 (stopped)
window        : 200.21 - 800.22 mV
Spectrum      : 672 channels in 0.17 s, sum 216013, 491 non-empty channels
```

Writing the limits and reading them back: 2000/5000/8000 mV → raw
3277/8192/13106 → 2000.24/5000.31/7999.76 mV. The original values were restored.

Note: `ReadLastChannel` is a command **with no `dtype_out`** — it returns
nothing, it updates `lastchannel` with whatever the card reports (last non-empty
channel + 1). Returning `None` is its correct behaviour, not a fault. And the
card rounds that value to the end of the page: with data up to channel 655 it
reports 671 (page 20 = channels 640-671).

---

## GPIO on Trixie: RPi.GPIO does not work, rpi-lgpio is needed (18-Aug-2026)

The warning under _Verify on real hardware_ has been confirmed, and in the worst
way: **it fails at run time, not on import**, so the chroot does not catch it and
the server starts up until it touches the pin.

`SEAWaterflowmeter/4` would not start on pi-vsm:

```
File ".../SEAWaterflowmeter.py", line 154, in init_device
    GPIO.add_event_detect(i, GPIO.RISING, callback=my_callback)
RuntimeError: Failed to add edge detection
```

Reproduced in two lines as user `pi` (who is in `gpio`, so **it is not a
permissions problem**), on a Pi 3B+ with kernel 6.18.39 and `python3-rpi.gpio`
0.7.1a4:

```
GPIO.setup(17, GPIO.IN)            -> OK, GPIO.input(17) -> 0
GPIO.add_event_detect(17, RISING)  -> RuntimeError: Failed to add edge detection
```

`setup`, `input` and `output` **still work**; what breaks is only **edge
detection**, which is the one thing RPi.GPIO still does through the old `sysfs`
interface. That is why SEAWaterflowmeter noticed it first: it is the only server
in the repository that uses `add_event_detect`.

**Remedy: `python3-rpi-lgpio`**, a shim that reimplements the RPi.GPIO API on top
of `lgpio`, which talks to `/dev/gpiochip*`. It is in the raspberrypi.com archive
for Trixie (0.6) and its dependency `python3-lgpio` was already installed.

```
Package:   python3-rpi-lgpio
Depends:   python3-lgpio, python3:any
Conflicts: python3-rpi.gpio
Provides:  python3-rpi.gpio
```

⚠️ **It replaces `python3-rpi.gpio`, and the NFS root is shared**: it is installed
in wolframite's chroot and affects **every Pi and every GPIO DS at once**.

Verified without touching the root, by downloading the .deb and extracting it in
`/tmp` with `PYTHONPATH` in front:

```
pin 6:  setup + add_event_detect OK, read 1
pin 13: setup + add_event_detect OK, read 0
```

and with the real server (instance 4, channels 6,13 per the DB):

```
state: ON | Measurement thread is running     channel0 = 0.0   channel1 = 0.0
```

### Second trap: lgpio and the read-only root (18-Aug-2026)

Installing the shim **is not enough**. `rpi-lgpio` imports `lgpio`, and `lgpio`
creates a notification FIFO **in the working directory** as soon as it is
imported. On these Pis that directory is on the read-only NFS root, so the import
dies:

```
File "/usr/lib/python3/dist-packages/lgpio.py", line 504, in __init__
    self._file = open('.lgd-nfy{}'.format(self._notify), 'rb')
FileNotFoundError: [Errno 2] No such file or directory: '.lgd-nfy-3'
```

The `-3` **is not a file number**: it is the error code for having failed to
create the pipe. A misleading message, of the same kind as the collations one.

It is not fixed by the Starter's CWD alone. That CWD is `/var/tmp/ds.log`, which
**is** writable… but it is `pi:pi drwxrwxr-x`, and the DS run as `tango`, who is
not in the `pi` group:

```
xCreatePipe: Can't set permissions (436) for /var/tmp/ds.log/.lgd-nfy0, No such file or directory
```

Nor does pointing everything at `/tmp` with a common `LG_WD` work: the FIFO's
name (`.lgd-nfy0`) is **per process, not per server**, and two Pis run two GPIO
servers each — pi-uleem (`RaspberrySwitch/1` + `SEAWaterflowmeter/1`) and pi-xps
(`RaspberryButton/1` + `SEAWaterflowmeter/3`) — which would end up sharing the
same FIFO. With `/tmp` the *sticky bit* comes in too: if the file already exists
from another user, the second cannot touch it.

**Fix applied in the code**, in all four GPIO servers, just before the
`import RPi.GPIO`:

```python
os.environ.setdefault("LG_WD", tempfile.mkdtemp(prefix="lgpio-"))
atexit.register(shutil.rmtree, os.environ["LG_WD"], True)
```

Each process takes its own private directory in `/tmp` (tmpfs, writable by
anyone) and deletes it on exit. It goes in the code rather than in the systemd
unit on purpose: that way it works whoever launches it — the Starter, an itango
session, or by hand — and it deploys through the same `git pull` as everything
else, without touching the shared root.

Verified on pi-vsm with the real server launched as `tango` from the Starter's
CWD: `ON | Measurement thread is running`.

What each live server uses from the API, to know what to check after the change:

| Server | Uses | Risk |
|---|---|---|
| SEAWaterflowmeter | `add_event_detect` | The one being fixed |
| RaspberrySwitch | `setup`, `input`, `PUD_UP/DOWN` | Low |
| WaterSwitch | `setup`, `input`, `PUD_UP` | Low |
| RaspberryButton | `setup`, `output` | Low |

`rpi-lgpio` documents behavioural differences in details such as event
*bouncetime* and in **PWM**. The only server that used PWM was Motor, which went
to `deprecated/` on 18-Aug-2026 when it was replaced by an Arduino with a
DRV8825, so that risk **no longer exists**.

Note: the empty `time` and `calibration` of `vsm/safety/water` in the DB are not
a problem — they have a `default_value` in the code (1.0 and 7.5).

### Third trap: lgpio respects the kernel's reservations, RPi.GPIO does not (18-Aug-2026)

With RPi.GPIO the pins **were not exclusive** — it went through `/dev/mem`,
bypassing the kernel. lgpio goes through the character device and respects who
holds each line, so **conflicts that had lain dormant for years surface on
migration**:

```
lgpio.error: 'GPIO busy'
```

It happened to `RaspberrySwitch/2` on pi-leem, configured on GPIO 4:

```
leem/power/xps    GPIOport = 4
gpiochip0 line 4: "GPIO4"  output drive=open-drain  consumer="onewire@4"
```

The kernel's `w1-gpio` overlay had it taken. And on pi-leem there is **no 1-Wire
sensor at all**: the devices it enumerated were `00-77…`, `00-f7…`, of family 0 —
that is, ghosts of an empty bus. A real DS18B20 is `28-…`.

**Overlays are per Pi, not shared.** This matters and was not obvious:
`/boot/firmware` *is* on the shared NFS root, but **it does not contain
`config.txt`** — the bootloader reads that over TFTP from `/tftpboot/<serial>/` on
wolframite. So it is solved without recabling or touching the DB, by removing the
overlay only where it is not needed:

| Pi | Serial | Real 1-Wire sensor | `w1-gpio` overlay |
|---|---|---|---|
| pi-rackmossbauer | — | `28-3cd5f649fc87` ✅ | **keep** (`TempSensorDS18B20/1`) |
| pi-leem | `487100ad` | no (ghosts) | removed — unblocks `RaspberrySwitch/2` |
| pi-vsm | `88ec955a` | no (ghosts) | removed (pending a reboot) |

Done on 18-Aug-2026. After rebooting pi-leem, GPIO 4 was free
(`line 4: "GPIO4" input`, with no consumer) and `RaspberrySwitch/2` **started on
its own**, with no intervention: `leem/power/xps -> Switch = True`. Its `UNKNOWN`
state is longstanding — that server never calls `set_state` — and is not an
after-effect.

⚠️ Correction to what was written on 17-Aug about TempSensorDS18B20: it said
there that the 1-Wire bus noise "deserves a look at the cabling". **That is
doubtful**: pi-leem and pi-vsm produce the same family-0 ghosts with nothing
connected, so those messages are normal on any Pi with the overlay set and the
bus empty or weak, not evidence of bad cabling. What does still stand is that the
real sensor can disappear and come back, which is why the DS retries.

### Configured pins of each GPIO server (18-Aug-2026)

To anticipate clashes before rebooting. Taken from the DB; mind the properties,
which are **not named the same** in all of them: `RaspberrySwitch` and
`WaterSwitch` use `GPIOport`, `RaspberryButton` uses **`Pin`**, and
`SEAWaterflowmeter` uses `channels` (a comma-separated list).

| Server | Pi | Boot | Pins |
|---|---|---|---|
| SEAWaterflowmeter/4 | pi-vsm | netboot | 6, 13 ✅ verified with lgpio |
| RaspberrySwitch/2 | pi-leem | netboot | 4 → resolved by removing the overlay |
| SEAWaterflowmeter/1 | pi-uleem | microSD | 26, 13, 6, 5 |
| SEAWaterflowmeter/2 | pi-mossbauer | microSD | 26, 13 |
| SEAWaterflowmeter/3 | pi-xps | microSD | 13 |
| RaspberrySwitch/1 | pi-uleem | microSD | 12 |
| RaspberryButton/1 | pi-xps | microSD | 26 |

`WaterSwitch` is not registered anywhere.

### Netboot versus microSD: not every Pi shares software

**Only pi-rackmossbauer, pi-leem and pi-vsm boot by netboot** from
`/nfs/pi-trixie`. pi-uleem, pi-xps and pi-mossbauer are still on their **own
microSD**, with their own software and their own passwords. Consequences:

- The move to `rpi-lgpio` **does not affect them**: they keep RPi.GPIO and their
  servers do not break on reboot. The pins in the table above will only matter
  the day they move to netboot.
- Nor do they get the repository's code through wolframite's `git pull`.
- The `LG_WD` workaround is harmless there: it is a variable the original
  RPi.GPIO does not even look at, so the same code serves both kinds of Pi.
- **Only the netbooting ones share SSH host keys** (same root, same key).
  Checking with `HostKeyAlias` against another Pi's key works between
  pi-rackmossbauer, pi-leem and pi-vsm, and **correctly fails** with the microSD
  ones.

> Out of date as of 26-Aug-2026: pi-uleem and pi-xps now netboot too, and
> **pi-hvleem is the only Pi left on microSD**. See the update under _Host →
> server assignments_ and `docs/netboot-shared-root.md`.

### Verified on hardware (18-Aug-2026)

- **`SEAWaterflowmeter/4`** on pi-vsm: starts from the Starter
  (`ON | Measurement thread is running`) and **measures correctly with the water
  running** (confirmed by the user). The initial zeros were the tap being closed,
  not a failure of the *callbacks*. Full chain validated: `rpi-lgpio` + private
  `LG_WD` + edge detection.
- **`RaspberrySwitch/2`** on pi-leem: input read (`Switch = True`).
- A practical detail of the change: with lgpio **a pin cannot be probed from
  outside while a DS holds it claimed** (`lgpio.error: 'GPIO busy'`). With
  RPi.GPIO it could be. If any tool or itango session measured pins live, it will
  stop working.

---

## TempSensorDS18B20 (corrected 17-Aug-2026)

It died at start-up, and **not through absent hardware**: the sensor
`28-3cd5f649fc87` is connected and reads. `init_device` called
`w1thermsensor.W1ThermSensor()` unprotected, and when that raised
`NoSensorFoundError` PyTango **terminated the whole process** — in
`/var/tmp/ds.log/TempSensorDS18B20_1.log`:
`Exiting: Server exited with tango.DevFailed … Exited`. The Starter marks it
FAULT and does not bring it back up.

Corrected: FAULT with the real message instead of dying; the control thread
retries acquiring the sensor and recovers to ON by itself; it no longer dies on a
failed `get_temperature()` (which previously left `Temperature` frozen at the
last value **for ever**); FAULT after three consecutive failures and
`ATTR_INVALID` when there is no sensor, so as not to serve a stale value as
fresh. The thread is a daemon and waits on an `Event`, and `init_device` stops
the previous one, so an `Init` from Astor does not leave two threads writing
`self.temp`.

⚠️ **This Pi's 1-Wire bus is noisy.** It reports a ghost slave on almost every
search:

```
w1_master_driver w1_bus_master1: Family 0 for 00.b3c800000000.12 is not registered.
```

153 of those in the `dmesg` buffer, one every ~45-60 s. With that noise the real
slave can disappear from `/sys/bus/w1/devices` and come back — which the software
now tolerates, but does **not** cure. It deserves a look at the cabling (length,
4.7 kΩ pull-up, shielding).

> See the correction under _GPIO on Trixie_ (18-Aug-2026): the family-0 ghosts
> also appear on Pis with nothing connected, so they are not by themselves
> evidence of bad cabling.

It also **stopped importing `RPi.GPIO`**: the pin is handled by the kernel's
`w1-gpio` overlay, configured in `config.txt`, not by the server. The `GPIOPin`
property stays, documented as informational, so as not to orphan the DB's values.

---

## Deploying code to the Pis: the NFS root is read-only from the client

Verified on 17-Aug-2026 on pi-rackmossbauer: **`git pull` on the Pi itself does
not work**. Its root is `10.43.88.3:/nfs/pi-trixie` over NFSv4 and, although the
client mounts it `rw`, every write gives `EROFS` — `/opt/tango/SURFMOSS_TangoDS`,
and even `/home/pi`, with `sudo` too. Only `/tmp` is writable (tmpfs). `/var` is,
through its own export: `10.43.88.3:/nfs/clients/pi-rackmossbauer/var` (which is
why the Starter's logs in `/var/tmp/ds.log/` do get written).

Before reaching the real reason, two git errors appear that throw you off:
`fatal: detected dubious ownership` (the repo belongs to `root`, you log in as
`pi`) and then, with `sudo`,
`cannot open '.git/FETCH_HEAD': Read-only file system`.

The pull has to be done **where `/nfs/pi-trixie` is writable** (wolframite), and
then the DS restarted on the Pi with the Starter.

**To test a patch against the hardware without deploying**: `scp` the module to
`/tmp` and exercise it with `importlib.util.spec_from_file_location`. For a
complete device server, `-nodb` avoids touching the database:

```bash
python3 /tmp/mods.py test -nodb -dlist test/temp/1 -ORBendPoint giop:tcp:127.0.0.1:12988
python3 -c 'import tango; print(tango.DeviceProxy("tango://127.0.0.1:12988/test/temp/1#dbase=no").state())'
```

With `-nodb` the properties take their `default_value`. Careful: the endpoint has
to be pinned to `127.0.0.1`, because the short name `pi-rackmossbauer` **does not
resolve on the Pi itself** (it also shows up as `sudo: unable to resolve host`)
and the published IOR ends up unreachable.

---

## GammaVacuumDigitel (reactivated 13-Aug-2026)

Source for the Gamma Vacuum DIGITEL SPCe ion pump, over Telnet on TCP (port 23 by
default). Returned to the root and registered as the **33rd entry** of
`pyproject.toml`. It already had the `argv[0]` fix.

No new dependencies: only `socket` and `struct`, from the standard library.

Two things set it apart from the rest:

- **It has no `.xmi`.** It is the only device server in the repository in that
  situation — it was written by hand, not with POGO. Practical consequence:
  **POGO can neither regenerate nor edit it**. POGO works from the `.xmi`, not
  from the `.py`, so adding protected regions to the code is not enough; the
  model would have to be rebuilt, declaring attributes, commands and properties,
  and generated again.
- **It had never been tested against the real controller.** That was the note in
  `inactive/README.md`, and it stopped being true on 27-Aug-2026, when it was
  pointed at the LEEM column ion pump on pi-laser. It did not work: see the
  status section at the top.

The `IP` property **has no default value** on purpose: there is no known address
to put there. It has to be set in the database when registering the device, or
`connect()` will fail with an empty string.

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
   - [x] WisselMCA encoding fix committed, and the server reactivated on
         13-Aug-2026: it lives at the root and is in `pyproject.toml` (32nd entry).
   - [x] GammaVacuumDigitel reactivated on 13-Aug-2026 (as GammaVacuumSPCe). No `.xmi` and
         untested against the controller; its `IP` property has no default and
         has to be set in the DB when registering the device.
   - [x] The four networked DS use `IP` / `Port` under the same name. Mind the
         orphaned values in the DB under `UviewIP`, `UviewPort` and `Host`.
2. **Trixie root install (in chroot, binds mounted)**
   - [ ] apt deps: `python3-tango python3-serial python3-rpi-lgpio`,
         plus `python3-numpy libhidapi-hidraw0` for WisselMCA.
   - [ ] pip deps: `simple-pid w1thermsensor` (`--break-system-packages`),
         plus WisselMCA's HID binding (see the dependencies section).
   - [ ] `pip install -e --no-deps --break-system-packages .` from repo root.
   - [ ] All 33 live wrappers present in `/usr/local/bin`; no parked ones.
   - [ ] `/etc/tangorc` = `TANGO_HOST=tangodb.lab:10000`.
   - [ ] **Unmount binds** (`/dev`, `/proc`, `/sys`) before any exportfs/rsync.
3. **Clean DB**
   - [ ] Build fresh DB with the 33 live servers only — parked ones never entered.
   - [ ] Each Pi's Starter control list matches its live-server set.
   - [ ] Disable wolframite's own Starter (DB host, runs no instrument servers).
   - [x] **Hardcoded IPs** externalised into properties (13-Aug-2026). Still to
         verify in Jive that no device carries a stale value in `IP` / `UviewIP`,
         which now is what counts (see the section above).
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

## Batch migration plan (grouped by switch)

Ports are changed per switch, not one at a time, so **every machine on a switch
changes network at once**.

### ✅ KEY (8-Aug-2026): the old Pis DO work against wolframite

**Checked with pi-rackmossbauer booting its Debian 10 root (Tango 9.2.5) against
wolframite (Tango 10): it boots and its device servers come up correctly** (the
only failures are from absent hardware). WisselMCA starts without trouble.

This **removes the bottleneck** of the original plan. It is no longer necessary
to migrate every Pi to Trixie before moving the ports. The sequence becomes:

1. Ask IT to change **all** the ports to the new network.
2. The lab keeps operating with the old Pis (Debian 10) against wolframite.
3. Migrate each Pi to Trixie whenever convenient, with no maintenance windows.

_Historical note: for hours it was believed that the old Pis were incompatible
with Databaseds 10. That was false: the real failure was the MariaDB collation
conflict, which affected Tango 9 and 10 alike. With that corrected, backward
compatibility works._

### Prerequisite before the port change

The two Debian 10 PCs (sputtering, vsm) also run device servers. They have to be
verified against wolframite before their switch is moved. **vsm** is the urgent
one (it goes in step 1); **sputtering** can wait for step 3.

### Phased migration sequence (per `traslado_red_laboratorio.md`)

The order protects what is in use: XPS and Mössbauer keep measuring until the
end. And the first phase served as a real test bench, with little at stake.

#### ✅ Phase 1 — COMPLETED (10-Aug-2026)

Bay 409 (VSM et al): VLAN 303 Talleres, port #01 Gi1/0/2.

| Machine | MAC | New IP | State |
|---|---|---|---|
| vsm (Debian 10 PC) | `00:15:17:50:bd:77` | `10.43.88.30` | ✅ device servers OK against wolframite |
| pi-vsm (netboot) | `b8:27:eb:ec:95:5a` | `10.43.88.12` | ✅ boots and DS OK |
| ITech source | `8c:c8:f4:41:bd:f4` | `10.43.88.40` | |
| 3dprinter (ender) | `b8:27:eb:26:ba:05` | `10.43.88.16` | |

**Key result**: it validates that **both the netboot Pis and the Debian 10 PCs**
work unchanged against wolframite (Tango 10). Nothing blocks the later phases.

#### ✅ Phase 2 — COMPLETED — Bay 408 (LEEM et al)

Rocasolano Talleres, VLAN 13; ports #4 Gi1/0/4, #5 Gi1/0/17.

leempc (`18:66:da:3d:88:2c`), tvips (`10:b6:76:49:fc:ad`),
ferberite (`10:ff:e0:63:02:ca`), Quadera mass spec (`00:50:c2:66:85:11`),
pi-leem (`b8:27:eb:71:00:ad`), pi-uleem (`b8:27:eb:86:01:9e`),
pi-hvleem (`b8:27:eb:56:e6:91`).

The instrument with the longest list of DS, working. The hardcoded IPs of
Itech6000C, ElmitecUview and ElmitecLEEM2k were updated at the same time.

#### ✅ Phase 2a — COMPLETED — hematite

Moved to `10.43.88.2` with a **static IP** (configured by IT/IQF, not by DHCP),
keeping IQF and VPN access. The name is served from wolframite's `/etc/hosts`.

⚠️ Until Phase 4, XPS and Mössbauer **have no access to the storage**: they must
save spectra locally.

With hematite on the new network, the intermediate hop through wolframite is no
longer needed to reach the Pis from the VPN.

#### ✅ Phase 3 — COMPLETED — XPS upper floor (offices)

Rocasolano-XPS, room 500B and offices 500C–500G. Includes magnetite
(`40:b0:76:0f:67:f3`), fortytwo (Juan's Mac, `a0:ce:c8:ff:9d:b0`), the Kyocera
printer and the group's personal machines.

The ports left out stay on the **IQF network**, not on the lab's old network, so
they will keep working after Phase 4.

#### ✅ Phase 4 — COMPLETED — XPS + Mössbauer (THE REAL CUTOVER)

Rocasolano-XPS, port #17 Gi2/0/17, and **localsurfmoss powered off** (port #18
Gi4/0/18).

localsurfmoss, specs (`40:b0:76:0f:68:08`), mossbauer (`00:24:8c:e8:8f:25`),
pi-xps (`b8:27:eb:36:cf:2f`), pi-mossbauer (`b8:27:eb:eb:87:7b`),
pi-rackmossbauer (`b8:27:eb:a9:82:05`), sputtering (`00:15:17:24:e6:4e`),
CANbox XPS (`00:50:c2:4a:23:0c`).

**The old network `10.10.99.0/24` is gone.** Wolframite is left single-homed
(`enp6s0f0` commented out) and is the only server: DHCP, DNS, TFTP, NFS, NTP and
the Tango DB.

**Test bench**: two ports on the new network (Juan's office + wolframite). It
allows taking a Pi down, validating it and returning it to its switch. Still
useful for preparing Trixie migrations.

Every production Pi was a **3B+** until pi-laser, a **Pi 4**, joined on
27-Aug-2026. The same arm64 shared root serves both; only the bootloader setup
differs, and that is covered in `docs/netboot-shared-root.md`.

### Work pending, by kind of machine

- **3 netboot Pis** (pi-leem, pi-rackmossbauer, pi-vsm): they already have a TFTP
  directory; to migrate to Trixie it is enough to point at `/nfs/pi-trixie` and
  copy the new firmware (see `netboot-pi-raiz-compartida.md`).
- **4 Pis on microSD** (pi-xps, pi-mossbauer, pi-hvleem, ender): **convert to
  netboot** (decided). Create their `/tftpboot/<serial>/` and note their MAC. No
  longer urgent: they can stay on their SD on the new network meanwhile.
- **2 Debian 10 PCs** (sputtering, vsm): check whether they work against
  wolframite. Dead repos → they have to be reinstalled or upgraded to Debian 13
  with Tango 10.

> Update (26-Aug-2026): pi-uleem and pi-xps have been converted to netboot.
> **pi-hvleem is the only Pi left on microSD.**

### Why migrate anyway

Debian 10 has dead repos (not even `git` can be installed without resorting to
`archive.debian.org`). The migration is still necessary, but it is now
**decoupled from the network change**: it can be done calmly, machine by machine.

---

## Remote access

**After Phase 3** (the offices already on the new network):

- From fortytwo or any other migrated machine: **wolframite is `10.43.88.3`**,
  directly. The old address `10.10.99.25` is no longer reachable from the new
  network.
- From outside, over VPN: `hematite.iqf.csic.es` (`10.43.88.2`) → any machine on
  the new network. The intermediate hop through wolframite is no longer needed.

A `~/.ssh/config` with `ProxyJump` through hematite is worth having for access
from home.

Wolframite's `enp6s0f0` interface (old network, `10.10.99.25`) stays up until
Phase 4; afterwards it can be retired.

**Tailscale does not work on the new network**: the FortiGate (`FG101FTK21000170`)
does TLS inspection and re-signs the certificate of
`controlplane.tailscale.com`. Tailscale pins it and rejects that by design. On
top of that, `UDP: false` and only one reachable DERP (Bengaluru). It is not a
rule that can be lifted without excluding the domain from TLS inspection.
Dropped.
