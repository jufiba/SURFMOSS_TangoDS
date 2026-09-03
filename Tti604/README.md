# Tti604

Reads a **Thurlby Thandar (TTi) 604** bench digital multimeter through its
optically-isolated serial link. As the docstring says, "it has a rather
horrible interface".

Manuals on the wiki: `MultimeterITTI1604Manual.pdf`,
`MultimeterITTI1604RemoteControI.pdf`.

> **Model check pending.** The wiki manuals are for the TTi **1604**; the DS
> and the instrument are labelled **604**. To be confirmed — the two share a
> family and probably the protocol.

Runs on **pi-vsm**, server `Tti604/1`, devices `vsm/measurement/DVMlockin` and
`vsm/measurement/DVMsondaHall`; also `Tti604/2` → `leem/measurement/sampleDVM`
on pi-hvleem. 9600, `dsrdtr=True`, RTS held low.

## The protocol

Single-character commands; the meter echoes the command byte back as an ack
(`command_tti` retries up to 5 times waiting for the echo). Readings come as
**10-byte binary frames** decoded through a 7-segment `numbercode` lookup
table into digits, sign, unit and range bits.

| Char | |
|---|---|
| `u` / `v` | start / stop the continuous data dump (logging mode) |
| `g` | toggle the meter output on/off |
| `f` / `i` / `d` / `e` | function: Voltage / Resistance / Current 10 A / Current mA |
| `a` / `b` / `c` | range up / down / auto |
| `l` / `m` | AC / DC |

Device states: `OFF`, `ON` (single reads), `RUNNING` (logging — `fast_read_tti`
parses the stream).

## Interface

- Property `SerialPort` (`/dev/ttyUSB0`).
- Attributes: `Reading` (double — reading it also refreshes `Units`, `Range`,
  `ACDC`, `FunctionInfo`), `Units`, `Range`, `ACDC` (enum), `FunctionInfo`
  (EXPERT), `Mode` (write-only enum: Voltage / Resistance / Current10A /
  CurrentmA).
- Commands: `On`, `Off`, `Run`, `Stop`, `AutoRange`, `IncreaseRange`,
  `DecreaseRange`, `setAC`, `setDC`, `SendCommand(str)` (EXPERT).

## Notes

Not hardened, and it shows:

- `init_device` sets the status to `"Can't connect to AMLPGC1"` / `"Connected
  to AMLPGC1"` — copy-paste from another server; the open is also not guarded,
  so a missing port takes the server down.
- `Stop()` calls `self.set_state(tango.DevEnum.ON)` — a typo that raises.
- The first frames after enabling output are garbage; `read_tti` retries up to
  10 times until `parse_output` succeeds, using a parse failure as the "no
  reading" signal.

Install: in `pyproject.toml`; needs `pyserial`.
