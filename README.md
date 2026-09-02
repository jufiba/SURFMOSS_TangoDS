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

## Device Servers

### Vacuum & Gauges

| Directory | Description |
|---|---|
| `GammaIonPump` | Gamma Vacuum ion pump controllers |
| `LeyboldCenterOne` | Leybold CenterOne single-channel vacuum gauge |
| `LeyboldIG3` | Leybold IG3 gauge electronics |
| `MKSGauge` | MKS PDR9000 unit with 972B transducer |
| `PfeifferDCU002` | Pfeiffer DCU002 display unit |
| `PfeifferTC100` | Pfeiffer TC100 turbopump controller |
| `PfeifferTU400` | Pfeiffer TU400 turbopump controller |
| `VarianMultiGauge` | Varian Multigauge controller (hot cathode gauge) |

### Pumps & Flow

| Directory | Description |
|---|---|
| `PfeifferHiScroll` | Pfeiffer HiScroll scroll pump |
| `VarianTV301nav` | Varian/Agilent TV301 Navigator turbopump with integrated controller |
| `BronkhorstMFC` | Bronkhorst mass flow controllers |
| `SEAWaterflowmeter` | SEA YF-S201 water flow sensor via Raspberry Pi GPIO |
| `WaterSwitch` | Cooling water flow detection sensor |

### Power Supplies & High Voltage

| Directory | Description |
|---|---|
| `AGPolaritySwitch` | Arduino-based polarity switcher for high-current (up to 30 A) power supply |
| `AMLPGC1` | AML PGC1 pressure/gauge controller |
| `FUGMCP` | FUG MCP 140-1250 HV power supply (1250 V, 100 mA) via Probus |
| `HuttingerPFG-DC` | Huttinger PFG-DC1500 DC power supply for magnetron sputtering |
| `HuttingerPFG-RF` | Huttinger PFG-RF300 RF power supply for magnetron sputtering |
| `Itech6000C` | ITech 6000C power supply via Ethernet |
| `tti604` | RS TTI 604 digital multimeter |

### Motion & Positioning

| Directory | Description |
|---|---|
| `ArduinoMotor` | Arduino-based motor driver |
| `MitutoyoPostable` | Mitutoyo positionable stage |
| `Motor` | Generic motor device server |

### Sensors & Instruments

| Directory | Description |
|---|---|
| `ArduinoPt` | Arduino connected to a Pt100/Pt1000 temperature module |
| `CryoCon32` | Cryocon32 temperature controller (Mossbauer transmission setup) |
| `Hygrometer` | Arduino with YL-69/YL-38 humidity/moisture sensors |
| `Keithley2100` | Keithley 2100 6½-digit digital multimeter (USB-TMC) |
| `SRIlockin830` | SRI 830 lock-in amplifier |
| `TempSensorDS18B20` | DS18B20 1-wire temperature sensor via Raspberry Pi |

### Data Acquisition

| Directory | Description |
|---|---|
| `ArduinoDAC` | Arduino-based DAC interface |
| `MCC1208LS` | Measurement Computing MCC 1208LS USB DAQ box |
| `PIDController` | Generic PID controller device server |
| `VSMControlDevice` | VSM data acquisition and hysteresis cycle imaging |

### Cameras & Imaging

| Directory | Description |
|---|---|
| `ElmitecUview` | PEEM end-station data reader (requires UView running) |
| `V4L2Camera` | V4L2 camera frame grabber |
| `WebCam` | Webcam via V4L2/pygame |
| `WisselMCA` | Wissel Multichannel Analyzer for Mossbauer spectroscopy |

### LEEM / SPECS Equipment

| Directory | Description |
|---|---|
| `ElmitecLEEM2k` | Settings interface for Elmitec LEEM2000 |
| `SpecsXRC1000` | SPECS XRC1000 X-ray gun electronics status |

### Network & Infrastructure

| Directory | Description |
|---|---|
| `NetworkUPSTools` | Wrapper for NUT (Network UPS Tools) |

Alarms used to live here too, in a vendored copy of ALBA's PANIC. That tree has
been removed — see [`deprecated/README.md`](deprecated/README.md) for why, and
[`docs/alarms-panic-legacy.md`](docs/alarms-panic-legacy.md) for what it
watched.

### Raspberry Pi

| Directory | Description |
|---|---|
| `RaspberryButton` | GPIO output pin control (e.g. relay) |
| `RaspberrySwitch` | GPIO input pin for reading a switch |

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
| `netboot-shared-root.md` | How the Pis netboot from one shared read-only NFS root on wolframite: exports, per-Pi `/var`, machine-id, per-host service activation, recovery |
| `surfmoss-device-server-migration-reference.md` | Device server restructuring and Trixie migration reference |
| `alarms-panic-legacy.md` | Every alarm the retired PANIC system carried, recovered from the old network's database — the reference for whatever replaces it |
| `panic-python3-qt-port-estimate.md` | What porting PANIC to Python 3 and current Qt would cost, and the alternatives |
