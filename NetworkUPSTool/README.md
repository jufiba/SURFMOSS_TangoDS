# NetworkUPSTool

A thin, read-only Tango view of one UPS, through **NUT** (Network UPS Tools).
It exposes the four figures worth watching on a synoptic — line/battery status,
load, charge, temperature — and nothing else.

This is the server you want still answering while the mains is misbehaving, so
it is written to assume nothing went right earlier.

## NUT, in one paragraph

NUT is the standard Linux UPS stack: a **driver** talks to the UPS (USB or
serial), **`upsd`** publishes its ~50 variables on TCP 3493, and clients
(`upsmon`, `upsc`, this server via the `PyNUT` client library) read them.
Configuration lives in `/etc/nut/` (`ups.conf`, `upsd.conf`, `upsd.users`).
List the units and their variables with:

```bash
upsc -l                 # unit names
upsc <unit>             # every variable and its value
```

`UPSunitName` is that unit name.

## Attributes

| Attribute | From NUT variable | Notes |
|---|---|---|
| `UpsStatus` | `ups.status` | `"OnLine"` if the flags contain `OL`, `"OnBattery"` if `OB`, otherwise the raw flag string. **This is a contract**: the retired PANIC alarm `LEEM_POWER` tested `UpsStatus == "OnBattery"` and the LEEM synoptic still shows it. |
| `Load` | `ups.load` | percent |
| `Charge` | `battery.charge` | percent |
| `Temperature` | `ups.temperature` | °C; many models never publish it |

A variable the UPS does not publish reads **INVALID**, not an error.

The device **state** comes from the `ups.status` flag set, not one word:
`OB`+`LB` → `ALARM` (on battery, nearly empty), `OB` → `STANDBY` (on battery),
`OL` → `ON`, anything else → `ALARM`. `FAULT` is reserved for this server being
unable to reach `upsd`. `"OL CHRG"` (recharging after a cut) and `"OB LB"` both
have something to say and neither is `FAULT`.

## Robustness

Two failure modes it has been bitten by, both fixed:

- **`upsd` not up at start-up.** An exception escaping `init_device` makes
  PyTango exit the whole process, so the server used to die if it started
  before `upsd`. It now goes `FAULT` with the reason and retries every
  `RETRY_PERIOD` (10 s) from `always_executed_hook` — no operator Init.
- **`upsd` restarted underneath it.** `PyNUT` opens one client and never
  renews it, so a restart of `upsd` left this end with a socket answering
  `BrokenPipeError` for ever — found in exactly that state on 30-Aug-2026:
  state `ON`, four attributes failing, the last real reading hours old. A
  failed fetch now drops the session and reconnects on the spot (`upsd` is
  local, a refused connection costs microseconds).

One fetch of all variables is cached for `CACHE_SECONDS` (0.5 s) and serves a
whole sweep of the four attributes, instead of four round trips for data that
`upsd` refreshes every two seconds.

`PyNUT` takes a timeout argument and ignores it (its `__init__` hard-codes
5 s), so every call is bounded but not by an amount you can set.

## Registration

Server `NetworkUPSTool/1`, class `NetworkUPSTool`, on whichever machine runs
`upsd` for the UPS in question.

| Property | Value |
|---|---|
| `UPSunitName` | the NUT unit name, as `upsc -l` prints it |

## Install

In the repo `pyproject.toml`. Needs `PyNUT` (the Python NUT client;
`python3-nut` on Debian) and a working local NUT install with `upsd` running.
The server decodes whatever `PyNUT` hands back — `python3-nut` returns `bytes`,
the older `python-nut` returned `str` — so it does not care which is installed.

## Not done

- **Read-only.** No `Test`, no `Shutdown`, no writing UPS variables. NUT can do
  those; this server deliberately does not.
- Only four of the ~50 variables are surfaced. `setCommand`-style passthrough
  was not added.
