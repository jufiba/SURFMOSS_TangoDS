# Hygrometer

A **flood detector**: an Arduino with YL-69/YL-38 resistive moisture boards,
laid where a water leak would pool. Despite the name it is used as a
safety input, watched by `AlarmNotifier` / a synoptic, not as a real hygrometer.
Home-made hardware; the Arduino sketch is the spec.

Two instances: `Hygrometer/2` → `xps/safety/hygrometer` on **pi-xps**,
`Hygrometer/3` → `leem/safety/hygrometer` on **pi-uleem**.

(The module docstring says "Hydrometer" — a typo; the class and directory are
`Hygrometer`.)

## The serial protocol

ASCII at 9600, open timeout 5.5 s.

| Sent | Reply |
|---|---|
| `id` | an identity line |
| `read` | a float — the moisture reading |

`init_device` sends `id` and checks the reply equals **`"Flood sensor above
XPS\r\n"`** exactly. That string is hard-coded, so every Arduino flashed for
this server — including the uLEEM one — has to report it or the device faults.

On a good identity a `ControlThread` polls `read` every 5 s and stores the
value; `Humidity` just returns the last poll.

## Interface

- Property `SerialPort` (default `/dev/ttyUSB0`).
- Attribute `Humidity` (double) — the last 5-second poll.

## Registration

| Server | Device | Host | `SerialPort` |
|---|---|---|---|
| `Hygrometer/2` | `xps/safety/hygrometer` | pi-xps | `…platform-3f980000.usb-usb-0:1.4:1.0-port0` |
| `Hygrometer/3` | `leem/safety/hygrometer` | pi-uleem | `…platform-3f980000.usb-usb-0:1.1.3:1.0-port0` |

## Install / not done

In `pyproject.toml`; needs `pyserial`. `init_device` is hardened (a silent
board faults instead of reading as "Connected"). But:

- The `ControlThread` has **no error handling** — if the Arduino drops out,
  `Humidity` freezes on its last value with no INVALID quality and no FAULT.
- The identity string should be a property, not a literal, so the two
  instances are not forced to lie about where they are.
- No calibration: `read` returns whatever the sketch computes.
