# HuttingerPFGRF

Controls a **Hüttinger PFG-RF** RF generator (and its matchbox) for magnetron
sputtering, over the Hüttinger binary serial protocol.

Manual on the wiki: `PowerSupply_Huttinger_RF_PFG_600_RF.pdf` (the PFG-RF-600;
the RF-300 shares the command set).

Runs on **sputtering** (`sputtering.labo`), server `HuttingerPFGRF/1`, two
devices: `sputtering/power/magRFmag`, `sputtering/power/magRFnonmag`. 9600 8N1.

## The protocol

5-byte binary frames:

```
struct >BBH  =  address, command byte, uint16 data     +  1-byte XOR checksum
```

`address` is **0 = generator**, **1 = matchbox**. Reply is `>BBHB`; command
byte `0x06` = ACK, `0x15` = NACK. Read codes are `0xCn`/`0xDn`, the matching
write code is `0x4n`/`0x5n` (e.g. `C1` read / `41` write nominal power).

| Code | Generator (addr 0) |
|---|---|
| C1/41 | nominal power (W) |
| C2/42 | nominal DC bias (V) |
| C7/47 | channel |
| CD/4D | regulation mode (1 Power, 2 DCBias, 3 ΔP, 4 RFPeak) |
| D1 | incident power | D2 | DC bias | D4 | reflected power |
| D7/57 | limit mode | D8/58 | nominal RF-peak voltage | D9 | RF-peak voltage |
| CE | control source (1 LOCAL … 3 RS232 … ) |
| 4F | output on (`1`) / off (`0`) |

| Code | Matchbox (addr 1) |
|---|---|
| C5/45 | nominal C_tune | D5 | C_tune | D6 | C_load | C6/46 | nominal C_load |
| CD/4D | matchbox mode (1 MANUAL, 2 AUTO, 3 REMOTE, 4 FREEZE, 5 DCAUTO) |

## Interface

Attributes mirror the codes above (`NominalPower`, `IncidentPower`,
`ReflectedPower`, `DCBias`, `RFPeakVoltage`, `RegulationMode`, `Limit`,
`Control`, `CT`, `CL`, `MathboxMode`, …), read-only for measured values and
read-write EXPERT for the nominal / mode settings. Commands: `On`, `Off`,
`SendCmd([addr, cmdhex, data])` (EXPERT).

## Notes

- `init_device` is hardened (a switched-off generator faults instead of taking
  the server down). No reconnect thread.
- `parse_response` checks the length and the XOR checksum before unpacking.
  It used to call `struct.unpack` on whatever came back, so an empty reply —
  what a silent instrument returns — raised _unpack requires a buffer of 5
  bytes_, naming neither the port nor the command nor the fact that nothing
  had arrived. This generator never showed it, because its cable has always
  worked; the DC one did, on 30-oct-2026, when it was first connected without
  a null-modem adapter. Same code, same defect, and the only difference was
  luck.
- `HuttingerPFGDC` is the DC sibling (PFG-DC1500) — same house protocol,
  different codes. Its README now documents the protocol in more detail than
  this one, including the *wait bit* that tells a query from a write, and the
  control-mode table. Worth reading before touching either driver.

Install: in `pyproject.toml`; needs `pyserial`.
