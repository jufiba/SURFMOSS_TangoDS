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

## The cable

The 350's connector is a **DB-25**, and its control lines matter (manual,
section 4.4):

| Signal | Pin | Direction  |
|--------|-----|------------|
| TxD    | 2   | to computer |
| RxD    | 3   | to 350      |
| RTS    | 4   | to computer |
| CTS    | 5   | to 350      |
| DSR    | 6   | to 350      |
| DCD    | 8   | to 350      |
| DTR    | 20  | to computer |

It transmits on pin 2, so it is wired as a DTE like the computer — hence the
null modem cable. Anything DE-9 in the chain is an adapter, and whether it
carries pins 4, 5, 6, 8 and 20 is exactly the question.

Three of those lines can stop the exchange dead, in two different ways that
both look like silence from this end:

- **DCD is tested as each character arrives**, and the character is ignored
  unless it is true. A false DCD means the 350 never parses anything. If DCD
  drops only part way through a message, what is left does not parse and the
  reply is `SYNTAX ERROR` — which is why that error is a wiring symptom here
  and not a bug in the message.
- **CTS and DSR are tested before each character it sends**, and it waits for
  both before transmitting. A false CTS or DSR means it parsed the message
  perfectly and will never reply.

All three are forced true by switches **[22]**, **[23]** and **[24]** on the
interface board, which is how it ships. With those set, the 350 needs nothing
from this end and a three-wire cable is enough. Check them before suspecting
the cable.

The 350 asserts **DTR** whenever it is powered and never negates it — the
manual calls it a "power on" indication — and on a null modem cable that lands
on the host's DSR. That looked like a way to prove the instrument was on and
the cable wired without the 350 having to answer anything.

**It does not work on this adapter.** Run against the port on pi-leem with
nothing plugged in at all, it reads `CTS=True DSR=True CD=True RI=False`: the
pl2303's inputs float high. True therefore proves nothing. A line reading
*false* still means something is actively pulling it down, so the probe
reports all four, but do not read anything into them being true.

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
