# RaspberrySwitch

Reads one **GPIO input pin** on a Raspberry Pi — a dry contact, a valve
limit switch, an "is that rack powered" sense line.

Two instances: `RaspberrySwitch/1` → `leem/vacuum/roughingvalve` on **pi-uleem**
(GPIO 12), `RaspberrySwitch/2` → `leem/power/xps` on **pi-leem** (GPIO 4).

## Interface

| Property | Meaning |
|---|---|
| `GPIOport` | BCM pin number |
| `PullUPorDOWN` | `true`: internal pull-up. `false`: pull-down |
| `Sense` | `true` (default): a HIGH reading means the switch is "on" (`Switch = True`, state `ON`). `false`: inverted |

| Attribute | |
|---|---|
| `Switch` | boolean, with `Sense` applied. Reading it also sets the device state `ON` / `OFF` to match |

No commands — it only reads.

## Notes

- `init_device` is hardened: claiming a pin the kernel already holds (a w1-gpio
  overlay took GPIO 4 on pi-leem once) gives `lgpio.error: 'GPIO busy'`, which
  now faults with the reason instead of taking the server down. It sets state
  `ON` once the pin is readable — before, it sat in `UNKNOWN` even when working.
- On the netbooted Pis `lgpio` cannot create its notification FIFO in the
  read-only NFS working directory; the server points `LG_WD` at a private
  tmpdir per process.

## Install

In `pyproject.toml`. Needs `RPi.GPIO` (or `rpi-lgpio`). Set `GPIOport`,
`PullUPorDOWN` and `Sense` per device.
