# Installing and running `leemgui` on Debian / Ubuntu

`leemgui` (in `scripts/`) opens the LEEM acquisition GUI (`LEEMgui.py`) with an
IPython console attached, both sharing one namespace. The GUI drives the
acquisition macros in `LEEMmacros.py`, which talk to the LEEM Tango device
servers.

This is the setup and operations guide. For *why* the GUI and the macros are
built the way they are, see [LEEMgui.md](LEEMgui.md) and
[LEEMmacros.md](LEEMmacros.md).

Target: the WSL (Ubuntu) environment on the LEEM PC. Everything here also works
on a normal Debian/Ubuntu desktop that can reach the instrument's Tango
database.

## What you get

| Command | Effect |
|---|---|
| `leemgui` | IPython + Qt event loop, macros imported, GUI window open |
| `leemgui -n` | the same console, no window; `gui()` opens it later |
| `python LEEMgui.py` | GUI alone, no console (still needs the macros and Tango) |

## Requirements

Everything is an `apt` package. There is no `pip` step, no virtualenv and no
`requirements.txt`: `LEEMmacros.py` and `LEEMgui.py` are imported straight from
the checkout, not installed.

| Package | For |
|---|---|
| `git` | the checkout |
| `ipython3` | the console and its `--gui=qt6` event-loop integration (IPython ≥ 8) |
| `python3-tango` | PyTango — `LEEMmacros` talks to the Tango servers |
| `python3-numpy` | arrays in the macros |
| `python3-scipy` | `scipy.interpolate` in the IV macros |
| `python3-matplotlib` | plots written to file (Figure API, no pyplot, no backend) |
| `python3-pyqt6` | the GUI itself: `QtCore`, `QtGui`, `QtWidgets` |
| `python3-pyqt6.qtsvg` | **not used by the GUI** — IPython's Qt loader imports `QtSvg` and rejects the whole PyQt6 binding without it. See _Troubleshooting_. |

```bash
sudo apt install git ipython3 python3-tango python3-numpy python3-scipy \
                 python3-matplotlib python3-pyqt6 python3-pyqt6.qtsvg
```

Do **not** `apt install 'python3-pyqt6.*'` — it pulls in QtWebEngine, hundreds
of MB for no benefit here.

If you run IPython from a virtualenv, apt packages are invisible to it unless
the venv was created with `--system-site-packages`. Simplest is to use the
system IPython.

## Install

```bash
git clone <the repository URL your lab uses> ~/SURFMOSS_TangoDS
mkdir -p ~/bin
ln -s ~/SURFMOSS_TangoDS/scripts/leemgui ~/bin/leemgui
```

Debian and Ubuntu login shells put `~/bin` on `PATH` automatically if it
exists; open a new shell or `source ~/.profile`.

`leemgui` resolves the symlink to find `LEEMmacros.py` / `LEEMgui.py` next to
the real script, so the link can live anywhere. Updating is `git pull` — there
is nothing to rebuild or reinstall.

## Point it at the instrument

`from LEEMmacros import *` builds `DeviceProxy` objects for `leem/control/*` and
`leem/measurement/*` **at import time**, so the Tango database must be reachable
before `leemgui` will start. There is no offline mode: the GUI cannot run
without network line-of-sight to the LEEM Tango database.

Set `TANGO_HOST` in one of:

```bash
echo 'TANGO_HOST=<db-host>:10000' | sudo tee /etc/tangorc     # system-wide
echo 'TANGO_HOST=<db-host>:10000' > ~/.tangorc                # per user
export TANGO_HOST=<db-host>:10000                             # this shell only
```

Check it:

```bash
python3 -c "import tango; print(tango.Database().get_info())"
```

should print the database server details, not raise.

The device *servers* may be down when `leemgui` starts — a `DeviceProxy` to a
device that is defined in the database but not currently running still
constructs, and fails only when a macro actually uses it. Only the database has
to be up.

## Running under WSL

The GUI needs an X or Wayland display.

- **Windows 11** — WSLg provides one. `echo "$WAYLAND_DISPLAY $DISPLAY"` should
  show something like `wayland-0 :0`. Nothing to install.
- **Windows 10** — no WSLg. Run an X server on Windows (VcXsrv, X410, …) and
  `export DISPLAY=<windows-host>:0`.

Under WSLg's X, Qt uses the `xcb` platform plugin. If the window fails to open
with *"could not load the Qt platform plugin xcb"*, install the runtime
libraries the xcb plugin needs but that a slim WSL image can lack:

```bash
sudo apt install libxcb-cursor0 libxkbcommon-x11-0
```

`QT_QPA_PLATFORM=xcb QT_DEBUG_PLUGINS=1 python3 scripts/LEEMgui.py` names the
missing `.so` if it is a different one.

## First run

```bash
leemgui
```

Expected:

```
LEEM macros loaded, GUI open. Running in /Superficies/LEEM_Madrid
In [1]:
```

plus the acquisition window. `uview`, `leem2k`, `leem_pid` and every macro are
at the prompt, sharing the module with the GUI.

If `/Superficies/LEEM_Madrid` is not mounted, `leemgui` says so and runs in the
checkout directory instead — fine for a smoke test, not for real acquisitions
(the run counter lives under the data directory).

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `TANGO_HOST` | from `/etc/tangorc` | the Tango database; **required** |
| `LEEM_CODEDIR` | the script's own directory | where `LEEMmacros.py` / `LEEMgui.py` live; prepended to `PYTHONPATH` |
| `LEEM_RUNDIR` | `/Superficies/LEEM_Madrid` | working directory for the session; where data and the run counter are written |
| `QT_API` | set to `pyqt6` by `leemgui` | forces the Qt binding so IPython cannot pick up a stray PyQt5 |

`leemgui` warns on startup if a stale `LEEMmacros.py` or `LEEMgui.py` sits in
`LEEM_RUNDIR`: Python imports the working directory before `PYTHONPATH`, so that
copy would silently win over the checkout. Delete such copies.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `ImportError: Could not load requested Qt binding … PyQt6 available (requires QtCore, QtGui, QtSvg, QtWidgets): False` at startup | `import PyQt6` works, but IPython's `--gui=qt6` loader also imports `QtSvg`, which Debian/Ubuntu package separately. `sudo apt install python3-pyqt6.qtsvg`. |
| `leemgui: neither ipython3 nor ipython found` | `sudo apt install ipython3` |
| `from LEEMmacros import *` hangs, or `DevFailed … TRANSIENT_CallTimedout` / `DB_DeviceNotDefined` | `TANGO_HOST` unset or the database unreachable. See _Point it at the instrument_. |
| `could not load the Qt platform plugin "xcb"` | missing xcb runtime libs: `sudo apt install libxcb-cursor0 libxkbcommon-x11-0`. Diagnose with `QT_DEBUG_PLUGINS=1`. |
| Window never appears, no error | no display. `echo "$DISPLAY $WAYLAND_DISPLAY"`; on Windows 10 start an X server and set `DISPLAY`. |
| apt-installed modules not found by IPython | IPython is in a virtualenv without `--system-site-packages`. Use the system IPython, or `pip install` the deps into the venv. |
| `leemgui: WARNING …/LEEMmacros.py DIFFERS …` | a stale copy in the data directory is the one being imported. Delete `$LEEM_RUNDIR/LEEMmacros.py` and `$LEEM_RUNDIR/LEEMgui.py`. |
| segfault when exiting the IPython session | omniORB / interpreter-finalisation race; `LEEMmacros` registers an `atexit` `tango.ApiUtil.cleanup()` for it. If it still happens, update the checkout. |

## Updating

```bash
cd ~/SURFMOSS_TangoDS && git pull
```

That is the whole deployment step. The next `leemgui` picks up the new macros;
nothing to rebuild.
