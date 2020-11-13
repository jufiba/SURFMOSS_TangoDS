# -*- coding: utf-8 -*-
#
# This file is part of the WebCam project
#
#
#
# Distributed under the terms of the GPL license.
# See LICENSE.txt for more info.

""" WebCam

A simple device server for a webcam conencted through v4l2, using pygame.
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
# PROTECTED REGION ID(WebCam.additionnal_import) ENABLED START #
import pygame
import pygame.camera
# PROTECTED REGION END #    //  WebCam.additionnal_import

__all__ = ["WebCam", "main"]


class WebCam(Device):
    """
    A simple device server for a webcam conencted through v4l2, using pygame.
    """
    __metaclass__ = DeviceMeta
    # PROTECTED REGION ID(WebCam.class_variable) ENABLED START #
    # PROTECTED REGION END #    //  WebCam.class_variable

    # -----------------
    # Device Properties
    # -----------------

    webcamdevice = device_property(
        dtype='str', default_value="/dev/video0"
    )

    height = device_property(
        dtype='uint16', default_value=480
    )

    width = device_property(
        dtype='uint16', default_value=640
    )

    # ----------
    # Attributes
    # ----------

    View = attribute(
        dtype=(('double',),),
        max_dim_x=1024, max_dim_y=1024,
    )

    # ---------------
    # General methods
    # ---------------

    def init_device(self):
        Device.init_device(self)
        # PROTECTED REGION ID(WebCam.init_device) ENABLED START #
        pygame.camera.init()
        #pygame.camera.list_cameras()
        self.cam = pygame.camera.Camera(self.webcamdevice, (self.width, self.height))
        self.cam.start()
        # PROTECTED REGION END #    //  WebCam.init_device

    def always_executed_hook(self):
        # PROTECTED REGION ID(WebCam.always_executed_hook) ENABLED START #
        pass
        # PROTECTED REGION END #    //  WebCam.always_executed_hook

    def delete_device(self):
        # PROTECTED REGION ID(WebCam.delete_device) ENABLED START #
        self.cam.stop()
        # PROTECTED REGION END #    //  WebCam.delete_device

    # ------------------
    # Attributes methods
    # ------------------

    def read_View(self):
        # PROTECTED REGION ID(WebCam.View_read) ENABLED START #
        img = self.cam.get_image()
        imgdata = pygame.surfarray.array3d(img)
        imgfinal=imgdata[:,:,0]*0.298+imgdata[:,:,1]*0.587+imgdata[:,:,2]*0.114
        return imgfinal.swapaxes(0,1)
        # PROTECTED REGION END #    //  WebCam.View_read


    # --------
    # Commands
    # --------

# ----------
# Run server
# ----------


def main(args=None, **kwargs):
    # PROTECTED REGION ID(WebCam.main) ENABLED START #
    return run((WebCam,), args=args, **kwargs)
    # PROTECTED REGION END #    //  WebCam.main

if __name__ == '__main__':
    main()
