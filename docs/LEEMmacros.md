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

## Known rough edges

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
