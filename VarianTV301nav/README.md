# VarianTV301nav

Monitors and controls a **Varian / Agilent Turbo-V 301 Navigator** turbopump
(pump with an integrated controller), over the Varian serial "window"
protocol. On the sputtering rig it is the main turbo.

Manual on the wiki: `Turbopump_Varian_TV301_NAVIGATOR_Controller.pdf`.

Runs on **sputtering** (`sputtering.labo`), server `VarianTV301nav/1`, device
`sputtering/vacuum/turbo`. `SerialPort = /dev/ttyS0`, 9600 8N1.

## The protocol

Binary frames:

```
STX(0x02)  ADDR(0x80)  WWW(3 ASCII digits)  0x30=read | 0x31=write  [data]  ETX(0x03)  CRC(2 hex chars, XOR of everything after STX)
```

A read reply carries the value in ASCII from byte 6; a write reply is one byte
(`0x06` ACK / `0x15` NAK).

| Window | Meaning |
|---|---|
| 000 | start / running (`1`/`0`) → `running`, `Start`, `Stop` |
| 008 | interface mode: `0` = serial (full control), `1` = remote (read-only) |
| 120 | set rotation speed (Hz) → `setSpeed`, `SetSpeed` |
| 122 | vent valve (`1` = closed) → `ventValve` |
| 125 | valve operation / error code → `valveOperation`, `errorCode` |
| 200–205 | current (mA), voltage (V), power (W), frequency (Hz), temperature (°C), status code → `current`, `voltage`, `power`, `frecuency`, `temperature`, `turboStatus` |

Status codes: `Stop`, `WaitinIntlk`, `Starting`, `Auto-tuning`, `Braking`,
`Normal`, `Fail`.

## Interface

- Property `serialPort` (**mandatory**).
- Read attributes: `temperature`, `power`, `current`, `voltage`, `frecuency`,
  `turboStatus`, `errorCode` (EXPERT).
- Read-write (EXPERT): `setSpeed`, `running`, `valveOperation`, `ventValve`.
- Commands: `Start`, `Stop`, `SetSpeed(uint16)` (clamped to 150–950).

## Notes

- **`init_device` puts the pump in serial mode (window 008 = 0)**, taking full
  control away from the front panel and the remote connector; `delete_device`
  hands it back to remote read-only. Stopping the server therefore releases
  control.
- Hardened: a switched-off pump faults with the reason instead of taking the
  server down. No reconnect thread.
- Typos left as found in the interface: attribute `frecuency`, status
  `Auto-tunning`.

Install: in `pyproject.toml`; needs `pyserial`.
