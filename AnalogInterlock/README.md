# AnalogInterlock

Generic threshold interlock between two Tango devices. Reads a numeric
attribute from an input device and asserts or de-asserts a permissive on an
output device, with hysteresis, read-failure tolerance and detection of a
frozen input publisher.

Replaces the `xps-interlock.py` cron script on pi-xps.

**This is a secondary protection layer.** It runs in userspace, over CORBA,
between two processes on a Raspberry Pi. Anything that genuinely must not
happen belongs in a hardware chain — a flow switch in series with the supply
enable — not here.

## ✅ pi-xps netboots (resolved 26-Aug-2026)

This is written for the shared NFS root. Until 26-Aug-2026 **pi-xps booted from
its own microSD** and shared no software with it, so installing into
`/nfs/pi-trixie` did not reach that machine and this server was deliberately
kept out of the install set. That is no longer the case.

Both prerequisites are in the repository: `SEAWaterflowmeter`'s `UpdateCount`
and `channelnames`, and `RaspberryButton`'s `Keepalive` / `DeadmanTimeout`. What
still has to be checked **on the machine** before bringing this up is what
`channelnames[0]` is actually set to on `xps/safety/water` — see
_Registration_ below, where this document and the code disagree.

## Installation into the repository

Done on 27-Aug-2026: `AnalogInterlock` is in `[project.scripts]`,
`[tool.setuptools] packages` and `[tool.setuptools.package-dir]`, which brings
the live count to 33 and makes the directory and installable counts agree again.

Installed is not registered: the server is built and its wrapper appears in
`/usr/local/bin`, but nothing starts until it is entered in the database with
the properties below.

To regenerate the entry-point wrapper on the shared NFS root:

```bash
sudo systemd-nspawn -D /nfs/pi-trixie
cd /opt/tango/SURFMOSS_TangoDS
pip install --no-deps --break-system-packages -e .
exit
# verify /nfs/pi-trixie/etc/resolv.conf, nspawn overwrites it silently
```

## Registration

Server `AnalogInterlock/xps`, class `AnalogInterlock`, device
`xps/safety/waterinterlock`, host pi-xps, **startup level 3** (after
`RaspberryButton/1` and `SEAWaterflowmeter/3`, both at level 2).

Set the properties *before* starting it for the first time: without
`InputDevice` and `OutputDevice` the `init_device` will fail.

| Property             | Value for pi-xps              |
|----------------------|-------------------------------|
| `InputDevice`        | `xps/safety/water`            |
| `InputAttribute`     | `xray` — confirmed, see below |
| `HeartbeatAttribute` | `UpdateCount`                 |
| `OutputDevice`       | `xps/safety/xrayguninterlock` |
| `ThresholdOff`       | `1.6`                         |
| `ThresholdOn`        | `2.0` (pending nominal flow)  |
| `PollPeriod`         | `1.0`                         |
| `Latching`           | `false` (hardware latches)    |
| `ProxyTimeout`       | `800` (default; see Timing)   |

The named attribute comes from `channelnames` on `xps/safety/water`, which has
`channels = '13'` — one channel, so one named attribute. **Settled on
27-Aug-2026 by reading the database: `channelnames = ['xray']`**, so the
attribute is `xray`. This document was right and the code's own example, which
says `xraygun`, is wrong.

The refactored server is deployed on pi-xps and running: `xps/safety/water` is
ON and exposes `xray` alongside `channel0..3` and `UpdateCount`. So is the
patched `RaspberryButton`: `xps/safety/xrayguninterlock` has `Pin = 26` and
publishes `PinLevel`, `Active` and `TimeSinceKeepalive`. Its `DeadmanTimeout` is
still unset, which is correct until commissioning step 4.

Requires the refactored `SEAWaterflowmeter` (for the named attribute and for
`UpdateCount`) and the patched `RaspberryButton` (for `Keepalive`).
On `RaspberryButton/1` set `DeadmanTimeout = 10.0`. It must be comfortably
longer than a restart of this server, or restarting the interlock drops the
permissive and someone has to walk over and press the physical reset button.

## Failure modes

| Condition                  | Response                                     |
|----------------------------|----------------------------------------------|
| input below `ThresholdOff` | de-assert, ALARM                             |
| input unreadable/INVALID   | de-assert after `MaxReadFailures`, FAULT     |
| heartbeat unreadable       | de-assert after `MaxReadFailures`, FAULT     |
| input publisher frozen     | de-assert after `StaleCycles`, ALARM         |
| this server dies           | keepalives stop, output device's deadman fires |
| output device unreachable  | FAULT; nothing else is possible from here    |

The frozen-publisher case is the one neither the cron script nor a naive
port could catch: a dead acquisition thread keeps returning its last good
reading, which is indistinguishable from healthy flow. `UpdateCount` is what
makes it visible.

A heartbeat that is **configured but unreadable** counts as a failure, not as an
absent heartbeat. Pointing `HeartbeatAttribute` at something that does not exist
— an older `SEAWaterflowmeter` without `UpdateCount`, say — therefore faults
loudly instead of leaving the server ON with its staleness detection silently
switched off. To run without it on purpose, set the property to the empty string.

### Timing

A trip takes at most `MaxReadFailures * (ProxyTimeout + PollPeriod)` when the
input device hangs instead of answering. With the defaults that is about **5 s**
(3 x (0.8 + 1.0)), which has to stay comfortably below the output device's
`DeadmanTimeout` of 10 s: otherwise the deadman fires first and recovery needs a
fresh `On()` rather than just the flow coming back. `ProxyTimeout` used to
default to 3000 ms, which gave 12 s and lost that race.

## Commissioning, with the gun off and no filament

1. `DeadmanTimeout = 0` still. Start only `AnalogInterlock` and check that
   `Permit` follows the flow and that `LastTripReason` fills in when the
   valve is closed.
2. `Trip` command from Jive: the permissive must drop **and stay down** — a
   manual trip latches whatever `Latching` says, since a person asked for it.
   Clear it with `Reset`.
3. Stop `SEAWaterflowmeter/3` from Astor: after `MaxReadFailures` cycles,
   FAULT and no permissive.
4. Set `DeadmanTimeout = 10`, Init `RaspberryButton/1`, issue `On()` by hand
   from Jive and touch nothing: it must go to ALARM on its own after 10 s.
5. `kill -9` the `AnalogInterlock` process: the permissive must drop within
   10 s.

Step 5 is the case the cron script never covered, and the reason for the
whole exercise.
