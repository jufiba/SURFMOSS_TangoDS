# Synoptics (JDraw)

One `.jdw` per instrument, opened by `launch`:

```bash
./launch leem        # runs synopticappli leem.jdw
```

so the file name must be **lowercase** and match the argument: `leem.jdw`,
`mossbauer.jdw`, `sputtering.jdw`, `xps.jdw`.

`LEEM_*.jdw` are sub-panels of the LEEM synoptic (chamber PCH, the two dosers,
the sample stage), not alternative versions of it.

## Versions live in git, not in the file name

`leem.jdw` was consolidated on 19-ago-2026 from a set of hand-numbered copies
(`LEEM.jdw`, `LEEM_v2`, `LEEM_v3`, `LEEM_v4`); the newest, v4, became
`leem.jdw`. All of them are in the history of the commit before that, so
recovering one is `git show <commit>:synoptics/LEEM_v3.jdw`. **Do not add
`_v5`** — commit the change to `leem.jdw` instead.

## Device references need checking against the DB

A drawing referring to a device that no longer exists shows up only as a dead
element at runtime, so it is worth checking rather than noticing by eye:

```bash
python3 tools/check_synoptics.py
```

It reads every reference out of the `.jdw` files and checks the device against
the Tango database and the attribute or command against the device itself.

**Resolved on 28-Aug-2026.** All 119 references across the eight drawings were
checked and six were broken:

| Referenced | What it was | Done |
|---|---|---|
| `leem/vacuum/gaugeMCH/Pressure_IG1` | the retired VarianMultiGauge's attribute | now `Pressure`, on the Granville Phillips 350 that replaced it |
| `mossbauer/termperature/criostat` | a misspelling, in two places | corrected to `temperature` |
| `leem/measurement/PositionXY` | retired hardware, twice and with two capitalisations | elements removed |
| `xps/measurement/xraygun` | retired hardware, twice | elements removed |

The remaining references all resolve, except those on `sputtering.jdw` and the
UPS on `leem.jdw`, whose devices are registered but not running — the drawings
are right, the instruments are switched off.

## Autostart on the panel Pis

`pi-xps`, `pi-leem` and `pi-rackmossbauer` each run a `synoptic.service` that
opens their own drawing full-screen on boot (`ConditionPathExists=/etc/synoptic/%H.jdw`
picks it per host, matched by name — `pi-rackmossbauer.jdw` links to
`mossbauer.jdw`, and so on; see `docs/netboot-shared-root.md`). `synoptic.service`
and `synoptic-session` here are what is actually deployed at
`/etc/systemd/system/synoptic.service` and `/usr/local/bin/synoptic-session`
in the shared root on wolframite — kept here for the record and for review,
copied over by hand rather than symlinked like the `.jdw` files, since a unit
change also needs `systemctl daemon-reload`.

### The race that left widgets permanently blank

Found 16-Sep-2026 on `pi-xps`: the Ion Pump and Turbo Pump readouts stayed
blank all session, while the same devices answered perfectly to a direct
`DeviceProxy` from a script. `synoptic.service` used to only wait on
`network-online.target`/`time-sync.target`, with no dependency on
`tango-starter.service` or on the local device servers actually being up.
`tango-starter` on `pi-xps` launches its six local servers one at a time,
about 7-8 s apart — the whole sequence took roughly 50 s that boot — while
the panel opened about a second after the *first* one started. Widgets whose
device came up soon after (`SEAWaterflowmeter` at +20 s, `AnalogInterlock`
at +28 s) recovered fine; `GammaVacuumDigitel` and `PfeifferTC100`, the last
two in the queue at +43 s and +49 s, did not — confirmed with a screenshot
(`scrot` over the session's own `DISPLAY=:0`), not just a guess.

A widget that connects successfully at least once *does* survive its device
restarting later: tested by hand, restarting `CryoCon32` from Astor under a
live `mossbauer.jdw` session on `pi-rackmossbauer` — `Sample Temperature`
kept reading correctly straight through the restart, no interruption. So the
bug is specifically the *first* connection attempt, at panel start-up: if it
fails, nothing here makes the widget try again for the rest of the session.

`synoptic-session` now waits for every device its own drawing references
(only the top-level one — a `LEEM_*.jdw` sub-panel opened later, well after
boot in practice, is not covered) to answer `tango_admin --ping-device`,
polling every 2 s for up to 120 s, before ever handing off to `synopticappli`.
Bounded, not indefinite: past the timeout it opens anyway and says so via
`logger`, so a device that is genuinely down does not also keep the panel
from opening. `synoptic.service` also now lists `tango-starter.service` in
`After=`/`Wants=`, a cheap addition that alone would not have been enough —
the Starter itself starts in seconds; its children take much longer.

Tested against a stubbed `tango_admin`/`hostname`/`synopticappli` on a
laptop, not against a live panel: all-up (proceeds immediately), all-down
(waits the full timeout, then proceeds and logs which devices are still
missing), and recovers-mid-wait (proceeds as soon as the last one answers,
logs how long that took).

### Deploying a change

The two files here are not symlinked into the shared root, so an edit needs
copying by hand, from wolframite:

```bash
cd /nfs/pi-trixie/opt/tango/SURFMOSS_TangoDS && git pull
cp synoptics/synoptic.service /nfs/pi-trixie/etc/systemd/system/synoptic.service
install -m 755 synoptics/synoptic-session /nfs/pi-trixie/usr/local/bin/synoptic-session
```

then, on each of `pi-xps`, `pi-leem` and `pi-rackmossbauer` (a unit file
change needs a reload on every machine that reads it, even though the file
itself is shared):

```bash
sudo systemctl daemon-reload
sudo systemctl restart synoptic.service
```
