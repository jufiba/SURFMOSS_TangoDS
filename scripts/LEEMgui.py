#!/usr/bin/python
# LEEM Madrid Macros - acquisition GUI
#
# Qt front end for the acquisition macros in LEEMmacros.py. Every acquisition
# runs in a worker thread so the window stays responsive, its printed output is
# streamed into the log box, and Stop unwinds it through the same cleanup path
# as CTRL-C (see leem_checkstop in LEEMmacros).
#
# The window is organised as groups (Image(s), IV, Sample temperature ramp,
# Doser ramp). Settings shared by several calls live in their own panel:
# exposure and average at the top, and the scan voltage inside the IV group.
# Each group picks one variant with radio buttons and has its own Run button,
# with a preview line showing the exact call it will make.
#
# Launch it with LEEMmacros.gui(), or run this file directly.
#
# Juan de la Figuera juan.delafiguera@gmail.com

import sys
import traceback

from PyQt6 import QtCore, QtGui, QtWidgets

import LEEMmacros as M

KEEP="(keep current)"

def _param(name,label,type_,default=None,choices=None,optional=False):
    """ One entry field. optional=True adds the "(keep current)" choice, which
    passes None so the macro keeps whatever the camera is set to. """
    return dict(name=name,label=label,type=type_,default=default,
                choices=choices,optional=optional)

_EXPOSURES=[100,200,400,500,1000]
_AVERAGES=[0,1,2,4,8,16,32,64]   # UView goes up to 64; 1 is a sliding average

# Shared by every call that takes images.
IMAGING=[_param("exp","Exposure (ms)",float,choices=_EXPOSURES,optional=True),
         _param("avg","Average (1=sliding)",int,choices=_AVERAGES,optional=True)]

# Shared by the IV variants.
SCANV=[_param("E0","E0 (V)",float,default="0.0"),
       _param("Ef","Ef (V)",float,default="10.0"),
       _param("dE","dE (V)",float,default="0.5")]

def _variant(label,func,params,stoppable=True,imaging=False,scanv=False,setpoint=None):
    """ One runnable call. imaging/scanv say which shared panels feed it;
    setpoint names the PID in LEEMmacros whose current value is shown as the
    read-only ramp start. """
    return dict(label=label,func=func,params=params,stoppable=stoppable,
                imaging=imaging,scanv=scanv,setpoint=setpoint)

GROUPS=[
    dict(label="Image(s)",variants=[
        _variant("Single image","leemSaveSingleImage",[],stoppable=False,imaging=True),
        _variant("Sequence of images","leemSequenceImages",
                 [_param("n","Images (-1=forever)",int,default="-1"),
                  _param("delay","Delay (s)",float,default="1.0")],imaging=True),
    ]),
    dict(label="IV",variants=[
        _variant("Plain IV","leemIV",
                 [_param("repeat","Repeat",bool,default=False)],imaging=True,scanv=True),
        _variant("IV + ROI","leemIV_ROI",
                 [_param("repeat","Repeat",bool,default=False),
                  _param("roi","ROIs",int,default="1",choices=[1,2]),
                  _param("saveImage","Save images",bool,default=False)],
                 imaging=True,scanv=True),
        _variant("IV + objective","leemIVandObj",
                 [_param("startObj","Start obj (mA)",float,default="0.0"),
                  _param("endObj","End obj (mA)",float,default="0.0")],
                 imaging=True,scanv=True),
    ]),
    dict(label="Sample temperature ramp (PID must be on)",variants=[
        _variant("Temperature + ROI (takes images)","leemRampTemperatureROI",
                 [_param("temp","Final T (C)",float,default="0.0"),
                  _param("step","T step (C)",float,default="1.0"),
                  _param("time_step","Time step (s)",float,default="1.0"),
                  _param("saveImage","Save images",bool,default=False)],
                 imaging=True,setpoint="leem_pid"),
        _variant("Temperature (setpoint only)","leemRampTemperatureTo",
                 [_param("temp","Final T (C)",float,default="0.0"),
                  _param("temp_step","T step (C)",float,default="1.0"),
                  _param("time_step","Time step (s)",float,default="1.0")],
                 setpoint="leem_pid"),
    ]),
    dict(label="Doser ramp (PID must be on)",variants=[
        _variant("Doser 1 power","doser1RampPowerTo",
                 [_param("power","Final power (W)",float,default="0.0"),
                  _param("power_step","Power step (W)",float,default="1.0"),
                  _param("time_step","Time step (s)",float,default="1.0")],
                 setpoint="doser1_pid"),
        _variant("Doser 2 power","doser2RampPowerTo",
                 [_param("power","Final power (W)",float,default="0.0"),
                  _param("power_step","Power step (W)",float,default="1.0"),
                  _param("time_step","Time step (s)",float,default="1.0")],
                 setpoint="doser2_pid"),
    ]),
]


def build_widget(p):
    if p["type"] is bool:
        w=QtWidgets.QCheckBox()
        w.setChecked(bool(p["default"]))
    elif p["choices"]:
        w=QtWidgets.QComboBox()
        w.setEditable(True)              # presets are shortcuts, not a cage
        if p["optional"]:
            w.addItem(KEEP)
        for c in p["choices"]:
            w.addItem(str(c))
        w.setCurrentText(KEEP if p["optional"] else str(p["default"]))
        w.setMinimumWidth(120)
    else:
        w=QtWidgets.QLineEdit(str(p["default"]))
        w.setMaximumWidth(90)
    return w

def read_widget(p,w):
    """ Value for one field, or None for "(keep current)". """
    if p["type"] is bool:
        return w.isChecked()
    text=(w.currentText() if isinstance(w,QtWidgets.QComboBox) else w.text()).strip()
    if p["optional"] and text in (KEEP,""):
        return None
    try:
        return p["type"](text)
    except ValueError:
        raise ValueError("%s: cannot read %r as %s"%(p["label"],text,p["type"].__name__))

def on_change(w,slot):
    if isinstance(w,QtWidgets.QCheckBox):
        w.toggled.connect(slot)
    elif isinstance(w,QtWidgets.QComboBox):
        w.currentTextChanged.connect(slot)
    else:
        w.textChanged.connect(slot)


class FieldPanel(QtWidgets.QWidget):
    """ A row of fields built from a param list. """

    def __init__(self,params,parent=None):
        super().__init__(parent)
        self.params=params
        self.widgets={}
        layout=QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        for p in params:
            layout.addWidget(QtWidgets.QLabel(p["label"]+":"))
            w=build_widget(p)
            self.widgets[p["name"]]=w
            layout.addWidget(w)
        layout.addStretch(1)

    def values(self):
        return {p["name"]:read_widget(p,self.widgets[p["name"]]) for p in self.params}

    def connect_all(self,slot):
        for w in self.widgets.values():
            on_change(w,slot)

    def set_enabled(self,on):
        for w in self.widgets.values():
            w.setEnabled(on)


class VariantPage(FieldPanel):
    """ The fields belonging to one variant, plus the read-only ramp start. """

    def __init__(self,variant,parent=None):
        super().__init__(variant["params"],parent)
        self.variant=variant
        self.startField=None
        if variant["setpoint"]:
            self.startField=QtWidgets.QLineEdit()
            self.startField.setReadOnly(True)
            self.startField.setMaximumWidth(90)
            self.startField.setToolTip("Current PID setpoint. The ramp starts here; "
                                       "it is not something the macros let you set.")
            row=self.layout()
            row.insertWidget(0,self.startField)
            row.insertWidget(0,QtWidgets.QLabel("From (setpoint):"))

    def refresh_start(self):
        """ Read the live setpoint. Never raises: the GUI must survive a device
        server being down. """
        if self.startField is None:
            return
        try:
            pid=getattr(M,self.variant["setpoint"])
            self.startField.setText("%.2f"%pid.SetPoint)
        except Exception:
            self.startField.setText("unavailable")


class GroupBox(QtWidgets.QGroupBox):
    """ One group: radio buttons choosing a variant, that variant's fields, a
    preview of the call and a Run button. """

    run=QtCore.pyqtSignal(object)

    def __init__(self,spec,shared,parent=None):
        super().__init__(spec["label"],parent)
        self.spec=spec
        self.shared=shared               # callable -> dict of shared values
        layout=QtWidgets.QVBoxLayout(self)

        self.buttons=QtWidgets.QButtonGroup(self)
        radios=QtWidgets.QHBoxLayout()
        for i,v in enumerate(spec["variants"]):
            b=QtWidgets.QRadioButton(v["label"])
            b.setChecked(i==0)
            self.buttons.addButton(b,i)
            radios.addWidget(b)
        radios.addStretch(1)
        layout.addLayout(radios)

        self.scanv=None
        if any(v["scanv"] for v in spec["variants"]):
            box=QtWidgets.QGroupBox("Scan voltage")
            inner=QtWidgets.QVBoxLayout(box)
            self.scanv=FieldPanel(SCANV)
            inner.addWidget(self.scanv)
            layout.addWidget(box)

        self.stack=QtWidgets.QStackedWidget()
        self.pages=[]
        for v in spec["variants"]:
            page=VariantPage(v)
            self.pages.append(page)
            self.stack.addWidget(page)
        layout.addWidget(self.stack)

        bottom=QtWidgets.QHBoxLayout()
        self.preview=QtWidgets.QLabel("")
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("color: gray;")
        self.preview.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        bottom.addWidget(self.preview,1)
        self.button=QtWidgets.QPushButton("Run")
        self.button.clicked.connect(lambda: self.run.emit(self))
        bottom.addWidget(self.button)
        layout.addLayout(bottom)

        self.buttons.idToggled.connect(self._switch)
        if self.scanv:
            self.scanv.connect_all(self.refresh_preview)
        for page in self.pages:
            page.connect_all(self.refresh_preview)

    def _switch(self,index,checked):
        if checked:
            self.stack.setCurrentIndex(index)
            self.pages[index].refresh_start()
            self.refresh_preview()

    def current(self):
        return self.spec["variants"][self.buttons.checkedId()]

    def values(self):
        """ Shared panels plus this variant's own fields, in call order. """
        v=self.current()
        page=self.pages[self.buttons.checkedId()]
        out={}
        if v["scanv"] and self.scanv:
            out.update(self.scanv.values())
        out.update(page.values())
        if v["imaging"]:
            out.update(self.shared())
        return out

    def refresh_preview(self):
        v=self.current()
        try:
            args=", ".join("%s=%r"%(k,val) for k,val in self.values().items())
            self.preview.setText("%s(%s)"%(v["func"],args))
        except ValueError as e:
            self.preview.setText("%s(...)   %s"%(v["func"],e))

    def refresh_start(self):
        self.pages[self.buttons.checkedId()].refresh_start()

    def set_enabled(self,on):
        self.button.setEnabled(on)
        for b in self.buttons.buttons():
            b.setEnabled(on)
        if self.scanv:
            self.scanv.set_enabled(on)
        for page in self.pages:
            page.set_enabled(on)


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

    line=QtCore.pyqtSignal(str)
    done=QtCore.pyqtSignal(str)     # empty string, or a traceback

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
        except BaseException:
            # BaseException, not Exception: a stray exit()/sys.exit() in a macro
            # raises SystemExit, which escaping run() segfaults the Qt binding's
            # QThread trampoline. Catch it here so it surfaces as a traceback in
            # the log with the buttons re-enabled, like any other crash.
            error=traceback.format_exc()
        finally:
            try:
                sys.stdout.flush()
            finally:
                sys.stdout=old
        self.done.emit(error)


class LEEMWindow(QtWidgets.QWidget):

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle("LEEM acquisition")
        self.worker=None
        layout=QtWidgets.QVBoxLayout(self)

        box=QtWidgets.QGroupBox("Imaging conditions")
        inner=QtWidgets.QVBoxLayout(box)
        self.imaging=FieldPanel(IMAGING)
        inner.addWidget(self.imaging)
        caption=QtWidgets.QLabel("Used by Image(s), IV and the temperature ramp with ROI. "
                                 "The setpoint-only ramps take no images and ignore these.")
        caption.setStyleSheet("color: gray;")
        caption.setWordWrap(True)
        inner.addWidget(caption)
        layout.addWidget(box)

        self.groups=[]
        for spec in GROUPS:
            g=GroupBox(spec,self.imaging.values)
            g.run.connect(self.start)
            layout.addWidget(g)
            self.groups.append(g)
        self.imaging.connect_all(self.refresh_previews)

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
        self.log.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        layout.addWidget(self.log,1)
        self.resize(1000,780)

        self.refresh_starts()
        self.refresh_previews()

    def refresh_previews(self):
        for g in self.groups:
            g.refresh_preview()

    def refresh_starts(self):
        for g in self.groups:
            g.refresh_start()

    def append(self,text):
        self.log.appendPlainText(text)

    def start(self,group):
        if self.worker is not None:
            return                      # already running; Run buttons are disabled anyway
        variant=group.current()
        try:
            kwargs=group.values()
        except ValueError as e:
            self.append("! %s"%e)
            return
        func=getattr(M,variant["func"])
        self.append(">>> %s(%s)"%(variant["func"],
                                  ", ".join("%s=%r"%kv for kv in kwargs.items())))
        self.worker=Worker(func,kwargs,self)
        self.worker.line.connect(self.append)
        self.worker.done.connect(self.finished)
        self._running(True,variant["stoppable"],variant["label"])
        self.worker.start()

    def stop(self):
        self.append("--- stop requested, finishing the current step ---")
        self.stopButton.setEnabled(False)
        M.leem_abort.set()

    def finished(self,error):
        if error:
            self.append(error.rstrip())
        self.worker=None
        self._running(False,False,"")
        self.append("--- finished ---")
        self.refresh_starts()           # a ramp will have moved the setpoint

    def _running(self,busy,stoppable,label):
        for g in self.groups:
            g.set_enabled(not busy)
        self.imaging.set_enabled(not busy)
        self.stopButton.setEnabled(busy and stoppable)
        self.status.setText(("Running: "+label) if busy else "Idle")

    def closeEvent(self,event):
        if self.worker is not None:
            M.leem_abort.set()
            self.worker.wait(5000)
        super().closeEvent(event)


_window=None

def _under_ipython():
    """ True when an IPython shell is driving this process.

    IPython installs its Qt hook when the prompt starts, which is *after* any
    startup code has run. So even under "ipython --gui=qt6 -c ...", both
    active_eventloop and QApplication.instance() are still empty at this point
    and cannot be used to detect it. Calling app.exec() here would block the
    console for good; leaving the loop alone lets IPython pump it as soon as
    the prompt appears.
    """
    try:
        from IPython import get_ipython
    except Exception:
        return False
    return get_ipython() is not None

def leem_gui_main():
    """ Show the acquisition window.

    Under plain python this blocks until the window is closed. Under ipython it
    returns immediately and the console stays usable, provided ipython drives
    the Qt event loop -- start it with --gui=qt6, or run %gui qt6 before this.
    The leemgui script does that for you.
    """
    global _window
    existing=QtWidgets.QApplication.instance()
    app=existing or QtWidgets.QApplication(sys.argv)
    _window=LEEMWindow()
    _window.show()
    if existing is None and not _under_ipython():
        app.exec()
    return _window


if __name__=="__main__":
    leem_gui_main()
