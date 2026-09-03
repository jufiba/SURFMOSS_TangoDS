# CryoCon32

Reads a **Cryocon Model 32** cryogenic temperature controller on the Mössbauer
transmission cryostat, over RS-232. It **reads and reports** — the only thing
it writes at start-up is the display units (`INPUT A:UNITS K`, `INPUT B:UNITS K`)
so the K the attributes declare is the K the controller answers with.

Manuals on the wiki:
`Temperature_Controller_Cryocon32-temperature_controller.pdf` (Table 4, Loop
#1 Output Summary, is where the heater full-scale figures come from),
`Temperature_sensor_Criocon_S700DS.pdf` (the sensor).

Runs on **pi-mossbauer**, server `CryoCon32/1`, device
`mossbauer/temperature/criostat`. `SerialPort = /dev/ttyS0` by default, 9600.

## The protocol

SCPI-style, `\n`-terminated. `_query` clears the input buffer first so a late
or unread reply cannot shift every reading after it by one.

| Sent | Read as |
|---|---|
| `*IDN?` | must start `Cryocon Model 32` |
| `INPUT? A` / `INPUT? B` | `TemperatureA` / `TemperatureB` (K) |
| `LOOP 1:SETPT?` / `LOOP 1:SETPT <v>` | `SetPoint` (K) |
| `CONTROL?` | device state: `OFF` → `OFF`, else `ON` |
| `LOOP 1:RANGE?` / `LOOP 1:RANGE LOW\|MID\|HI` | `HeaterLevel` (enum LOW/MID/HIGH) |
| `LOOP 1:OUTPWR?` + `LOOP 1:LOAD?` + range | `HeaterPower` (W) |
| `CONTROL ON` / `STOP` | `On` / `Off` commands |

**`HeaterPower`** is the point of interest: the controller reports the output
as a **percentage of the full scale of the selected range**, and the range and
load resistance must be read with it to get watts — HI into 50 Ω is 50 W full
scale, so 45 % is 22.5 W. Reading the percentage alone invites taking it for
watts, or for the HI/MID/LOW setting.

A channel the controller cannot measure answers `-------` (open sensor, out of
range, nothing wired). That reads **INVALID** here, with the reason in the
status — it used to reach clients as
`ValueError: could not convert string to float: b'-------\n'`.

## Interface

- Properties `SerialPort` (`/dev/ttyS0`), `SerialSpeed` (9600).
- Read attributes: `TemperatureA`, `TemperatureB`, `HeaterPower` (W).
- Read-write: `SetPoint` (K), `HeaterLevel` (enum).
- Commands: `On`, `Off`, `SendCmd(str)`, `SendQuery(str)`.

## Notes

- **Hardened.** A controller off or unplugged at start-up is picked up later
  by the `always_executed_hook` retry (every `RETRY_PERIOD` = 10 s) — no Init.
  The device state also follows the control loop being switched on/off at the
  front panel (re-read once a second), which it did not before.
- It no longer sends `LOOP 1:TYPE PID` at start-up — a server restart, Init
  included, used to silently put the loop back into PID. How the cryostat is
  controlled is the operator's decision, not a start-up side effect.
- Per-channel status: A and B write into a shared problem dict so they do not
  overwrite each other's status message every sweep.

Install: in `pyproject.toml`; needs `pyserial`.
