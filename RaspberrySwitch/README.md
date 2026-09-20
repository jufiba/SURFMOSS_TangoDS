# RaspberrySwitch

Reads one **GPIO input pin** on a Raspberry Pi — a dry contact, a valve
limit switch, an "is that rack powered" sense line.

Two instances: `RaspberrySwitch/1` → `leem/vacuum/roughingvalve` on **pi-uleem**
(GPIO 12), `RaspberrySwitch/2` → `leem/power/xps` on **pi-leem** (GPIO 4).

## Interface

| Property | Meaning |
|---|---|
| `GPIOport` | BCM pin number |
| `PullUPorDOWN` | `true`: internal pull-up. `false`: pull-down |
| `Sense` | `true` (default): a HIGH reading means the switch is "on" (`Switch = True`, state `ON`). `false`: inverted |

| Attribute | |
|---|---|
| `Switch` | boolean, with `Sense` applied |

No commands — it only reads.

## Notes

- `init_device` is hardened: claiming a pin the kernel already holds (a w1-gpio
  overlay took GPIO 4 on pi-leem once) gives `lgpio.error: 'GPIO busy'`, which
  now faults with the reason instead of taking the server down. It sets state
  `ON` once the pin is readable — before, it sat in `UNKNOWN` even when working.
- On the netbooted Pis `lgpio` cannot create its notification FIFO in the
  read-only NFS working directory; the server points `LG_WD` at a private
  tmpdir per process.

### State is read in `always_executed_hook`, not in `read_Switch`

Found 20-Sep-2026, wiring `leem/vacuum/roughingvalve` and `leem/power/xps` into
`AlarmNotifier` rules for the first time. `set_state()` used to live entirely
inside `read_Switch()`, so it only ran when a client read the `Switch`
attribute. `AlarmNotifier` never does that — it watches bare `State()` — so the
state it saw was whatever the last attribute read (by anyone, ever) happened to
leave behind, or just the `ON` `init_device` sets at start-up if nothing had
read `Switch` yet. Confirmed in the database: neither instance had `polled_attr`
set, so nothing was reading `Switch` on a schedule either.

Patched for the moment with `polled_attr` on `Switch` (10 s) so *something*
reads the attribute and the state rides along — it works, but it is fragile:
a database property nobody associates with the alarm, silently gone if anyone
ever removes it for an unrelated reason.

Fixed properly by moving the GPIO read into `always_executed_hook()`, which
Tango calls before *every* command or attribute, `State()`/`Status()`
included. `GPIO.input()` is a syscall, cheap enough to afford on every call.
`read_Switch()` now just returns the value `always_executed_hook` already
computed for this same call, rather than reading the pin a second time.
**The `polled_attr` on `Switch` is no longer needed for this** and can be
removed from the database — it is not doing anything the fix above does not
already do, and removing it saves a little chatter on both instances.

A read failure now also faults cleanly: `always_executed_hook` catches it and
sets `FAULT` with the reason, rather than letting it escape and break every
subsequent call to the device, State included.

## Install

In `pyproject.toml`. Needs `RPi.GPIO` (or `rpi-lgpio`). Set `GPIOport`,
`PullUPorDOWN` and `Sense` per device.
