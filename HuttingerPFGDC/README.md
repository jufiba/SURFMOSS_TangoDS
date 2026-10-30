# HuttingerPFGDC

Driver for the Hüttinger **DC** generators — the PFG-DC 1500 on the sputtering
rig, a 1500 W / 1 kV supply for magnetron growth. Sibling of `HuttingerPFGRF`,
which drives the RF generator on the same machine and speaks the same
protocol.

Registered as `sputtering/power/magDC` on **sputtering**.

## The serial protocol

RS232 at 9600 8N1, five-byte blocks in both directions:

| byte | meaning |
|---|---|
| 0 | address — always `00` for the generator itself |
| 1 | function byte: top bit is the manual's *wait bit*, lower seven the command |
| 2–3 | data, 16-bit unsigned, big-endian |
| 4 | checksum: XOR of the first four bytes |

**The wait bit is what tells a query from a write**, and it is the thing to
understand before touching this driver. A query is its write command with the
top bit set: `4E` writes the control mode, `CE` reads it; `4F` writes the
operating state, `CF` reads it. A write is answered with `ACK` (`06`) or `NAK`
(`15`); a query is answered with the function byte *without* the wait bit and
the value. Verified against the live generator on 30-oct-2026:

```
CE -> 00 4e 0002 4c     control mode = 2 (REALTIME)
CF -> 00 4f 0000 4f     operating state = 0 (off)
4E data 3 -> 00 06 0000 06    ACK
CE -> 00 4e 0003 4d     control mode now 3 (RS232)
```

Control modes (manual, table 8.12, row N): 1=LOCAL, 2=REALTIME, **3=RS232**,
4=REMOTE1, 5=REMOTE2, 6=RS485, 7=PROFIBUS, 8=REMOTE3, 9=REMOTE4. Only RS232
lets this server command anything. The generator answers queries in any mode.

## Start-up asks, it does not command

`init_device` sends **one** `CE` query and reports what it finds. It does not
write. This matters twice over, and both halves were wrong until
30-oct-2026:

- it used to send `4F` with data 0, which **switches the output off**.
  Starting the device server, or an `Init` from Jive, dropped a generator
  somebody might have been using. `HuttingerPFGRF` never did this.
- it used to set the control mode to **4 = REMOTE1**, which is control over
  the I/O connector, not the serial line. The serial line wants 3.

Taking control away from whoever has the front panel is a decision for a
person, so it is now an explicit command: **`SetRemoteControl`**. It writes
mode 3, reads it back, and reports the mode actually in force — a refused
write answers `NAK` and leaves the mode alone, and reporting success there
would be the worst outcome, because every later command would quietly fail.

`delete_device` **does** switch the output off, which is the opposite decision
on purpose: a generator left running with nothing watching it is the dangerous
state, and this supply has no deadman of its own. An `Init` calls
`delete_device` too, so an `Init` drops the output — worth knowing before
using it on a running deposition.

## Failure modes

| | |
|---|---|
| port will not open | `FAULT`, status names the path and the OS error |
| generator silent | `FAULT`, status says how many bytes arrived (zero) |
| short or corrupt reply | `HuttingerError` naming the length or the checksum mismatch |
| control mode not RS232 | `OFF` with a status saying which mode, and that commands will be refused |
| `SetRemoteControl` refused | returns `refused: still <mode>`, status agrees |

Before 30-oct-2026 the first three all surfaced as

```
No usable answer on /dev/serial/...: unpack requires a buffer of 5 bytes
```

because `parse_response` called `struct.unpack` on whatever came back. An
empty reply is what a silent instrument returns, so that was the likely input
rather than the exotic one, and the message named neither the port, nor the
command, nor the fact that nothing had arrived.

## Wiring

**The generator needs a null-modem cable** (TX/RX crossed). The first
connection on 30-oct-2026 was made with a straight cable: nothing arrived in
either direction, every query returned zero bytes, and the server faulted with
the `unpack` message above. A null-modem adapter fixed it immediately. The RF
generator next to it has always had its own, already-proven cable, which is
why that one worked and this one did not.

## Interface

- Property `SerialPort`.
- Attributes mirror the RF driver: nominal/actual power, voltage, current,
  arc counters, regulation and operation mode.
- Commands: `On_with_ramp`, `reset_arc_counter`, `SetRemoteControl`,
  `SendCmd(cmd, data)` (EXPERT, raw protocol access).

`tools/test_huttingerpfgdc.py` covers the handshake and the frame handling
against a stub port, using the frames the real generator returned.

## The RF sibling

`HuttingerPFGRF` had the same `struct.unpack` on an unchecked length and the
same missing checksum test; both were fixed in the same change, covered by
`tools/test_huttingerpfgrf.py`. Its `init_device` needed nothing — it has
always opened with a single `CE` query and commanded nothing, which is what
made the comparison between the two drivers point straight at the problem
here.
