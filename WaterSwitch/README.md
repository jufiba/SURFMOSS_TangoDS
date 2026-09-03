# WaterSwitch

Detects whether cooling water is flowing, from a single flow switch on a
Raspberry Pi GPIO pin. Effectively a `RaspberrySwitch` with everything
hard-wired.

## Interface

- **No properties.** GPIO **21**, internal pull-up, and inverted sense are all
  baked into the code.
- Attribute `WaterFlowing` (bool): `True` when the pin reads **LOW** (switch
  closed = water flowing). Reading it sets the device state `ON` / `OFF` to
  match.

## Notes

- `init_device` is hardened (`GPIO busy` → `FAULT`, not a server crash), and
  sets `ON` once pin 21 is readable.
- `lgpio` on the netbooted Pis cannot create its FIFO in the read-only NFS
  working directory, so the server sets `LG_WD` to a private tmpdir.
- **No instance is registered in the Tango database right now.** If it comes
  back into use, consider registering it as a `RaspberrySwitch` instead
  (`GPIOport = 21`, `PullUPorDOWN = true`, `Sense = false`) so the pin and
  polarity are visible as properties rather than hidden in the source.

## Install

In `pyproject.toml`. Needs `RPi.GPIO` (or `rpi-lgpio`).
