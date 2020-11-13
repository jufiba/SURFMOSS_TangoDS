# -*- coding: utf-8 -*-
#
# This file is part of the V4L2Camera project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" V4L2Camera

A simple driver to obtain frames from a V4L2 Camera.
"""

# PyTango imports
import PyTango
from PyTango import DebugIt
from PyTango.server import run
from PyTango.server import Device, DeviceMeta
from PyTango.server import attribute, command
from PyTango.server import device_property
from PyTango import AttrQuality, DispLevel, DevState
from PyTango import AttrWriteType, PipeWriteType
# Additional import
# PROTECTED REGION ID(V4L2Camera.additionnal_import) ENABLED START #
import cv2
# PROTECTED REGION END #    //  V4L2Camera.additionnal_import

__all__ = ["V4L2Camera", "main"]


class V4L2Camera(Device):
    """
    A simple driver to obtain frames from a V4L2 Camera.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(V4L2Camera.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  V4L2Camera.class_variable

    # -----------------
    # Device Properties
    # -----------------

    CaptureDevice = device_property(
        dtype='str', default_value="/dev/video0"
    )

    # ----------
    # Attributes
    # ----------

    width = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
    )

    Height = attribute(
        dtype='char',
        access=AttrWriteType.READ_WRITE,
    )

    View = attribute(
        dtype=(('float',),),
        max_dim_x=640, max_dim_y=480,
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(V4L2Camera.init_device) ENABLED START #
        self.video_capture = cv2.VideoCapture(0)
        if not self.video_capture.isOpened():
            self.set_status("Cannnot connect to camera")
            self.debug_stream("Cannot connet to camera")
            self.set_state(PyTango.DevState.FAULT)
        self.set_status("Connected to camera")
        self.set_state(PyTango.DevState.ON)
        self.video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        # PROTECTED REGION END #    //  V4L2Camera.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(V4L2Camera.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  V4L2Camera.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(V4L2Camera.delete_device) ENABLED START #
        video_capture.release()
        # PROTECTED REGION END #    //  V4L2Camera.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_width(self):
        # PROTECTED REGION ID(V4L2Camera.width_read) ENABLED START #
        return 0
        # PROTECTED REGION END #    //  V4L2Camera.width_read

    def write_width(self, value):
        # PROTECTED REGION ID(V4L2Camera.width_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  V4L2Camera.width_write

    def read_Height(self):
        # PROTECTED REGION ID(V4L2Camera.Height_read) ENABLED START #
        return 0
        # PROTECTED REGION END #    //  V4L2Camera.Height_read

    def write_Height(self, value):
        # PROTECTED REGION ID(V4L2Camera.Height_write) ENABLED START #
        pass
        # PROTECTED REGION END #    //  V4L2Camera.Height_write

    def read_View(self):
        # PROTECTED REGION ID(V4L2Camera.View_read) ENABLED START #
        ret, frame = self.video_capture.read()
        #img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return gray
        # PROTECTED REGION END #    //  V4L2Camera.View_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(V4L2Camera.main) ENABLED START #
    return run((V4L2Camera,), args=args, **kwargs)
    # PROTECTED REGION END #    //  V4L2Camera.main

if __name__ == '__main__':
    main()
