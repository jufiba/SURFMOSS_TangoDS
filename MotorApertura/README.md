# MotorApertura

Drives the **LEEM aperture** — a stepper on an **Arduino Mega 2560** with a
**DRV8825** step/dir driver, over USB serial. Home-made hardware: this file,
`MotorApertura.py` and `firmware/MotorApertura/MotorApertura.ino` are the
specification, and they have to be kept in step with each other.

The aperture has **four working positions**.

Intended for `pi-laser`, device `leem/motion/apertura`. Not registered in the
Tango database yet.

## The serial protocol

ASCII, `\n`-terminated, 8N1 at 9600. One line of reply per command.

| Sent | Reply | |
|---|---|---|
| `I` | `MotorApertura 1` | identity and protocol version |
| `?` | `POS <n>` | where the board thinks it is |
| `+<n>` | `OK <moved> <position>` | move `n` steps forward |
| `-<n>` | `OK <moved> <position>` | move back; `moved` is negative |
| `Z` | `OK 0 0` | call this spot zero |
| `H` | `ERR nohome` | reserved for a limit switch that is not fitted |
| anything else | `ERR formato` | |

**The reply to a move comes out when the move has finished**, not when it
starts. That is the whole point of the protocol: it is what lets this server
know a move is done, and tell a finished move from one that never happened.

**The unit is steps.** The previous sketch multiplied the number by 200, so
its `+5` meant five turns; here `+5` is five steps. At the driver's current
full-step setting a turn is 200 steps, which is `StepsPerRevolution` — kept
only so the number is written down if the DRV8825's microstep jumpers are
ever changed.

## Where the state lives, and why

| | Where | Why |
|---|---|---|
| The **position** | the Arduino, in EEPROM | Opening the serial port resets the board, so a counter in RAM would be lost on every connection. The board is the single source of truth; this server asks and never guesses. |
| The **four presets** | `PresetPositions`, a device property | A position that has drifted is then a number typed into Jive, not a reflash — and reflashing means unplugging the board from the Pi, or putting an AVR toolchain into the shared NFS root the whole fleet boots from. The Tango database is backed up; one board's EEPROM is not. |

### The EEPROM will not wear out

The ATmega2560 is rated **100,000 write cycles per cell**, which at one write
per move and 100 moves a day is about four years — a real risk, not a
theoretical one. So the records rotate through a ring of **512 slots**, each
holding a sequence number and the position, and the live record is whichever
has the highest sequence:

```
100,000 cycles x 512 slots = 51,200,000 moves
```

Over a thousand years at the same rate. Two things that keep it that way, and
that must not be undone:

- the position is written **once per move, never per step** — a write inside
  the stepping loop would destroy the EEPROM in days;
- `EEPROM.put` is update-based, so bytes that do not change are not written.

## Interface

| Property | |
|---|---|
| `SerialPort` | the **by-id** path, carrying this board's serial number. Not `/dev/ttyACM0`: that number depends on what enumerated first and moves when the board is replugged |
| `Baudrate` | 9600 |
| `MaxStepsPerMove` | 20000. A single move longer than this is refused — there is no limit switch, so a mistyped `MoveSteps(200000)` would drive the aperture into its end stop for eight minutes |
| `StepsPerRevolution` | 200, informational only |
| `PresetPositions` | the working positions, in steps, in order |

| Attribute | |
|---|---|
| `Position` | steps, read-only, from the board. **INVALID** when it is not known |

| Command | |
|---|---|
| `MoveSteps(n)` | signed: positive forward, negative back |
| `GoToPreset(n)` | preset `n`, counting from 1. Works out the distance from where it is |
| `SavePreset(n)` | save the position now as preset `n` — drive the aperture there by eye, then name the spot |
| `Zero()` | call this spot zero |

States: `ON` idle, `MOVING` while the board is stepping, `FAULT` when the
port or the board cannot be talked to.

## Things worth knowing

- **There is no limit switch and no encoder.** The position is what the board
  has counted since it was last zeroed. Anything that moves the mechanism
  without going through here — a hand on the shaft, a serial terminal — puts
  it out of step with reality, and only `Zero()` at a known place fixes it.
  `H` is answered with `ERR nohome` rather than ignored, so the day a switch
  is fitted only that branch of the sketch needs filling in.
- **A move does not block the Tango call.** At 2.4 ms a step even a modest
  move takes seconds, and a client call that blocked that long would hit the
  default 3 s Tango timeout and be reported as a failure while the aperture
  moved perfectly well. `MoveSteps` hands the work to a thread and returns;
  the state is `MOVING` until the board answers.
- **A second move while one is running is refused.** The board would queue it
  in its 64-byte serial buffer and run it afterwards, which is not what
  asking twice usually means.
- **A move that goes unanswered marks the position unknown**, and `Position`
  reads INVALID until `Zero()`. The move may or may not have happened; a
  number that is quietly wrong would be read as a measurement.
- **The board is asked to identify itself at start-up** and a board that
  answers anything but `MotorApertura` is `FAULT`, not driven. There is more
  than one Arduino on this lab's USB trees, and `ArduinoMotor` learned the
  same lesson.
- `SavePreset` **writes a device property**, which nothing else in this
  repository does. The alternative was a memorized attribute holding JSON,
  as `AnalogInterlock` uses for `BypassState`; the property won because it
  shows up in Jive where someone would look for it. It updates the in-memory
  copy too, since a property otherwise only takes effect at `Init`.

## The firmware

Two sketches live under `firmware/`:

- `MotorApertura/MotorApertura.ino` — the one described above.
- `Motor/Motor.ino` — **the original, kept verbatim** as it was found on the
  board in November 2026, before any of this. It took revolutions rather than
  steps, answered before moving and said nothing afterwards, kept no
  position, and had a `delay(1000)` after every move. Kept because the
  repository tracked no `.ino` at all until now, even though `ArduinoMotor`'s
  and `AGPolaritySwitch`'s READMEs both call "the Arduino sketch" part of
  their specification.

Building and flashing, with the board plugged into a machine that has
`arduino-cli` and the `arduino:avr` core:

```bash
arduino-cli compile -b arduino:avr:mega MotorApertura/firmware/MotorApertura
arduino-cli upload  -b arduino:avr:mega -p /dev/ttyACM0 MotorApertura/firmware/MotorApertura
```

⚠️ **Stop the device server first** if it is running: it holds the port open
and the upload will fail. And remember that opening the port at all resets
the board.

To keep a copy of what is on the board before overwriting it:

```bash
avrdude -c wiring -p atmega2560 -P /dev/ttyACM0 -b 115200 -D -U flash:r:before.hex:i
```

## Testing

```bash
python3 tools/test_motorapertura.py
```

Runs against a stub serial port that answers the protocol, so no board is
contacted and nothing moves. It covers the parts that matter: that a move is
believed at the position the **board** reports rather than the one this end
expected, that an unanswered move leaves the position INVALID, that a second
move and an over-long one are refused, that `GoToPreset` works out the right
distance, and that every exchange carries a deadline.

## Install

In `pyproject.toml`. Needs `pyserial`.
