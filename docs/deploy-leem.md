# Deploying the LEEM macros and device servers

Written 23-Nov-2026, preparing the deployment of v3.13–v3.16. The pieces live
on three machines and none of them updates itself, so a change that is one
commit here is three separate acts in the lab.

## What runs where

| Machine | What | How it gets there |
|---|---|---|
| `tvips` (10.43.88.35) | `scripts/LEEMmacros.py`, `scripts/LEEMgui.py` | a git clone **inside WSL** at `~/SURFMOSS_TangoDS` |
| `pi-laser` | `ElmitecLEEM2k`, `ElmitecUview` | the shared NFS root on wolframite, `/nfs/pi-trixie/opt/tango/SURFMOSS_TangoDS` |
| `wolframite` | that shared root | `git pull` there, once, for the whole Pi fleet |

`tvips` is a Windows box: its SSH drops you in `cmd`, and the Linux side —
where the macros, `/Superficies` and the clone live — is reached with
`wsl -- bash -lc "..."`. UView itself is the native Windows program, which is
why `macros.dat` carries a POSIX prefix for the macros and a UNC `wprefix`
for UView.

## State on 23-Nov-2026

Both sides sat at **v3.12**, which is the important thing: v3.12 was one
change spanning the macros *and* the two Elmitec device servers, so a
half-deployment would have the servers raising on error replies at macros
that do not expect it. They were in step.

Missing on the instrument: v3.13, **v3.14 (the UView wait — the point of the
exercise)**, v3.15 and v3.16.

⚠️ **`tvips` had a commit of its own**, `8aad07c` "go back to initial Start
Voltage after measurement", made on the instrument and never pushed. It
touches `leemIV`, `leemIV_ROI` and `leemIVandObj` — the same three functions
v3.14 and v3.15 rewrote — so a plain `git pull` there would have conflicted,
and resolving a conflict by hand on the acquisition machine mid-campaign is
the last thing anyone wants. It is re-applied here as v3.16, so the
instrument can fast-forward instead.

**Check for this again before every deployment.** The instrument is a place
where work gets done, so it can carry commits that never reached here:

```bash
ssh tvips@tvips.lab 'wsl -- bash -lc "cd ~/SURFMOSS_TangoDS && git status -sb && git log --oneline origin/main..HEAD"'
```

Anything listed by that last command exists only on the instrument. Get it
into the repository *before* updating, never after.

## Order

The macros and the Elmitec servers must not be deployed far apart, for the
v3.12 reason above. Nothing in v3.13–v3.16 changes the device servers, so
**this particular deployment is macros only** — the Pi side is already at
v3.12 and needs nothing.

Deploy **between runs**, never during one: the macros are loaded into a live
ipython session and only a fresh session picks up a change.

## Deploying the macros (tvips)

```bash
# 1. make sure nothing on the instrument is unpushed (see above)
ssh tvips@tvips.lab 'wsl -- bash -lc "cd ~/SURFMOSS_TangoDS && git log --oneline origin/main..HEAD"'

# 2. update
ssh tvips@tvips.lab 'wsl -- bash -lc "cd ~/SURFMOSS_TangoDS && git pull --ff-only"'

# 3. check what landed
ssh tvips@tvips.lab 'wsl -- bash -lc "cd ~/SURFMOSS_TangoDS && grep -m1 __version__ scripts/LEEMmacros.py"'
```

Then **restart the acquisition session** (`leemgui`, or the ipython session
that did `from LEEMmacros import *`). Until that restart the old code is
still what is running, however new the file is.

If step 2 refuses to fast-forward, stop: something is on the instrument that
is not here. Go back to step 1.

## Deploying a device server (pi-laser and the rest)

```bash
ssh juan@wolframite.lab 'cd /nfs/pi-trixie/opt/tango/SURFMOSS_TangoDS && sudo git pull'
```

That reaches every Pi, but a **running server keeps the code it started
with**: restart the affected ones from Astor, or

```bash
ssh pi@pi-laser.lab 'ps -eo pid,lstart,cmd | grep -E "ElmitecLEEM2k|ElmitecUview" | grep -v grep'
```

to see whether they have been restarted since the files changed. Compare
against the file date:

```bash
ssh pi@pi-laser.lab 'ls -l --time-style=long-iso /opt/tango/SURFMOSS_TangoDS/ElmitecUview/ElmitecUview/ElmitecUview.py'
```

A server started *before* that date is running the old code.

## After deploying v3.13–v3.16

Worth watching for, in this order:

1. **Does UView still wedge?** v3.14 makes a stall survivable, not impossible:
   the macro now says so once a minute and keeps waiting, and pressing
   *acquire* in UView still unblocks it. If the wedge keeps happening at the
   same rate now that polling is ~50× gentler, the suspicion that the old
   busy-wait helped cause it was wrong. Note which way it goes — see
   `LEEMmacros.md`, "Known rough edges".
2. **Is the command log filling again?** v3.15 logs from inside the macros,
   so a run typed at the prompt is recorded too. The file is
   `/Superficies/LEEM_Madrid/<YYYYMMDD>/<YYYYMMDD>_commands.log`, and lines
   now carry the experiment number:
   `2026-11-24 10:05:00  003  leemIV(E0=1, Ef=2.5, ...)`.
3. **Does an IV scan leave StartVoltage where it found it?** That is v3.16,
   which came off the instrument in the first place.

`tools/leem_acquisition_watchdog.py` is unaffected by any of this and can
keep running across the deployment.
