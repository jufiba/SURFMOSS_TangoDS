#!/usr/bin/env python3
"""Mail when a LEEM acquisition stops writing data.

Every acquisition in scripts/LEEMmacros.py takes each image like this:

    uview.AcquireSingleImage()
    while (uview.ContinousAcquisition):
        pass

That loop has no deadline and no sleep, so if UView wedges -- the
"WaitForSingleObject failed 100000x in a row" window -- the macro spins there
for ever and the run silently stops advancing. Pressing "acquire" in UView by
hand is what unblocks it. ARRES is the one that meets this most often, only
because it chains the most images (nk x nE).

This watchdog does NOT look at UView. It watches the *data* instead: the
mtime of the newest file under the day folder. One image written is one .dat
plus a line in LOG0.txt, so a run that is advancing keeps that mtime moving,
and a run that has wedged stops it dead. Nothing here touches UView's single
socket -- which the busy-wait above is already hammering, and which is a
plausible contributor to the wedge in the first place (ElmitecUview.py:327
records aip and AcquisitionInProgress "stepping on each other" on that same
socket once before).

Deliberately NOT importing LEEMmacros: that module opens DeviceProxies to
Uview and LEEM2k at import time, and the whole point here is to add no
traffic to the instrument. macros.dat is four comma-separated fields and is
parsed directly.

Start it by hand when you start a long run, Ctrl-C when the run ends. It is
not automatic on purpose: when a run finishes normally the files also stop
being written, and ContinousAcquisition cannot tell the two apart (it reads 1
both while acquiring a single image and while the live view is running, which
is what leemARRESrun leaves on when it finishes).

Usage:
    python3 tools/leem_acquisition_watchdog.py                 # 5 min, mails
    python3 tools/leem_acquisition_watchdog.py --timeout 10
    python3 tools/leem_acquisition_watchdog.py --test-mail     # prove the mail path
    python3 tools/leem_acquisition_watchdog.py --dry-run       # print, never mail

Exit: 0 on Ctrl-C, 2 if it could not start at all.
"""

import argparse
import atexit
import os
import signal
import sys
import time
from datetime import date

DEFAULT_COUNTER = "/Superficies/LEEM_Madrid/macros.dat"
DEFAULT_NOTIFIER = "lab/alarm/notifier"


def raise_keyboard_interrupt(signum, frame):
    """SIGTERM -> the same clean exit Ctrl-C takes."""
    raise KeyboardInterrupt()


_cleanup_registered = False


def register_tango_cleanup():
    """Shut the ORB down at the start of shutdown, before the race.

    Seen on tvips on 20-Nov-2026: `--test-mail` sent its mail and then exited
    with a segmentation fault. Same thing LEEMmacros v3.7 hit and fixed the
    same way -- omniORB's client threads racing Python finalisation, which
    shows up or not depending on the pytango build (it does not reproduce on
    wolframite). Guarded for the same reason v3.7 guards it: cleanup() is a
    no-op or raises depending on that build.

    Registered on the first real tango import rather than at module level, so
    --dry-run still runs where pytango is not installed at all.
    """
    global _cleanup_registered
    if _cleanup_registered:
        return
    _cleanup_registered = True

    def _tango_cleanup():
        try:
            import tango
            tango.ApiUtil.cleanup()
        except Exception:                                     # noqa: BLE001
            pass

    atexit.register(_tango_cleanup)


def stamp(when=None):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when))


def say(text):
    """One line, flushed: this runs in a terminal someone is watching over
    VNC, and a buffered watchdog looks dead."""
    print("%s  %s" % (stamp(), text), flush=True)


def read_counter(path):
    """(prefix, dayfolder) out of macros.dat.

    leem_getfolder() expects four fields (wprefix,prefix,dayfolder,exp), but
    leemSetDailyFolder() writes only three (prefix,dayfolder,exp) -- a latent
    bug in LEEMmacros that would also break this script, so both shapes are
    accepted rather than depending on which wrote the file last.
    """
    with open(path) as handle:
        fields = handle.readline().strip().split(",")
    if len(fields) == 4:
        return fields[1], fields[2]
    if len(fields) == 3:
        return fields[0], fields[1]
    raise ValueError("%s has %d comma-separated fields, expected 3 or 4: %r"
                     % (path, len(fields), fields))


def day_folders(prefix, dayfolder):
    """The folders worth watching: the one macros.dat names and today's.

    Both, because a run started before midnight keeps writing into
    yesterday's folder while date.today() has already moved on.
    """
    today = date.today()
    names = {dayfolder, "%04d%02d%02d" % (today.year, today.month, today.day)}
    return [os.path.join(prefix, name) for name in sorted(names)]


def newest_file(folders):
    """(mtime, path) of the most recently written file, or (None, None).

    A stat that fails is skipped rather than fatal: a .dat being written at
    this instant may vanish from the listing between scandir and stat.
    """
    best_time, best_path = None, None
    for folder in folders:
        for root, _dirs, files in os.walk(folder):
            for name in files:
                path = os.path.join(root, name)
                try:
                    when = os.stat(path).st_mtime
                except OSError:
                    continue
                if best_time is None or when > best_time:
                    best_time, best_path = when, path
    return best_time, best_path


class Mailer:
    """SendMessage on the AlarmNotifier, reconnecting on failure.

    SendMessage is the sanctioned route for this -- its own comment says
    "for a person at a keyboard or an end-of-run script". A failure to mail
    is reported and retried, never fatal: a watchdog that dies because the
    mail server hiccuped is worse than no watchdog.
    """

    def __init__(self, device, dry_run=False):
        self.device = device
        self.dry_run = dry_run
        self.proxy = None

    def send(self, subject, body):
        if self.dry_run:
            say("[dry-run] NO se envia correo:")
            say("[dry-run]   asunto: %s" % subject)
            for line in body.splitlines():
                say("[dry-run]   %s" % line)
            return True
        try:
            import tango
            register_tango_cleanup()
            if self.proxy is None:
                self.proxy = tango.DeviceProxy(self.device)
            self.proxy.SendMessage([subject, body])
            say("correo enviado: %s" % subject)
            return True
        except Exception as exc:                              # noqa: BLE001
            self.proxy = None
            say("NO se pudo enviar el correo (%s): %s" % (self.device, exc))
            say("  asunto era: %s" % subject)
            return False


def body_for_stall(folders, age, newest, newest_at):
    return "\n".join([
        "La adquisicion del LEEM lleva %.1f minutos sin escribir nada." % (age / 60.0),
        "",
        "Ultimo fichero escrito: %s" % (newest or "(ninguno)"),
        "A las:                  %s" % (stamp(newest_at) if newest_at else "-"),
        "Carpetas vigiladas:     %s" % ", ".join(folders),
        "",
        "Pinta de ser el cuelgue conocido de UView: el bucle de espera de",
        "LEEMmacros (while uview.ContinousAcquisition: pass) no tiene timeout,",
        "asi que se queda girando indefinidamente.",
        "",
        "Que mirar por VNC en el ordenador de adquisicion:",
        "  - si UView tiene la ventana 'WaitForSingleObject failed 100000x in a row'",
        "  - darle al boton de adquirir en UView suele desatascarlo",
        "",
        "Aviso de tools/leem_acquisition_watchdog.py",
    ])


def body_for_resume(age_was, newest, newest_at):
    return "\n".join([
        "La adquisicion del LEEM ha vuelto a escribir.",
        "",
        "Estuvo parada al menos %.1f minutos." % (age_was / 60.0),
        "Fichero mas reciente: %s" % (newest or "(ninguno)"),
        "A las:                %s" % (stamp(newest_at) if newest_at else "-"),
        "",
        "Aviso de tools/leem_acquisition_watchdog.py",
    ])


def main(argv):
    parser = argparse.ArgumentParser(
        description="Avisa por correo si la adquisicion del LEEM deja de "
                    "escribir datos.")
    parser.add_argument("--timeout", type=float, default=5.0,
                        help="minutos sin escribir antes de avisar (5)")
    parser.add_argument("--poll", type=float, default=30.0,
                        help="segundos entre comprobaciones (30)")
    parser.add_argument("--remind", type=float, default=30.0,
                        help="minutos entre recordatorios mientras sigue "
                             "parada; 0 los desactiva (30)")
    parser.add_argument("--counter", default=DEFAULT_COUNTER,
                        help="fichero macros.dat (%s)" % DEFAULT_COUNTER)
    parser.add_argument("--folder", action="append", default=None,
                        help="vigilar esta carpeta en vez de deducirla de "
                             "macros.dat; se puede repetir")
    parser.add_argument("--notifier", default=DEFAULT_NOTIFIER,
                        help="device del AlarmNotifier (%s)" % DEFAULT_NOTIFIER)
    parser.add_argument("--dry-run", action="store_true",
                        help="imprime los avisos, no manda ningun correo")
    parser.add_argument("--test-mail", action="store_true",
                        help="manda un correo de prueba y sale")
    args = parser.parse_args(argv[1:])

    # Ctrl-C already works in the foreground. This is for the other way it
    # gets run: launched with "&" or nohup over VNC, where bash hands the
    # child SIGINT set to ignore, so Ctrl-C and even "kill -INT" do nothing
    # and only "kill" would reach it. Routing SIGTERM through the same
    # KeyboardInterrupt path means it stops the same tidy way either way.
    signal.signal(signal.SIGTERM, raise_keyboard_interrupt)

    mailer = Mailer(args.notifier, args.dry_run)

    if args.test_mail:
        ok = mailer.send(
            "prueba del watchdog de adquisicion",
            "Correo de prueba de tools/leem_acquisition_watchdog.py.\n"
            "Si lo recibes, la ruta de aviso funciona.\n")
        return 0 if ok else 2

    timeout = args.timeout * 60.0
    remind = args.remind * 60.0

    if args.folder:
        folders = list(args.folder)
        say("vigilando las carpetas indicadas: %s" % ", ".join(folders))
    else:
        try:
            prefix, dayfolder = read_counter(args.counter)
        except Exception as exc:                              # noqa: BLE001
            say("no puedo leer %s: %s" % (args.counter, exc))
            say("usa --folder para indicar la carpeta a mano")
            return 2
        folders = day_folders(prefix, dayfolder)
        say("segun %s: prefix=%s dayfolder=%s" % (args.counter, prefix, dayfolder))

    existing = [f for f in folders if os.path.isdir(f)]
    if not existing:
        say("ninguna de estas carpetas existe todavia: %s" % ", ".join(folders))
        say("seguire mirando por si aparecen")
    else:
        say("vigilando: %s" % ", ".join(existing))
    say("aviso si pasan %.1f min sin escribir; compruebo cada %.0f s"
        % (args.timeout, args.poll))

    # Armado: no avisar hasta tener constancia de que la adquisicion va.
    # Si al arrancar el fichero mas reciente ya es fresco, la tanda esta viva
    # y vigilamos desde ya; si no, esperamos a ver la primera escritura. Sin
    # esto, arrancar el watchdog antes de lanzar la tanda daria un aviso falso
    # inmediato por culpa de los ficheros viejos del dia.
    armed = False
    stalled = False
    last_mail = 0.0
    last_seen_time, last_seen_path = newest_file(folders)
    if last_seen_time is not None and time.time() - last_seen_time < timeout:
        armed = True
        say("adquisicion viva (ultimo: %s, %s). Vigilando."
            % (os.path.basename(last_seen_path), stamp(last_seen_time)))
    else:
        say("esperando a ver la primera escritura antes de empezar a vigilar")

    try:
        while True:
            time.sleep(args.poll)
            now = time.time()
            newest_time, newest_path = newest_file(folders)

            if newest_time is None:
                continue

            if last_seen_time is None or newest_time > last_seen_time:
                if not armed:
                    armed = True
                    say("primera escritura vista (%s). Vigilando."
                        % os.path.basename(newest_path))
                last_seen_time, last_seen_path = newest_time, newest_path

            if not armed:
                continue

            age = now - last_seen_time

            if not stalled and age > timeout:
                stalled = True
                last_mail = now
                say("PARADA: %.1f min sin escribir (ultimo: %s)"
                    % (age / 60.0, last_seen_path))
                mailer.send(
                    "adquisicion del LEEM parada (%.0f min sin escribir)"
                    % (age / 60.0),
                    body_for_stall(folders, age, last_seen_path, last_seen_time))

            elif stalled and age <= timeout:
                stalled = False
                say("reanudada (ultimo: %s)" % os.path.basename(last_seen_path))
                mailer.send(
                    "adquisicion del LEEM reanudada",
                    body_for_resume(age, last_seen_path, last_seen_time))

            elif stalled and remind > 0 and now - last_mail >= remind:
                last_mail = now
                say("sigue parada: %.1f min" % (age / 60.0))
                mailer.send(
                    "adquisicion del LEEM sigue parada (%.0f min)"
                    % (age / 60.0),
                    body_for_stall(folders, age, last_seen_path, last_seen_time))

    except KeyboardInterrupt:
        say("parado a mano")
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
