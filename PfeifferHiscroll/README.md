# PfeifferHiscroll

Monitors and controls a **Pfeiffer HiScroll 12** dry scroll pump through the
Pfeiffer Vacuum Protocol on RS-485, doing what the DCU display unit does.

Manuals on the wiki: `RoughingPump_Pfeiffer_HiScroll_12.pdf` (the pump),
`Software_Pfeiffer_Interface_RS32.pdf` (the serial protocol and parameter
list, shared with `PfeifferTC100` and `PfeifferTU400`).

Runs on **pi-uleem**, server `PfeifferHiscroll/1`, device
`leem/vacuum/scrollPump`. 9600 8N1, RS-485 address **002**.

## The protocol

ASCII frames, `CR`-terminated:

```
AAA CC PPP LL <data>  KKK CR
```

`AAA` address, `CC` action (`00` read / query with data `=?`, `10` write),
`PPP` 3-digit parameter number, `LL` data length, `KKK` checksum (sum of the
preceding bytes mod 256, 3 digits). `sendcommand()` checks the terminator,
length, checksum and that the reply is for the parameter asked — any failure
raises `PfeifferError` ("no reading to be had").

| Parameter | Read here as |
|---|---|
| P316 | `Power` (W) |
| P310 | `Current` (÷100 → A) |
| P398 | `ActualSpeed` (rpm) |
| P326 | `TemperatureElectronics` (°C) |
| P346 | `TemperatureMotor` (°C) |
| P324 | `TemperatureFinalStage` (°C) — P316 is the drive *power*, not a temperature; this was fixed |
| P010 | pump on/off (status) |
| P002 | standby |

## Interface

- Property `SerialPort`.
- Attributes: `Power`, `Current`, `ActualSpeed`, `TemperatureElectronics`,
  `TemperatureMotor`, `TemperatureFinalStage` (all read).
- Commands: `Start` (P010←111111), `Stop` (P010←000000), `Standby`
  (P002←111111), `Normal` (P002←000000), `readParameter(str)`,
  `setParameter([param, data])`.

## Notes

`init_device` is hardened — a stale `SerialPort` or a silent pump faults with
the reason instead of taking the server down (the old code passed `read_until`
the pyserial-2 `terminator=` kwarg, which raised `TypeError` on every
exchange). No reconnect thread.

Install: in `pyproject.toml`; needs `pyserial`.
