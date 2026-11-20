# LEEMmacros.py

Acquisition macros for the LEEM instrument, driving the Elmitec LEEM2000 and
UView through their Tango device servers. The file is loaded directly in the
control session — it is not installed as a package.

The in-file header keeps a one-line changelog per version. This document keeps
the reasoning that does not fit there: why each change was made, what constraints
forced it, and what to be careful about when changing the file again.

## Versioning

`LEEMmacros.py` used to be kept as a series of `LEEMmacros_vX_pY.py` copies. Those
snapshots were imported into git history in July 2026. There is now one canonical
`scripts/LEEMmacros.py`, and every version is a commit tagged `leemmacros-vX.Y`.

```bash
git tag -l 'leemmacros-*' | sort -V          # list versions
git log -p scripts/LEEMmacros.py             # change history
git show leemmacros-v2.3:scripts/LEEMmacros.py   # retrieve an old version
git diff leemmacros-v2.7 leemmacros-v2.8 -- scripts/LEEMmacros.py
```

To release a version: edit the file in place, update `__version__` and the header
changelog, commit, and tag `leemmacros-vX.Y`. Do not create new `_vX_pY.py` files.

Three things about the imported history:

- **The history begins at `leemmacros-v1.7`.** The snapshots were grafted onto a
  tip that already carried v2.2, so that first commit shows a large diff going
  *backwards*. That is the graft point, not a regression.
- **There is no `leemmacros-v2.4`.** The changelog records a v2.4
  (`rampLEEMROI`, 21/2/2024) but no copy of it survived; the file that was named
  `LEEMmacros_v2p4.py` contains v2.5 and says so in its own header.
- **v2.6 is the Python 3 port.** Every tag up to and including `leemmacros-v2.5`
  is Python 2 and will not parse under Python 3.

## The instrument runs its own copy

The macros are loaded in the control session on the LEEM machine, and the device
servers are installed there separately. **The repository is the record, not the
deployment.** It can lag or lead what is actually running, in both directions:
the tracked `LEEMmacros.py` sat at v2.2 from 2022 until July 2026 while the
instrument ran up to v2.7.

A change spanning the macros and a device server is one commit in git but two
separate deployments in the lab. Committing it does nothing to the running
instrument.

## Change history and reasoning

### v2.8 — TVIPS camera, single RW `ContinousAcquisition`

Changes needed to work with the new TVIPS camera. The macros stop continuous
acquisition around any sequence that needs synchronisation, add settling delays,
and discard one image after each mode switch, because of a known triggering
problem between UView and the TVIPS camera.

This was one logical change spanning two components. The `ElmitecUview` device
server previously had a write-only `ContinousAcquisition` **and** a read-only
`AcquisitionInProgress`, both of which sent UView's `aip` command over the single
socket, so they interfered with each other. The server now has a single
`READ_WRITE` `ContinousAcquisition`, and `AcquisitionInProgress` is a stub
returning `True`, kept only so any remaining client does not break.

The device-server side was ported surgically rather than copied: the working copy
edited on the instrument predated the repository's Python 3 work, so taking it
wholesale would have reverted the byte-string socket sends, the
`metaclass=DeviceMeta` form, and the `IntensityROI2` attribute.

> Note the typo: the attribute is `ContinousAcquisition`, missing an `u`. It is
> spelled that way in the device server, so the macros must spell it that way too.

### v2.9 — only stop the camera when the exposure must change

Stopping continuous acquisition costs a discarded image every time. The macros
now compare the requested exposure against the current one and stop only when it
actually differs; otherwise the camera is left running, started first if it
happened to be stopped.

Only *exposure* forces a stop. Average is written live on the keep-running path.

**The constraint that shapes this:** on a running camera, reading
`ContinousAcquisition` returns `True` forever, because the read is UView's `aip`
("acquisition in progress") and a continuously running camera is always
acquiring. The `AcquireSingleImage()` + `while (uview.ContinousAcquisition): pass`
idiom therefore only terminates when the camera is **stopped**. On the
keep-running path `leemSaveSingleImage` saves the frame UView already holds
instead of triggering a fresh one — using the trigger there would hang the
session in an infinite loop.

Consequence worth knowing: on that path, with `avg=1` (a sliding average) the
saved image can include frames from before the call.

Exposure and average also became optional. Left out they default to `None`,
meaning "use whatever the camera is set to", so calling either function with no
arguments never stops the camera. This changed the old no-argument behaviour,
which forced 500 ms/avg 0 for a single image and 400 ms/avg 1 for a sequence.

### v3.0 — no live plotting, and the module became importable

The file only worked when run into an `ipython --pylab` session. `show`,
`savefig`, `zeros`, `array` and `flip` were used **without ever being imported**,
and resolved only from the ambient pylab namespace. Imported as a module they are
all `NameError`s — which blocked the GUI, since `import LEEMmacros` is how the
GUI reaches the macros.

Plots now use matplotlib's `Figure` object API rather than `pyplot`: no global
state, no backend to choose, no window, and safe to call from a worker thread.
This deliberately avoids `matplotlib.use("Agg")`, which is process-global and
would also disable interactive plotting in the user's own session.

Two bugs fixed here:

- `leemIV_ROI` crashed on its **default** arguments. `fig.add_subplot` sat outside
  the `if (plot==True)` guard, so `plot=False` raised `NameError` on `fig`. The
  `plot` parameter was removed entirely; `plot.png` and `plot.pdf` are always
  written. `plot.png` is rewritten each pass, so it can be watched during a repeat.
- `leemARRESrun` left the camera stopped on the two-direction path, disagreeing
  with the one-direction path.

### v3.1 — the GUI, and a stop mechanism

See [LEEMgui.md](LEEMgui.md) for the GUI itself. The macro-side additions:

`leem_abort` (a `threading.Event`) and `leem_checkstop()`, which raises
`KeyboardInterrupt` when the event is set. The acquisition loops call it once per
iteration. **A GUI stop therefore unwinds through exactly the same
`except KeyboardInterrupt` cleanup as CTRL-C**, rather than duplicating that
cleanup somewhere else.

The sleeps in `leemSequenceImages` and `leemRampTemperatureROI` became
`leem_abort.wait(...)`, so a stop does not have to wait out the delay.

`leemIVandObj` gained the `KeyboardInterrupt` handler it never had. It restored
the camera at the end of the function but had no handler, so **CTRL-C had always
skipped that restore**, leaving the camera stopped at the wrong exposure.

### v3.2 — the PID ramps became stoppable

`leemRampTemperatureTo`, `doser1RampPowerTo` and `doser2RampPowerTo` all delegate
to `pidRampTo`, which holds the only loop. It now polls `leem_checkstop()` and
waits on `leem_abort`, so all three are stoppable and CTRL-C is caught rather than
escaping as a traceback.

Ramps touch no camera state, so an interrupt needs no cleanup: the ramp stops
where it got to and prints the setpoint it reached.

### v3.3 — average up to 64

UView allows averages up to 64; the GUI offered only up to 8. The field is
labelled "Average (1=sliding)" so the meaning of 1 is visible without reading a
docstring.

### v3.4 — `exp=None` / `avg=None` everywhere

For the GUI's shared imaging panel to work, all the acquisition functions had to
agree on what "keep current" means. `leemIV`, `leemIV_ROI`, `leemIVandObj`,
`leemRampTemperatureROI` and `leemARRESrun` now accept `exp=None` and `avg=None`
and fall back to the camera's present values, as `leemSaveSingleImage` and
`leemSequenceImages` already did.

Their signature defaults are unchanged, so command-line calls behave exactly as
before. Only passing `None` explicitly is new.

### v3.12 — ARRES fixes, and error replies from the device servers

Prompted by writing the acquisition scripts for Gong Chen's SPLEEM (Oct 2026),
which talk to LEEM2000 and UView directly over TCP and so met their error
replies head on. Changed together with `ElmitecLEEM2k` and `ElmitecUview`,
which now raise on error replies instead of reading `-102` as a value or
dropping a refused setting (see their READMEs).

- **`leemARRESrun` with one direction crashed.** `if (len(b>2))` is the length
  of a boolean array, i.e. the number of rows, so it was always true and
  `b[2,0]` raised `IndexError` for a two-row `b`, before the `len(b)==2` exit
  for one direction could ever run. Only reachable when `b` is built by hand:
  `leemARRESset()` always returns three rows.
- **`leemARRESrun` had no cleanup.** CTRL-C or an error left the deflectors off
  normal incidence and the camera stopped at the ARRES exposure. It now has a
  `try/finally` that restores both, and the partial `LOG<d>.txt`, `.npy` and
  plots are still written. The two directions are one helper,
  `_leem_arres_direction`; `interp1d` on `[0,1]` is replaced by the same
  linear interpolation written out, so scipy is no longer needed.
- **Direction 0 is still plotted with k reversed.** That looked like an
  inconsistency but is kept: it makes the two plots side by side read from
  endpoint 1 through normal incidence to endpoint 2.
- **`leemARRESset` printed `b[1]` as endpoint 2**, and its `b>200 -> 0` loop was
  removed. The loop covered only `b[0]` and three of the four deflectors, and
  would zero a real setting above 200 mA (the SPLEEM ran at 235 mA). The
  likeliest thing it once caught is LEEM2000's COM "special values"
  (99997.9–99999.9 for ramping/fault/local); error replies now raise instead.
- **`leem_read(attr)`** retries for up to 10 s while LEEM2000 answers
  `ErrorCode -102` (ramping). `leemReadDeflection` uses it, and takes
  `ErrorCode -101` on ImEqX/ImEqY as 0 with a warning, which is what -101 meant
  on the SPLEEM.
- **`leem_savesettings`** writes `unreadable (...)` for a module it cannot read,
  e.g. the MCP in local mode, instead of the error code as a number. Without
  this, the servers raising would have failed every acquisition at its start.
- **`leem_savedat()`** prints a warning when UView does not answer `"0"` to a
  save. Every macro used to print only on success, so a failed save was silent.
- **`leem_energies(E0,Ef,dE)`** builds the energies for `leemIV`, `leemIV_ROI`
  and `leemIVandObj`. `numpy.arange(E0,Ef+dE,dE)` and `frange()` step in
  floating point, so the end point came out one too many or one too few:
  `leemIV(0,0.2,0.1)` took four images, the last at 0.3 V. Over E0 0–10,
  dE 0.02–0.5 and 1–119 steps, arange was wrong in 14% of cases and frange in
  38%. The step count is now rounded and every energy is `E0 + n*dE`.
  `frange` is kept for anyone calling it by hand.

Not changed, and still worth testing on this instrument (they went wrong on the
SPLEEM): no wait for LEEM2000 to finish ramping after a set (`wai` is never
sent); `while (uview.ContinousAcquisition): pass` has no timeout and polls as
fast as Tango allows; stopping a running camera waits a fixed 0.5 s before
the throw-away image.

## Invariants to preserve

- **Never use `AcquireSingleImage()` plus a `while (uview.ContinousAcquisition)`
  wait on a running camera.** The read means "acquisition in progress" and stays
  `True` forever while continuous mode is on. That loop only terminates on a
  stopped camera.
- **Any function reachable from a GUI Run button must have an
  `except KeyboardInterrupt` handler** that leaves the camera in a sane state.
  Adding `leem_checkstop()` to a function whose cleanup is not in a handler makes
  Stop actively harmful. `leemSaveSingleImage` is the exception: it has no loop,
  cannot be interrupted, and its Stop button is disabled rather than lying.
- **`exp=None` / `avg=None` means "use the camera's current value"**, in every
  acquisition function.
- Exposure is read back from UView as a float, so compare it with a tolerance —
  `leem_exposure_differs()` exists for this.
- **ElmitecLEEM2k raises on LEEM2000 error replies** (since v3.12). A read
  that can meet a ramp goes through `leem_read()`, and nothing that only
  documents the run, like `leem_savesettings`, may let one unreadable module
  stop an acquisition.

## Known rough edges

- **The wait for each image has no deadline.** Every acquisition takes its
  images as

  ```python
  uview.AcquireSingleImage()
  while (uview.ContinousAcquisition):
      pass
  ```

  — thirteen times across the file. `read_ContinousAcquisition` sends `aip`
  over UView's socket, so that loop is a CORBA round trip plus a TCP exchange
  **with no sleep and no timeout**. If UView wedges (its
  `WaitForSingleObject failed 100000x in a row` window) the macro spins there
  for ever and the run stops advancing silently; pressing *acquire* in UView
  by hand is what unblocks it. ARRES meets this most often only because it
  chains the most images (nk × nE).

  Worth suspecting, though not proven: that busy-wait hammers the **single**
  UView socket, and `ElmitecUview.py:327` already records `aip` and
  `AcquisitionInProgress` "stepping on each other" on that same socket once
  before. The loop may be contributing to the wedge, not just failing to
  survive it. A `sleep` inside it would cost nothing in acquisition time and
  remove almost all of that traffic.

  Until it is fixed, `tools/leem_acquisition_watchdog.py` mails when a run
  stops writing data. It watches file mtimes, never UView, so it adds no
  traffic to the instrument. Start it by hand alongside a long run:

  ```bash
  python3 tools/leem_acquisition_watchdog.py --test-mail   # prove the mail path first
  python3 tools/leem_acquisition_watchdog.py --timeout 10
  ```

  It is not automatic on purpose: a run that *finishes* also stops writing,
  and `ContinousAcquisition` cannot tell the two apart — it reads 1 both while
  acquiring an image and while the live view runs, which is what
  `leemARRESrun` leaves on when it ends.

- **`leemSetDailyFolder()` writes `macros.dat` with the wrong number of
  fields.** It writes three (`prefix,dayfolder,0`) where `leem_getfolder()`
  unpacks four (`wprefix,prefix,dayfolder,exp`), so calling it by hand leaves
  the counter file unreadable by the next call. The same three-field write
  inside `leem_makenextfolder_and_inc()` is harmless, because a correct
  four-field write overwrites it before that function returns.
- The shebang is `#!/usr/bin/python` on a Python 3 file. Harmless while the file
  is imported or `%run`, but `./LEEMmacros.py` breaks where `/usr/bin/python` is
  Python 2 or absent.
- `DeviceProxy` objects are created at **module level**, so `import LEEMmacros`
  connects to Tango at import time. An unreachable device server surfaces as a
  connection error during import rather than a clean message.
- `leemARRESset()` blocks on `input()` at the terminal, which is why ARRES is not
  in the GUI. Making it work there needs a two-phase flow with dialogs.
- `pressure_limit` on the ramps does nothing: the pressure check inside
  `pidRampTo` is commented out, along with the `gaugeMCH` proxy it needs. The GUI
  deliberately does not offer the parameter.
- The ramps always start from the PID's **current setpoint**. There is no
  parameter to pass a starting value, and adding one would mean the first move
  could be a jump rather than a ramp — a thermal shock on the sample, or a sudden
  step on a doser.
