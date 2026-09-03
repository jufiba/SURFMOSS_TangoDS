# SRIlockin830

Interface to a **Stanford Research Systems SR830** DSP lock-in amplifier over
RS-232, using the SR830 command set. On the VSM it is the signal lock-in.

Manual on the wiki: `LockInAmplifier_SRI830m.pdf`.

Runs on **pi-vsm**, server `SRIlockin830/1`, device `vsm/measurement/lockin`.
Default port a `by-path` USB-serial name, 9600.

## The protocol

SR830 ASCII, `\r`-terminated. `*IDN?` must answer
`Stanford_Research_Systems,SR830…`.

| Sent | → attribute |
|---|---|
| `OUTP ? 1` / `2` / `3` / `4` | `X` / `Y` / `Mod` (= R) / `Phase` |
| `FREQ ?` | `Frequency` (Hz) |
| `OFLT ?` / `OFLT <n>` | `TimeConstant` — the SR830 **index** 0–19, not seconds |
| `SENS ?` / `SENS <n>` | `Sensitivity` — the SR830 **index** 0–26 |
| `SYNC ?` / `SYNC 0\|1` | `Sync` (sync filter < 200 Hz) |
| `APHS` / `AGAN` / `ARSV` | `AutoPhase` / `AutoGain` / `AutoReserve` (the last two poll `*STB? 1` until not busy) |

## Interface

- Properties `SerialPort`, `Speed` (9600).
- Read attributes: `X`, `Y`, `Mod`, `Phase` (deg — the label says `grad`),
  `Frequency`.
- Read-write, memorized: `TimeConstant`, `Sensitivity` (both as SR830 index
  codes — consult the manual's tables), `Sync`.
- Commands: `AutoPhase`, `AutoGain`, `AutoReserve`, `SendCmd(str)` (EXPERT),
  `SndCmdResponse(str)` (EXPERT).

## Notes

`init_device` faults with a message if `*IDN?` does not identify an SR830, but
is otherwise not hardened (bare `except:` on the open; `delete_device` will
`AttributeError` if the port never opened). No reconnect thread.
`TimeConstant` / `Sensitivity` expose the raw index — a friendlier version
would map to seconds and volts.

Install: in `pyproject.toml`; needs `pyserial`.
