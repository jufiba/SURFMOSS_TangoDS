# AnalogInterlock

Generic threshold interlock between two Tango devices. Reads a numeric
attribute from an input device and asserts or de-asserts a permissive on an
output device, with hysteresis, read-failure tolerance and detection of a
frozen input publisher.

Replaces the `xps-interlock.py` cron script on pi-xps, which is retired to
`deprecated/`. A second instance on pi-mossbauer watches the compressor cooling
water without commanding anything.

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

## The properties, one by one

Every knob is a device property, read once at `init_device`; changing one needs
an `Init` or a server restart to take effect. The two registration tables below
are worked examples — this is what each field means. Values in parentheses are
the defaults, and the running example is `xps/safety/interlockxraygun`.

### What it reads

**`InputDevice`** — the Tango device the measured quantity comes from. No
default; `init_device` fails without it. For the X-ray gun that is
`xps/safety/water`, the `SEAWaterflowmeter` on the gun's cooling line.

**`InputAttribute`** (`channel0`) — the attribute on `InputDevice` to read. On
`interlockxraygun` it is `xray`, the named channel for the gun's flow. Prefer a
named attribute over a positional one like `channel0`: if the channel order on
the flowmeter is ever changed, a named attribute simply disappears and this
server faults, whereas `channel0` silently starts watching a different line.

**`HeartbeatAttribute`** (`none`) — a counter on `InputDevice` that advances
once per acquisition cycle. Name it and the server tells a healthy reading from
a dead acquisition thread handing back its last good value forever; it trips
after `StaleCycles` if the counter stops.

Staleness detection is **opt-in**, and which family of input you have decides
whether to opt in:

- **Cached-acquisition input** — a `SEAWaterflowmeter`, which reads GPIO in its
  own loop and serves the last value. Its characteristic failure is that loop
  dying while the server stays up and `State` stays `ON`: the flow freezes and
  nothing looks wrong. Name `HeartbeatAttribute` here — it is `UpdateCount`,
  and it is the only defence against that failure.
- **Read-on-demand input** — a serial or socket pump controller that talks to
  the hardware inside each `read_*`. There is no cached value to freeze; a dead
  instrument raises and the interlock already reports it as `FAULT`. Leave
  `HeartbeatAttribute` at `none` — a counter there would be decorative.

The off switch is the word `none` (or `-`), no quotes. A name that points at
nothing is a fault, not an off switch (see _Failure modes_). An empty string is
honoured if a database layer delivers one, but PyTango substitutes the default
for an empty value before the server sees it, so it cannot be relied on — use
the word.

When the heartbeat is off, every status line says so: _staleness detection is
OFF … a frozen reading would be trusted_. It is not raised in `State` — an
`AlarmNotifier` rule wanting to catch it should match the status text, not a
state, so that a healthy read-on-demand interlock is not parked permanently in
`ALARM`.

**Migration note.** Changing this default from `UpdateCount` to `none`
(10-Sep-2026) silently disables staleness detection on any interlock that was
relying on the default — which was every `SEAWaterflowmeter` input in the lab.
The explicit `HeartbeatAttribute=UpdateCount` was written to the six affected
devices **before** the code change; it must never be applied after. See
_Registration_ for the list.

### Whether it evaluates at all

**`GateDevice`** — a Tango device whose state decides whether this interlock
runs at all. No default; empty means always evaluate, which is
`leem/safety/interlockP2lens`, the XPS instance and pi-mossbauer, unchanged to
the cycle. Set it to the thing the interlock protects. For
`leem/safety/interlockhv1` that is `leem/power/hv1`, so that the resting state
of the lab — hv1 off, doser cooling water deliberately shut — is not read as a
trip. See _The trip that was the resting state_.

**`GateStates`** — the comma-separated Tango state names in which the gate is
**open** and evaluation runs, e.g. `ON` or `ON,RUNNING`. Required once
`GateDevice` is set; the server refuses to start if it names something that is
not a Tango state, or if `GateDevice` is set and this is left empty. It is the
set that means *open*, not an inventory of the gate device's states:
`leem/power/hv1` only ever reports `ON` or `OFF`, so `GateStates = ON,OFF`
would leave the gate permanently open and silently restore the pre-gating
behaviour — the server warns in `Status` when `GateStates` looks like it covers
everything the gate device can publish.

While the gate is shut the device is `OFF`: it reads nothing, commands nothing,
and leaves the `LastTrip*` fields alone. A trip that latched before the gate
shut stays latched. An **unreadable** gate counts as open — for a
command-on-trip interlock, failing towards acting is recoverable and failing
towards silence is not — and `Status` says the gate could not be read.
Reopening the gate restarts evaluation from a clean slate, so a condition that
was already bad while the gate was shut is caught on the next cycle rather than
inherited as good.

### What it commands

**`OutputDevice`** — the device that actually holds the permissive. No default;
required unless `WatchOnly`. On pi-xps it is `xps/safety/switchxraygun`, a
`RaspberryButton` driving GPIO 26.

**`OnCommand`** (`On`) / **`OffCommand`** (`Off`) — the commands sent to
`OutputDevice` to grant and withdraw the permissive. The defaults match
`RaspberryButton` and `FUGMCP`; set them for an output device that names those
operations differently.

**`KeepaliveCommand`** (`Keepalive`) — sent to `OutputDevice` on every cycle
while the permissive is granted, to feed that device's deadman. That is what
makes this server *dying* drop the permissive rather than leave it frozen
asserted. Empty string if the output device has no deadman.

**`WatchOnly`** (`false`) — if true, no command is ever sent: the server reads,
applies the thresholds and hysteresis, and only publishes `Permit` and a state.
`OutputDevice` must then be empty. See _Which way round, and whether it commands
anything_.

### The thresholds and their direction

**`ThresholdOn`** (`2.0`) / **`ThresholdOff`** (`1.6`) — the input levels at
which the permissive is granted and withdrawn. They are deliberately not equal:
the gap is the hysteresis that stops the output chattering when the input rides
the trip point. Normally `ThresholdOff` is the lower of the two.

**`Reverse`** (`false`) — which side is safe. `false`: the input must stay
**high**, as a cooling flow must — granted above `ThresholdOn`, withdrawn below
`ThresholdOff`. `true`: it must stay **low**, as a temperature or a pressure
must — the comparisons and the ordering of the two thresholds both flip.
Declared, not inferred from which threshold is larger, so a pair typed the wrong
way round is refused at start-up instead of silently inverting the interlock.
Full account in _Which way round, and whether it commands anything_.

### Tolerance and timing

**`PollPeriod`** (`1.0`) — seconds between cycles. No use polling faster than the
input device's own integration period.

**`MaxReadFailures`** (`3`) — consecutive failed or `INVALID` reads tolerated
before the server trips. Absorbs a transient CORBA timeout without leaving the
output asserted through a real outage.

**`StaleCycles`** (`5`) — how many cycles `HeartbeatAttribute` may fail to
advance before the server trips on a frozen input publisher.

**`ReassertCycles`** (`30`) — re-send `OnCommand` every N cycles while granted,
so the permissive comes back on its own if `OutputDevice` was restarted
underneath the interlock. `0` disables the re-assert.

**`ProxyTimeout`** (`800`) — milliseconds a single read or command may block.
This sets how long a trip takes when the input device *hangs* rather than
answering: worst case `MaxReadFailures * (ProxyTimeout + PollPeriod)`, about 5 s
with the defaults. It has to stay well below the output device's
`DeadmanTimeout` — see _Timing_.

**`Latching`** (`false`) — if true, a trip stays asserted until the `Reset`
command is called, even after the input recovers. Leave it `false` where the
hardware already latches and wants a physical reset button (pi-xps); set it
`true` for a watch whose whole point is to record that a dip happened
(pi-mossbauer), or where an operator must look at the machine before the
permissive comes back (`leem/safety/interlockP2lens`).

Write the three bool properties — `Latching`, `WatchOnly`, `Reverse` — as a bare
`true` or `false`, with nothing around the word. PyTango converts them by
comparing the stored string with the literal `"true"`, so `True⇥` and `1` both
come out `False`. Since 08-Sep-2026 the server compares what it was handed
against what the database actually holds and refuses to start on a
disagreement — see _The latch that was never read_. `MaxBypassHours` and
`BypassWarnMinutes` are floats and `GateDevice` / `GateStates` are strings, so
the same stray tab does them no harm; only the bools are fragile.

### The bypass

**`MaxBypassHours`** (`8`) — the most a single `BypassFor` may ask for. A
larger request is **refused**, not clamped: on a safety device the number the
operator typed has to be the number in force. Cover a longer run by renewing.
Mirrors `AlarmNotifier`'s `MaxSnoozeHours`.

**`BypassWarnMinutes`** (`30`) — how long before a bypass expires the state
goes from `DISABLE` to `STANDBY`, so an `AlarmNotifier` rule can mail ahead of
the expiry. A bypass requested for less than this stays `DISABLE` for its whole
life and never raises the warning.

The bypass mechanism itself is in _Bypassing the interlock for a day_.

### What it publishes back

Read-only attributes, for a synoptic or AlarmNotifier: `InputValue`, `Permit`,
`Tripped`, `LastTripTime`, `LastTripValue`, `LastTripReason`, and `ThresholdOn`
/ `ThresholdOff` / `Latching` as read-backs of the properties in force. The
`Latching` read-back is the value the server is actually using, not the string
in the database — the point of publishing it is that the two can differ.

**`UpdateCount`** advances once per poll, gated and bypassed cycles included. A
rule on it is how a stopped sweep thread becomes a mail — see _Nothing here
catches this server dying_.

The bypass publishes `Bypassed`, `BypassRemaining` (minutes), `BypassUntil`,
`BypassSince`, `BypassReason` and `BypassRenewals`. `BypassSince` and
`BypassRenewals` are the honest numbers for a report — "bypassed 14 h, 3
renewals" — where `BypassRemaining` is reassuring and says nothing.
`BypassState` is a memorized JSON blob, not for hand editing, that carries a
live bypass across a restart.

Since `AlarmNotifier` reads `State` and nothing else, the state machine is the
whole operator-visible API:

| State | Meaning |
|---|---|
| `ON` | gate open, condition good, permissive granted |
| `ALARM` | tripped — or readable but inside the hysteresis band with no permit |
| `FAULT` | input unreadable, heartbeat unreadable, or a configuration refused at start-up |
| `OFF` | gate shut — not evaluating |
| `DISABLE` | bypassed, more than `BypassWarnMinutes` left |
| `STANDBY` | bypassed, inside the final `BypassWarnMinutes` before expiry |

`INIT` is the startup state, held until the first reading and after `Reset`;
`OFF` outranks it, so a device that starts with its gate shut shows `OFF`
rather than a night of `INIT` that reads as a hang. A frozen input publisher
trips to `ALARM`, not `FAULT` — the reading cannot be trusted but the device is
not broken. "The flow is lost" and "the sensor is dead" both arrive as `ALARM`;
the difference is in `LastTripReason` and in the mail, not in the state.

Commands: `Trip` (manual de-assert, to test the chain without touching the
water), `Reset` (clear a latched trip), and `BypassFor` / `Arm` (see
_Bypassing the interlock for a day_).

## Registration

Server `AnalogInterlock/1`, class `AnalogInterlock`, device
`xps/safety/interlockxraygun`, host pi-xps, **startup level 3** (after
`RaspberryButton/1` and `SEAWaterflowmeter/3`, both at level 2).

Renamed on 30-Aug-2026, together with the device it commands. The two names
used to describe each other's job: the GPIO output was called
`xps/safety/xrayguninterlock` and the interlock proper was called
`xps/safety/interlockXgun`. They are now `switchxraygun` and
`interlockxraygun` — what each one is, then what it is attached to, as the
vacuum devices are named. A third name, `xps/safety/waterinterlock`, appeared
in this document and in AlarmNotifier's rule and had never existed at all.

Set the properties *before* starting it for the first time: without
`InputDevice` and `OutputDevice` the `init_device` will fail.

| Property             | Value for pi-xps              |
|----------------------|-------------------------------|
| `InputDevice`        | `xps/safety/water`            |
| `InputAttribute`     | `xray` — confirmed, see below |
| `HeartbeatAttribute` | `UpdateCount`                 |
| `OutputDevice`       | `xps/safety/switchxraygun`    |
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
patched `RaspberryButton`: `xps/safety/switchxraygun` has `Pin = 26` and
publishes `PinLevel`, `Active` and `TimeSinceKeepalive`. Its `DeadmanTimeout` is
still unset, which is correct until commissioning step 4.

Requires the refactored `SEAWaterflowmeter` (for the named attribute and for
`UpdateCount`) and the patched `RaspberryButton` (for `Keepalive`).
On `RaspberryButton/1` set `DeadmanTimeout = 10.0`. It must be comfortably
longer than a restart of this server, or restarting the interlock drops the
permissive and someone has to walk over and press the physical reset button.

## Which way round, and whether it commands anything

Two properties say what the server is for. Both are declared rather than
guessed from the other values, because in each case the thing that would be
guessed is also what a mistake looks like.

`Reverse` gives the direction. `False`, the default, is a quantity that must
stay **high** — a cooling flow, a supply pressure: granted above `ThresholdOn`,
withdrawn below `ThresholdOff`, so `ThresholdOff` is the lower of the two.
`True` is a quantity that must stay **low** — a temperature, a chamber
pressure: granted below `ThresholdOn`, withdrawn above `ThresholdOff`, so
`ThresholdOff` is the higher. The direction could have been read off which
threshold is larger, and then a pair typed the wrong way round would silently
invert the interlock instead of being refused at start-up.

`WatchOnly` says the server commands nothing: it reads the input, applies the
same thresholds and hysteresis, and publishes `Permit` and a state for
something else to act on — AlarmNotifier, a synoptic. That is what the
`<instrument>/warn/` domain means, as against `<instrument>/safety/`. An empty
`OutputDevice` is *not* taken to mean it, and either property without the other
is refused at start-up: a `safety/` device whose `OutputDevice` went missing
must fault rather than quietly demote itself to a bystander. That is not
hypothetical — see below.

### The watch that could not grant

`mossbauer/warn/watercompressor` (`AnalogInterlock/2`, pi-mossbauer) was
registered with no `OutputDevice` at all, and until 29-Aug-2026 reported

```
ALARM | No permit: newcompressor = 10.80, must rise above 9.00
```

with the flow at 10.8 l/min, comfortably above the threshold of 9. The reading
was right and the conclusion was nonsense. What happened each cycle: the value
was past `ThresholdOn`, `grant()` ran, `send("On")` could not build a proxy to
the empty device name and set FAULT with a status saying so — and then `cycle()`
fell through to its tail, which unconditionally set ALARM and "must rise above".
The FAULT was overwritten within the same cycle by the code that came after it,
so the real reason was never visible to anybody. `trip()` had always guarded
against exactly this and `grant()` had not.

`grant()` now reports whether it succeeded and `cycle()` stops when it did not,
leaving the FAULT standing. And the configuration that provoked it is now
refused outright at start-up instead of running in that state for weeks.

### The latch that was never read

`leem/safety/interlockP2lens` had `Latching` set, and did not latch. Cut the P2
cooling water and it tripped correctly; restore the water and the permissive
came straight back, with no `Reset`, exactly as if the property said `false`.
Setting it to `false` changed nothing either — the same behaviour both ways,
which is the shape of a value that is not being read at all.

It was not. The database held the string `'True\t'`: the word with a tab behind
it, from a paste into Jive. PyTango 10.0.2 converts a `dtype='bool'` device
property in `_seqStr_2_obj_from_type` with

```python
if tg_type == CmdArgType.DevBoolean:
    return seq[0].lower() == "true"
```

and `"true\t"` is not `"true"`, so the property arrived as `False`. `'False\t'`
arrives as `False` too, which is why both settings behaved identically. Nothing
in the conversion complains; nothing downstream can tell the difference. The
other properties were unharmed, because `float("2.0\t")` and `int("30\t")`
tolerate the whitespace that a string comparison does not.

`Latching` was the one bool here that nothing contradicted. A `WatchOnly` lost
the same way runs into the `OutputDevice` check and a `Reverse` into the
threshold check, and the server refuses to start — by accident rather than by
design, and with the wrong diagnosis in the status. A lost `Latching` just
quietly stops latching.

Since 08-Sep-2026 `init_device()` reads the three bool properties back from the
database as raw strings, before any other validation, and refuses to start if
what it was handed disagrees with what the string plainly means. The status
names the property, quotes the stored value and says what to write instead.
`Latching` is also published as a read-back attribute, so an ATKPanel shows what
the server is actually enforcing.

The trade-off is deliberate and worth knowing: a bool property with a stray tab
now takes the interlock out of service rather than running it in the wrong mode.
The output device's `DeadmanTimeout` is what covers the machine while it is
down, and it drops the lens without raising it again.

Note what this does *not* catch: a `'False\t'` meaning `false` is accepted,
because the value in force and the value intended agree. The string is just as
dirty and will bite whoever next edits it to `true`.

### The disable that never disabled

`leem/warn/turbotemp` watches `leem/vacuum/turboPCH`, a turbo controller that
has no `UpdateCount`, so its heartbeat had to be switched off. The property doc
said an empty string does that, and an empty string was entered in Jive — as
`""`, the two quote characters. That is a non-empty string, so the guard passed
and the server asked its input for an attribute literally named `""`. The error
came back as `attribute "" not found`, indistinguishable from *the name was
blank*: the bug wore its own diagnosis, and cost a day.

Entered as a genuine empty string it fared no better. The database stores `''`
faithfully, but PyTango's `device_property` layer substitutes `default_value`
for an empty value before the server sees it, so the device asked for
`UpdateCount` — 181 consecutive faults on a turbo that does not publish one.
The off switch the code documented could not be written from the database at
all.

Since 10-Sep-2026 the off switch is the **word** `none` (or `-`), which stores
and round-trips intact (see `HeartbeatAttribute` above). Alongside it,
`init_device()` now runs `clean_properties()` over every string property used
as a name or an enumerated value — `HeartbeatAttribute`, `InputDevice`,
`InputAttribute`, `GateDevice`, `GateStates`, `OutputDevice` and the three
command names. Each is stripped; a value wrapped in a matched pair of quotes is
unwrapped and the value actually used is named in a standing status line, so
`""` now reads as *disabled, and here is why your value was changed* rather than
as a mystery attribute. Every status and error message that quotes a property
value or an attribute name now uses `repr()`: `attribute '""'` is legible where
`attribute ""` was not.

## The trip that was the resting state

There are three shapes this server runs in, and they do not fail the same way.

**Permissive** — `leem/safety/interlockP2lens`, the XPS instance, pi-mossbauer.
The server holds a permissive up continuously and sends `Keepalive` to a
`RaspberryButton` deadman every cycle. If it dies, the deadman expires and the
permissive drops. Silence is safe.

**Command-on-trip** — `leem/safety/interlockhv1`, new. The server sends a
one-shot `OutputOff` to `leem/power/hv1` when the doser cooling water goes bad,
and otherwise says nothing. No deadman, nothing in hardware behind it. Silence
is **not** safe.

**Watch-only** — `OutputDevice` empty, `WatchOnly` set. Evaluates, commands
nothing, publishes a verdict for something else to act on.

`interlockhv1` was brought up with no `GateDevice`, and it cannot see hv1. The
lab's resting state is hv1 **off** and the doser water **shut** — the water is
only opened for a run — so the input sits permanently on the unsafe side, which
is the condition the interlock exists to act on. That produced two faults on
two different clocks.

**Every cycle.** With hv1 off and the water shut the device sat in `ALARM`. It
commanded nothing and wrote no `LastTrip*` — the un-granted tail of the poll
only sets the state — but `AlarmNotifier` reads `State` and nothing else, and a
standing `ALARM` is indistinguishable from a live trip. A rule on
`interlockhv1` would have mailed the first evening and every evening after. The
device was unalarmable, which on a safety layer is the whole of the problem.

**Every working day.** The end-of-day sequence is the start-up one reversed:
hv1 `OutputOff` first, then the doser water is closed. The interlock knows
nothing about hv1, so its permissive is still granted when the water closes,
and that transition is a real trip — one `OutputOff` to a supply already off,
`LastTripTime` / `LastTripValue` / `LastTripReason` overwritten with a routine
shutdown so that Tuesday's genuine trip is gone by Wednesday, and with
`Latching = true` a latch that survives to the next morning and blocks the run
until someone runs `Reset`. `Latching` was not usable: it latched every night.

### What the gate fixes

`GateDevice = leem/power/hv1`, `GateStates = ON`. While hv1 is off the gate is
shut, the device is `OFF`, and none of that happens: no `ALARM` to mail on, no
command sent, the `LastTrip*` record left intact, and a latch from a real trip
held rather than joined by a nightly one. When hv1 is switched on the gate
opens and evaluation restarts clean; switch it on with the water still closed
and the interlock trips at once and sends `OutputOff`, which is correct — that
is a real attempt to run the gun with no cooling.

### The display that stayed shut after the gate reopened

Found 11-Sep-2026, testing the gate live on `leem/warn/turbotemp` and
`leem/safety/interlockhv1`. Both can sit granted across a gate cycle — the
turbo stays hot with the gate open, hv1 stays on with the doser water good —
and in that case reopening the gate left `State`/`Status` stuck at `OFF` /
`Gate ... not evaluating` forever, even though the gate device itself had
gone back to `GateStates` and the permit was, underneath, still correctly
held.

The gate condition was never the problem: `gate_open()` re-reads the gate
device's state on every cycle, with no caching. What was missing is that
`cycle()`'s *maintain the permissive* tail — reached whenever the permit is
already granted and stays that way — only sent `KeepaliveCommand` and
returned; it never touched `State`/`Status`, because normally there is
nothing to say: the device was already showing `ON` from the cycle that
granted it. `enter_gated()` (and `serve_bypass()`, ending a bypass is the
same shape) had in the meantime forced `State`/`Status` to something else
entirely, and nothing downstream put them back once the reason for that had
gone away, because the permit itself never changed and so neither `grant()`
nor `trip()` ever ran again to refresh the display.

The fix makes that tail refresh `State`/`Status` to the granted values on
every cycle it runs, the same way the *no permit* tail at the bottom of
`cycle()` already refreshes `ALARM` unconditionally rather than only on a
fresh trip. A `Keepalive` or reassert failure still faults and returns before
that refresh, exactly as before — the same guard `grant()` already had (see
“The status that a later line overwrote”, `docs/DS-architecture.md` section
3) is what stops the granted refresh from overwriting a `FAULT` `send()` just
set.

`tools/test_analoginterlock.py`'s `gate()` drives both shapes — a permit held
across a gate reopen, and one held across a bypass ending — against a stub
gate device, without touching a live chain.

### Shutdown order now means something

With the gate in place the order of the end-of-day steps carries weight. hv1
off, *then* the water closed: the gate shuts before the water moves, the close
is never evaluated, nothing happens — the intended outcome. The reverse order,
water closed while hv1 is still energised, is a genuine trip and a correct one.
The routine the lab already follows is the right one; the gate is what makes
following it matter.

### Nothing here catches this server dying

The permissive shape is covered by the output device's deadman. The
command-on-trip shape is not: if this server stops sweeping, no `OutputOff` is
ever sent and hv1 is unprotected, with nothing to show for it. A process cannot
watch itself, so this cannot be fixed here. It needs an `AlarmNotifier` rule
watching `leem/safety/interlockhv1` — its `State` for `ALARM` / `FAULT`, and
its `UpdateCount` as an `op=edge` rule so that a counter that has stopped
advancing becomes a mail. For `interlockhv1` that rule is part of the
deployment, not an extra.

## Registration on pi-mossbauer

Server `AnalogInterlock/2`, class `AnalogInterlock`, device
`mossbauer/warn/watercompressor`.

| Property         | Value                       |
|------------------|-----------------------------|
| `InputDevice`    | `mossbauer/safety/waterflow` |
| `InputAttribute` | `newcompressor` (l/min)     |
| `WatchOnly`      | `true`                      |
| `ThresholdOn`    | `9`                         |
| `ThresholdOff`   | `8`                         |
| `Latching`       | `true`                      |

`Reverse` stays at its default: the flow must stay high.

`Latching = true` on a watch means a dip below 8 l/min keeps the warning
asserted after the flow recovers, until somebody calls `Reset`. On a compressor
that is usually what is wanted — the point is to learn that it happened — but
it is a choice, and the alarm will not clear by itself.

## Registration for leem/safety/interlockhv1

Class `AnalogInterlock`, device `leem/safety/interlockhv1`, host pi-leem. The
command-on-trip shape: a one-shot `OutputOff` to `leem/power/hv1` when the
doser cooling water fails, gated on hv1 being on.

| Property             | Value                                        |
|----------------------|----------------------------------------------|
| `InputDevice`        | `leem/safety/water`                          |
| `InputAttribute`     | `doser`                                      |
| `HeartbeatAttribute` | `UpdateCount`                                |
| `OutputDevice`       | `leem/power/hv1`                             |
| `OnCommand`          | `OutputOn`                                   |
| `OffCommand`         | `OutputOff`                                  |
| `KeepaliveCommand`   | *(empty — the supply has no deadman)*        |
| `GateDevice`         | `leem/power/hv1`                             |
| `GateStates`         | `ON`                                         |
| `ThresholdOn`        | `1.5`                                        |
| `ThresholdOff`       | `1.0`                                        |
| `Latching`           | `true` — a real trip must be looked at before hv1 comes back |

`GateStates = ON` because `ON` on `leem/power/hv1` means the output is enabled;
adding `OFF` would make the gate meaningless. `KeepaliveCommand` is empty
because the supply implements no deadman — which is exactly why silence is
unsafe for this device and why it needs the `AlarmNotifier` rule described in
_Nothing here catches this server dying_.

## Bypassing the interlock for a day

Some runs use an evaporator with no water cooling and need the interlock out of
the way for a working day. Editing `enabled` in Jive and restarting the server
is not acceptable under a running instrument, and a plain disable switch is
worse — it has to be remembered. The bypass expires on its own.

`BypassFor "<hours> <reason>"` — a scalar string, because ATKPanel will not
render a `DevVarStringArray` command and the generic panel is the only
interface most of the lab opens; this is why `AlarmNotifier` grew `SnoozeFor`
next to `Snooze`. The reason is **mandatory** — the command is rejected without
one. The friction is deliberate: the reason goes into `BypassReason`, into the
record, and into the mail. `Arm` ends the bypass immediately and forces a fresh
evaluation, exactly as reopening the gate does.

While bypassed the device is `DISABLE`, then `STANDBY` for the last
`BypassWarnMinutes`. No trip command is sent, `LastTrip*` is left alone, and
`Keepalive` **keeps going out** where an output deadman needs it — otherwise
the bypass would drop the permissive, which is the exact trip it was meant to
prevent. On `interlockhv1`, which sets no `KeepaliveCommand`, nothing is sent.
`BypassFor` on a watch-only device is refused: it commands nothing, so there is
nothing to bypass, and what silences it is `SnoozeFor` on the `AlarmNotifier`
rule that watches it.

### Renewal is absolute

Renewing is `BypassFor` again on an already-bypassed device — there is no
separate extend command. It sets the remaining time to the new request from
*now*, whatever was left before: `BypassFor "4 ..."` on a bypass with two hours
still to run leaves four, not six. Cumulative renewal would let two distracted
calls add up to an afternoon nobody decided on, and would stop `MaxBypassHours`
bounding anything. Renewals are unlimited — each is a deliberate act with its
own reason and its own mail — and the defence against drift is the record, not
a refusal: `BypassSince` and `BypassRenewals` do not move or reset on renewal,
so a report reads "bypassed since 09:12, 3 renewals", not "4 h left".

### It survives a restart, on purpose

A bypass live when the server stops is restored from the memorized
`BypassState`; the wall-clock expiry is kept, not the remaining duration, so a
restart cannot extend it. This direction is deliberate and worth not reversing
on instinct: the bypass exists because someone chose to run without the
protection, and a Starter restart at 03:00 that silently re-armed would trip
the very experiment the bypass was holding open. The time cap, not the restart,
is what stops a bypass being forgotten. If the stored expiry is already in the
past at start-up the server comes up armed and says so in `Status`.

### The post-trip renewal surprise

If a bypass expires, the interlock trips and switches hv1 off, and the operator
then calls `BypassFor` again a few minutes later, the bypass is reinstated —
but hv1 stays off and the latch stays set. The bypass holds the interlock off;
it does not raise the output. `Status` and the command's return value both say
so, because the natural reading of "I bypassed it and nothing came back" is
that the command failed. Clear it with `Reset` and a manual `OutputOn` once the
bypass is in place.

## Failure modes

| Condition                  | Response                                     |
|----------------------------|----------------------------------------------|
| input past `ThresholdOff`  | de-assert, ALARM                             |
| input unreadable/INVALID   | de-assert after `MaxReadFailures`, FAULT     |
| heartbeat unreadable       | de-assert after `MaxReadFailures`, FAULT     |
| input publisher frozen     | de-assert after `StaleCycles`, ALARM (only if `HeartbeatAttribute` is named) |
| no `HeartbeatAttribute` named (the default) | staleness not checked; every status line says so |
| this server dies (permissive) | keepalives stop, output device's deadman fires |
| this server dies (command-on-trip) | no `OutputOff` is ever sent; only an `AlarmNotifier` rule on `State` and `UpdateCount` catches it |
| output device unreachable  | FAULT; nothing else is possible from here    |
| output command refused     | FAULT, not granted; the status names the command |
| bool property mangled in the database | refused at start-up; the status quotes the string |
| str property quoted or whitespace-padded in the database | stripped and de-quoted at start-up; a status line names the value actually used |
| gate device outside `GateStates` | `OFF`, not evaluating; a latched trip is held |
| gate device unreadable     | evaluated anyway (fail towards acting); the status says the gate could not be read |
| `GateStates` invalid, or set without `GateDevice` | refused at start-up; the status names the value |
| bypass expires unnoticed   | re-arms, evaluates from a clean slate, trips if the condition is still bad |
| `BypassFor` after a trip   | bypass reinstated, but the output stays off and latched; needs `Reset` + a manual on |

The frozen-publisher case is the one neither the cron script nor a naive
port could catch: a dead acquisition thread keeps returning its last good
reading, which is indistinguishable from healthy flow. `UpdateCount` is what
makes it visible — but only on an interlock that names it, which since
10-Sep-2026 is not the default (see `HeartbeatAttribute` above). Where it is
not named, every status line says staleness detection is off.

A heartbeat that is **configured but unreadable** counts as a failure, not as an
absent heartbeat. Pointing `HeartbeatAttribute` at something that does not exist
— an older `SEAWaterflowmeter` without `UpdateCount`, say — therefore faults
loudly instead of leaving the server ON with its staleness detection silently
switched off. To run without it on purpose, set the property to `none` (or `-`).

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
