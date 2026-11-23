#!/usr/bin/python
# LEEM Madrid Macros
# Simple acquisition using tango device servers
#
# v3.15 23/11/2026 The macros log themselves. leem_log() had exactly one caller, LEEMgui's Run button, so nothing typed at the prompt was ever recorded -- and ARRES, being command line only (leemARRESset uses input()), was never recorded at all: 101 experiments between 18 and 23 November left no log line, while 5 November logged 6 of its 8. New leem_log_call() now goes in each of the ten macros the GUI could run (the seven that take an experiment folder, plus the three PID ramps), and the call in LEEMgui is gone so a GUI run is not logged twice. It builds the line from the caller's own arguments instead of a format string per macro, so it cannot drift from the signature. leem_log() is told the folder number rather than guessing it from the counter file: that guess only worked because the GUI logged before the acquisition took its folder, and would now be one too high. Something with no folder of its own, a ramp, logs --- in that column. Found because the log for the recent ARRES days was missing; the same look showed the deployed copy predates v3.11, since no line since 10 September carries the experiment number v3.11 added.
#
# v3.14 20/11/2026 New leem_acquire_and_wait(), replacing the bare "uview.AcquireSingleImage(); while (uview.ContinousAcquisition): pass" at twelve places. That loop asked as fast as CORBA and TCP allowed, on UView's single socket, which may well have been helping to wedge UView rather than merely failing to survive it (ElmitecUview's aip and AcquisitionInProgress interfered on that socket once before, see v2.8). It now asks every LEEM_POLL_IMAGE (50 ms): about eight questions per 400 ms exposure instead of one per round trip, for at most 50 ms of added latency per image. It also says so every LEEM_WARN_IMAGE (60 s) while an image does not arrive, where before a wedged UView stopped a run silently and for ever -- it does NOT give up, because pressing acquire in UView unblocks it and the run carries on, so losing the acquisition would be worse than the stall; tools/leem_acquisition_watchdog.py is what tells you from elsewhere. And it polls leem_checkstop() through leem_abort.wait(), so the GUI Stop button can now interrupt a wait: CTRL-C always could, but a GUI stop had nothing to poll. New tools/test_leemmacros.py covers the wait and the v3.13 counter file against a stub tango, no instrument needed.
#
# v3.13 20/11/2026 leemSetDailyFolder() wrote macros.dat with three fields (prefix,dayfolder,exp) where leem_getfolder() unpacks four, so calling it left a counter file the next call could not read: every macro then died on "not enough values to unpack". The same three-field write inside leem_makenextfolder_and_inc() was harmless only because a correct four-field write overwrote it before that function returned. There were four copies of this write in two spellings, which is how the two wrong ones survived, so the layout now lives in one place: new leem_setfolder(wprefix,prefix,dayfolder,exp), used by all four.
#
# v3.12 16/11/2026 ARRES fixes, and the macros cope with ElmitecLEEM2k/ElmitecUview now raising on error replies (same change). leemARRESrun: a two-row b (one direction) crashed on "if (len(b>2))", always true, before reaching its own one-direction exit; CTRL-C or an error now puts the deflectors back at normal incidence and the camera back as it was (it had no handler), and the partial data and plots are still written. The two directions share one helper, and scipy's interp1d is gone (plain linear interpolation, same values). leemARRESset printed b[1] as endpoint 2, and its "b>200 -> 0" loop is removed: it only covered b[0] and three deflectors, and zeroed real values above 200 mA. New leem_read() retries a value while LEEM2000 answers ErrorCode -102 (ramping), and leemReadDeflection takes ErrorCode -101 on the image equalizers as 0 with a warning. leem_savesettings writes "unreadable (...)" for a module it cannot read instead of failing the acquisition. New leem_savedat() prints a warning when UView does not save an image, which every macro skipped silently. New leem_energies() for leemIV, leemIV_ROI and leemIVandObj: numpy.arange and frange() stepped in floating point and often took one point too many or too few (leemIV(0,0.2,0.1) took four images, the last at 0.3).
#
# v3.11 16/09/2026 leem_log() now stamps each line with the day's %03d experiment
# counter, right before the command, so a log line can be matched to the folder
# it produced (e.g. "2026-09-16 18:30:00  007  leemSaveSingleImage(...)" for
# 20260916_007). The counter was already being read for the day-rollover check
# and simply never written out. Also fixes the rollover case itself: on the
# first log call of a new day, the on-disk counter was correctly reset to 0,
# but the local exp variable this function had already read (from yesterday's
# line) was not, so that first line would have logged yesterday's leftover
# count instead of the 000 the folder is about to get.
#
# v3.10 10/09/2026 leem_gui_main() now keeps the QApplication it creates in a module global (_app), like _window. Under "ipython --gui=qt6 -c" the Qt inputhook, and the QApplication that comes with it, is only installed when the prompt first appears -- after the startup code -- so QApplication.instance() is None when gui() runs and leem_gui_main() builds its own. It was held only in a local, so it was garbage-collected the moment gui() returned; destroying a QApplication destroys its top-level widgets, so the window was torn down before the prompt drew it. Symptom: leemgui reaches the prompt normally but no panel appears. Reproduced on IPython 8.39 and 9.17 alike, so this is not a version regression; the leemgui launcher's -c path had simply never been run on the instrument (the Aug 2026 test predates the launcher and used %gui qt6 then gui() at the prompt, where a QApplication already exists). Standalone "python LEEMgui.py" still blocks in _app.exec() as before.
#
# v3.9 02/09/2026 Added leem_log(command): the GUI now appends every acquisition it launches, as the exact call it makes, to <dayfolder>/<YYYYMMDD>_commands.log next to the data, with a timestamp. Opens and closes per line so nothing is lost if a run hangs. Only the final call from a Run button is logged -- typed commands are not intercepted. leem_log never raises; if there is no counter file it silently does nothing.
#
# v3.8 02/09/2026 LEEMgui.py moved from PySide6 to PyQt6: PyQt6 is a single Debian package (python3-pyqt6) that is already on the instrument, no new dependency, and IPython 8.x's qt inputhook works with it where it broke on PySide6 >= 6.7 (lazy submodule attributes). Changes were mechanical: import, QtCore.Signal -> QtCore.pyqtSignal, and the QFontDatabase.FixedFont enum now needs its SystemFont scope. leemgui pins QT_API=pyqt6.
#
# v3.7 02/09/2026 Register an atexit hook that calls tango.ApiUtil.cleanup(). omniORB's client threads were racing Python finalisation and segfaulting on exit from an ipython leemgui session -- reproducible with just "ipython --gui=qt6 -c 'from LEEMmacros import *'" then exit, and not with "--gui=qt6" alone, so it is the Tango client, not the Qt inputhook. cleanup() shuts the ORB down at the start of shutdown, before the race. Guarded in try/except because it is a no-op or raises depending on the pytango build.
#
# v3.6 02/09/2026 Superficies moved from /home/tvips/Superficies to /Superficies, so counter_filename pointed at a path that no longer exists. leem_getfolder() reacted to the missing counter file by calling exit(), which from the GUI worker thread raised SystemExit past Worker.run()'s "except Exception" and segfaulted PySide6's QThread trampoline ("QThreadStorage: entry destroyed before end of thread") -- the hang/crash seen when saving a sequence. counter_filename now points at /Superficies/LEEM_Madrid/macros.dat (its wprefix/prefix fields were already correct), and leem_getfolder() raises RuntimeError instead of exit() so a bad path surfaces as a traceback in the log with the buttons re-enabled. The leemgui launcher default rundir moved too. macros.dat itself is unchanged.
#
# v3.5 03/08/2026 Fixed gui() blocking the ipython prompt. IPython installs its Qt hook when the prompt starts, which is after any startup code has run, so under "ipython --gui=qt6 -c ..." both active_eventloop and QApplication.instance() are still empty when gui() runs and cannot be used to detect that IPython will drive the loop. gui() now simply skips app.exec() whenever an IPython shell is present and lets IPython pump the event loop once the prompt appears; under plain python it still blocks as before.
#
# v3.4 03/08/2026 GUI reorganised into groups: Image(s), IV, Sample temperature ramp and Doser ramp, each choosing one variant with radio buttons and having its own Run button and a preview line showing the exact call it will make. Exposure and average moved to a shared "Imaging conditions" panel, E0/Ef/dE to a "Scan voltage" panel inside the IV group. The ramps show the PID setpoint they will start from as a read-only field, because the macros always ramp from the current setpoint and there is no way to pass a starting value. For the shared panel to work, leemIV, leemIV_ROI, leemIVandObj, leemRampTemperatureROI and leemARRESrun now accept exp=None and avg=None meaning "use whatever the camera is set to", as leemSaveSingleImage and leemSequenceImages already did; their defaults are unchanged, so calling them from the command line behaves exactly as before.
#
# v3.3 03/08/2026 GUI average presets now go up to 64, matching UView, and the field is labelled "Average (1=sliding)" so the sliding average is visible without reading the docstring. The boxes stay editable, so any value in between can still be typed.
#
# v3.2 03/08/2026 Added the three PID ramps to the GUI: leemRampTemperatureTo, doser1RampPowerTo and doser2RampPowerTo. They all go through pidRampTo, which now polls leem_checkstop() and waits on leem_abort, so the Stop button works for them and CTRL-C is caught instead of escaping as a traceback. A ramp needs no cleanup, it just stops where it got to, and the setpoint it reached is printed. pressure_limit is not offered in the GUI because the pressure check inside pidRampTo is commented out and the parameter currently does nothing.
#
# v3.1 01/08/2026 Added a Qt acquisition GUI, in LEEMgui.py, opened with gui(). It exposes single image, sequence, IV, IV with ROI, IV with objective and the temperature ramp, each with its parameters, a Stop button and a log box. ARRES stays command line only because leemARRESset() asks for input() at the terminal. Acquisitions run in a worker thread, so a stop cannot use CTRL-C: instead leem_abort is set and the loops poll it through leem_checkstop(), which raises KeyboardInterrupt so a GUI stop unwinds through exactly the same cleanup as CTRL-C. The sleeps in leemSequenceImages and leemRampTemperatureROI now use leem_abort.wait(), so stopping does not have to wait out the delay. leemIVandObj gained the KeyboardInterrupt handler it never had, which also fixes CTRL-C there leaving the camera stopped at the wrong exposure.
#
# v3.0 31/07/2026 Removed all live plotting, so the macros no longer open windows and no longer depend on the ipython --pylab namespace. show(), savefig(), zeros(), array() and flip() were being used without ever being imported, and only resolved because the file is run into a --pylab session; they are now numpy./Figure. calls. Plots are written to files with matplotlib's Figure object API (no pyplot, no backend, no global state), so they also work from a worker thread. leemIV_ROI has lost its plot parameter, it always writes plot.png/plot.pdf now, and no longer crashes on its default arguments (fig was used outside the plot guard). leemARRESrun writes arres0/arres1 .pdf and .png and no longer leaves the camera stopped on the two-direction path. Fixed a python2 leftover bare print. The module can now be imported, which is what the GUI needs.
#
# v2.9 31/07/2026 leemSaveSingleImage and leemSequenceImages now only stop the camera when the requested exposure differs from the current one. Otherwise the camera is left running (started if it was stopped) and the average is changed live, which saves the thrown-away image. BEWARE: on that path leemSaveSingleImage no longer triggers a fresh exposure, it saves the frame UView currently holds, so with avg=1 (sliding average) the image can include frames from before the call. Note also that with the camera running ContinousAcquisition reads True forever, so the single-image trigger and its wait loop can only be used on the stopped path. Exposure and average are now optional in both commands: left out, the value already set in the camera is used, so calling them with no arguments never stops the camera. This changes the old no-argument behaviour, which forced 500ms/avg 0 for a single image and 400ms/avg 1 for a sequence.
#
# v2.8 27/07/2026 Modified to stop Continuous acquisition for every sequence that requires synchronization (modified also the UView device server to use only a RW ContinuousAcquisition variable instead of a W ContinuousAcquisition and a R AcquisitionInProgress, which I think were stepping on each other). Note there is still a typo: Continous instead of Continuous. Also had to add a delay after switching on and off continuous mode, and we also have to throw away one image after such changes.
#
# v2.7 17/07/2026 Modified to stop acquisition before any exposure change
#
# v2.6 26/9/2024 Modified for python3 again...
#
# v2.5 23/4/2024 Added CONTROL-C check in leemRampTemperaureROI
#
# v2.4 21/2/2024 rampLEEMROI
#
# v2.3 Minor cleaning
#
# v2.2 13/7/2022 Added doser1,2RampPowerTo, leemARRES
#
# v2.1 28/5/2021 Added leemRampTemperatureTo. This requires the PID controller to be on, and the gauge of the main chamber working.
#
# v2.0 25/02/2020 Autoselect day. Now leemSetDailyFolder is called at every experiment, and if the day is the same an an already existing folder, it does nothing. Otherwise, it creates the folder and resets the experiment number. Added time stamp in LEEMIV_ROI, LEEMIV
# v1.9 06/02/2020
#
# 06/02/2020 Changed number range in saving sequences from 3 digits to 4 digits. Removed LEEMIV_ROI_and_save, and added "saveImage" option in LEEMIV_ROI.
# 
# 20/02/2023 Adapted to Python3.
#
# Juan de la Figuera juan.delafiguera@gmail.com

__version__ = "3.15"

from datetime import date
import tango
import os
import sys
import numpy
import time
import threading
import atexit
from matplotlib.figure import Figure

# omniORB's client threads race Python finalisation and segfault on exit --
# seen leaving an ipython leemgui session after any DeviceProxy use ("ipython
# -c 'from LEEMmacros import *'" then exit is enough). Shut the Tango client API
# down cleanly at the start of interpreter shutdown, before that race. Guarded
# because cleanup() is a no-op-or-raise depending on pytango build.
@atexit.register
def _tango_cleanup():
    try:
        tango.ApiUtil.cleanup()
    except Exception:
        pass

# Set by the GUI Stop button. The acquisition loops poll it through
# leem_checkstop() and raise KeyboardInterrupt, so a GUI stop unwinds through
# exactly the same cleanup code as CTRL-C from the command line.
leem_abort=threading.Event()

def leem_checkstop():
    """ Raise KeyboardInterrupt if a stop has been requested from the GUI. """
    if leem_abort.is_set():
        raise KeyboardInterrupt

# Seconds between asking UView whether the image is ready. Until v3.14 this
# was effectively zero: a bare "while (uview.ContinousAcquisition): pass",
# where every turn is a CORBA round trip plus a TCP exchange on UView's
# single socket, as fast as both allow. At 50 ms a 400 ms exposure costs
# about eight questions instead of several hundred, for at most 50 ms of
# added latency per image.
LEEM_POLL_IMAGE=0.05

# Seconds without the image arriving before saying so, and again every
# LEEM_WARN_IMAGE after that.
LEEM_WARN_IMAGE=60.0

def leem_acquire_and_wait(what=""):
    """ Trigger one image and wait for UView to finish it.

    Replaces the bare

        uview.AcquireSingleImage()
        while (uview.ContinousAcquisition):
            pass

    which stood at twelve places. Three things that loop did not do:

    - it asked as fast as CORBA and TCP allowed, on UView's single socket;
    - it had no timeout, so a wedged UView -- its "WaitForSingleObject failed
      100000x in a row" window -- stopped a run silently and for ever, as
      happened to an ARRES run on 20-Nov-2026;
    - it never polled leem_checkstop(), so the GUI Stop button could not
      interrupt it. CTRL-C could, having nothing to poll, but a GUI stop had
      no way in.

    The wait is deliberately unbounded. It warns and keeps waiting rather
    than raising, because pressing *acquire* in UView by hand unblocks it
    and the run then carries on from where it was: turning a recoverable
    stall into a lost acquisition would be worse than the stall.
    tools/leem_acquisition_watchdog.py is what tells you from elsewhere. A
    stop you ask for does raise, through leem_checkstop(), as everywhere
    else.

    BEWARE the v2.9 invariant: on a *running* camera this never returns,
    because the read is UView's "aip" and a running camera is always
    acquiring. That used to hang in silence; it now says so once a minute.
    """
    uview.AcquireSingleImage()
    started=time.monotonic()
    warned=0
    while (uview.ContinousAcquisition):
        # wait() rather than sleep() so a GUI stop does not have to sit out
        # the interval, as in leemSequenceImages and the PID ramps.
        leem_abort.wait(LEEM_POLL_IMAGE)
        leem_checkstop()
        waited=time.monotonic()-started
        if (waited>=LEEM_WARN_IMAGE*(warned+1)):
            warned+=1
            print("WARNING: %.0f s waiting for UView to finish the image%s. "
                  "Still waiting, nothing is lost. If UView shows "
                  "'WaitForSingleObject failed', press acquire there to "
                  "unblock it."%(waited," ("+what+")" if what else ""))

def gui():
    """ Open the acquisition GUI. Imported lazily so that a plain command line
    session does not need PyQt6. """
    from LEEMgui import leem_gui_main
    return leem_gui_main()

def frange(start, stop=None, step=None):
    #Use float number in range() function
    # if stop and step argument is null set start=0.0 and step = 1.0
    # Change 20/6/2019 in order to output up to the last value stop.
    if stop == None:
        stop = start + 0.0
        start = 0.0
    if step == None:
        step = 1.0
    while True:
        if step > 0 and start >= stop+ step:
            break
        elif step < 0 and start <= stop+ step:
            break
        yield ("%g" % start) # return float number
        start = start + step
#end of function frange()

def leem_energies(E0,Ef,dE):
    """ E0, E0+dE, ... up to and including Ef, rounded to whole steps.

    numpy.arange(E0,Ef+dE,dE) and frange() step in floating point, so the
    last point came out one too many or too few: leemIV(0,0.2,0.1) took four
    images, ending at 0.3. Over E0 0-10, dE 0.02-0.5 and 1-119 steps, arange
    was wrong in 14% of cases and frange in 38%. The number of steps is
    rounded instead, and each energy is E0 plus a whole number of steps.
    """
    n=int(round((Ef-E0)/dE))+1
    return E0+dE*numpy.arange(max(n,0))


counter_filename="/Superficies/LEEM_Madrid/macros.dat"
name="000"

#gaugeMCH=tango.DeviceProxy("leem/vacuum/gaugeMCH")
leem_pid=tango.DeviceProxy("leem/control/sample_leem_pid")
doser1_pid=tango.DeviceProxy("leem/control/doser_pid")
doser2_pid=tango.DeviceProxy("leem/control/doser2_pid")
leem2k=tango.DeviceProxy("leem/measurement/LEEM2k")
uview=tango.DeviceProxy("leem/measurement/Uview")

def leemSetDailyFolder():
    (wprefix,prefix,dayfolder,exp)=leem_getfolder()
    today=date.today()
    dayfolder="%04d%02d%02d"%(today.year,today.month,today.day)
    dayname=prefix+"/"+dayfolder
    if not os.path.exists(dayname):
        os.mkdir(dayname)
        print("Directory "+dayname+" Created ")
        leem_setfolder(wprefix,prefix,dayfolder,0)
    else:
        print("Dayfolder "+dayname+" exists. Doing nothing.")
    
def leem_setfolder(wprefix,prefix,dayfolder,exp):
    """ Write the counter file. The only place that knows its layout.

    It has to stay in step with leem_getfolder(), which unpacks four fields,
    and that is exactly what went wrong while there were four copies of this
    write in two different spellings: leemSetDailyFolder() wrote three
    (prefix,dayfolder,exp), leaving a counter file the next leem_getfolder()
    could not unpack at all.
    """
    f=open(counter_filename,"w")
    f.write("%s,%s,%s,%d"%(wprefix,prefix,dayfolder,int(exp)))
    f.close()

def leem_getfolder():
    if not os.path.exists(counter_filename):
        raise RuntimeError("no counter file at %s (run leemSetDailyFolder() "
                           "or fix counter_filename)"%counter_filename)
    f=open(counter_filename,"r")
    count=f.readline()
    f.close()
    (wprefix,prefix,dayfolder,exp)=count.split(",")
    return(wprefix,prefix,dayfolder,int(exp))

def leem_makenextfolder_and_inc():
    (wprefix,prefix,dayfolder,exp)=leem_getfolder()
    #Check that day folder exists
    today=date.today()
    dayfolder="%04d%02d%02d"%(today.year,today.month,today.day)
    dayname=prefix+"/"+dayfolder
    if not os.path.exists(dayname):
        os.mkdir(dayname)
        print("Directory "+dayname+" Created ")
        leem_setfolder(wprefix,prefix,dayfolder,0)
        exp=0
    full=prefix+"/"+dayfolder+"/"+dayfolder+"_%03d"%exp
    wfull=wprefix+"/"+dayfolder+"/"+dayfolder+"_%03d"%exp
    name="%03d"%exp
    if not os.path.exists(full):
        os.mkdir(full)
        print("Directory "+full+" Created ")
    else:
        print("Directory "+full+" already exists")
    exp+=1
    leem_setfolder(wprefix,prefix,dayfolder,exp)
    return(wfull,full,name)

def leem_log(command,name=None):
    """ Append one timestamped line to <dayfolder>/<YYYYMMDD>_commands.log, so
    the day folder next to the data keeps a record of every acquisition run
    that day, whoever launched it.

    `name` is the %03d of the experiment folder the run was given, so a line
    can be matched to the data it produced; None, for something that makes no
    folder such as a PID ramp, writes --- in that column instead. Until v3.15
    this function guessed the number from the counter file instead of being
    told, which only worked because the GUI logged *before* the acquisition
    took its folder.

    Never raises: a logging failure must not abort an acquisition.
    """
    try:
        (wprefix,prefix,dayfolder,exp)=leem_getfolder()
        today=date.today()
        dayfolder="%04d%02d%02d"%(today.year,today.month,today.day)
        dayname=prefix+"/"+dayfolder
        if not os.path.exists(dayname):
            # Something that makes no folder can be the first thing of the
            # day. Create it the way leem_makenextfolder_and_inc would, and
            # reset the counter with it, so the first acquisition after this
            # still gets _000 rather than yesterday's leftover number.
            os.mkdir(dayname)
            leem_setfolder(wprefix,prefix,dayfolder,0)
        stamp=time.strftime("%Y-%m-%d %H:%M:%S")
        f=open(dayname+"/"+dayfolder+"_commands.log","a")
        f.write(stamp+"  "+(name if name else "---")+"  "+command+"\n")
        f.close()
    except Exception:
        pass

def _leem_log_value(value):
    """ One argument of a logged call, on one line and short enough to read.
    leemARRESrun's b is a 3x4 numpy array whose repr runs over several. """
    try:
        if isinstance(value,float):
            return "%g"%value
        text=repr(value)
    except Exception:
        return "<unprintable>"
    text=" ".join(text.split())
    if (len(text)>80):
        text=text[:77]+"..."
    return text

def leem_log_call(name=None):
    """ Log the acquisition the calling macro was asked to do.

    Called from inside each macro rather than from the GUI, so a run is
    recorded wherever it was launched from. Until v3.15 the only caller was
    the GUI's Run button, which meant nothing typed at the prompt was ever
    logged -- and ARRES, being command line only, was never logged at all.
    101 experiments between 18 and 23 November produced no log line.

    The line is built from the caller's own arguments rather than a
    hand-written format string per macro, so it cannot drift from the
    signature. This file has been bitten twice by copies of one thing
    drifting apart: macros.dat written four ways (v3.13) and the image wait
    written twelve (v3.14).
    """
    try:
        frame=sys._getframe(1)
        code=frame.f_code
        parts=[]
        for argname in code.co_varnames[:code.co_argcount]:
            if argname in frame.f_locals:
                parts.append("%s=%s"%(argname,
                                      _leem_log_value(frame.f_locals[argname])))
        leem_log("%s(%s)"%(code.co_name,", ".join(parts)),name)
    except Exception:
        pass

def _leem_setting(attr,fmt):
    """ One LEEM2000 value for leem_savesettings, or the error instead. Since
    ElmitecLEEM2k raises on LEEM2000 error replies, a module in local mode
    must not stop the acquisition; it used to be written as e.g. -100.00. """
    try:
        return fmt%leem_read(attr)
    except tango.DevFailed as e:
        try:
            why=e.args[0].desc.strip().splitlines()[-1]
        except Exception:
            why="Tango error"
        return "unreadable (%s)"%why

def leem_savesettings(name):
    f=open(name,"w")
    f.write("LEEM2k----------------------------\n")
    f.write("StartVoltage: %s Volt\n"%_leem_setting("StartVoltage","%5.2f"))
    f.write("Preset      : %s \n"%leem2k.Preset)
    f.write("Objective   : %s mA\n"%_leem_setting("Objective","%7.1f"))
    f.write("FieldLens   : %s mA\n"%_leem_setting("FieldLens","%7.1f"))
    f.write("TransferLens: %s mA\n"%_leem_setting("TransferLens","%7.1f"))
    f.write("IntermLens  : %s mA\n"%_leem_setting("IntermLens","%7.1f"))
    f.write("P1Lens      : %s mA\n"%_leem_setting("P1Lens","%7.1f"))
    f.write("MCHP        : %s kV\n"%_leem_setting("ChannelPlateVoltage","%5.2f"))
    f.write("Temperature : %s C\n"%_leem_setting("SampleTemperature","%5.1f"))
    f.write("Uview-----------------------------\n")
    f.write("Exposure    : %5.3f ms\n"%uview.Exposure)
    f.write("Average     : %5d \n"%uview.Average)
    f.write("ImageHeight : %4d \n"%uview.ImageHeight)
    f.write("ImageWidth  : %4d \n"%uview.ImageWidth)
    f.close()

def leem_exposure_differs(current,exp):
    """ True if the camera is not already at the requested exposure (ms).

    Only an exposure change needs the camera stopped and restarted, which costs
    a thrown-away image because of the UView/TVIPS triggering problem. Compared
    with a tolerance because Exposure is read back as a float from UView.
    """
    return abs(current-exp)>0.01

def leemSaveSingleImage(exp=None,avg=None):
    """ leemSaveSingleImage( exposure (ms), average )

    Both are optional. Left out, whatever the camera is already set to is used.

    BEWARE: 1 average means sliding average
    """
    (wfull,full,name)=leem_makenextfolder_and_inc()
    leem_log_call(name)
    expname="IMG"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    if exp is None:
        exp=oldExposure
    if avg is None:
        avg=oldAverage
    restarted=leem_exposure_differs(oldExposure,exp)
    if restarted:
        uview.ContinousAcquisition=False
        time.sleep(0.5)
        uview.Exposure=exp
        uview.Average=avg
        leem_acquire_and_wait("throw-away")
        leem_acquire_and_wait()
    else:
        # Exposure already correct, so keep the camera running and grab the
        # frame it has. BEWARE: with the camera running, ContinousAcquisition
        # reads True forever, so AcquireSingleImage and the wait loops above
        # must not be used here.
        if avg!=oldAverage:
            uview.Average=avg
        if not uview.ContinousAcquisition:
            uview.ContinousAcquisition=True
            time.sleep(0.5)
    leem_savesettings(full+"/"+expname+".txt")
    if leem_savedat(wfull,expname):
        print("Succesfull saving %s"%expname)
    if restarted:
        uview.Exposure=oldExposure
        uview.Average=oldAverage
        uview.ContinousAcquisition=True
    elif avg!=oldAverage:
        uview.Average=oldAverage

def leemSequenceImages(exp=None,avg=None,n=-1,delay=1.0):
    """ leemSequenceImage (exposure (ms), average, number_of_images (-1=infinite), delay (s)

    Save sequence of images. For infinite, press CTRL-C to stop.

    Exposure and average are optional. Left out, whatever the camera is already
    set to is used.

    BEWARE: 1 average means sliding average
    """
    (wfull,full,name)=leem_makenextfolder_and_inc()
    leem_log_call(name)
    expname="SEQ"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    if exp is None:
        exp=oldExposure
    if avg is None:
        avg=oldAverage
    restarted=leem_exposure_differs(oldExposure,exp)
    if restarted:
        uview.ContinousAcquisition=False
        uview.Exposure=exp
        uview.Average=avg
        time.sleep(0.5)
        uview.ContinousAcquisition=True
        time.sleep(0.5)
    else:
        # Exposure already correct, so leave the camera running.
        if avg!=oldAverage:
            uview.Average=avg
        if not uview.ContinousAcquisition:
            uview.ContinousAcquisition=True
            time.sleep(0.5)
    leem_savesettings(full+"/"+expname+".txt")
    try:
        if (n==-1):
            a=0
            while (1):
                leem_checkstop()
                savename=expname+"_%05d"%a
                if leem_savedat(wfull,savename):
                    print("Saved %s"%savename)
                a+=1
                leem_abort.wait(delay)
        else:
            for a in range(n):
                leem_checkstop()
                savename=expname+"_%05d"%a
                if leem_savedat(wfull,savename):
                    print("Saved %s"%savename)
                leem_abort.wait(delay)
    except KeyboardInterrupt:
        print("Ok, so you want to finish. Let me clean up.")
    if restarted:
        uview.ContinousAcquisition=False
        uview.Exposure=oldExposure
        uview.Average=oldAverage
        uview.ContinousAcquisition=True
    elif avg!=oldAverage:
        uview.Average=oldAverage

def leemIV(E0,Ef,dE,exp=400.0,avg=0,repeat=False):
    """ leemIV (Initial Energy (V), Final Energy (V), increment E (V), exposure (ms), average, repeat (default=False)
    
    Save sequence of images changing energy and objective.
    For repeated loops (repeat=True), press CTRL-C to finish.
    
    BEWARE: 1 average means sliding average
    """
    (wfull,full,name)=leem_makenextfolder_and_inc()
    leem_log_call(name)
    expname="LEEMIV"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    if exp is None:
        exp=oldExposure
    if avg is None:
        avg=oldAverage
    uview.ContinousAcquisition=False
    time.sleep(0.5)
    uview.Exposure=exp
    uview.Average=avg
    leem_savesettings(full+"/"+expname+".txt")
    f=open(full+"/LOG.txt","w")
    f.write("# Image number  Energy (eV) time\n")

    leem_acquire_and_wait("throw-away")
    a=0
    try:
        while (True):
            e=leem_energies(E0,Ef,dE)
            for i in e:
                leem_checkstop()
                leem2k.StartVoltage=float(i)
                t=time.localtime()
                timenow=time.strftime("%c", t)
                print("Image %d Energy %f Time %s"%(a,float(i),timenow))
                f.write("%d %f %s\n"%(a,float(i),timenow))
                leem_acquire_and_wait()
                savename=expname+"_%05d"%a
                if leem_savedat(wfull,savename):
                    print("Saved %s"%savename)
                a+=1
            if (repeat==False):
                break
    except KeyboardInterrupt:
        print("Ok, ok, stopping adquisition. Let me clean up")
    f.close()
    uview.Exposure=oldExposure
    uview.Average=oldAverage
    uview.ContinousAcquisition=True


def leemIV_ROI(E0,Ef,dE,exp=400.0,avg=0,repeat=False,roi=1,saveImage=False):
    """ leemIV (Initial Energy (V), Final Energy (V), increment E (V), exposure (ms), average, repeat (default=False), roi (default=1, or use 2 for two boxes), saveImage (default=False)

    Save intensity of ROI changing energy. The curve is written to plot.png and
    plot.pdf in the experiment folder, no window is opened.
    For repeated loops (repeat=True), press CTRL-C to finish.

    BEWARE: 1 average means sliding average
    """
    (wfull,full,name)=leem_makenextfolder_and_inc()
    leem_log_call(name)
    expname="LEEMIV"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    if exp is None:
        exp=oldExposure
    if avg is None:
        avg=oldAverage
    uview.ContinousAcquisition=False
    time.sleep(0.5)
    uview.Exposure=exp
    uview.Average=avg
    leem_savesettings(full+"/"+expname+".txt")
    f=open(full+"/LOG.txt","w")
    leem_acquire_and_wait("throw-away")
    f.write("# Image number  Energy (eV) ROI1 (arb.u.) time\n")
    a=0
    fig=Figure()
    if (roi==1):
        ax=fig.add_subplot(111)
    else:
        ax=fig.add_subplot(211)
        ax2=fig.add_subplot(212)
    try:
        while (True):
            e=leem_energies(E0,Ef,dE)
            rois=numpy.zeros(len(e))
            if (roi!=1):
                rois2=numpy.zeros(len(e))
            k=0
            for i in e:
                leem_checkstop()
                leem2k.StartVoltage=i
                leem_acquire_and_wait()
                rois[k]=float(uview.IntensityROI1)
                if (roi==2):
                    rois2[k]=float(uview.IntensityROI2)
                t=time.localtime()
                timenow=time.strftime("%c", t)
                if (saveImage==True):
                    savename=expname+"_%05d"%a
                    if leem_savedat(wfull,savename):
                        print("Saved %s"%savename)
                if (roi==1):
                    print("Image %d Energy %f ROI1 %f time %s"%(a,i,rois[k],timenow))
                    f.write("%d %f %f %s\n"%(a,i,rois[k],timenow))
                else:
                    print("Image %d Energy %f ROI1 %f ROI2 %f time %s"%(a,i,rois[k],rois2[k],timenow))
                    f.write("%d %f %f %f %s\n"%(a,i,rois[k],rois2[k],timenow))
                a+=1
                k+=1
            ax.plot(e,rois)
            if (roi!=1):
                ax2.plot(e,rois2)
            # Rewritten every pass, so the file can be watched while repeating.
            fig.savefig(full+"/plot.png")
            f.flush()
            if (repeat==False):
               break
    except KeyboardInterrupt:
        print("Ok, ok, you want me to stop. Cleaning up.")
    f.close()
    fig.savefig(full+"/plot.pdf")
    fig.savefig(full+"/plot.png")
    uview.Exposure=oldExposure
    uview.Average=oldAverage
    uview.ContinousAcquisition=True


def leemIVandObj(E0,Ef,dE,startObj,endObj, exp=400.0,avg=0):
    """ leemIVandObj (Initial Energy (V), Final Energy (V), increment E (V), Start Objective (mA), End Objective (mA), exposure (ms), average
    
    Save sequence of images changing energy and objective.
    
    BEWARE: 1 average means sliding average
    """
    (wfull,full,name)=leem_makenextfolder_and_inc()
    leem_log_call(name)
    expname="LEEMIV"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    if exp is None:
        exp=oldExposure
    if avg is None:
        avg=oldAverage
    uview.ContinousAcquisition=False
    time.sleep(0.5)
    uview.Exposure=exp
    uview.Average=avg
    leem_savesettings(full+"/"+expname+".txt")
    leem_acquire_and_wait("throw-away")
    f=open(full+"/LOG.txt","w")
    f.write("# Image number  Energy (eV) Objective (mA)\n")
    e=leem_energies(E0,Ef,dE)
    a=0
    try:
        for i in e:
            leem_checkstop()
            leem2k.StartVoltage=float(i)
            leem2k.Objective=float((endObj-startObj)*(float(i)-E0)/(Ef-E0)+startObj)
            print("Image %d Energy %f Objective %f"%(a,float(i),float((endObj-startObj)*(float(i)-E0)/(Ef-E0)+startObj)))
            f.write("%d %f %f\n"%(a,float(i),float((endObj-startObj)*(float(i)-E0)/(Ef-E0)+startObj)))
            leem_acquire_and_wait()
            #uview.SaveImageAsPNG(expname)
            savename=expname+"_%05d"%a
            if leem_savedat(wfull,savename):
                print("Saved %s"%savename)
            a+=1
    except KeyboardInterrupt:
        print("Ok, so you want to finish. Let me clean up.")
    f.close()
    uview.Exposure=oldExposure
    uview.Average=oldAverage
    uview.ContinousAcquisition=True

def pidRampTo(pid,final,step=1.0,time_step=1.0,pressure_limit=1):
    """ pidRampTo (desired_setpoint, step, time_step, pressure_limit)
    Ramp PID setpoint (PID must be activated before!!)
    Parameters:
        desired: final desired setpoint
        step: setpoint change per step (default 1)
        time_step: waiting time per step (deault is 1s)"""
    start=pid.SetPoint
    if (start>final):
        r=numpy.arange(start,final,-step)
    else:
        r=numpy.arange(start,final,step)
    try:
        for a in r:
            leem_checkstop()
            pid.SetPoint=a
            print("Going to %f"%a)
            #while (gaugeMCH.Pressure_IG1 > pressure_limit):
            #     time.sleep(10)
            leem_abort.wait(time_step)
    except KeyboardInterrupt:
        # Nothing to restore, a ramp just stops where it got to.
        print("Ok, stopping the ramp. Setpoint left at %f"%pid.SetPoint)

def leemRampTemperatureROI(temp, step=1.0, time_step=1.0, exp=100, avg=0, saveImage=False):
    """ leemRampTemperatureROI( temp, temp_step=1.0, time_step=1.0, exposure=100, average=0, saveimage=False)"""
    (wfull,full,name)=leem_makenextfolder_and_inc()
    leem_log_call(name)
    expname="TEMPRAMP"+name
    start=leem_pid.SetPoint
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    if exp is None:
        exp=oldExposure
    if avg is None:
        avg=oldAverage
    uview.ContinousAcquisition=False
    time.sleep(0.5)
    uview.Exposure=exp
    uview.Average=avg
    leem_savesettings(full+"/"+expname+".txt")
    f=open(full+"/LOG.txt","w")
    leem_acquire_and_wait("throw-away")
    f.write("# Image number Temp SetTemp ROI time\n")
    if (start>temp):
        r=numpy.arange(start,temp,-step)
    else:
        r=numpy.arange(start,temp,step)
    c=0
    try:
        for a in r:
            leem_checkstop()
            leem_pid.SetPoint=a
            print("Going to %f"%a)
            leem_abort.wait(time_step)
            temp=leem2k.SampleTemperature
            leem_acquire_and_wait()
            roi=float(uview.IntensityROI1)
            t=time.localtime()
            timenow=time.strftime("%c", t)
            if (saveImage==True):
                savename=expname+"_%05d"%c
                if leem_savedat(wfull,savename):
                   print("Saved %s"%savename)
            print("Image %d Temp %f SetTemp %f ROI1 %f time %s"%(c,temp,a,roi,timenow))
            f.write("%d %f %f %f %s\n"%(c,temp,a,roi,timenow))
            c+=1
    except KeyboardInterrupt:
       print("Ok, ok, you want me to stop. Cleaning up.")
    f.flush()
    f.close()
    uview.Exposure=oldExposure
    uview.Average=oldAverage
    uview.ContinousAcquisition=True

def leemRampTemperatureTo(temp,temp_step=1.0,time_step=1.0,pressure_limit=1):
    """ leemRampTemperatureTo (temp, temp_step, time_step, pressure_limit)
    Ramp temperature using PID (must be on before!)
    Parameters: 
        temp: final temperature (in C)
        temp_step: temperature change per step (default 1C)
        time_step: waiting time per step (default 1s)
        pressure_limit: if pressure above the limit, will wait (default 1, no limit) """ 
    leem_log_call()
    pidRampTo(leem_pid,temp,temp_step,time_step,pressure_limit)
    
def doser1RampPowerTo(power,power_step=1.0,time_step=1.0,pressure_limit=1):
    """ leemRampTemperatureTo (temp, temp_step, time_step, pressure_limit)
    Ramp temperature using PID (must be on before!)
    Parameters: 
        power: final power (in W)
        power_step: temperature change per step (default 1C)
        time_step: waiting time per step (default 1s)
        pressure_limit: if pressure above the limit, will wait (default 1, no limit) """ 
    #pid=tango.DeviceProxy("leem/power/doser1_pid")
    leem_log_call()
    pidRampTo(doser1_pid,power,power_step,time_step,pressure_limit)

def doser2RampPowerTo(power,power_step=1.0,time_step=1.0,pressure_limit=1):
    """ leemRampTemperatureTo (temp, temp_step, time_step, pressure_limit)
    Ramp temperature using PID (must be on before!)
    Parameters: 
        power: final power (in W)
        power_step: temperature change per step (default 1C)
        time_step: waiting time per step (default 1s)
        pressure_limit: if pressure above the limit, will wait (default 1, no limit) """ 
    #pid=tango.DeviceProxy("leem/power/doser1_pid")
    leem_log_call()
    pidRampTo(doser2_pid,power,power_step,time_step,pressure_limit)

def leem_read(attr, fault_as_zero=False):
    """ Read a leem2k attribute, waiting out a ramp.

    Since ElmitecLEEM2k raises on LEEM2000 error replies instead of reading
    them as numbers, a module that is still ramping answers "ErrorCode -102":
    retry for up to 10 s. With fault_as_zero, "ErrorCode -101" is read as 0
    with a warning: the SPLEEM's LEEM2000 answers -101 for the image
    equalizers when their value is exactly 0.
    """
    t0=time.time()
    while True:
        try:
            return float(getattr(leem2k,attr))
        except tango.DevFailed as e:
            text=str(e)
            if "ErrorCode -101" in text and fault_as_zero:
                print("WARNING: %s answers ErrorCode -101 (fault), taken as 0"%attr)
                return 0.0
            if "ErrorCode -102" not in text or time.time()-t0>10.0:
                raise
        time.sleep(0.1)

def leem_savedat(wfull,savename):
    """ Save the current UView image as DAT. True if UView said "0"; otherwise
    print a warning, which used to be skipped silently. """
    res=uview.SaveImageAsDAT(wfull+"/"+savename)
    if res!="0":
        print("WARNING: UView did not save %s: %s"%(savename,res))
    return res=="0"

def leemARRESset():
    """ leemARRESset()
    Reads normal incidence IDX,IDY,IEX,IEY and ask to change the incidence for two endpoints.
    Used as reciprocal space positions in leemARRESrun()
    """
    b = numpy.zeros((3,4)) # Array to keep the settings for the ARRES scans. b[0] is the 0 position, b[1] is the 1st endpoint, b[2] is the 2nd endpoint. Second coordinate is (IllDefX,IllDefY,ImEqX,ImEqY)
    b[0]=leemReadDeflection()
    print("Normal Incidence condition IDX,IDY,IEX,IEY = ",b[0])
    input("Move to endpoint 1 in reciprocal space and press enter")
    b[1]=leemReadDeflection()
    print("Endpoint 1 condition IDX,IDY,IEX,IEY = ",b[1])
    leemSetDeflection(b[0])
    input("Move to endpoint 2 in reciprocal space and press enter")
    b[2]=leemReadDeflection()
    leemSetDeflection(b[0])
    print("Endpoint 2 condition IDX,IDY,IEX,IEY = ",b[2])
    return(b)

def _leem_arres_direction(wfull,full,expname,d,b0,b1,e,k,result,flip):
    """ One ARRES direction, from b0 (k=0) to b1 (k=1): LOG<d>.txt, images
    <expname>_<d>_NNNNN, arres<d>.npy/.pdf/.png. The array is appended to
    result before the scan starts, so a stopped scan still hands back what it
    measured; the files are written in any case. """
    f=open(full+"/LOG%d.txt"%d,"w")
    f.write("# Imagenumber k Energy(eV) roi time\n")
    arres=numpy.zeros((len(k),len(e)))
    result.append(arres)
    a=0
    try:
        for a_k,j in enumerate(k):
            beam=b0+j*(b1-b0)
            leemSetDeflection(beam)
            print("%5.1f"%beam[0],"%5.1f"%beam[1],"%5.1f"%beam[2],"%5.1f"%beam[3])
            for a_e,i in enumerate(e):
                leem_checkstop()
                leem2k.StartVoltage=float(i)
                t=time.localtime()
                timenow=time.strftime("%c", t)
                leem_acquire_and_wait()
                savename=expname+"_%d_%05d"%(d,a)
                if leem_savedat(wfull,savename):
                    print("%s %f %f "%(savename,j,i))
                roi=float(uview.IntensityROI1)
                arres[a_k,a_e]=roi
                f.write("%d %f %f %f %s\n"%(a,j,i,roi,timenow))
                a+=1
            print()
    finally:
        f.close()
        numpy.save(full+"/arres%d.npy"%d,arres)
        image=arres.swapaxes(0,1)
        if flip:
            image=numpy.flip(image,1)
        fig=Figure()
        ax=fig.add_subplot(111)
        ax.imshow(image,aspect="auto",origin="lower")
        fig.savefig(full+"/arres%d.pdf"%d)
        fig.savefig(full+"/arres%d.png"%d)

def leemARRESrun(E0,Ef,nE,nk,b,exp=400,avg=0,):
    """ leemARRESrun(E0,Ef,nE,nk,b,exp=400,avg=0)
    Runs a Angle-Resolved Reflection Electron Spectroscopy scan. Needs energy limits (E0,Ef, nE), and number of k points (nk).
    The incidence settings are read by leemARRESset(). With b of two rows
    (normal incidence and one endpoint) only one direction is measured.
    Press CTRL-C to stop: the deflectors go back to normal incidence and the
    camera to its previous settings.
    """
    b=numpy.asarray(b,dtype=float)
    (wfull,full,name)=leem_makenextfolder_and_inc()
    leem_log_call(name)
    expname="ARRES"+name
    oldExposure=uview.Exposure
    oldAverage=uview.Average
    if exp is None:
        exp=oldExposure
    if avg is None:
        avg=oldAverage
    result=[]
    try:
        uview.ContinousAcquisition=False
        time.sleep(0.5)
        uview.Exposure=exp
        uview.Average=avg
        leem_savesettings(full+"/"+expname+".txt")
        leem_acquire_and_wait("throw-away")

        f=open(full+"/"+expname+"_deflection.txt","w")
        f.write("Normal Incidence condition IDX %f IDY %f IEX %f IEY %f \n"%(b[0,0],b[0,1],b[0,2],b[0,3]))
        f.write("Endpoint 1 condition IDX %f IDY %f IEX %f IEY %f \n"%(b[1,0],b[1,1],b[1,2],b[1,3]))
        if len(b)>2:
            f.write("Endpoint 2 condition IDX %f IDY %f IEX %f IEY %f \n"%(b[2,0],b[2,1],b[2,2],b[2,3]))
        f.close()

        e=numpy.linspace(E0,Ef,nE)
        k=numpy.linspace(0.0,1.0,nk)
        # Direction 0 is plotted with k reversed, as before, so that the two
        # plots side by side run from endpoint 1 through normal incidence to
        # endpoint 2.
        _leem_arres_direction(wfull,full,expname,0,b[0],b[1],e,k,result,True)
        if len(b)>2:
            _leem_arres_direction(wfull,full,expname,1,b[0],b[2],e,k,result,False)
    except KeyboardInterrupt:
        print("Ok, stopping the ARRES scan. Let me clean up.")
    finally:
        leemSetDeflection(b[0])
        uview.Exposure=oldExposure
        uview.Average=oldAverage
        uview.ContinousAcquisition=True
    if len(b)==2:
        return(result[0] if result else None)
    return(tuple(result))

def leemSetDeflection(beam):
    leem2k.IllDefX = beam[0]
    leem2k.IllDefY = beam[1]
    leem2k.ImEqX = beam[2]
    leem2k.ImEqY = beam[3]

def leemReadDeflection():
    idx=leem_read("IllDefX")
    idy=leem_read("IllDefY")
    iex=leem_read("ImEqX",fault_as_zero=True)
    iey=leem_read("ImEqY",fault_as_zero=True)
    return(numpy.array([idx,idy,iex,iey]))
