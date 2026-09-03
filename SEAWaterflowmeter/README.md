# SEAWaterflowmeter

Cooling-water flow rates from **SEA YF-S201** hall-effect flow sensors on
Raspberry Pi GPIO pins. Each sensor emits a pulse train whose frequency is
proportional to flow; the server counts edges and publishes litres/minute per
channel. Up to four channels per instance.

Four instances, all under `<instrument>/safety/`:

| Server | Device | Host | `channels` (BCM) |
|---|---|---|---|
| `SEAWaterflowmeter/1` | `leem/safety/water` | pi-uleem | `26,13,6,5` |
| `SEAWaterflowmeter/2` | `mossbauer/safety/waterflow` | pi-mossbauer | `26` |
| `SEAWaterflowmeter/3` | `xps/safety/water` | pi-xps | `13` |
| `SEAWaterflowmeter/4` | `vsm/safety/water` | pi-vsm | `6` |

`xps/safety/water` is the input to `xps/safety/interlockxraygun` — see
[`AnalogInterlock/README.md`](../AnalogInterlock/README.md).

## How the rate is computed

A rising-edge interrupt increments a per-pin counter. Every `time` seconds a
`ControlThread` snapshots the counters and the monotonic clock and computes

```
rate[i] = (pulses_now - pulses_prev) / (elapsed_measured * calibration)   # l/min
```

from the **difference** between two snapshots over the **measured** elapsed
time — so pulses arriving mid-snapshot are not lost and a late cycle does not
report a spike. `calibration` is the YF-S201 constant (pulses per second per
l/min), default **7.5**.

The loop body is guarded: an exception sends the device to `FAULT` rather than
freezing the last good reading — the failure an interlock reading these
attributes could not otherwise see. `UpdateCount` increments once per cycle;
a client that watches it stop knows the readings are stale even though the
flow attributes still return their last value. `AnalogInterlock` uses it as
its `HeartbeatAttribute`.

## Interface

| Property | Default | Meaning |
|---|---|---|
| `channels` | `6,13` | comma-separated BCM pins, one per sensor (≤ 4) |
| `channelnames` | `turbo,xraygun` | comma-separated names, one per pin |
| `calibration` | `7.5` | pulses·s⁻¹ per l/min |
| `time` | `1.0` | integration period, seconds |

| Attribute | |
|---|---|
| `channel0`…`channel3` | l/min, EXPERT, labelled from `channelnames`. Unconfigured channels read **INVALID**, never `0.0` |
| *one per named channel* | dynamic attribute named after the line (`xraygun`, not `channel0`), so a client that names a line faults loudly if the channel order changes instead of silently watching the wrong pin |
| `UpdateCount` | monotonic per-cycle counter — the staleness signal |

Commands `turnON` / `turnOFF` start and stop the measurement thread.

## Watch out

- **Set `channels` explicitly on every device.** The default used to be
  `6,13,19,26`, which claimed BCM 26 on any instance that did not override it
  and collided with `RaspberryButton` on pi-xps (pin 26). The default is now
  `6,13` but the point stands.
- `lgpio` on the netbooted Pis cannot create its FIFO in the read-only NFS
  working directory; the server sets `LG_WD` to a private tmpdir per process.
- `delete_device` releases only the pins this device claimed, not a bare
  `GPIO.cleanup()` that would drop sibling devices' pins in the same process.

## Install

In `pyproject.toml`. Needs `RPi.GPIO` (or `rpi-lgpio`). Prerequisite for the
`AnalogInterlock` on pi-xps (provides `xray` and `UpdateCount`).
