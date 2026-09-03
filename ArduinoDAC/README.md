# ArduinoDAC

Sets an analog output through an **Arduino driving a DAC board**. On the
sputtering rig it commands the current of the sample heating supply. Home-made
hardware, no vendor manual.

Runs on **sputtering.lab**, server `ArduinoDAC/1`, device `sputtering/power/heating`.

## What it does

One **write-only** attribute, `Output` (0–30, labelled as a current in A). The
value is turned into raw DAC counts by a linear calibration and sent as one
line:

```
counts = value * (ScaleFactorMax - ScaleFactorMin) / Range + ScaleFactorMin
*DAC <counts>\n            # ASCII, 8N1, 9600 baud
```

There is no readback and no identify handshake — the server opens the port and
declares `ON`.

## Properties

| Property | Default | Meaning |
|---|---|---|
| `SerialPort` | — | the Arduino's serial device |
| `ScaleFactorMin` | `32815` | DAC counts for output = 0 |
| `ScaleFactorMax` | `50350` | DAC counts for output = `Range` |
| `Range` | `30.0` | full-scale value of `Output` |
| `Unit` / `Format` / `Parameter` | `V` / `%4.2f` / `Voltage` | metadata only; not used for anything |

`ScaleFactorMin` / `ScaleFactorMax` **are the calibration** — measure the real
supply output at two settings and fit the line. The defaults are for one
particular supply.

## Registration

Server `ArduinoDAC/1`, device `sputtering/power/heating`, host sputtering.lab.
`SerialPort` = the `by-path` name of the Arduino
(`/dev/serial/by-path/pci-…-usb-…-port0`).

## Install / not done

In `pyproject.toml`; needs `pyserial`.

- Write-only: nothing reads the DAC back, so a lost command is invisible.
- `init_device` is not hardened (bare `except:`), and `delete_device` will
  `AttributeError` if the port never opened.
- No clamp beyond the attribute's `min_value` / `max_value` (0–30); a
  calibration error could still drive the supply hard.
