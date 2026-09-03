# PfeifferTU400

Monitors and controls a **Pfeiffer turbopump through a TU400 / TCP electronic
drive unit**, over the Pfeiffer Vacuum Protocol on RS-485 — the same protocol,
`sendcommand()` and command set as
[`PfeifferHiscroll`](../PfeifferHiscroll/README.md), see there for the frame
format.

Manuals on the wiki: `Turbopump_Pfeiffer_TC400_Operating_Instructions.pdf`
(the TC400 drive electronics — the nearest one held; the TU400 uses the same
Pfeiffer protocol), `Software_Pfeiffer_Interface_RS32.pdf` (protocol +
parameter list).

Runs on **pi-uleem**, server `PfeifferTU400/1`, device `leem/vacuum/turboPCH`.
9600 8N1, RS-485 address **001**.

## Interface

- Property `SerialPort`.
- Attributes: `Power` (P316, W), `Current` (P310, A), `ActualSpeed` (P309,
  rpm), `TemperatureBearing` (P342, °C), `TemperatureMotor` (P346, °C).
- Commands: `Start`, `Stop`, `Standby`, `Normal`, `readParameter(str)`,
  `setParameter([param, data])`, and one that writes **P308** (set rotation
  speed) as `%06d`.

## Notes

`init_device` hardened. No reconnect thread. See `PfeifferTC100` for the
smaller sibling. The exact drive-unit model (TU400 pump vs the marking on the
electronics) is worth confirming against the wiki manual naming.

Install: in `pyproject.toml`; needs `pyserial`.
