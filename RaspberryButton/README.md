# RaspberryButton

Drives one **GPIO output pin** on a Raspberry Pi — in practice the coil of a
relay in a permissive chain. It is the "owns the output" half of the
interlock split described in
[`AnalogInterlock/README.md`](../AnalogInterlock/README.md): another process
*decides*, this one *holds* the pin, and a deadman here drops it if the
decider stops talking.

Runs on **pi-xps**, server `RaspberryButton/1`, device
`xps/safety/switchxraygun` (Pin 26), the X-ray gun HV permissive.

## Interface

| Property | Meaning |
|---|---|
| `Pin` | BCM pin number |
| `TrueHigh` | `true`: asserted = HIGH. `false`: asserted = LOW (active-low relay board) |
| `DeadmanTimeout` | seconds without a `Keepalive` after which the pin is dropped. `0` (default) disables the deadman |

| Attribute | |
|---|---|
| `Active` | logical output state, `TrueHigh` applied |
| `PinLevel` | raw electrical level; disagreeing with `Active` means something else reconfigured the pin |
| `TimeSinceKeepalive` | seconds since the last `Keepalive` / `On` |

| Command | |
|---|---|
| `On` | assert the pin; also arms and refreshes the deadman and clears a trip |
| `Off` | de-assert |
| `Keepalive` | refresh the deadman timer only — never asserts; recovery from a trip needs an explicit `On` |

## Behaviour worth knowing

- **The deadman lives here on purpose.** `RPi.GPIO` leaves an output latched at
  its last level when the owning process dies, and a killed process never runs
  `delete_device`. With `DeadmanTimeout` set, the pin falls to its inactive
  level `DeadmanTimeout` seconds after keepalives stop — so a killed
  `AnalogInterlock` drops the permissive by default. State goes `ALARM` on a
  trip; clear it with `On`.
- **`delete_device` leaves the pin driven at its inactive level**, not floating.
  `GPIO.cleanup()` would return it to a pull-less input and the relay box would
  see whatever pull it happens to provide; a driven inactive output is
  unambiguous. A restart of this server therefore does **not** glitch the
  output.
- **`DeadmanTimeout` must exceed this server's own restart time**, or restarting
  it drops the permissive and someone has to press the physical reset.
- On the netbooted Pis the working directory is a read-only NFS root, where
  `lgpio` cannot create its notification FIFO; the server points `LG_WD` at a
  private tmpdir per process to get around it.

## Install

In `pyproject.toml`. Needs `RPi.GPIO` (or `rpi-lgpio` providing the same API).
Set `Pin` and `TrueHigh` before the first start; leave `DeadmanTimeout` at `0`
until commissioning step 4 in the AnalogInterlock README.
