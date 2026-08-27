# GranvillePhillips350

Pressure from a Granville Phillips 350 ion gauge controller, through its RS-232
interface module. On pi-leem, over a USB-serial adapter and a null modem cable.

**Written from the manual on 27-Aug-2026 and not yet run against the
instrument**, which was disconnected that day. The parsing is exercised against
the real methods over a stub (`tools/gp350_probe.py --self-test`); nothing here
has seen a byte from a 350.

## The protocol

The RS-232 module's command set is small and closed:

| Message  | Answer                        |
|----------|-------------------------------|
| `DS IG`  | pressure, `X.XXE±XX`          |
| `DS IG1` | same, for filament 1 only     |
| `DS IG2` | same, for filament 2 only     |
| `DGS`    | `1` degassing, `0` not        |
| `IG1 ON` / `IG1 OFF` | `OK` or `INVALID` |
| `IG2 ON` / `IG2 OFF` | `OK` or `INVALID` |
| `DG ON` / `DG OFF`   | `OK` or `INVALID` |

Upper-case ASCII, CRLF terminated. Every message gets a reply. On a bad
message the reply is `SYNTAX ERROR`, `OVERRUN ERROR` or `PARITY ERROR` instead.

Two things in it are traps rather than readings:

- **`9.90E+09` is not a pressure.** It is what the 350 answers when no filament
  is on, and for the first few seconds after one is lit. Served as a number it
  would be nonsense; served as `0.0` it would read as perfect vacuum. The
  server reports `ATTR_INVALID` and state OFF.
- **`OK` does not mean it worked.** The manual is explicit that `OK` to
  `IG1 ON` means only that the request reached the electrometer: the tube can
  still fail to light at too high a pressure, or if it is disconnected. Degas
  will not start above 5e-5 Torr. Read `Filament1On` or `DegasOn` afterwards to
  find out what actually happened.

## What cannot be asked, and so is a property

**The byte framing.** DIP switches on the interface board set it, and nothing
in the protocol reports it. Factory defaults are 300 baud, 7 data bits, no
parity, 2 stop bits, and those are this server's defaults, but there is no
reason to expect any particular instrument to still be on them.

**The pressure unit.** A switch on the electrometer module selects it and the
front panel is labelled accordingly. The 350 sends a bare number. `PressureUnit`
is therefore only a label — it is never used to convert anything — and it must
be set to whatever that label says.

| Property       | Default | Notes                                    |
|----------------|---------|------------------------------------------|
| `SerialPort`   | none    | must be set                              |
| `Baudrate`     | 300     | S6-S8; 75 to 9600                        |
| `Bytesize`     | 7       | S3-S5; 7 or 8                            |
| `Parity`       | `N`     | S3-S5; N, E or O                         |
| `Stopbits`     | 2       | S3-S5; 1 or 2                            |
| `PressureUnit` | `Torr`  | label only, read it off the front panel  |
| `Timeout`      | 3.0     | s; generous because 300 baud is slow     |

On pi-leem the port is
`/dev/serial/by-path/platform-3f980000.usb-usb-0:1.1.3:1.0-port0`.

## First connection

Run the probe before registering anything. It is read-only — it sends `DS IG`
and `DGS` and nothing else, so it cannot light a filament or start a degas:

```bash
python3 tools/gp350_probe.py
```

It listens first for unsolicited traffic, then walks all 8 baud rates by 8
framings from the manual's tables and prints the ones that answer, ending with
the property values to set.

What the outcomes mean:

- **A pressure, or `9.90E+09`** — the link works. Set the properties it prints.
  `9.90E+09` is a perfectly good result here: it says the cable and framing are
  right and the gauge is simply off.
- **`SYNTAX ERROR` on `DS IG`** — the bytes are arriving and the framing is
  right, but the message is not being accepted. The manual gives DCD not being
  asserted during transmission as a cause, which on a null modem cable is a
  wiring question. Switches [22], [23] and [24] on the interface board force
  DCD, CTS and DSR true.
- **Unsolicited lines with nothing sent** — switch S1 was off at power-up and
  the module is in talk-only mode, pushing all three displays every five
  seconds. No command/response server can work against that; S1 has to be on.
- **Nothing at all, on any combination** — no bytes are getting through in at
  least one direction. Check the cable and that the 350 is powered. Note that
  `DGS` answers `0` even with no filament on, so a live link should say
  *something*.

## Registration

Server `GranvillePhillips350/1`, class `GranvillePhillips350`, device to be
chosen (`leem/vacuum/iongauge` would match the naming of the others), host
pi-leem.

Set `SerialPort` and the framing properties **before** the first start:
`init_device` asks `DGS` and goes FAULT with the reason if there is no answer,
rather than taking the server down with it.

## Not done

- Never run against the instrument. Everything below the parsing is untested:
  the framing, the cable, DCD, and whether the unit is in talk-only mode.
- `StartFilament1` / `StopFilament1`, the filament 2 pair and
  `DegasStart` / `DegasStop` are implemented from the manual and have never
  been sent. They energise a filament and a degas cycle. Read the pressure
  first and satisfy yourself the link is sane before using them.
