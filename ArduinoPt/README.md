# ArduinoPt

Reads one **Pt100 / Pt1000 RTD** through an Arduino with a resistance-to-digital
module. On the sputtering rig it is the sample-plate temperature. Home-made
hardware, no vendor manual.

Runs on **sputtering** (`sputtering.labo`), server `ArduinoPt/1`, device
`sputtering/measurement/temperature`.

## The serial protocol

ASCII, `\n`-terminated, 8N1 at 9600 (open timeout 5 s). One command:

| Sent | Reply | Meaning |
|---|---|---|
| `*PT\n` | a float | temperature, °C |
| | `Fault` | the module is up but no RTD is connected |
| | *(empty line)* | no board answering |

## Interface

- Property `SerialPort` (default `/dev/ttyS0`).
- Attribute `Temperature` (double, °C). On `Fault` the device goes `FAULT` and
  returns `0.0`; on no reply it goes `OFF` and returns `0.0`.

`init_device` tells the three cases apart: an **empty** answer to `*PT` is
treated as "no board" and faults loudly — it used to fall through and read as
"Pt resistor connected".

## Registration

Server `ArduinoPt/1`, device `sputtering/measurement/temperature`, host
sputtering. `SerialPort` = the Arduino's `by-path` name.

> The registered value currently has a **leading space**
> (`' /dev/serial/by-path/…'`). Trim it when you next touch the property.

## Install / not done

In `pyproject.toml`; needs `pyserial`. No reconnect thread; the read path
downgrades to `OFF`/`FAULT` on failure but does not retry the open.
