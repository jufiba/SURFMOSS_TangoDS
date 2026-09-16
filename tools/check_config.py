#!/usr/bin/env python3
"""Two database-wide checks that no single device server can make for itself.

Both come from failures found on 15/16-sep-2026, and both are the same shape:
a property that is perfectly valid on its own device and wrong only in
relation to another one. A device server cannot see that, because it only
ever sees its own properties.

WHAT IT REPORTS

    shared serial port
        Two devices configured on the same SerialPort. They then interleave
        on one line and each reads the other's answers. Found on pi-uleem
        (leem/vacuum/gaugeEvap and leem/safety/hygrometer both on ...1.1.3,
        the gauge answering NAK to every PR1) and on pi-vsm
        (vsm/measurement/Polarity and vsm/measurement/DVMlockin, the
        multimeter stuck in FAULT). Neither device could tell: from inside,
        each just saw an instrument answering nonsense.

    property written but not in force
        A device property whose last change is newer than the start of the
        server that holds it. Device properties are read in init_device, so
        until the server restarts the written value is not the value in use,
        and every tool that reads the database -- including the two checks
        below -- reports the intention rather than the behaviour. Found
        immediately on xps/safety/interlockxraygun: GateStates was set to
        ON,FAULT at 13:57:15 on 16-sep-2026 and AnalogInterlock/1 had started
        at 13:54:44, so the running gate still opened on ON alone.

    gate without FAULT
        An AnalogInterlock whose GateStates does not include FAULT. Whether
        it should is a per-device decision and the server deliberately does
        not override it -- it only writes a standing note in its own Status.
        This lists them so the decision gets made deliberately rather than by
        default. leem/power/hv2 was found reporting FAULT while holding 619 V
        on the LEEM's microchannel plate, with leem/safety/interlockhv2
        reading "not evaluating": an energised supply outside its own water
        interlock, exactly while it was misbehaving.

Read-only: it opens the database and reads properties. It writes nothing and
contacts no instrument.

Usage:  python3 tools/check_config.py
Exit:   0 nothing to report, 1 something to look at, 2 could not run.
"""

import collections
import datetime
import re
import sys

PORT_PROPERTIES = ("SerialPort", "Port", "Device", "SerialDevice", "TTY")


def devices_by_server(db):
    """(server, device, host) for everything registered, host lower-cased."""
    out = []
    for srv in db.get_server_list():
        try:
            host = (db.get_server_info(srv).host or "?").split(".")[0].lower()
        except Exception:
            host = "?"
        for cls in db.get_server_class_list(srv):
            for dev in db.get_device_name(srv, cls):
                out.append((srv, dev, host))
    return out


def parse_started(text):
    """'16th September 2026 at 13:54:44' -> datetime, or None.

    The two timestamps this tool compares come from different corners of the
    database and are formatted differently; neither is parseable with a single
    strptime. Returning None rather than raising keeps one odd device from
    hiding every other finding.
    """
    if not text:
        return None
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text).replace(" at ", " ")
    for fmt in ("%d %B %Y %H:%M:%S", "%d %b %Y %H:%M:%S"):
        try:
            return datetime.datetime.strptime(cleaned.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_changed(text):
    """'16/09/2026 13:57:15' -> datetime, or None."""
    if not text:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    return None


def written_but_not_running(db, registry):
    """Properties changed after the server that reads them last started.

    Device properties are read once, in init_device. A value written later is
    in the database and not in the process, and nothing anywhere says so --
    which also means every other check in this tool, and every look at Jive,
    describes the intention rather than what is actually running.
    """
    hits = []
    unparsed = []
    for srv, dev, host in registry:
        low = dev.lower()
        if low.startswith("tango/admin/") or low.startswith("dserver/"):
            # The Starter's own properties: logging targets, polled_attr,
            # StartDsPath. Tango's housekeeping, not the lab's configuration,
            # and every one of them would be listed for ever.
            continue
        try:
            info = db.get_device_info(dev)
        except Exception:
            continue
        if not info.exported:
            continue                      # not running: nothing to be stale
        started = parse_started(info.started_date)
        if started is None:
            unparsed.append((dev, info.started_date))
            continue
        try:
            names = list(db.get_device_property_list(dev, "*"))
        except Exception:
            continue
        for name in names:
            if name.startswith("__"):
                continue                  # __SubDevices and friends: Tango
                #                           writes these itself at runtime
            try:
                hist = db.get_device_property_history(dev, name)
            except Exception:
                continue
            if not len(hist):
                continue
            changed = parse_changed(hist[-1].get_date())
            if changed is None or changed <= started:
                continue
            try:
                value = list(hist[-1].get_value().value_string)
            except Exception:
                value = []
            hits.append((dev, srv, host, name, value, changed, started))
    return hits, unparsed


def shared_ports(db, registry):
    """Devices on the same host sharing one serial port.

    Keyed by (host, port): the same /dev path on two different machines is two
    different cables and perfectly fine.
    """
    claims = collections.defaultdict(list)
    for srv, dev, host in registry:
        props = db.get_device_property(dev, list(PORT_PROPERTIES))
        for name, values in props.items():
            if len(values) and str(values[0]).startswith("/dev"):
                claims[(host, str(values[0]))].append((dev, srv, name))

    hits = []
    for (host, port), who in sorted(claims.items()):
        if len(who) > 1:
            hits.append((host, port, who))
    return hits


def gates_without_fault(db, registry):
    """AnalogInterlock devices whose GateStates leaves FAULT out."""
    hits = []
    for srv, dev, host in registry:
        if not srv.lower().startswith("analoginterlock/"):
            continue
        props = db.get_device_property(dev, ["GateDevice", "GateStates"])
        gatedev = props["GateDevice"][0] if len(props["GateDevice"]) else ""
        gateraw = props["GateStates"][0] if len(props["GateStates"]) else ""
        if not gatedev.strip():
            continue                      # no gate at all: nothing to decide
        names = [s.strip().upper() for s in gateraw.split(",") if s.strip()]
        if "FAULT" not in names:
            hits.append((dev, host, gatedev, gateraw))
    return hits


def main():
    try:
        import tango
    except ImportError as exc:
        print("cannot import PyTango (%s)" % exc)
        return 2
    try:
        db = tango.Database()
        registry = devices_by_server(db)
    except Exception as exc:
        print("cannot read the database: %s" % exc)
        return 2

    found = 0

    # First, because it qualifies everything else: a database that has been
    # written to since the server started does not describe what is running.
    print("== Properties written but not in force (server not restarted) ==")
    hits, unparsed = written_but_not_running(db, registry)
    if not hits:
        print("   none")
    for dev, srv, host, name, value, changed, started in hits:
        found += 1
        shown = repr(value)
        if len(shown) > 110:
            shown = shown[:107] + "...'"
        print("   %s  %s = %s" % (dev, name, shown))
        print("       written %s, but %s on %s started %s"
              % (changed.strftime("%d-%b %H:%M:%S"), srv, host,
                 started.strftime("%d-%b %H:%M:%S")))
    if hits:
        print("   (a server with a reload command -- AlarmNotifier's"
              " ReloadRules -- may")
        print("    already have picked the value up without restarting;"
              " this cannot tell)")
    for dev, text in unparsed:
        print("   (could not read a start time for %s: %r)" % (dev, text))
    print()

    print("== Serial ports claimed by more than one device ==")
    hits = shared_ports(db, registry)
    if not hits:
        print("   none")
    for host, port, who in hits:
        found += 1
        print("   %s  %s" % (host, port))
        for dev, srv, name in who:
            print("       %-34s %-24s (%s)" % (dev, srv, name))
    print()

    print("== Gated interlocks whose GateStates leaves FAULT out ==")
    print("   (a decision, not a defect: include FAULT for any gate that can")
    print("    be energised while faulted, leave it out knowingly otherwise)")
    hits = gates_without_fault(db, registry)
    if not hits:
        print("   none")
    for dev, host, gatedev, gateraw in hits:
        found += 1
        print("   %-32s on %-16s gate %-24s GateStates=%r"
              % (dev, host, gatedev, gateraw))

    print()
    print("%d thing(s) to look at" % found)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
