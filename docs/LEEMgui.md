# LEEMgui.py

Qt front end for the acquisition macros in [LEEMmacros.py](LEEMmacros.md). It
exposes the acquisitions and ramps as buttons with parameter fields, streams
their output into a log box, and can stop a running acquisition.

This document records the design and the reasoning behind it, including the
options that were considered and rejected.

## Running it

```bash
pip install PySide6            # or: sudo apt install python3-pyside6.qtwidgets
```

The easiest way, GUI and console together:

```bash
leemgui           # -n / --no-gui for the console alone
```

`leemgui` starts ipython with the Qt event loop already integrated, imports the
macros and opens the window, then leaves you at a prompt sharing the same module
as the GUI. It prefers `ipython3` over `ipython`, pins `QT_API=pyside6` so
ipython cannot pick a PyQt5 that happens to be installed, and uses `-i`, so if
the GUI fails to open you get the traceback and still land at the prompt.

It is meant to be symlinked into a bin directory, and resolves the link to find
the macros next to the real script:

```bash
ln -s ~/SURFMOSS_TangoDS/scripts/leemgui ~/bin/leemgui
```

Two directories, separately overridable, because the code and the data do not
live in the same place on the instrument:

| Variable | Default | Meaning |
|---|---|---|
| `LEEM_CODEDIR` | the script's own directory | where `LEEMmacros.py` and `LEEMgui.py` are; goes on `PYTHONPATH` |
| `LEEM_RUNDIR` | `/Superficies/LEEM_Madrid` | working directory for the session |

On the LEEM PC the checkout lives on the WSL local disk while the data lives on
the mounted server share, so `git pull` is the whole deployment step.

**Python searches the working directory before `PYTHONPATH`**, so a copy of
`LEEMmacros.py` left in the data directory silently wins over the checkout —
which is exactly how the repository and the instrument drifted apart before.
`leemgui` checks for that on startup and says which copy will be imported,
loudly if the two differ. Delete the copies in the data directory once the
checkout works.

Standalone, no console:

```bash
cd .../scripts && python LEEMgui.py
```

From ipython, keeping the prompt usable:

```python
%gui qt6
from LEEMmacros import *
gui()
```

`%gui qt6` must come **before** `gui()`. Without it, `gui()` calls `app.exec()`
and blocks the console until the window closes.

`LEEMgui.py` must sit next to `LEEMmacros.py` — `gui()` does a plain
`from LEEMgui import ...` and finds it on the same path. The import is lazy, so a
command-line session that never calls `gui()` does not need PySide6.

### `%gui qt` failing with "could not load the requested Qt binding"

IPython's Qt integration imports more PySide6 submodules than the GUI does, and
Debian/Ubuntu ship one package per Qt module. The GUI itself needs only QtCore,
QtGui and QtWidgets, which is why `python LEEMgui.py` works while `%gui qt` does
not. Install what IPython wants:

```bash
sudo apt install python3-pyside6.qtsvg python3-pyside6.qtprintsupport python3-pyside6.qtnetwork
```

Avoid a blanket `'python3-pyside6.*'` — it pulls in QtWebEngine, hundreds of
megabytes for no benefit here.

If ipython lives in a venv, apt packages are invisible to it unless the venv was
created with `--system-site-packages`.

## Why Qt rather than tkinter

tkinter is in the standard library and would have avoided a dependency, but plain
Tk widgets look dated and under WSLg the app renders as a Linux client, so `ttk`
only offers the plain Linux themes.

The original argument *for* tkinter was avoiding two competing event loops
between a Qt GUI and matplotlib's Tk backend. **v3.0 removed all live plotting**,
so that conflict disappeared and Qt became the better choice. Qt also gives
`QThread` with signals, which is cleaner than tkinter's `queue` + `after()`
polling, and `QPlainTextEdit` handles a fast-scrolling log far better than Tk's
`Text`.

## Architecture

### Acquisitions run in a worker thread

Every acquisition is a blocking loop; `leemSequenceImages(n=-1)` runs forever.
Called directly from a button handler it would freeze the event loop: the window
would stop repainting and the Stop button would be unclickable. `Worker` is a
`QThread` running exactly one acquisition at a time.

### Stopping reuses the macros' own cleanup

CTRL-C cannot be delivered to a thread. Rather than duplicating each macro's
cleanup in the GUI, Stop sets `M.leem_abort`; the macro loops poll it through
`leem_checkstop()`, which raises `KeyboardInterrupt`. **A GUI stop therefore
unwinds through the same `except KeyboardInterrupt` blocks as CTRL-C**, and the
camera is restored identically.

Two details that matter:

- `leem_abort.clear()` happens at the **start of each worker run**, not in the
  Stop handler. Otherwise one stop would poison every subsequent acquisition with
  an immediate `KeyboardInterrupt`.
- Stop is only enabled for variants marked `stoppable`. `leemSaveSingleImage` has
  no loop and cannot be interrupted, so its Stop button stays disabled rather
  than pretending otherwise.

### Output reaches the log through signals

While an acquisition runs, `sys.stdout` is replaced by `_Stream`, which buffers
whole lines and emits a Qt signal. Qt delivers cross-thread signals through the
event loop, so the worker never touches a widget. The macros keep using plain
`print()`.

`redirect`-style stdout replacement is **process-global**, so anything else
printing during a run — including an ipython prompt sharing the process — lands
in the log box. `sys.stdout` is restored in a `finally`, and exceptions travel on
a separate signal rather than through stdout, so a crash surfaces as a traceback
in the log with the buttons re-enabled.

## Layout

```
Imaging conditions:  Exposure [(keep current)]  Average (1=sliding) [(keep current)]
                     used by Image(s), IV and the temperature ramp with ROI

Image(s)                  (•) Single image  ( ) Sequence of images
IV                        (•) Plain IV  ( ) IV + ROI  ( ) IV + objective
                            └ Scan voltage: E0 / Ef / dE
Sample temperature ramp   (•) Temperature + ROI (takes images)  ( ) Temperature (setpoint only)
Doser ramp                (•) Doser 1 power  ( ) Doser 2 power
```

Four groups, each choosing one variant with radio buttons and having its own Run
button. Settings used by several calls were hoisted out of the individual rows:
exposure and average appeared in six places, `E0`/`Ef`/`dE` in three.

### The preview line

Three Run buttons mean three selections are live at once, so a shared panel
cannot be greyed to indicate which call it applies to. Instead each group shows a
grey preview of the exact call its Run will make:

```
leemIV_ROI(E0=0.0, Ef=10.0, dE=0.5, repeat=False, roi=1, saveImage=False, exp=200.0, avg=64)
```

Editing the shared panel updates every preview, which makes the indirection
visible. It doubles as a crib for typing the same call at the prompt. Variants
that take no images show no `exp`/`avg` at all, so the scope of the shared panel
is legible without greying anything.

### The shared panel forced a macro change

The panel defaults to "(keep current)", which passes `None`. Only
`leemSaveSingleImage` and `leemSequenceImages` accepted `None` at the time; the
others would have executed `uview.Exposure=None` and thrown from Tango on the
first run. v3.4 made `None` mean "use the camera's current value" in every
acquisition function. See [LEEMmacros.md](LEEMmacros.md#v34--expnone--avgnone-everywhere).

### The read-only ramp start

Ramps show the PID setpoint they will start from as a **read-only** field,
refreshed when the variant changes and after a run finishes, since a ramp moves
it. If a device server is unreachable it reads `unavailable` rather than throwing.

It is read-only because `pidRampTo` and `leemRampTemperatureROI` always ramp from
the current setpoint and take no starting value. An editable field would have
implied the first move could be a jump rather than a ramp — a thermal shock on
the sample, or a sudden step on a doser. Adding a `start=` parameter was
considered and rejected for that reason.

## Adding an acquisition

The GUI is driven by the `GROUPS` table. To expose another function, add a
`_variant(...)` to the right group:

```python
_variant("Label shown on the radio button", "functionNameInLEEMmacros",
         [_param("n","Images",int,default="-1")],   # its own fields
         stoppable=True,      # False if it has no loop to interrupt
         imaging=True,        # takes exp/avg from the shared panel
         scanv=False,         # takes E0/Ef/dE from the Scan voltage panel
         setpoint="leem_pid") # show this PID's setpoint as the ramp start
```

Before wiring a Run button, check the function has an `except KeyboardInterrupt`
handler if you mark it `stoppable` — see the invariants in
[LEEMmacros.md](LEEMmacros.md#invariants-to-preserve).

## Testing

There is no Tango or camera in a development checkout, so the GUI is tested
offscreen against a stub standing in for `LEEMmacros`, with
`QT_QPA_PLATFORM=offscreen`. What that covers:

- output streaming across the thread boundary
- Stop running the macro's own cleanup, and a run after a stop still working
- Run buttons disabled during a run and re-enabled after, including after a crash
- bad input reported per group without starting a worker
- shared panels feeding only the calls that take them, and previews tracking edits
- the read-only setpoint tracking the selected ramp

A static check parses both files and verifies every GUI field against the real
function signatures — no unknown kwargs, no missing required arguments.

What it does **not** cover: real Qt rendering, and anything touching Tango or the
camera. Those are only exercised on the instrument.

The grouped layout of v3.4 was run on the instrument on 3 August 2026 and
behaved correctly, so the worker thread, the shared imaging panel and the
read-only setpoint fields are confirmed against real device servers and not only
against the stub.

## Deliberately left out

- **ARRES.** `leemARRESset()` blocks on `input()` at the terminal, which does not
  work from a worker thread. It needs a two-phase flow — capture normal
  incidence, then endpoint 1, then endpoint 2 via dialogs on the GUI thread —
  holding `b` in GUI state for `leemARRESrun`. Run it from the console meanwhile.
- **`pressure_limit`** on the ramps: the pressure check inside `pidRampTo` is
  commented out, so a field for it would imply a safety interlock that is not
  running.
- **An "apply now" button** on the imaging panel, to set exposure/average without
  running anything. The macros restore the previous values when they finish, so
  an applied value would not survive the next run; judged more confusing than
  helpful.

## Possible future work

An embedded console was discussed and put **on hold** in August 2026: running the
GUI alongside an external ipython, with `%gui qt6` or in a second terminal, turned
out to be easier in practice. Revisit only if that stops being true. Two
approaches were considered:

- **A command line into the log box.** A `QLineEdit` evaluated against the
  LEEMmacros namespace, output to the existing log. No new dependencies, and it
  can dispatch through the existing `Worker`, so a typed acquisition would keep
  the Stop button and the streamed log.
- **`qtconsole` with an in-process kernel.** A real IPython console sharing the
  GUI's process, so the same `uview`/`leem2k` proxies. Gives completion, history
  and magics, but adds `qtconsole`/`ipykernel`/`jupyter_client` plus the split
  PySide6 packages — and an in-process kernel runs in the GUI thread, so a long
  command typed there would freeze the window, Stop included.
