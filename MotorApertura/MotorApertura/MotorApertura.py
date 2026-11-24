# -*- coding: utf-8 -*-
#
# This file is part of the MotorApertura project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" MotorApertura

Stepper driving the LEEM aperture, through an Arduino Mega 2560 with a
DRV8825 step/dir driver on a USB-serial link. Home-made hardware: this file,
README.md and firmware/MotorApertura/MotorApertura.ino are the specification.

The aperture has four working positions. Those live here, in the
PresetPositions property, rather than in the board: a position that has
drifted is then a number typed into Jive, not a reflash -- and reflashing
means either unplugging the board from the Pi or putting an AVR toolchain
into the shared NFS root that every Pi boots from. The Tango database is
also backed up, where one board's EEPROM is not.

What does live on the board is where the aperture *is*. Opening the serial
port resets the Arduino, so a counter in its RAM would be lost on every
connection; it is kept in EEPROM instead, over a ring of slots so the write
endurance is not a worry (see the sketch). The board is therefore the single
source of truth for the position and this server only asks.

There is no limit switch and no encoder. The position is what the board has
counted since it was last zeroed, so anything that moves the mechanism
without going through here -- a hand on the shaft, a serial terminal -- puts
it out of step with reality, and only Zero() at a known place fixes that.

Failure modes and what this server does about each:

  port missing at start-up   -> FAULT with the reason; the server stays up
                                rather than taking the whole process down
  board does not identify    -> FAULT. Another Arduino on the same USB tree
                                would otherwise be driven as if it were this
                                one
  no reply to a move         -> FAULT; the move may or may not have happened,
                                so the position is marked unknown rather than
                                guessed
  a move while one is running -> refused. The board would queue it in its
                                64-byte serial buffer and run it afterwards,
                                which is not what anyone asking twice means
  asked past MaxStepsPerMove -> refused, with the number named
"""

# PyTango imports
import tango
from tango import DebugIt
from tango.server import run
from tango.server import Device
from tango.server import attribute, command
from tango.server import device_property
from tango import AttrQuality, DispLevel, DevState
from tango import AttrWriteType
# Additional import
# PROTECTED REGION ID(MotorApertura.additionnal_import) ENABLED START #
import os
import sys
import time
import queue
import threading
import serial

# Seconds per step, from the sketch: two 1200 us half-periods. Used only to
# work out how long to wait for the "OK" line, never to decide that a move
# has finished -- the board says that itself.
SECONDS_PER_STEP = 0.0024

# Added to the computed duration before giving up on the reply, to cover the
# serial round trip and a board that is a little slower than the arithmetic.
REPLY_MARGIN = 5.0


class MoveThread(threading.Thread):
    """Runs the moves, so a Tango call never waits for one.

    A move of any size takes seconds -- 2.4 ms a step -- and a client call
    that blocks that long hits the default 3 s Tango timeout and is reported
    as a failure while the aperture is moving perfectly well. So MoveSteps
    hands the work to this thread and returns at once, the state is MOVING
    until the board answers, and Position is served from the last value the
    board gave.

    It also owns the serial port, which is what keeps a Position read from
    landing in the middle of a move's reply.
    """

    def __init__(self, ds):
        threading.Thread.__init__(self, name="MotorApertura-move")
        self.daemon = True
        self.ds = ds

    def run(self):
        ds = self.ds
        while True:
            job = ds.jobs.get()
            if job is None:
                return
            command, steps = job
            try:
                ds.set_state(tango.DevState.MOVING)
                ds.set_status("Moving %+d steps" % steps if steps
                              else "Zeroing")
                reply = ds.exchange(command, abs(steps) * SECONDS_PER_STEP)
                ds.parse_move_reply(reply, steps)
            except Exception as exc:                          # noqa: BLE001
                # Whether the move happened is now unknown, and a position
                # that is quietly wrong is worse than one that admits it.
                ds.position_known = False
                ds.set_state(tango.DevState.FAULT)
                ds.set_status("Move %+d steps failed: %s. The position is no "
                              "longer known; Zero() at a known place to "
                              "recover it." % (steps, exc))
                ds.error_stream("Move %+d steps failed: %s" % (steps, exc))


# PROTECTED REGION END #    //  MotorApertura.additionnal_import

__all__ = ["MotorApertura", "main"]


class MotorApertura(Device):
    """
    Stepper driving the LEEM aperture, through an Arduino with a DRV8825.
    """
    # PROTECTED REGION ID(MotorApertura.class_variable) ENABLED START #
    # These live here because class_variable is the only region inside the
    # class body that this POGO template emits, and so the only one it keeps
    # if the code is ever regenerated from the .xmi.

    def exchange(self, text, extra_wait=0.0):
        """One command, one line of reply. Never called from two threads at
        once: everything that touches the port goes through MoveThread, or
        runs in init_device before it starts."""
        with self.lock:
            self.ser.reset_input_buffer()
            self.ser.write((text + "\n").encode("ascii"))
            # A read without a deadline is how a device server stops
            # answering altogether, so the timeout is set per exchange from
            # how long this particular move should take.
            self.ser.timeout = REPLY_MARGIN + extra_wait
            line = self.ser.readline()
        if not line:
            raise RuntimeError("no reply to %r within %.1f s"
                               % (text, REPLY_MARGIN + extra_wait))
        return line.decode("ascii", "replace").strip()

    def parse_move_reply(self, reply, steps):
        """OK <moved> <position> -- anything else is a failed move."""
        parts = reply.split()
        if len(parts) != 3 or parts[0] != "OK":
            raise RuntimeError("expected 'OK <moved> <position>', got %r"
                               % reply)
        self.position = int(parts[2])
        self.position_known = True
        self.set_state(tango.DevState.ON)
        self.set_status("At %d steps" % self.position)

    def preset_list(self):
        """PresetPositions as a list, or [] if it is not usable.

        A property that is set but the wrong length is refused rather than
        half-used: GoToPreset(3) against a two-entry list should say so, not
        reach for an index that is not there.
        """
        values = list(self.PresetPositions or [])
        return values
    # PROTECTED REGION END #    //  MotorApertura.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str',
        default_value="/dev/serial/by-id/usb-Arduino__www.arduino.cc__0042_75833313633351D02011-if00",
        doc="The by-id path, not /dev/ttyACM0: the ACM number depends on what "
            "else enumerated first and moves when the board is replugged or "
            "the machine reboots, while the by-id name carries this board's "
            "own serial number.",
    )

    Baudrate = device_property(dtype='int', default_value=9600)

    MaxStepsPerMove = device_property(
        dtype='int', default_value=20000,
        doc="A single move larger than this is refused. There is no limit "
            "switch, so a mistyped MoveSteps(200000) would drive the "
            "aperture into its end stop for eight minutes. 20000 steps is "
            "100 turns at the driver's current full-step setting.",
    )

    StepsPerRevolution = device_property(
        dtype='int', default_value=200,
        doc="Informational: nothing here divides by it. 200 is full step on "
            "this motor; keep it in step with the DRV8825's microstep "
            "jumpers if those are ever changed, so the number of steps in a "
            "turn is written down somewhere.",
    )

    PresetPositions = device_property(
        dtype=('int',),
        doc="The aperture's working positions, in steps, in order. Set them "
            "by driving the aperture there with MoveSteps and calling "
            "SavePreset, or by typing the numbers in Jive. Kept here rather "
            "than in the board so that changing one does not mean "
            "reflashing, and so they are covered by the database backup.",
    )

    # ----------
    # Attributes
    # ----------

    Position = attribute(
        dtype='int', label="Position", unit="steps",
        doc="Where the board says the aperture is. INVALID after a failed "
            "move, when it is no longer known.",
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(MotorApertura.init_device) ENABLED START #
        self.ser = None
        self.lock = threading.Lock()
        self.jobs = queue.Queue()
        self.mover = None
        self.position = 0
        self.position_known = False

        # An exception escaping init_device makes PyTango exit the whole
        # process, and the Starter cannot then bring it back. FAULT with the
        # reason instead; OFF would be a lie, it means an instrument that
        # answered and is switched off.
        try:
            self.ser = serial.Serial(self.SerialPort, baudrate=self.Baudrate,
                                     bytesize=8, parity="N", stopbits=1,
                                     timeout=2)
        except Exception as exc:                              # noqa: BLE001
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't open %s: %s" % (self.SerialPort, exc))
            self.error_stream("Can't open %s: %s" % (self.SerialPort, exc))
            return

        # Opening the port resets the Arduino, which then needs a moment
        # before it is listening, and prints its identity line on the way
        # up. Ask anyway rather than relying on catching that banner.
        try:
            identity = ""
            for _attempt in range(10):
                try:
                    identity = self.exchange("I")
                except Exception:                             # noqa: BLE001
                    identity = ""
                if identity.startswith("MotorApertura"):
                    break
                time.sleep(0.5)
            if not identity.startswith("MotorApertura"):
                self.set_state(tango.DevState.FAULT)
                self.set_status("The board on %s did not identify itself as "
                                "MotorApertura: %r. Refusing to drive it."
                                % (self.SerialPort, identity))
                self.error_stream("Bad identity on %s: %r"
                                  % (self.SerialPort, identity))
                return
            self.identity = identity
            reply = self.exchange("?")
            if not reply.startswith("POS "):
                raise RuntimeError("expected 'POS <n>', got %r" % reply)
            self.position = int(reply.split()[1])
            self.position_known = True
        except Exception as exc:                              # noqa: BLE001
            self.set_state(tango.DevState.FAULT)
            self.set_status("No usable answer from %s: %s"
                            % (self.SerialPort, exc))
            self.error_stream("No usable answer from %s: %s"
                              % (self.SerialPort, exc))
            return

        self.mover = MoveThread(self)
        self.mover.start()
        self.set_state(tango.DevState.ON)
        self.set_status("At %d steps (%s)" % (self.position, identity))
        # PROTECTED REGION END #    //  MotorApertura.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(MotorApertura.always_executed_hook) ENABLED START #
        # Nothing to refresh: the state is maintained by MoveThread as moves
        # start and finish, so State is already current when it is read.
        # Polling the board here would put a second talker on the port.
        pass
        # PROTECTED REGION END #    //  MotorApertura.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(MotorApertura.delete_device) ENABLED START #
        if getattr(self, "mover", None) is not None:
            self.jobs.put(None)
            self.mover.join(timeout=5.0)
        if getattr(self, "ser", None) is not None:
            try:
                self.ser.close()
            except Exception:                                 # noqa: BLE001
                pass
        # PROTECTED REGION END #    //  MotorApertura.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Position(self):
        # PROTECTED REGION ID(MotorApertura.Position_read) ENABLED START #
        if not self.position_known:
            # A number that is quietly wrong would be read as a measurement.
            return (self.position, time.time(),
                    tango.AttrQuality.ATTR_INVALID)
        return self.position
        # PROTECTED REGION END #    //  MotorApertura.Position_read

    # --------
    # Commands
    # --------

    @command(dtype_in='int',
             doc_in="steps, signed: positive forward, negative back")
    @DebugIt()
    def MoveSteps(self, argin):
        # PROTECTED REGION ID(MotorApertura.MoveSteps) ENABLED START #
        self.queue_move(int(argin))
        # PROTECTED REGION END #    //  MotorApertura.MoveSteps

    @command(dtype_in='int', doc_in="which preset, counting from 1")
    @DebugIt()
    def GoToPreset(self, argin):
        # PROTECTED REGION ID(MotorApertura.GoToPreset) ENABLED START #
        self.do_gotopreset(argin)
        # PROTECTED REGION END #    //  MotorApertura.GoToPreset

    @command(dtype_in='int',
             doc_in="which preset to overwrite with the position now")
    @DebugIt()
    def SavePreset(self, argin):
        # PROTECTED REGION ID(MotorApertura.SavePreset) ENABLED START #
        self.do_savepreset(argin)
        # PROTECTED REGION END #    //  MotorApertura.SavePreset

    @command()
    @DebugIt()
    def Zero(self):
        # PROTECTED REGION ID(MotorApertura.Zero) ENABLED START #
        # Goes through the queue like a move so it cannot land in the middle
        # of one, and so it waits its turn rather than racing for the port.
        self.queue_move(0)
        # PROTECTED REGION END #    //  MotorApertura.Zero

    # PROTECTED REGION ID(MotorApertura.protected_methods) ENABLED START #
    # The bodies of the commands live here, out of the @DebugIt() wrappers,
    # so they can be driven without a logger -- as do_bypass and do_arm do
    # in AnalogInterlock, and for the same reason: tools/test_motorapertura.py
    # cannot call a decorated command outside a running server.

    def do_gotopreset(self, index):
        presets = self.preset_list()
        index = int(index)
        if not presets:
            raise ValueError("no PresetPositions are set on this device")
        if index < 1 or index > len(presets):
            raise ValueError("preset %d does not exist; there are %d"
                             % (index, len(presets)))
        if not self.position_known:
            raise ValueError(
                "the position is not known, so the distance to preset %d "
                "cannot be worked out. Drive there with MoveSteps and call "
                "Zero(), or SavePreset once it is right." % index)
        self.queue_move(presets[index - 1] - self.position)

    def do_savepreset(self, index):
        """Save where it is now as preset `index`.

        Writes the device property, so it survives a restart and shows up in
        Jive beside the others. The in-memory copy is updated too: a property
        otherwise only takes effect at Init, and GoToPreset must not go on
        using the old number until someone remembers to do that.
        """
        presets = self.preset_list()
        index = int(index)
        if index < 1:
            raise ValueError("presets count from 1")
        if not self.position_known:
            raise ValueError("the position is not known, so there is nothing "
                             "worth saving. Zero() at a known place first.")
        if self.get_state() == tango.DevState.MOVING:
            raise ValueError("still moving; wait for it to stop before "
                             "calling this spot a preset")
        while len(presets) < index:
            presets.append(0)
        presets[index - 1] = self.position
        tango.Database().put_device_property(
            self.get_name(), {"PresetPositions": [str(p) for p in presets]})
        self.PresetPositions = presets
        self.set_status("At %d steps; saved as preset %d"
                        % (self.position, index))

    def queue_move(self, steps):
        """Check what can be checked here, then hand it to MoveThread.

        Refusing in the command, rather than in the thread, is what lets the
        caller see why: a command that returns and then quietly does nothing
        is the failure this whole server is written to avoid.
        """
        if self.ser is None:
            raise ValueError("the serial port is not open; see Status")
        if self.get_state() == tango.DevState.MOVING:
            raise ValueError("already moving. The board would queue a second "
                             "command in its serial buffer and run it "
                             "afterwards, which is not what asking twice "
                             "usually means")
        if steps == 0:
            self.jobs.put(("Z", 0))
            return
        if abs(steps) > self.MaxStepsPerMove:
            raise ValueError("%d steps is more than MaxStepsPerMove (%d). "
                             "There is no limit switch, so a move this long "
                             "is refused rather than driven into the end stop"
                             % (steps, self.MaxStepsPerMove))
        self.jobs.put(("%+d" % steps, steps))
    # PROTECTED REGION END #    //  MotorApertura.protected_methods

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(MotorApertura.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((MotorApertura,), args=args, **kwargs)
    # PROTECTED REGION END #    //  MotorApertura.main


if __name__ == '__main__':
    main()
