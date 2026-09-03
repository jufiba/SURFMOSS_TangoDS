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

Install: in `pyproject.toml`; standard library only (`socket`).
