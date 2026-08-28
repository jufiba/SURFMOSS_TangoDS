#!/usr/bin/env python3
"""Check every Tango reference in the synoptics against the database.

A JDraw drawing that names a device or an attribute which does not exist fails
silently: the element is simply dead at runtime, and on a wall-mounted synoptic
nobody notices until someone needs the number it was supposed to show. Nothing
ties the drawings to the database, so the two drift apart on their own -- the
same failure mode tools/check_xmi.py exists for between a model and its code.

Run on 28-Aug-2026 over the eight drawings, this found six broken references
out of 119. Two were stale names left by hardware that had been replaced
(VarianMultiGauge's Pressure_IG1, still asked of the Granville Phillips 350
that took over leem/vacuum/gaugeMCH), one was a misspelling that had never
worked in two places (mossbauer/termperature/criostat), and four pointed at
retired instruments.

WHAT IT CHECKS

For every `name:"..."` in every .jdw file:

    device does not exist in the DB      the element is dead
    device exists, member does not       the element is dead
    device exists, is not running        cannot be checked, reported separately

The last case is not a fault. A drawing for an instrument that is switched off
is correct; it just cannot be verified today. Those are listed apart so they do
not drown the real findings.

Usage:  python3 tools/check_synoptics.py [--root PATH] [--self-test] [file ...]
Exit:   0 nothing broken, 1 broken references, 2 the self-test failed or it
        could not run.
"""

import collections
import glob
import os
import re
import sys

REFERENCE = re.compile(r'name:"([^"]+)"')


def references(path):
    """(reference, line number) for every name: in one drawing."""
    out = []
    with open(path, encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, 1):
            found = REFERENCE.search(line)
            if found and "/" in found.group(1):
                out.append((found.group(1), number))
    return out


def split(reference):
    """(device, member) -- member is None for a bare device reference."""
    parts = reference.split("/")
    if len(parts) < 3:
        return (None, None)
    return ("/".join(parts[:3]), parts[3] if len(parts) > 3 else None)


class Catalogue:
    """The database's answer about a device, asked once per device."""

    def __init__(self, db, tango):
        self.db = db
        self.tango = tango
        self.known = {}

    def look_up(self, device):
        if device not in self.known:
            self.known[device] = self._ask(device)
        return self.known[device]

    def _ask(self, device):
        try:
            self.db.get_device_info(device)
        except Exception:                                      # noqa: BLE001
            return ("absent", None)
        try:
            proxy = self.tango.DeviceProxy(device)
            proxy.set_timeout_millis(4000)
            members = {a.lower() for a in proxy.get_attribute_list()}
            members |= {c.cmd_name.lower() for c in proxy.command_list_query()}
            return ("running", members)
        except Exception:                                      # noqa: BLE001
            return ("stopped", None)


def check(paths, catalogue):
    dead, unverifiable = [], []
    total = 0
    for path in paths:
        for reference, number in references(path):
            device, member = split(reference)
            if device is None:
                continue
            total += 1
            state, members = catalogue.look_up(device)
            where = "%s:%d" % (os.path.basename(path), number)
            if state == "absent":
                dead.append((where, reference, "no such device in the database"))
            elif state == "stopped":
                unverifiable.append((where, reference))
            elif member and member.lower() not in members:
                dead.append((where, reference,
                             "the device has no %r" % member))
    return total, dead, unverifiable


# ------------------------------------------------------------- the self-test
FIXTURE = '''JDFile v11 {
  Global {
  }
  JDSwingObject {
    name:"leem/vacuum/gaugeMCH/Pressure"
  }
  JDSwingObject {
    name:"leem/vacuum/gaugeMCH/Pressure_IG1"
  }
  JDSwingObject {
    name:"leem/measurement/PositionXY/Position"
  }
  JDLabel {
    text:"not a reference"
  }
  JDSwingObject {
    name:"leem/vacuum/scrollPump"
  }
}
'''


class FakeCatalogue:
    """One device that runs, one that is absent, one registered but stopped."""

    def look_up(self, device):
        if device == "leem/vacuum/gaugeMCH":
            return ("running", {"pressure", "filament1on", "state"})
        if device == "leem/vacuum/scrollPump":
            return ("stopped", None)
        return ("absent", None)


def self_test(repo):
    ok = True

    found = references_from_text(FIXTURE)
    if len(found) != 4:
        print("SELF-TEST FAILED: the fixture holds four references and a label "
              "that is not one; %d were read" % len(found))
        ok = False

    total, dead, unverifiable = check_text(FIXTURE, FakeCatalogue())
    reasons = {reference: why for (_, reference, why) in dead}

    if "leem/vacuum/gaugeMCH/Pressure" in reasons:
        print("SELF-TEST FAILED: an attribute the device has must not be "
              "reported")
        ok = False
    if "leem/vacuum/gaugeMCH/Pressure_IG1" not in reasons:
        print("SELF-TEST FAILED: an attribute the device does not have is the "
              "case this tool exists for, and it was not reported")
        ok = False
    if "leem/measurement/PositionXY/Position" not in reasons:
        print("SELF-TEST FAILED: a device absent from the database must be "
              "reported")
        ok = False
    if len(unverifiable) != 1:
        print("SELF-TEST FAILED: a registered but stopped device is not a "
              "fault and must be listed apart; %d were" % len(unverifiable))
        ok = False
    if any("scrollPump" in reference for (_, reference, _) in dead):
        print("SELF-TEST FAILED: a stopped device was reported as broken. A "
              "drawing for a switched-off instrument is correct.")
        ok = False

    # A bare device reference with no member must not be judged on members.
    total2, dead2, _ = check_text('JDFile v11 {\n  JDBar {\n'
                                  '    name:"leem/vacuum/gaugeMCH"\n  }\n}\n',
                                  FakeCatalogue())
    if dead2:
        print("SELF-TEST FAILED: a reference to a device alone, with no "
              "attribute, was reported as broken")
        ok = False

    if ok:
        print("the reader and the verdicts check out against the fixture")
    return ok


def references_from_text(text):
    out = []
    for number, line in enumerate(text.split("\n"), 1):
        found = REFERENCE.search(line)
        if found and "/" in found.group(1):
            out.append((found.group(1), number))
    return out


def check_text(text, catalogue):
    dead, unverifiable = [], []
    total = 0
    for reference, number in references_from_text(text):
        device, member = split(reference)
        if device is None:
            continue
        total += 1
        state, members = catalogue.look_up(device)
        where = "<fixture>:%d" % number
        if state == "absent":
            dead.append((where, reference, "no such device in the database"))
        elif state == "stopped":
            unverifiable.append((where, reference))
        elif member and member.lower() not in members:
            dead.append((where, reference, "the device has no %r" % member))
    return total, dead, unverifiable


DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        index = args.index("--root")
        repo = args[index + 1]
        del args[index:index + 2]
    only_test = "--self-test" in args
    if only_test:
        args.remove("--self-test")

    if not self_test(repo):
        print("\nthe method does not pass its own tests; the result of a run "
              "would mean nothing")
        return 2
    if only_test:
        return 0

    try:
        import tango
    except ImportError:
        print("PyTango is not installed here, so the database cannot be "
              "asked. This part runs on a Pi.")
        return 2
    try:
        db = tango.Database()
    except Exception as exc:                                   # noqa: BLE001
        print("cannot reach the Tango database: %s" % exc)
        return 2

    paths = args or sorted(glob.glob(os.path.join(repo, "synoptics", "*.jdw")))
    if not paths:
        print("no .jdw files found")
        return 2

    total, dead, unverifiable = check(paths, Catalogue(db, tango))

    if dead:
        print("\nBROKEN -- these elements are dead at runtime:")
        for where, reference, why in dead:
            print("   %-26s %-46s %s" % (where, reference, why))
    if unverifiable:
        print("\nnot checkable, the device is registered but not running "
              "(the drawing is not necessarily wrong):")
        seen = set()
        for where, reference in unverifiable:
            device = split(reference)[0]
            if device not in seen:
                seen.add(device)
                print("   %-26s %s" % (where, device))
    print("\n%d references in %d drawings, %d broken"
          % (total, len(paths), len(dead)))
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
