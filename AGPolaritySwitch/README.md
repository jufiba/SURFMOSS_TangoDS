# AGPolaritySwitch

Flips the polarity of the high-current (up to 30 A) power supply that feeds the
VSM electromagnet. The hardware is a **home-made relay box with an Arduino** on
a USB-serial link; there is no vendor manual — this file and the Arduino sketch
are the specification.

Runs on **pi-vsm**, server `AGPolaritySwitch/1`, device `vsm/measurement/Polarity`.

## The serial protocol

ASCII, newline-terminated, 8N1 at the `Speed` baud rate (set it to 9600). The
Arduino answers a status query with two lines — the state, then a second line
that this server reads and discards.

| Sent | Reply | |
|---|---|---|
| `*STAT?\n` | `positive` or `negative`, then one more line | read the polarity |
| `*POS\n` | — | relays to positive |
| `*NEG\n` | — | relays to negative |

## Interface

- Property `SerialPort`, `Speed` (baud; no default, use 9600).
- Attribute `Polarity` — `"positive"` / `"negative"`, read straight from `*STAT?`.
- Commands `setPositive`, `SetNegative`, and `sendCommand(str)` (EXPERT
  passthrough — the string is sent verbatim with a `\n` appended, one line read
  back).
- State: `ON` when the polarity reads `positive`, `OFF` otherwise. It is a
  label for which way the relays are thrown, not an on/off.

## Registration

Server `AGPolaritySwitch/1`, device `vsm/measurement/Polarity`, host pi-vsm.

| Property | Value |
|---|---|
| `SerialPort` | `/dev/serial/by-path/platform-3f980000.usb-usb-0:1.1.3:1.0-port0` |
| `Speed` | `9600` |

## Install / not done

In the repo `pyproject.toml`; needs `pyserial`.

- **`init_device` is not hardened.** It uses a bare `except:` and does not set
  `self.ser = None` first, so `delete_device` (`self.ser.close()`) raises
  `AttributeError` if the port never opened. Unlike the newer servers, an
  unreachable box leaves it FAULT but a following Init can still trip on the
  missing attribute.
- No reconnect, no keepalive.
