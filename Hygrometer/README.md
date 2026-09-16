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

`init_device` asks `id` and compares the reply with the **`Identity`**
property, whitespace and line endings stripped from both sides. The default is
`Flood sensor above XPS`, the banner this check was originally written
against, so `Hygrometer/2` needs no database change.

The identity check is not optional and there is no way to switch it off. Two
devices talking down one serial port is a mistake this lab made twice in one
week — `leem/vacuum/gaugeEvap` answering `NAK` to every `PR1` because the
hygrometer was polling the same adapter, and `vsm/measurement/DVMlockin` stuck
in `FAULT` behind the polarity switch. Asking the board who it is, and
refusing to talk to it if the answer is wrong, is what catches that.

`id` is sent three ways, stopping at the first that answers: bare `id`, then
`id\n`, then `id\r\n`. Bare comes first because that is what the XPS board has
always been asked. The fallbacks exist because a sketch that reads a whole
line before parsing never completes a command that carries no terminator, and
stays silent for ever — which looks exactly like a dead board. The status
records which form worked.

The three failures are distinguished, because they send you to different
places:

| Status | What it means |
|---|---|
| `Can't open …` | no adapter at that path |
| `Nothing answered 'id' … The port is there; the board is not talking.` | adapter present, board silent to all three forms: wiring, an unflashed or crashed sketch, or the wrong port |
| `The board on … answered X …, and Identity says this device is Y` | a board that works, under the wrong name — put its own line in `Identity` |

Every failure path **closes the port**. A FAULTed hygrometer used to hold the
adapter for ever, which is precisely what obstructs the person re-cabling to
find out why it faulted.

On a good identity a `ControlThread` polls `read` every 5 s and stores the
value; `Humidity` just returns the last poll.

## Interface

- Properties `SerialPort` (default `/dev/ttyUSB0`), `Identity` (default
  `Flood sensor above XPS`).
- Attribute `Humidity` (double) — the last 5-second poll.

## Registration

| Server | Device | Host | `SerialPort` | `Identity` |
|---|---|---|---|---|
| `Hygrometer/2` | `xps/safety/hygrometer` | pi-xps | `…usb-0:1.4:1.0-port0` | unset → the default |
| `Hygrometer/3` | `leem/safety/hygrometer` | pi-uleem | `…usb-0:1.3:1.0-port0` | **needs the LEEM board's own line** |

`Hygrometer/3` moved from `…1.1.3…` to `…1.3…` on 16-sep-2026: it had been
sharing `1.1.3` with `leem/vacuum/gaugeEvap`, and each was reading the other's
answers. As of that date nothing answers on `1.3` in any of the three forms,
at 9600, 19200, 38400, 57600 or 115200, spontaneously or after a DTR reset
pulse, and the port does not echo — so the board is not talking at all and the
`Identity` for it is still unknown. Read it off the sketch, or off the board
once it speaks.

## Install / not done

In `pyproject.toml`; needs `pyserial`. `init_device` is hardened: a silent
board faults instead of reading as "Connected", the identity is a property,
and the port is given back on every failure. `tools/test_hygrometer.py` covers
the handshake against a stub port. What is still wrong:

- The `ControlThread` has **no error handling**, and this is the serious one.
  `self.ds.h = float(resp)` on a short read raises, the thread dies, and
  nothing notices: `running` stays true, the state stays `ON`, and `Humidity`
  keeps returning the last value it managed to read — for ever, at full
  quality, on a device whose job is to notice a flood. It is the same shape as
  the frozen ion-pump reading on the XPS synoptic on 15-sep-2026, and the
  argument for `UpdateCount` elsewhere in this repo: a counter that stops is
  loud, a reading that stops is silent.
- No calibration: `read` returns whatever the sketch computes.
