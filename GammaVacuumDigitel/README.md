# GammaVacuumDigitel

Reads a **Gamma Vacuum DIGITEL ion-pump power supply** over its Ethernet
Telnet interface (TCP 23). Confirmed against two models of the family that
share the transport, prompt, framing and command codes:

| Model | reports as | pumps | pressure unit |
|---|---|---|---|
| **SPCe** | `SPC2` | 1 | `MBA` |
| **QPC** | `DIGITEL QPC` | 4 | `MBAR` |

Manuals on the wiki: `IonPump_Gammavacuum_SPCe.pdf`,
`IonPump_Gammavacuum_Digitel.pdf`.

Two instances: `GammaVacuumDigitel/1` → `leem/vacuum/ColumnsIonPump` (host
pi-laser, `leemColumnsIonPump.lab`), `GammaVacuumDigitel/2` →
`xps/vacuum/ionpump` (host pi-xps, `XPSIonPump.lab`).

## The protocol

```
spc <two-digit hex code> [data]         ->   <ADDR> <OK|ER> <CODE> [data] <checksum><CR>
```

The **supply number** (`Supply` property, 1–4) is on every command: the QPC
requires it, the SPCe ignores it. Command codes used: `01` model, `0A`
current, `0B` pressure, `0C` voltage, `1D`/`1E` setpoint thresholds, `61` HV
on/off, plus the supply-status query. `DigitelError` is raised for any failed
exchange; `HVOff` is a subclass for "HV is off" so an idle pump is a *state*,
not a fault (it used to go red in Astor and send an alarm mail that could not
say which).

## Interface

| Property | |
|---|---|
| `IP` | controller hostname/IP (**no default**) |
| `Port` | 23 |
| `Supply` | which pump (1 for a single-pump SPCe) |

| Attribute | |
|---|---|
| `Pressure` | mbar, converted from the controller's unit (`MBA`/`MBAR` = 1, `Torr` = 1.33322, `Pa` = 0.01). An **unknown unit is refused**, not assumed 1.0 |
| `Current`, `Voltage` | A, V |
| `SupplyStatus` | the controller's status string |
| `SetpointOn`, `SetpointOff` | interlock relay thresholds, mbar. `SetpointOff` reads INVALID when it is the `0.1E-10` marker (relay latches on, never releases) |
| `SetpointActive` | relay state; **INVALID on the SPCe**, which does not report it — deriving it from the pressure would be a guess |

With HV off, `Pressure`/`Current`/`Voltage` read INVALID (the controller sends
`0.1E-09` / `0.1E-10` sentinels; an HV-off pump used to report 1e-11 mbar,
i.e. an outstanding vacuum).

## Notes

- **Pacing**: the QPC drops back-to-back commands (24 timeouts in 30 reads
  measured); a 0.2 s minimum gap fixes it. The SPCe tolerates back-to-back and
  just pays the 0.2 s. A full seven-attribute sweep is ~1.4 s.
- Telnet negotiation / banner bytes are discarded on connect.
- Reconnects on a dropped socket.

### State is re-checked in `always_executed_hook`, not only from a read

Found 20-Sep-2026, auditing device servers for the same hole that had
`leem/vacuum/roughingvalve` (`RaspberrySwitch`) and `leem/safety/ups`
(`NetworkUPSTool`) reporting a stale `State` to `AlarmNotifier`, which watches
bare `State()` and never reads an attribute. This server has it too:
`_read_hv_state()` is the only thing that re-derives `ON`/`OFF`/`FAULT` from
a live query of the controller, and it used to run only from `_connect()` and
from the `On()`/`Off()` commands. If the pump tripped off by itself between
one of those and the next client happening to read `Pressure` or `Current`
(whose failure paths also call into the state-setting helpers), `State` kept
showing whatever it last was.

Both registered instances (`leem/vacuum/ColumnsIonPump`, `xps/vacuum/ionpump`)
are in `AlarmNotifier`'s rules with `alarm=ALARM,FAULT,OFF ok=ON` — and both
already happened to have `polled_attr` set on a numeric attribute, for the
unrelated load-reduction reason in `docs/DS-architecture.md` section 2. That
polling was quietly the only thing keeping their alarm honest, exactly the
"a database property nobody associates with the alarm" fragility the other
two fixes above were written to remove — it would have gone silently the day
someone tuned or removed that `polled_attr` for performance reasons alone.

Fixed the same way in spirit, adapted to the cost of this device:
`always_executed_hook` now calls `_read_hv_state()` on every command or
attribute, `State()` included, but rate-limited to once per
`_STATE_POLL_INTERVAL` (2 s) — unlike a GPIO read or a cached NUT fetch, this
is a real Telnet round trip to hardware already documented as intolerant of
being hit too often, so it is not something to do unconditionally on every
single dispatch. **The existing `polled_attr` is no longer needed to keep
`State` honest** and can be removed if its only purpose was that; it may
still be worth keeping if the numeric attribute it polls is watched for its
own sake.

One side effect: `_read_hv_state()` also sets `Status` to a generic
"high voltage on/off" line, which during normal operation now overwrites the
more detailed connect-time status (model name, relay-support note) far more
often than before (every 2 s of activity rather than only on `On()`/`Off()`).
Not a correctness issue — the model/relay note is still shown once, right
after `Init` or a reconnect — but `Status` will look plainer than it used to
while the device is otherwise idle.

Install: in `pyproject.toml`; standard library only (`socket`).
