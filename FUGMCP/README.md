# FUGMCP

Controls a **FUG MCP 140-1250** high-voltage power supply (1250 V, 100 mA)
through its USB digital interface, which speaks **FUG Probus V** — a simple
ASCII command set. On the LEEM these are the sample / mirror HV supplies.

Manual on the wiki: `Fug_MCP_Probus.pdf`.

Three instances on **pi-leem**: `FUGMCP/1` → `leem/power/hv1`, `FUGMCP/2` →
`leem/power/hv2` (`Speed = 115200`), `FUGMCP/3` → `leem/power/hv3`
(`Speed = 115200`).

> `FUGMCP/1` uses the default `Speed` (625000); `/2` and `/3` are set to
> `115200`. Confirm each supply's baud rate — Probus V modules are configurable.

## The protocol

ASCII, `\n`-terminated. Queries end `?`, replies are `<tag>:<value>`.

| Sent | Reply | |
|---|---|---|
| `*IDN?` | `FUG MCP140-1250 …` / `FUG HCP 140-1250 …` | identify |
| `>M0 ?` / `>M1 ?` | `M0:<V>` / `M1:<A>` | measured voltage / current |
| `>S0 ?` / `>S0 <v>` | `S0:<V>` / `E0` | voltage setpoint |
| `>S1 ?` / `>S1 <a>` | `S1:<A>` / `E0` | current setpoint |
| `>BON ?` / `>BON 1` / `>BON 0` | `BON:1`/`BON:0` / `E0` | output on/off |
| `>DVR ?` / `>DIR ?` | `DVR:1` / `DIR:1` | in voltage / current regulation |

`E0` is "command accepted"; anything else on a write faults with the reply
text (decoded with `errors="replace"` — the one message that says what went
wrong must not be lost to a strict decode).

## Interface

- Properties `SerialPort` (`/dev/ttyUSB0`), `Speed` (625000).
- Read attributes: `Voltage`, `Current`, `Power` (= V·I), `CC` (in current
  regulation), `CV` (in voltage regulation), `Identification` (EXPERT).
- Read-write: `SetVoltage`, `SetCurrent`.
- Commands: `OutputOn`, `OutputOff`, `sendCommand(str)` (EXPERT).

## Notes

Hardened `init_device` (identity checked; a supply that answers `*IDN?` then
goes quiet faults with that fact, distinct from an unreachable one). No
reconnect thread. `SetCurrent`'s attribute `max_value` is `100` but the supply
is 100 mA — the value is in A, so anything above 0.1 is out of range in
practice.

Install: in `pyproject.toml`; needs `pyserial`.
