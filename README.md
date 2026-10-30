# SURFMOSS Tango Device Servers

A collection of [Tango Controls](https://www.tango-controls.org/) device servers developed for the SURFMOSS laboratory. The servers cover vacuum equipment, power supplies, motion control, sensors, cameras, and data acquisition hardware.

## Requirements

- Python 3
- [PyTango](https://pytango.readthedocs.io/) (the `pytango` pip package)
- A running Tango database

See `requirements.txt` for the full list of Python dependencies.

## Installation

Clone the repository:

```bash
git clone <repo-url>
cd SURFMOSS_TangoDS
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install an individual device server:

```bash
cd <DeviceServerDirectory>
pip install .
```

**That is not how the laboratory runs it.** The Raspberry Pis netboot from a
read-only shared root on wolframite, where this repository is checked out once
at `/nfs/pi-trixie/opt/tango/SURFMOSS_TangoDS` and installed **editable**, so a
`git pull` is enough for a code change and no server is installed per machine.
Everything is done from wolframite — a `git pull` or a `pip` from a Pi fails
with `Read-only file system`. See
[`docs/netboot-shared-root.md`](docs/netboot-shared-root.md).

## Device Servers

**35 servers install** from this repository (`[project.scripts]`), of which
**33 have devices registered** in the Tango database, for **53 devices** in
total. `LeyboldIG3` and `WaterSwitch` install but have no registered instance.

Each server has its own `README.md` with the instrument's protocol and the
traps found along the way; that is the reference, not this table.

Retired and paused servers are **not** listed here — see
[`deprecated/README.md`](deprecated/README.md) (dead hardware) and
[`inactive/README.md`](inactive/README.md) (paused but revivable).

### Vacuum & gauges

| Directory | Description |
|---|---|
| `AMLPGC1` | AML PGC1 ion gauge controller (LEEM preparation chamber) |
| `CenterOneGauge` | Leybold CenterOne single-channel vacuum gauge |
| `GammaVacuumDigitel` | Gamma Vacuum DIGITEL ion-pump supplies (SPCe, QPC) over Telnet |
| `GranvillePhillips350` | Granville Phillips 350 gauge controller |
| `LeyboldIG3` | Leybold IG3 gauge electronics — *installed, no registered device* |
| `MKSGauge` | MKS PDR9000 unit with 972B transducer |

### Pumps & flow

| Directory | Description |
|---|---|
| `PfeifferHiscroll` | Pfeiffer HiScroll scroll pump |
| `PfeifferTC100` | Pfeiffer TC100 turbopump controller |
| `PfeifferTU400` | Pfeiffer TU400 turbopump controller |
| `VarianTV301nav` | Varian/Agilent TV301 Navigator turbopump with integrated controller |
| `MFC` | Bronkhorst mass flow controllers |
| `SEAWaterflowmeter` | YF-S201 water flow sensors via Raspberry Pi GPIO, with `UpdateCount` |
| `WaterSwitch` | Fixed-pin, fixed-polarity variant of `RaspberrySwitch` — *no registered device; use `RaspberrySwitch`* |

### Power supplies & high voltage

| Directory | Description |
|---|---|
| `AGPolaritySwitch` | Arduino relay box that reverses the VSM magnet supply (up to 30 A) |
| `FUGMCP` | FUG MCP 140-1250 HV supply (1250 V, 100 mA) over Probus V, with deadman |
| `HuttingerPFGDC` | Huttinger PFG-DC 1500 DC supply for magnetron sputtering |
| `HuttingerPFGRF` | Huttinger PFG-RF 300 RF supply for magnetron sputtering |
| `Itech6000C` | ITECH IT-6000C regenerative supply (VSM magnet coil), with deadman |

### Motion

| Directory | Description |
|---|---|
| `ArduinoMotor` | Stepper motor via Arduino and DRV8825 (sputtering target position) |

### Sensors & instruments

| Directory | Description |
|---|---|
| `ArduinoPt` | Arduino with a Pt100/Pt1000 temperature module |
| `CryoCon32` | Cryocon 32 temperature controller (Mossbauer transmission cryostat) |
| `Hygrometer` | Arduino with YL-69/YL-38 humidity sensors |
| `SRIlockin830` | Stanford Research SR830 DSP lock-in amplifier |
| `TempSensorDS18B20` | DS18B20 1-wire temperature sensor (kernel `w1-gpio` overlay) |
| `Tti604` | Thurlby Thandar TTi 604 bench multimeter |

### Acquisition & control

| Directory | Description |
|---|---|
| `ArduinoDAC` | Arduino-based DAC interface |
| `PIDController` | Generic PID loop between two Tango devices |
| `WisselMCA` | WissEl CMCA-550 multichannel analyser for Mossbauer spectroscopy |

### LEEM

| Directory | Description |
|---|---|
| `ElmitecLEEM2k` | Control of Elmitec's LEEM2000 program (a client of it, not of the hardware) |
| `ElmitecUview` | Control of Elmitec's UView acquisition program |

### Safety & infrastructure

| Directory | Description |
|---|---|
| `AnalogInterlock` | Generic threshold interlock between two devices: hysteresis, gate, heartbeat, bypass |
| `AlarmNotifier` | Watches other servers' `State` and sends mail. Replaces PANIC/PyAlarm |
| `NetworkUPSTool` | UPS monitoring through NUT (Network UPS Tools) |
| `RaspberryButton` | GPIO output pin holding a permissive, with a deadman |
| `RaspberrySwitch` | GPIO input pin, for reading a switch or a valve position |

How these combine into the cooling-water safety chain is in
[`AnalogInterlock/README.md`](AnalogInterlock/README.md) and
[`AlarmNotifier/README.md`](AlarmNotifier/README.md).

Alarms used to live here too, in a vendored copy of ALBA's PANIC. That tree has
been removed — see [`deprecated/README.md`](deprecated/README.md) for why, and
[`docs/alarms-panic-legacy.md`](docs/alarms-panic-legacy.md) for what it
watched.

## Scripts

The `scripts/` directory contains Tango macros and utility scripts for instrument control (LEEM, VSM, sputtering, dosing). These are loaded directly in the instrument control session, not installed as packages.

`LEEMgui.py` is a Qt front end for the LEEM acquisition macros, opened with `LEEMmacros.gui()` or by running the file directly. It needs PyQt6, imported lazily so a command line session does not.

See [docs/LEEMmacros.md](docs/LEEMmacros.md) and [docs/LEEMgui.md](docs/LEEMgui.md) for the reasoning behind their design and the constraints to respect when changing them.

### Versioning

`LEEMmacros.py` was historically kept as a series of `LEEMmacros_vX_pY.py` copies. Those snapshots are now imported into git history: there is one canonical `scripts/LEEMmacros.py`, and each past version is a commit tagged `leemmacros-vX.Y`.

```bash
git tag -l 'leemmacros-*'                          # list known versions
git log -p scripts/LEEMmacros.py                   # change history
git show leemmacros-v2.3:scripts/LEEMmacros.py     # retrieve an old version
```

To release a new version, edit `LEEMmacros.py` in place, update `__version__` and the header changelog, commit, and tag it `leemmacros-vX.Y`. Do not create new `_vX_pY.py` files.

The imported history begins at the `leemmacros-v1.7` commit. Because the snapshots were grafted onto a tip that carried v2.2, that first commit shows a large diff going *backwards* to v1.7 — that is the graft point, not a regression.

Note: `leemmacros-v2.6` is the Python 3 port. Tags up to and including `leemmacros-v2.5` are Python 2 and will not run under Python 3. There is no `leemmacros-v2.4` tag — that version appears in the changelog but no copy of it survived.

## Keeping the models honest

Each device server has a `.xmi` next to its `.py` describing the interface it
exposes. **POGO does not regenerate these servers** — doing so produces a file
that will not compile, see
[the migration reference](docs/surfmoss-device-server-migration-reference.md) —
so the `.xmi` is documentation, kept in step by hand. Nothing enforces that by
itself, and every case of drift found so far was found by accident.

`tools/check_xmi.py` compares the two: attributes, commands, properties with
their defaults, declared states, and polling periods.

```bash
python3 tools/check_xmi.py              # 0 if all agree, 1 if any diverge
python3 tools/check_xmi.py WisselMCA    # one server
```

### Install the pre-commit hook, once per clone

`tools/hooks/pre-commit` runs that check on whatever is staged and refuses the
commit if a model and its code disagree. **Git hooks do not travel with a
clone**, so a fresh checkout has no hook at all — which is exactly when it is
most wanted. One command per clone:

```bash
git config core.hooksPath tools/hooks
```

It only runs when the commit touches a `.py` or an `.xmi`, and it judges the
staged content rather than the working tree, so staging half your changes is
not judged against the other half. To get past it on a commit you know is
mid-way:

```bash
git commit --no-verify
```

## Synoptics

The `synoptics/` directory contains Tango synoptic panel definitions.

## Documentation

The `docs/` directory holds the longer-form documentation:

| File | Contents |
|---|---|
| `DS-architecture.md` | Two failure modes shared by the device servers: an exception in `init_device` taking the whole server down, and attributes read live from the instrument on every client request. Audits, measurements and what to do |
| `LEEMmacros.md` | LEEM acquisition macros: versioning, change history with reasoning, invariants to preserve |
| `LEEMgui.md` | Acquisition GUI: architecture, layout decisions, how to add an acquisition, testing |
| `leemgui-install.md` | Installing and running the LEEM GUI on Debian/Ubuntu, including WSL: apt dependencies, `TANGO_HOST`, display setup, troubleshooting |
| `netboot-shared-root.md` | How the Pis netboot from one shared read-only NFS root on wolframite: exports, per-Pi `/var`, machine-id, per-host service activation, recovery |
| `surfmoss-device-server-migration-reference.md` | Device server restructuring and Trixie migration reference |
| `alarms-panic-legacy.md` | Every alarm the retired PANIC system carried, recovered from the old network's database — the reference for whatever replaces it |
| `panic-python3-qt-port-estimate.md` | What porting PANIC to Python 3 and current Qt would cost, and the alternatives |
