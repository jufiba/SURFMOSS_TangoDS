# ArduinoMotor

Drives the sputtering **sample-stage motor** through an Arduino on a USB-serial
link. Home-made hardware; this file and the Arduino sketch are the spec.

Runs on **sputtering.lab**, server `ArduinoMotor/1`, device `sputtering/motion/sample`.

## The serial protocol

ASCII, `\n`-terminated, 8N1 at 9600. Every query returns one line.

| Sent | Purpose |
|---|---|
| `IDN?` | identity; must start with `Motor Sputtering` |
| `POS?` | current position (integer) → `Position` |
| `STAT?` | free-text status → `Info` |
| `MODO?` | mode string → `Mode` |
| `MOVE <n>` | move `n` steps (relative) |
| `MOVEP <s>` | move to a named/absolute position |
| `CAL` | run the calibration / homing routine |
| `STOP` | stop now |

**Opening the port resets the Arduino**, so `init_device` sends `IDN?` up to
ten times before giving up, and checks the reply begins with `Motor
Sputtering` — a board that opens but does not identify itself is `FAULT`, not
`ON`.

## Interface

- Property `SerialPort` (default `/dev/ttyUSB0`).
- Attributes `Position` (uint), `Info`, `Mode`, `Version` (str, all read live).
- Commands `MoveSteps(uint)`, `MoveToPos(str)`, `Calibrate`, `Stop`.

## Registration

Server `ArduinoMotor/1`, device `sputtering/motion/sample`, host sputtering.lab.
`SerialPort` = the `by-path` name of the Arduino.

## Install / not done

In `pyproject.toml`; needs `pyserial`. `init_device` is hardened (FAULT with
the reason instead of taking the server down; identity checked). No reconnect —
if the Arduino is re-enumerated the device stays FAULT until an Init.
