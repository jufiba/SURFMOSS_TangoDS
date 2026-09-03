# PfeifferTC100

Monitors and controls a **Pfeiffer turbopump through a TC100 electronic drive
unit**, over the Pfeiffer Vacuum Protocol on RS-485 — the same protocol,
`sendcommand()` and command set as
[`PfeifferHiscroll`](../PfeifferHiscroll/README.md), see there for the frame
format.

Manuals on the wiki: `Turbopump_Pfeiffer_TC100_Operating_Instructions.pdf`,
`Software_Pfeiffer_Interface_RS32.pdf` (protocol + parameter list).

Runs on **pi-xps**, server `PfeifferTC100/1`, device `xps/vacuum/turboPCH`.
9600 8N1, RS-485 address **001**.

## Interface

- Property `SerialPort`.
- Attributes: `Power` (P316, W), `Current` (P310, A), `ActualSpeed` (P309,
  rpm). Fewer than HiScroll — no temperatures are exposed.
- Commands: `Start`, `Stop`, `Standby`, `Normal`, `readParameter(str)`,
  `setParameter([param, data])`, and one that writes **P308** (set rotation
  speed) as `%06d`.

## Notes

`init_device` hardened (silent pump → `FAULT`, not a server crash). No
reconnect thread. `PfeifferTU400` is the sibling for the larger TU400 drive
unit — more parameters exposed, otherwise identical.

Install: in `pyproject.toml`; needs `pyserial`.
