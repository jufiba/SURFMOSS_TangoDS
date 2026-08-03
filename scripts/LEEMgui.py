#!/usr/bin/python
# LEEM Madrid Macros - acquisition GUI
#
# Qt front end for the acquisition macros in LEEMmacros.py. Every acquisition
# runs in a worker thread so the window stays responsive, its printed output is
# streamed into the log box, and Stop unwinds it through the same cleanup path
# as CTRL-C (see leem_checkstop in LEEMmacros).
#
# Launch it with LEEMmacros.gui(), or run this file directly.
#
# Juan de la Figuera juan.delafiguera@gmail.com

import sys
import traceback

from PySide6 import QtCore, QtGui, QtWidgets

import LEEMmacros as M

KEEP="(keep current)"

def _param(name,label,type_,default=None,choices=None,optional=False):
    """ One entry field. optional=True adds the "(keep current)" choice, which
    passes None so the macro leaves the camera setting alone. """
    return dict(name=name,label=label,type=type_,default=default,
                choices=choices,optional=optional)

_EXPOSURES=[100,200,400,500,1000]
_AVERAGES=[0,1,2,4,8]

def _exposure():
    return _param("exp","Exposure (ms)",float,choices=_EXPOSURES,optional=True)

def _average():
    return _param("avg","Average",int,choices=_AVERAGES,optional=True)

# Everything the GUI can launch. stoppable=False greys out Stop, so the button
# never claims an acquisition can be interrupted when it cannot.
ACQUISITIONS=[
    dict(label="Single image", func="leemSaveSingleImage", stoppable=False,
         params=[_exposure(),_average()]),
    dict(label="Sequence of images", func="leemSequenceImages", stoppable=True,
         params=[_exposure(),_average(),
                 _param("n","Images (-1=forever)",int,default="-1"),
                 _param("delay","Delay (s)",float,default="1.0")]),
    dict(label="IV scan", func="leemIV", stoppable=True,
         params=[_param("E0","E0 (V)",float,default="0.0"),
                 _param("Ef","Ef (V)",float,default="10.0"),
                 _param("dE","dE (V)",float,default="0.5"),
                 _param("exp","Exposure (ms)",float,default="400",choices=_EXPOSURES),
                 _param("avg","Average",int,default="0",choices=_AVERAGES),
                 _param("repeat","Repeat",bool,default=False)]),
    dict(label="IV scan with ROI", func="leemIV_ROI", stoppable=True,
         params=[_param("E0","E0 (V)",float,default="0.0"),
                 _param("Ef","Ef (V)",float,default="10.0"),
                 _param("dE","dE (V)",float,default="0.5"),
                 _param("exp","Exposure (ms)",float,default="400",choices=_EXPOSURES),
                 _param("avg","Average",int,default="0",choices=_AVERAGES),
                 _param("repeat","Repeat",bool,default=False),
                 _param("roi","ROIs",int,default="1",choices=[1,2]),
                 _param("saveImage","Save images",bool,default=False)]),
    dict(label="IV scan with objective", func="leemIVandObj", stoppable=True,
         params=[_param("E0","E0 (V)",float,default="0.0"),
                 _param("Ef","Ef (V)",float,default="10.0"),
                 _param("dE","dE (V)",float,default="0.5"),
                 _param("startObj","Start obj (mA)",float,default="0.0"),
                 _param("endObj","End obj (mA)",float,default="0.0"),
                 _param("exp","Exposure (ms)",float,default="400",choices=_EXPOSURES),
                 _param("avg","Average",int,default="0",choices=_AVERAGES)]),
    dict(label="Temperature ramp with ROI", func="leemRampTemperatureROI", stoppable=True,
         params=[_param("temp","Target T (C)",float,default="0.0"),
                 _param("step","T step (C)",float,default="1.0"),
                 _param("time_step","Time step (s)",float,default="1.0"),
                 _param("exp","Exposure (ms)",float,default="100",choices=_EXPOSURES),
                 _param("avg","Average",int,default="0",choices=_AVERAGES),
                 _param("saveImage","Save images",bool,default=False)]),
    # Ramps only move a PID setpoint, they take no images. pressure_limit is not
    # offered because the pressure check inside pidRampTo is commented out.
    dict(label="Ramp temperature (PID must be on)", func="leemRampTemperatureTo", stoppable=True,
         params=[_param("temp","Target T (C)",float,default="0.0"),
                 _param("temp_step","T step (C)",float,default="1.0"),
                 _param("time_step","Time step (s)",float,default="1.0")]),
    dict(label="Ramp doser 1 power (PID must be on)", func="doser1RampPowerTo", stoppable=True,
         params=[_param("power","Target power (W)",float,default="0.0"),
                 _param("power_step","Power step (W)",float,default="1.0"),
                 _param("time_step","Time step (s)",float,default="1.0")]),
    dict(label="Ramp doser 2 power (PID must be on)", func="doser2RampPowerTo", stoppable=True,
         params=[_param("power","Target power (W)",float,default="0.0"),
                 _param("power_step","Power step (W)",float,default="1.0"),
                 _param("time_step","Time step (s)",float,default="1.0")]),
]


class _Stream:
    """ Stands in for sys.stdout while an acquisition runs, forwarding whole
    lines to the GUI. Qt delivers cross-thread signals via the event loop, so
    the worker never touches a widget itself. """

    def __init__(self,emit):
        self._emit=emit
        self._buf=""

    def write(self,s):
        self._buf+=s
        while "\n" in self._buf:
            line,self._buf=self._buf.split("\n",1)
            self._emit(line)
        return len(s)

    def flush(self):
        if self._buf:
            self._emit(self._buf)
            self._buf=""


class Worker(QtCore.QThread):
    """ Runs one acquisition. """

    line=QtCore.Signal(str)
    done=QtCore.Signal(str)     # empty string, or a traceback

    def __init__(self,func,kwargs,parent=None):
        super().__init__(parent)
        self.func=func
        self.kwargs=kwargs

    def run(self):
        # Cleared here rather than in the Stop handler, so a previous stop can
        # never abort the next acquisition before it starts.
        M.leem_abort.clear()
        error=""
        old=sys.stdout
        sys.stdout=_Stream(self.line.emit)
        try:
            self.func(**self.kwargs)
        except KeyboardInterrupt:
            # Macros with a handler clean up and return normally; this only
            # catches one that re-raises, so the GUI does not treat it as a crash.
            pass
        except Exception:
            error=traceback.format_exc()
        finally:
            try:
                sys.stdout.flush()
            finally:
                sys.stdout=old
        self.done.emit(error)


class AcquisitionRow(QtWidgets.QGroupBox):
    """ One acquisition: its parameter fields and a Run button. """

    run=QtCore.Signal(object)

    def __init__(self,spec,parent=None):
        super().__init__(spec["label"],parent)
        self.spec=spec
        self.widgets={}
        layout=QtWidgets.QHBoxLayout(self)
        for p in spec["params"]:
            layout.addWidget(QtWidgets.QLabel(p["label"]+":"))
            layout.addWidget(self._build(p))
        layout.addStretch(1)
        self.button=QtWidgets.QPushButton("Run")
        self.button.clicked.connect(lambda: self.run.emit(self))
        layout.addWidget(self.button)

    def _build(self,p):
        if p["type"] is bool:
            w=QtWidgets.QCheckBox()
            w.setChecked(bool(p["default"]))
        elif p["choices"]:
            w=QtWidgets.QComboBox()
            w.setEditable(True)          # presets are shortcuts, not a cage
            if p["optional"]:
                w.addItem(KEEP)
            for c in p["choices"]:
                w.addItem(str(c))
            w.setCurrentText(KEEP if p["optional"] else str(p["default"]))
            w.setMinimumWidth(120)
        else:
            w=QtWidgets.QLineEdit(str(p["default"]))
            w.setMaximumWidth(90)
        self.widgets[p["name"]]=w
        return w

    def values(self):
        """ Read the fields. Raises ValueError naming the offending field. """
        out={}
        for p in self.spec["params"]:
            w=self.widgets[p["name"]]
            if p["type"] is bool:
                out[p["name"]]=w.isChecked()
                continue
            text=(w.currentText() if isinstance(w,QtWidgets.QComboBox) else w.text()).strip()
            if p["optional"] and text in (KEEP,""):
                out[p["name"]]=None
                continue
            try:
                out[p["name"]]=p["type"](text)
            except ValueError:
                raise ValueError("%s: cannot read %r as %s"%(p["label"],text,p["type"].__name__))
        return out

    def set_enabled(self,on):
        self.button.setEnabled(on)
        for w in self.widgets.values():
            w.setEnabled(on)


class LEEMWindow(QtWidgets.QWidget):

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle("LEEM acquisition")
        self.worker=None
        layout=QtWidgets.QVBoxLayout(self)

        self.rows=[]
        for spec in ACQUISITIONS:
            row=AcquisitionRow(spec)
            row.run.connect(self.start)
            layout.addWidget(row)
            self.rows.append(row)

        note=QtWidgets.QLabel("ARRES is command line only: run leemARRESset() then "
                              "leemARRESrun() from the console.")
        note.setStyleSheet("color: gray;")
        layout.addWidget(note)

        bar=QtWidgets.QHBoxLayout()
        self.status=QtWidgets.QLabel("Idle")
        bar.addWidget(self.status)
        bar.addStretch(1)
        self.stopButton=QtWidgets.QPushButton("Stop")
        self.stopButton.setEnabled(False)
        self.stopButton.clicked.connect(self.stop)
        bar.addWidget(self.stopButton)
        clear=QtWidgets.QPushButton("Clear log")
        clear.clicked.connect(lambda: self.log.clear())
        bar.addWidget(clear)
        layout.addLayout(bar)

        self.log=QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        self.log.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
        layout.addWidget(self.log,1)
        self.resize(900,600)

    def append(self,text):
        self.log.appendPlainText(text)

    def start(self,row):
        if self.worker is not None:
            return                      # already running; Run buttons are disabled anyway
        try:
            kwargs=row.values()
        except ValueError as e:
            self.append("! %s"%e)
            return
        func=getattr(M,row.spec["func"])
        shown=", ".join("%s=%r"%(k,v) for k,v in kwargs.items())
        self.append(">>> %s(%s)"%(row.spec["func"],shown))
        self.worker=Worker(func,kwargs,self)
        self.worker.line.connect(self.append)
        self.worker.done.connect(self.finished)
        self._running(True,row.spec["stoppable"],row.spec["label"])
        self.worker.start()

    def stop(self):
        self.append("--- stop requested, finishing the current image ---")
        self.stopButton.setEnabled(False)
        M.leem_abort.set()

    def finished(self,error):
        if error:
            self.append(error.rstrip())
        self.worker=None
        self._running(False,False,"")
        self.append("--- finished ---")

    def _running(self,busy,stoppable,label):
        for row in self.rows:
            row.set_enabled(not busy)
        self.stopButton.setEnabled(busy and stoppable)
        self.status.setText(("Running: "+label) if busy else "Idle")

    def closeEvent(self,event):
        if self.worker is not None:
            M.leem_abort.set()
            self.worker.wait(5000)
        super().closeEvent(event)


_window=None

def leem_gui_main():
    """ Show the acquisition window.

    Under a plain python/ipython prompt this blocks until the window is closed.
    Run %gui qt in ipython first to keep the console usable while it is open.
    """
    global _window
    existing=QtWidgets.QApplication.instance()
    app=existing or QtWidgets.QApplication(sys.argv)
    _window=LEEMWindow()
    _window.show()
    if existing is None:
        app.exec()
    return _window


if __name__=="__main__":
    leem_gui_main()
