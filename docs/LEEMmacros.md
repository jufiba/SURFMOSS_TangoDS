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

### v3.13 — one place writes `macros.dat`

`leemSetDailyFolder()` wrote the counter file with **three** fields
(`prefix,dayfolder,exp`) where `leem_getfolder()` unpacks **four**
(`wprefix,prefix,dayfolder,exp`). Calling it therefore left a file the next
call could not read at all — every macro then died at

```
ValueError: not enough values to unpack (expected 4, got 3)
```

and the Windows prefix, which is what `SaveImageAsDAT` needs to tell UView
where to write, was the field being dropped.

It survived because nothing calls `leemSetDailyFolder()` automatically any
more: `leem_makenextfolder_and_inc()` handles the day rollover itself, so the
broken function is only reachable by hand. Its own copy of the same
three-field write was harmless for a different reason — a correct four-field
write overwrites it before that function returns.

The real cause is that **four copies of this write existed in two different
spellings**, which is how the two wrong ones went unnoticed. The layout now
lives in exactly one function, `leem_setfolder(wprefix,prefix,dayfolder,exp)`,
used by all four sites. Verified against a temporary counter file: the
round-trip through `leemSetDailyFolder()` → `leem_getfolder()` now works and
keeps the Windows prefix, a day rollover still restarts at `_000`, and the
same check raises the `ValueError` above against the previous code.

### v3.14 — one helper waits for an image, gently and out loud

The `uview.AcquireSingleImage()` + `while (uview.ContinousAcquisition): pass`
pair stood at **twelve** places, and the v3.12 note above had already listed
it as untested. It was tested the hard way on 20-Nov-2026, when it wedged a
live ARRES run. All twelve are now `leem_acquire_and_wait()`, which fixes
three separate things that loop did:

- **It asked as fast as CORBA and TCP allowed.** The read sends UView's
  `aip` over its single socket, so the loop was a round trip per turn with
  no pause at all. It now asks every `LEEM_POLL_IMAGE` (50 ms): about eight
  questions per 400 ms exposure instead of one per round trip, for at most
  50 ms of added latency per image. Whether that *also* stops UView wedging
  is the open question — see "Known rough edges".
- **It had no timeout**, so a wedged UView stopped a run silently and for
  ever. It now prints a warning every `LEEM_WARN_IMAGE` (60 s) naming what
  it is waiting for and what to do about it.
- **It never polled `leem_checkstop()`**, so the GUI Stop button could not
  interrupt a wait. CTRL-C could, having nothing to poll, but a GUI stop had
  no way in. The sleep is `leem_abort.wait()`, as in `leemSequenceImages`
  and the PID ramps, so a stop does not have to sit out the interval either.

**The timeout deliberately does not give up.** Pressing *acquire* in UView
unblocks the wait and the run carries on from exactly where it was, so
turning a recoverable stall into a lost acquisition would be the worse
outcome. The asymmetry is intended: the timeout never raises, a stop *you*
ask for always does.

`tools/test_leemmacros.py` is new and covers this against a stub tango
module — the questions stay in single figures over an exposure, an image
already finished costs one question and no sleep, the warning repeats
without raising, and a stop interrupts the wait. It covers the v3.13
counter file too, and needs no instrument, so unlike the device-server tests
here it also runs on a laptop.

### v3.15 — the macros log themselves

`leem_log()` had **exactly one caller**: `LEEMgui.py`'s Run button. So the
"log of every command" only ever saw GUI button presses, and nothing typed
at the ipython prompt was recorded. ARRES is command line only —
`leemARRESset()` asks for `input()` at the terminal — so an ARRES campaign
produced no log at all. Counted on the share:

```
20261105  experiments=8   log=6 lines
20261118  experiments=30  NO LOG
20261119  experiments=32  NO LOG
20261120  experiments=11  NO LOG
20261121  experiments=27  NO LOG
20261123  experiments=1   NO LOG
```

101 experiments, no line. Not a breakage: the day folders are `drwxrwxrwx`,
`macros.dat` is well formed, and 5 November wrote fine — the function simply
was not called. The macro mix is the tell: 5 November was all IMG and
LEEMIV, while 19 and 21 November are the ARRES days.

`leem_log_call()` now sits in each of the ten macros the GUI could run (the
seven that take an experiment folder, plus the three PID ramps), and the
call in `LEEMgui` is gone so a GUI run is not logged twice. Two details:

- **The line is built from the caller's own arguments**, by reading the
  calling frame, rather than a format string written out per macro. Twelve
  copies of the image wait (v3.14) and four of the `macros.dat` write
  (v3.13) are what this file keeps being bitten by; a format string per
  macro would be ten more copies to drift from ten signatures. Long values
  are put on one line and clipped, because `leemARRESrun`'s `b` is a 3×4
  array whose `repr` spans several.
- **`leem_log()` is told the folder number** instead of guessing it from the
  counter file. That guess worked only because the GUI logged *before* the
  acquisition took its folder; from inside the macro the counter has already
  moved on, so it would now be one too high. A ramp, which takes no folder,
  writes `---` in that column.

### What is actually deployed, checked 23-Nov-2026

The logs invited a wrong conclusion and it is worth recording, because the
next person reading them will reach for it too. No line from 10 September to
5 November carries the experiment number v3.11 added on 16 September:

```
2026-09-10 18:28:36  leemSaveSingleImage(...)
2026-11-05 11:56:45  leemIVandObj(...)
```

That looks like proof the instrument is older than v3.11. It is not. Every
log that exists predates the v3.12 update, because logging had already
stopped when the GUI stopped being used — so there is no recent line to
carry the number either way. Checking the machines themselves:

| Where | What runs there | State on 23-Nov-2026 |
|---|---|---|
| `tvips` (WSL), `~/SURFMOSS_TangoDS` | the macros and the GUI | **v3.12**, plus one local commit |
| `pi-laser`, via the shared root | `ElmitecLEEM2k`, `ElmitecUview` | **v3.12** (files 18-Nov), both servers restarted 23-Nov |

So the macros and the device servers **are in step at v3.12** — which
matters, because v3.12 was one change spanning both, and half of it would
mean the servers raising at macros that do not expect it. Missing on the
instrument are v3.13, v3.14 (the UView wait, the point of all this) and
v3.15.

⚠️ **`tvips` carries a commit that is not in this repository**: `8aad07c`,
"go back to initial Start Voltage after measurement", made on the instrument
on 23-Nov. It touches the same three functions this repository has been
rewriting, so a plain `git pull` there would conflict. It is folded into
v3.16 below; the deployment note is in `docs/deploy-leem.md`.

See "The instrument runs its own copy" above: committing a change does
nothing to the running instrument, and the instrument can commit things
that never reach here.

## Invariants to preserve

- **Wait for an image with `leem_acquire_and_wait()`, never by hand.** Since
  v3.14 it is the only place that triggers an image and waits for it, and it
  carries the poll interval, the warning and the `leem_checkstop()` call. A
  hand-written `while (uview.ContinousAcquisition): pass` loses all three,
  which is exactly how the stall of 20-Nov-2026 was possible.
- **Never wait for an image on a running camera**, through that helper or
  otherwise. The read means "acquisition in progress" and stays `True`
  forever while continuous mode is on, so the wait only terminates on a
  stopped camera. Since v3.14 that mistake at least says so once a minute
  instead of hanging in silence.
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

- **UView can still wedge; v3.14 only makes it survivable.** The stall of
  20-Nov-2026 is not cured, it is made visible and harmless: the macro now
  says so once a minute and keeps waiting, and pressing *acquire* in UView
  is still what unblocks it. Why UView gets into that state —
  `WaitForSingleObject failed 100000x in a row` — is not understood. The
  suspicion recorded in v3.14 is that the old busy-wait was helping to cause
  it; if the wedge keeps happening at the same rate now that the polling is
  ~50× gentler, that suspicion is wrong and the cause is elsewhere. **Worth
  noting which way it goes.**

  `tools/leem_acquisition_watchdog.py` is what tells you from elsewhere: it
  mails when a run stops writing data, watching file mtimes rather than
  UView, so it adds no traffic to the instrument. Start it by hand alongside
  a long run:

  ```bash
  python3 tools/leem_acquisition_watchdog.py --test-mail   # prove the mail path first
  python3 tools/leem_acquisition_watchdog.py --timeout 10
  ```

  It registers the same `atexit` → `tango.ApiUtil.cleanup()` hook as v3.7:
  on tvips, `--test-mail` sent its mail and then exited with a segmentation
  fault, omniORB's client threads racing Python finalisation again. It does
  not reproduce on wolframite, so it depends on the pytango build there, as
  v3.7 already found.

  It is not automatic on purpose: a run that *finishes* also stops writing,
  and `ContinousAcquisition` cannot tell the two apart — it reads 1 both while
  acquiring an image and while the live view runs, which is what
  `leemARRESrun` leaves on when it ends.

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
