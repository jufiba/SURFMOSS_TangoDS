# LeyboldIG3

Pressure from a **Leybold / Inficon IG3** Bayard-Alpert ion-gauge controller,
over its RS-232 interface. Manual on the wiki:
`Gauge_Inficon_Leybold_IG3.pdf`.

**No instance is registered in the Tango database right now.** Default port
`/dev/ttyUSB0`, 9600 8N1; register with `SerialPort` set to the gauge's
`by-path` name.

## The protocol

Binary framed. A command is

```
STX(0x02)  len  <body ASCII>  checksum(sum(body) mod 256)
```

A reply is `<len byte><len data bytes><1 checksum byte>`; the first data byte
is **0x06 = ACK** or **0x15 = NAK**, the rest is the payload. `response()`
checks length, checksum and frame type and raises `IG3Error` on any of them —
one exception because to the caller they all mean "no reading".

| Body | Purpose |
|---|---|
| `H` | identify; the payload starts `IG3` |
| `S00` | read the pressure (mbar) |
| `S14` | emission on (`1`) / off (`0`) |
| `R09` | start emission |
| `R10` | stop emission |

## Interface

- Properties `SerialPort` (`/dev/ttyUSB0`), `Speed` (9600).
- Attribute `Pressure` (mbar). When emission is off, or on any framing
  failure, it reads **INVALID** — never `0.0`, which on a pressure gauge means
  perfect vacuum and is the most dangerous value to hand an interlock (same
  reasoning as `SEAWaterflowmeter`, `TempSensorDS18B20`).
- Commands `Start`, `Stop`, `SendCommand(str)` — all EXPERT. `SendCommand`
  lets its `DevFailed` through rather than hiding the reason in a string.

## Notes

`init_device` is hardened: everything that can fail becomes `FAULT` with the
reason, so a gauge that is off or unplugged at start-up leaves a device that
says why instead of taking the server down. No reconnect thread, though — a
gauge that comes back needs an Init.

Install: in `pyproject.toml`; needs `pyserial`.
