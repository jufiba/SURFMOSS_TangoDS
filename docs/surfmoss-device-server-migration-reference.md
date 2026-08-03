# SURFMOSS Device Servers — Migration Reference

_Single source of truth for installing the SURFMOSS Tango device servers onto
the new Trixie NFS root (`/nfs/pi-trixie` on wolframite) and reconciling them at
the clean-DB cutover. Built from the Python-3 audit, the entry-point inventory,
and the dependency map._

_Last updated: 30-jun-2026_

---

## Status

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

Tally: **31 live · 9 inactive · 3 deprecated** (= 43 entry-point servers), plus
RaspberryButton_old (dead duplicate, remove) and PANIC (third-party, separate).

---

## Server inventory

### LIVE — install on the Trixie root (31)

Entry point in `[project.scripts]`, installed, registered in the new DB.

AGPolaritySwitch, AMLPGC1, ArduinoDAC, ArduinoMotor, ArduinoPt, MFC
(BronkhorstMFC), CryoCon32, ElmitecLEEM2k, ElmitecUview, FUGMCP, HuttingerPFGDC,
HuttingerPFGRF, Hygrometer, Itech6000C, CenterOneGauge (LeyboldCenterOne),
LeyboldIG3, MKSGauge, Motor, NetworkUPSTool, PfeifferHiscroll, PfeifferTC100,
PfeifferTU400, RaspberryButton, RaspberrySwitch, SEAWaterflowmeter, SRIlockin830,
TempSensorDS18B20, VarianTV301nav, WaterSwitch, Tti604, **PIDController**.

### INACTIVE — keep in repo, do NOT install (9)

Move to `inactive/`. Code present but hardware idle or work remains. Not in
`[project.scripts]`, not registered in the new DB until revived. See
`inactive/README.md` for per-server revival notes.

GammaIonPump, GammaVacuumSPCe, Keithley2100, MCC1208LS, PfeifferDCU002,
V4L2Camera, VSMControlDevice, WebCam, WisselMCA.

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
  other users (VSMControlDevice, WisselMCA) are inactive.
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

### pi-rackmossbauer (.11, /nfs/rackmossbauer) — TBD

_Populate from this Pi's Starter controlled-server list in Astor._

### pi-vsm (.12, /nfs/vsm) — TBD

_Populate from this Pi's Starter in Astor. Note VSMControlDevice is inactive —
confirm whether this host still needs it before reviving._

### Other Pis (pi-xps, pi-mossbauer, pi-hvleem, ender, …) — TBD

_Populate per host from Astor as each is migrated._

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
   - [ ] Top-level `pyproject.toml` lists exactly the **31** live entry points
         (build-backend = `setuptools.build_meta`).
   - [ ] PIDController added as a live entry; its Makefile removed.
   - [ ] 3 dead → `deprecated/`, 9 paused → `inactive/`, both excluded in
         `packages.find`.
   - [ ] RaspberryButton_old removed.
   - [ ] WisselMCA encoding fix committed (done) — note it lives in `inactive/`.
2. **Trixie root install (in chroot, binds mounted)**
   - [ ] apt deps: `python3-tango python3-serial python3-rpi.gpio`.
   - [ ] pip deps: `simple-pid w1thermsensor` (`--break-system-packages`).
   - [ ] `pip install -e --no-deps --break-system-packages .` from repo root.
   - [ ] All 31 live wrappers present in `/usr/local/bin`; no parked ones.
   - [ ] `/etc/tangorc` = `TANGO_HOST=tangodb.lab:10000`.
   - [ ] **Unmount binds** (`/dev`, `/proc`, `/sys`) before any exportfs/rsync.
3. **Clean DB**
   - [ ] Build fresh DB with the 31 live servers only — parked ones never entered.
   - [ ] Each Pi's Starter control list matches its live-server set.
   - [ ] Disable wolframite's own Starter (DB host, runs no instrument servers).
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
