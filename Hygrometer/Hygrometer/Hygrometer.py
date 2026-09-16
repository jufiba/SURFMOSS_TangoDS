# -*- coding: utf-8 -*-
#
# This file is part of the Hygrometer project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" Hydrometer

DS for reading the data from an Arduino connected to YL-69/YL-38 sensors.
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
# PROTECTED REGION ID(Hygrometer.additionnal_import) ENABLED START #
import os
import sys
import serial
from threading import Thread
import time

class ControlThread(Thread):
    
    def __init__ (self, ds):
        Thread.__init__(self)
        self.ds = ds
 
    def run(self):        
        while(self.ds.running):
            self.ds.ser.write(bytes("read","ascii"))
            self.ds.ser.inWaiting()
            resp=self.ds.ser.readline()
            self.ds.h=float(resp)
            time.sleep(5)
# PROTECTED REGION END #    //  Hygrometer.additionnal_import

__all__ = ["Hygrometer", "main"]


class Hygrometer(Device):
    """
    DS for reading the data from an Arduino connected to YL-69/YL-38 sensors.
    """
    
    # PROTECTED REGION ID(Hygrometer.class_variable) ENABLED START #
    h=0
    running=True
    ser=None

    def close_port(self):
        """Give the adapter back.

        Every failure path in init_device calls this. A FAULTed hygrometer
        used to hold the port open for ever, which is precisely what gets in
        the way of the person re-cabling to find out why it faulted -- on
        16-sep-2026 leem/safety/hygrometer sat in FAULT holding /dev/ttyUSB2
        while the board behind it was being hunted for.
        """
        if (self.ser is not None):
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser=None
    # PROTECTED REGION END #    //  Hygrometer.class_variable

    # -----------------
    # Device Properties
    # -----------------

    SerialPort = device_property(
        dtype='str', default_value="/dev/ttyUSB0"
    )

    Identity = device_property(
        dtype='str', default_value="Flood sensor above XPS",
        doc="The line the board must answer to 'id' before this server will "
            "talk to it, compared with surrounding whitespace and line "
            "endings stripped from both sides. The default is the XPS "
            "board's own banner, which is what this check was written "
            "against; any other board -- the one over the LEEM, say -- "
            "announces itself differently and has to say so here, or it is "
            "rejected as an impostor however well it works. The check itself "
            "is not optional: telling the wrong instrument from the right "
            "one is the whole point of asking, and two devices on one serial "
            "port is a mistake this lab has made twice.",
    )

    # ----------
    # Attributes
    # ----------

    Humidity = attribute(
        dtype='double',
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(Hygrometer.init_device) ENABLED START #
        # The exchange below was already guarded; opening the port was not,
        # and that is the call that fails when the adapter is unplugged.
        self.ser=None
        try:
            self.ser=serial.Serial(self.SerialPort,baudrate=9600,timeout=5.5)
        except (serial.SerialException,ValueError) as e:
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't open %s: %s"%(self.SerialPort,e))
            self.error_stream("Can't open %s: %s"%(self.SerialPort,e))
            return
        resp=b""
        asked=""
        try:
            # 'id' bare is what the XPS board has always been asked, so it
            # stays first and that board's behaviour does not change. The two
            # terminated forms are a fallback for a board whose sketch reads
            # a whole line before parsing -- which a bare 'id' never completes,
            # leaving it silent for ever with nothing to say why.
            for probe in (b"id", b"id\n", b"id\r\n"):
                self.ser.reset_input_buffer()
                self.ser.write(probe)
                resp=self.ser.readline()
                if resp.strip():
                    asked=repr(probe)
                    break
        except Exception as e:
            self.close_port()
            self.set_state(tango.DevState.FAULT)
            self.set_status("Can't connect to Hygrometer on %s: %s"%(self.SerialPort,e))
            self.error_stream("Can't connect to Hygrometer on %s: %s"%(self.SerialPort,e))
            return
        # Stripped on both sides: the board's line ending is its own business,
        # and a trailing space pasted into Jive behind the property must not
        # be the difference between a working flood detector and a FAULT.
        wanted=self.Identity.strip()
        if (resp.decode("ascii","replace").strip()==wanted):
            self.set_status("Connected to Arduino Hygrometer (%s, answered %s)"
                            %(wanted,asked))
            self.debug_stream("Connected to Arduino Hygrometer on %s"%self.SerialPort)
            self.set_state(tango.DevState.ON)
            self.running=True
            ctrlloop = ControlThread(self)
            ctrlloop.start()
        elif not resp.strip():
            # Nothing came back to any of the three forms. Distinct from the
            # wrong board answering: this is silence, and it means the adapter
            # is not wired to the sketch, the sketch is not running, or the
            # board is not the one on this port at all.
            self.close_port()
            self.set_state(tango.DevState.FAULT)
            self.set_status("Nothing answered 'id' on %s, in any of the three "
                            "forms tried. The port is there; the board is not "
                            "talking."%self.SerialPort)
            self.error_stream("Silent board on %s"%self.SerialPort)
        else:
            # An empty line is what a silent board gives, and it used to be
            # announced as "Connected" before failing the comparison.
            self.close_port()
            self.set_state(tango.DevState.FAULT)
            self.set_status("The board on %s answered %r to %s, and Identity "
                            "says this device is %r. If that is the right "
                            "board, put its own line in Identity."
                            %(self.SerialPort,resp,asked,wanted))
            self.error_stream("Unexpected identity on %s: %r"%(self.SerialPort,resp))
        # PROTECTED REGION END #    //  Hygrometer.init_device
    def always_executed_hook(self):
        # PROTECTED REGION ID(Hygrometer.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  Hygrometer.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(Hygrometer.delete_device) ENABLED START #
        # running first: the reading thread is in ser.write/readline, and
        # closing the port under it would raise there rather than here.
        self.running=False
        self.close_port()
        # PROTECTED REGION END #    //  Hygrometer.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_Humidity(self):
        # PROTECTED REGION ID(Hygrometer.Humidity_read) ENABLED START #
        return(self.h)
        # PROTECTED REGION END #    //  Hygrometer.Humidity_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(Hygrometer.main) ENABLED START #
    # pip install -e leaves an absolute path in argv[0], and PyTango 10 uses
    # argv[0] as the server name, which the database registers as the bare name.
    sys.argv[0] = os.path.basename(sys.argv[0])
    return run((Hygrometer,), args=args, **kwargs)
    # PROTECTED REGION END #    //  Hygrometer.main

if __name__ == '__main__':
    main()
