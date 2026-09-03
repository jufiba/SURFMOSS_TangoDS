# PIDController

A generic software PID loop between two Tango attributes: it reads a measured
value from one device, computes a correction with the
[`simple_pid`](https://github.com/m-lundberg/simple-pid) algorithm, and writes
it to another device. No hardware of its own.

On the LEEM it runs the sample-temperature loop and the two doser-power loops
(`leem/control/sample_leem_pid`, `leem/control/doser_pid`,
`leem/control/doser2_pid`), driven from `scripts/LEEMmacros.py`'s `pidRampTo`
and `leemRampTemperatureROI`, which walk `SetPoint` in steps.

## How it works

`StartCtrlLoop` spawns a `ControlThread`:

1. reads the current value of the output attribute and seeds the PID with it
   (`set_auto_mode(True, last_output=...)`) so the first correction is a
   bumpless continuation, not a step;
2. loops: read `InputAttribute` from `InputDS` → `output = pid(input)` →
   write `output` to `OutputAttribute` on `OutputDS`;
3. runs until `StopCtrlLoop` sets the stop flag, then goes `OFF`.

`init_device` builds the two `DeviceProxy`s and goes `FAULT` if either name
does not resolve.

## Properties

| Property | Default | Meaning |
|---|---|---|
| `InputDS` | `leem/power/hv1` | device the measured value is read from |
| `InputAttribute` | `Power` | attribute on `InputDS` to read |
| `OutputDS` | `leem/power/hv1` | device the correction is written to |
| `OutputAttribute` | `SetVoltage` | attribute on `OutputDS` to write |

The defaults are placeholders — both point at the same device.

## Attributes

All `READ_WRITE`, `EXPERT`, memorized (they persist across restarts).

| Attribute | `simple_pid` term |
|---|---|
| `Proportional` | `Kp` |
| `Integral` | `Ki` |
| `Differential` | `Kd` |
| `SetPoint` | the target the loop drives the input to |
| `LoopTime` | `sample_time` — the PID returns its previous output if called again sooner than this |
| `OutputLimit` | clamps the output to `(0, OutputLimit)` — the **lower bound is fixed at 0** |

## Commands

`StartCtrlLoop` / `StopCtrlLoop` — start and stop the control thread. Starting
while already `ON`, or stopping while `OFF`, does nothing.

## Install

In the repo `pyproject.toml`. Needs `simple_pid`.

## Not done / known limits

- **Old POGO 8 template.** This server is still `PyTango.Device_4Impl` +
  `PIDControllerClass`, not `class X(Device)`, and still `import PyTango` — it
  was not converted in the Aug-2026 rename pass, so `tools/check_xmi.py` cannot
  compare its `.xmi` and code. `doc_html/` and `Makefile` are stale POGO
  leftovers; `doc_html/` still describes `InputValue` / `OutputValue` /
  `StartOutputValue` attributes from an earlier revision that the current code
  and `.xmi` no longer have.
- **The control thread has no error handling.** If `InputDS` or `OutputDS`
  throws mid-loop (device restarted, network blip) the thread dies and
  `set_state(OFF)` never runs, so the device is left reporting `ON` with no
  loop running. There is no reconnect.
- **The loop does not sleep.** `simple_pid`'s `sample_time` throttles the
  *maths*, but the input read and output write still run as fast as CORBA
  allows. `LoopTime` limits how often the correction changes, not the traffic.
- No pressure/limit interlock, no anti-windup tuning beyond `simple_pid`'s
  defaults, no readback of the live input or computed output as attributes.
