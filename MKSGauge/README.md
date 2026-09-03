# MKSGauge

Pressure from an **MKS PDR900 series** display/controller with a **972B**
dual Pirani / cold-cathode transducer, over RS-232. A very thin reader — it
asks for one number.

Manuals on the wiki: `Gauge_MKS-PDR900-vacuum-gauge-controller-manual.pdf`,
`Gauge_MKS_972B_Dual_Pirani_ColdCathode.pdf`.

Runs on **sputtering.lab**, server `MKSGauge/1`, device
`sputtering/vacuum/gauge`. `Speed = 115200`.

## The protocol

MKS ASCII, `;FF`-terminated:

```
@254PR4?;FF          ->   @253ACK<8-char float>;FF
```

`254` is the broadcast address, the transducer answers as `253`. `PR4` is the
combined pressure reading; `read_Pressure` returns `float(reply[7:15])`.

## Interface

- Properties `SerialPort` (**mandatory**), `Speed` (**mandatory** — 115200
  here; the 972B ships at 9600, so check what it is set to).
- Attribute `Pressure` (mbar).
- Command `sendCommand(str)` — appends `;FF`, returns the raw reply.

## Notes

- `init_device` is hardened (a missing port faults instead of crashing the
  server). But `read_Pressure` still **returns `9999`** when the reply does
  not parse, rather than INVALID quality — a rough edge worth fixing, since
  9999 mbar is a number an alarm could act on.
- No reconnect thread.
- Pressure unit assumed mbar: the 972B can be set to Torr or Pa and the reply
  carries no unit. Confirm the transducer's unit setting matches.

Install: in `pyproject.toml`; needs `pyserial`.
