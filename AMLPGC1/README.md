# AMLPGC1

Tango device server for the **Arun Microelectronics PGC1 Pressure Gauge
Controller**, which runs the ion gauge on the LEEM preparation chamber. It
reads the pressure and switches the ion gauge emission on and off over the
PGC1's RS-232 interface, and — like ElmitecLEEM2k — carries a reconnect thread
and a Keepalive/deadman so it survives a reboot and can be an `AnalogInterlock`
output.

Runs on **pi-leem**, server `AMLPGC1/1`, device `leem/vacuum/gaugePCH`, over a
Prolific PL2303 USB-serial adapter.

## The instrument

The PGC1 (Arun Microelectronics Ltd., Arundel, UK; manual issue 1.31, program
version 2.00 onward; interface manual issue 2, program version 2.20 onward) is
a 1U rack "intelligent" gauge controller. One box drives up to:

- a **Bayard-Alpert ionisation gauge** — thermionic triode, thin axial
  collector, grid biased +, filament (tungsten or iridium). Smooth DC filament
  supply for ~1 % emission control; logarithmic electrometer for a wide, smooth
  dynamic range; selectable 0.1 / 1 / 10 mA emission or `AUTO`; ion-bombardment
  degas up to ~50 W.
- **two Pirani gauges** (thermal conductivity, ~0.5 mbar down to ~1e-3 mbar),
  one of which can interlock the ion gauge.
- a **capacitance manometer** (10 / 100 / 1000 mbar or Torr full scale).
- four mains-rated changeover **relays**, assignable to any gauge or to TSP /
  bakeout control, with trip pressures and hysteresis.

Pressure is shown in mbar, Pa or Torr (a setup choice; the number on the wire
is bare, in the selected display units). An analog recorder output (+0.25 V per
decade) and a leak-detector mode are also provided.

## The RS-232 protocol

**9600 baud, 8 data bits, 1 stop bit, no parity, no handshaking.** Up to eight
PGC1s can share one line; each has an address `'0'`–`'8'` set in its setup menu.

A host command is:

```
'*'  <command char>  <address>  [parameters]  CR LF
```

`<address>` is a digit for one instrument or `'X'` for all (no reply to an
`'X'` command). Numeric parameters go as ASCII scientific strings like
`"9.9E+99,"`; string parameters end in `0`, `13` or `','`.

Every addressed command replies with a **status byte**, an **error byte**, then
— if a report was asked for — the report, a two-byte hex checksum, and `CR-LF`.

| Command sent | Meaning | Server use |
|---|---|---|
| `*S0` | short status report (status, error, relays, then a record per gauge) | `read_Pressure` |
| `*P0` | poll: status + error byte only | `read_Remote` |
| `*C0` | take remote control (**stops emission**) | `SetRemote` |
| `*R0` | release to local control (**stops emission**) | `SetLocal`, `delete_device` |
| `*E0` | reset the error flags | — |
| `*i0<N>` | ion gauge on; `N` = 0:100 µA, 1:1 mA, 2:10 mA, 3:auto | `Start` sends `*i03` |
| `*o0` | ion gauge off | `Stop`, and the deadman |
| `*d0<text>` | write up to 24 chars to the LCD | via `setCommand` |

**Status byte**: bits 3-0 = `0100` (PGC1); **bit 4 = 1 in remote mode**; bits
5-7 fixed. **Error byte**: bit 0 gauge-specific error, bit 1 over-temperature
trip, bit 2 settings lost / restored to factory default, bit 3 temperature
warning, bit 4 auto-emission error, bit 5 host command not accepted, bit 6
always 1. The error byte latches until an `*E` (reset error).

**Short report** — after the status/error/relay/unused bytes, one record per
gauge: `'G'`, gauge type (`'I'` Bayard-Alpert, `'P'` Pirani, `'M'` capacitance
manometer), gauge number, a gauge-status byte (bit 0 operating, bit 1 starting,
bit 3 in degas, …), a gauge-error byte, then **8 bytes of pressure** as a
comma-delimited scientific string, e.g. `"1.3E-07,"`, or spaces if that gauge
is not operating. `read_Pressure` takes the first gauge record's pressure —
the ion gauge — as `float(reply[9:].split(b",")[0])`.

### Local / remote, and the lack of a comms watchdog

The PGC1 powers up in **local** control. `*C` puts it in remote; the front
panel can then still change the display but not start gauges or move setpoints.
**Taking remote control stops emission**, and so does returning it to local
(`*R`). At switch-on, on an embedded-program derangement, or on an external
reset the instrument goes to local with the HV off.

There is **no comms timeout in the instrument**: it stays in remote, with
whatever emission the host last set, until `*R`, a reset, or a power cycle. So
a "keepalive" is not needed to keep it in remote — the deadman here is purely
the `AnalogInterlock`-output pattern (below).

## What the server adds

`init_device` used to do `resp[7]` straight after the `try/except`; an empty
reply (PGC1 off, cable, flaky adapter) raised `IndexError` **outside** the
guard and PyTango aborted the whole server — which is why Astor showed it
*stopped* after the pi-leem reboot rather than FAULT. Fixed, plus:

- **`connect()`** — opens the port, sends `*S0`, sets `ON` / `OFF` from the
  gauge-operating bit, or `FAULT` with a clear status. Never raises.
- **`_Reconnect` thread** — retries `connect()` every `ReconnectPeriod` (10 s)
  while the link is down, so a PGC1 that comes back after a reboot recovers on
  its own, no Init.
- **`Keepalive` command + `DeadmanTimeout` property** (default 0 = disabled).
  Past the timeout with no `Keepalive` and the gauge asserted, the `_Deadman`
  thread does what `Stop` does — `*o0`, ion gauge off — so an `AnalogInterlock`
  process dying drops the gauge HV by default. `Start` arms and refreshes the
  deadman and clears a trip; `Stop` / `SetLocal` disarm it. With
  `DeadmanTimeout = 0` none of this has any effect.
- **`TimeSinceKeepalive` / `DeadmanTripped`** read-only attributes.
- All serial exchanges go through one locked `_cmd()`: the reconnect and
  deadman threads run outside Tango's serialization monitor. `Start` / `Stop`
  now read their reply instead of leaving it in the buffer for the next read
  to trip over.

### The USB adapter

`/dev/ttyUSB*` on pi-leem, a **Prolific PL2303** (`067b:2303`, `bcdDevice
4.00`). After the reboot it came up wedged —

```
pl2303 ttyUSB3: pl2303_set_control_lines - failed: -71
```

— and opening the port returned `OSError(5) EIO`. An unbind/rebind cleared it:

```bash
echo -n 1-1.2.4:1.0 | sudo tee /sys/bus/usb/drivers/pl2303/unbind
echo -n 1-1.2.4:1.0 | sudo tee /sys/bus/usb/drivers/pl2303/bind
```

(the `1-1.2.4:1.0` is the interface, from `udevadm info -n /dev/ttyUSB3`). If
the port will not open, try that before suspecting the instrument.

## Registration

Server `AMLPGC1/1`, class `AMLPGC1`, device `leem/vacuum/gaugePCH`, host
pi-leem.

| Property | Value | Notes |
|---|---|---|
| `SerialPort` | `/dev/serial/by-path/platform-3f980000.usb-usb-0:1.2.4:1.0-port0` | the by-path name is stable across reboots; `/dev/ttyUSBn` is not |
| `ReconnectPeriod` | `10.0` (default) | seconds between reconnect attempts |
| `DeadmanTimeout` | `0.0` (default, disabled) | set only when an `AnalogInterlock` drives `Start`/`Stop`; then > that interlock's restart time |

Set `SerialPort` before the first start. With the instrument off the server now
comes up `FAULT` ("No reply from AMLPGC1 …") and the reconnect thread picks it
up when it is powered and cabled — no Init needed.

## Install

`AMLPGC1` is in the repo `pyproject.toml`. The shared NFS root is read-only
from pi-leem; deploy from the host that serves `/nfs/pi-trixie`:

```bash
sudo git -C /nfs/pi-trixie/opt/tango/SURFMOSS_TangoDS pull
```

An editable install and a `.py`-only change need no re-`pip install`; restart
`AMLPGC1/1` from Astor. Needs `pyserial`.

## Not done / known limits

- **`init_device` does not send `*C0`.** The server reads status without it, but
  `Start` / `Stop` need the PGC1 in remote — call `SetRemote` first, or add
  `*C0` to `connect()`.
- **Only the first gauge record is read.** `read_Pressure` returns the ion
  gauge's pressure; a Pirani or capacitance-manometer pressure would need
  parsing the later records of the short report.
- **Address `0` is hard-coded** in every command. Fine for one instrument on
  the line.
- The deadman's safe action is "ion gauge off". If this box is ever used to
  gate something else, that has to change.
