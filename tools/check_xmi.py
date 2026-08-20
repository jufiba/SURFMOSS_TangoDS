#!/usr/bin/env python3
"""Report where a device server's .xmi model and its .py have drifted apart.

The .xmi is documentation of the interface, not a source POGO regenerates
from: POGO 9.10.6 cannot round-trip these servers (see the migration
reference). Nothing keeps the two in step automatically, and the drift found
by hand in August 2026 -- an attribute present only in the code, a property
default only in the model, a whole new interface the model knew nothing about
-- had gone unnoticed for months. This is that check, made repeatable.

Reports only. It never edits the .xmi or the .py.

The .py is parsed with `ast`, never imported: most of these servers cannot be
imported off the Pi at all (RPi.GPIO, lgpio, PyNUT, serial).

Usage:  python3 tools/check_xmi.py [--root PATH] [server ...]

        --root  repository to check; defaults to the one this script lives in,
                so it can be pointed at a worktree of an older commit to see
                what it would have caught back then.

Exit:   0 clean, 1 divergences found, 2 could not run.
"""

import ast
import os
import sys
import xml.etree.ElementTree as ET

SKIP = {"PANIC"}
ROOTS = (".", "inactive", "deprecated")

# POGO's dataType names, collapsed to the family that actually matters. Width
# is deliberately kept (int vs uint) but spelling is not: the PythonHL template
# writes 'float' for a DoubleType and the newer one writes 'DevDouble', and
# neither is a divergence.
XMI_TYPES = {
    "DoubleType": "float", "FloatType": "float",
    "IntType": "int", "LongType": "int", "ShortType": "int",
    "DevLong64Type": "int", "LongLongType": "int",
    "UIntType": "uint", "ULongType": "uint", "UShortType": "uint",
    "UCharType": "uint", "ULongLongType": "uint",
    "StringType": "str", "ConstStringType": "str",
    "BooleanType": "bool",
    "StateType": "state",
    "VoidType": "void",
    "EnumType": "enum",
}

PY_TYPES = {
    "double": "float", "float": "float", "DevDouble": "float",
    "DevFloat": "float", "float64": "float", "float32": "float",
    "int": "int", "int16": "int", "int32": "int", "int64": "int",
    "DevLong": "int", "DevShort": "int", "DevLong64": "int",
    "uint": "uint", "uint16": "uint", "uint32": "uint", "uint64": "uint",
    "DevULong": "uint", "DevUShort": "uint", "DevULong64": "uint",
    "uchar": "uint", "DevUChar": "uint", "char": "uint",
    "str": "str", "string": "str", "DevString": "str",
    "bool": "bool", "DevBoolean": "bool",
    "DevEnum": "enum",
    "DevState": "state",
    "None": "void",
}


def norm_xmi(node):
    """Canonical type of an <argin>/<argout>/<type>/<dataType> element."""
    if node is None:
        return "void"
    t = node.get("{http://www.w3.org/2001/XMLSchema-instance}type", "")
    t = t.split(":")[-1]
    array = t.endswith("ArrayType")
    if array:
        t = t[: -len("ArrayType")] + "Type"
    base = XMI_TYPES.get(t, t or "?")
    return base + "[]" if array else base


def norm_py(node):
    """Canonical type of a dtype= expression in the .py."""
    if node is None:
        return "void"
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "void"
        return PY_TYPES.get(str(node.value), str(node.value))
    if isinstance(node, (ast.Tuple, ast.List)):
        inner = node.elts[0] if node.elts else None
        # (('uint16',),) is an image, ('uint16',) a spectrum; one [] is enough
        # to tell either from a scalar, which is the distinction that matters.
        return norm_py(inner) + "[]"
    if isinstance(node, ast.Attribute):          # e.g. tango.DevDouble
        return PY_TYPES.get(node.attr, node.attr)
    if isinstance(node, ast.Name):
        return PY_TYPES.get(node.id, node.id)
    return "?"


def kw(call, name):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


def const(node):
    return node.value if isinstance(node, ast.Constant) else None


def access_of(call):
    """AttrWriteType of an attribute() call; READ when unstated, as PyTango."""
    node = kw(call, "access")
    if node is None:
        return "READ"
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant):
        return str(node.value)
    return "?"


def called(node, name):
    return (isinstance(node, ast.Call) and
            ((isinstance(node.func, ast.Name) and node.func.id == name) or
             (isinstance(node.func, ast.Attribute) and node.func.attr == name)))


# A property default is written two different ways for the same value: POGO
# stores lines of text, the code has a Python literal. "6,13" against ['6,13']
# is not a divergence, and neither is 3 against "3". Everything is flattened to
# a string here, and compared numerically as well where both sides look like
# numbers, so that the check reports disagreements and not spelling.

UNCOMPARABLE = object()      # multi-line default; do not force it to a verdict


def default_from_py(node):
    """default_value= as text, or None if absent, or UNCOMPARABLE."""
    if node is None:
        return None
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return str(node.value).lower()
        return str(node.value)
    if isinstance(node, (ast.List, ast.Tuple)):
        if len(node.elts) == 1:
            return default_from_py(node.elts[0])
        return UNCOMPARABLE
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = default_from_py(node.operand)
        return None if inner in (None, UNCOMPARABLE) else "-" + inner
    return UNCOMPARABLE          # an expression; not worth guessing at


def default_from_xmi(prop):
    """<DefaultPropValue> as text, or None if absent, or UNCOMPARABLE."""
    values = [(d.text or "").strip() for d in prop.findall("DefaultPropValue")]
    values = [v for v in values if v]
    if not values:
        return None
    if len(values) > 1:
        return UNCOMPARABLE
    return values[0]


def same_default(a, b):
    """True when two default spellings mean the same value."""
    if a.strip() == b.strip():
        return True

    def number(text):
        text = text.strip()
        try:
            return float(text)
        except ValueError:
            pass
        try:
            return float(int(text, 0))   # 0x0925 in the code, 2341 in the model
        except ValueError:
            return None

    na, nb = number(a), number(b)
    if na is not None and nb is not None:
        return na == nb
    return a.strip().lower() == b.strip().lower()   # True vs true


def read_py(path):
    """Interface declared in a .py, or None if it is not the modern template."""
    tree = ast.parse(open(path, encoding="utf-8", errors="replace").read())

    cls = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            if "Device" in bases:
                cls = node
                break
    if cls is None:
        return None                      # old POGO template, or not a server

    attrs, cmds, props = {}, {}, {}
    for node in cls.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if not targets:
                continue
            name = targets[0]
            if called(node.value, "attribute"):
                attrs[name] = (norm_py(kw(node.value, "dtype")),
                               access_of(node.value),
                               const(kw(node.value, "polling_period")))
            elif called(node.value, "device_property"):
                props[name] = (norm_py(kw(node.value, "dtype")),
                               default_from_py(kw(node.value, "default_value")))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if called(dec, "attribute"):
                    attrs[node.name] = (norm_py(kw(dec, "dtype")),
                                        access_of(dec),
                                        const(kw(dec, "polling_period")))
                elif called(dec, "command"):
                    cmds[node.name] = (norm_py(kw(dec, "dtype_in")),
                                       norm_py(kw(dec, "dtype_out")))
                elif isinstance(dec, ast.Name) and dec.id == "command":
                    cmds[node.name] = ("void", "void")
    return attrs, cmds, props


def read_xmi(path):
    root = ET.parse(path).getroot()
    attrs, cmds, props, states = {}, {}, {}, {}
    for a in root.iter("attributes"):
        period = a.get("polledPeriod") or "0"
        # Rank lives in attType, not in dataType: a spectrum of ULong is
        # <attributes attType="Spectrum"> with <dataType ULongType>, which on
        # the Python side is dtype=('uint64',).
        rank = {"Spectrum": "[]", "Image": "[][]"}.get(a.get("attType", ""), "")
        attrs[a.get("name")] = (norm_xmi(a.find("dataType")) + rank,
                                a.get("rwType", "READ"),
                                int(period) if period.isdigit() else 0)
    for c in root.iter("commands"):
        name = c.get("name")
        if name in ("State", "Status"):        # inherited from Device_Impl
            continue
        argin, argout = c.find("argin"), c.find("argout")
        cmds[name] = (norm_xmi(argin.find("type") if argin is not None else None),
                      norm_xmi(argout.find("type") if argout is not None else None))
    for p in root.iter("deviceProperties"):
        props[p.get("name")] = (norm_xmi(p.find("type")), default_from_xmi(p))
    for s in root.iter("states"):
        states[s.get("name")] = (s.get("description") or "").strip()
    return attrs, cmds, props, states


def compare(name, xmi_path, py_path):
    """Return (list of divergences, list of notes)."""
    bad, notes = [], []
    try:
        xattrs, xcmds, xprops, xstates = read_xmi(xmi_path)
    except Exception as exc:
        return ["the .xmi will not parse: %s" % exc], notes

    try:
        parsed = read_py(py_path)
    except SyntaxError as exc:
        return ["the .py will not parse: %s" % exc], notes
    if parsed is None:
        notes.append("old POGO template (no `class X(Device)`); the interface "
                     "is declared in a DeviceClass and cannot be compared here")
        return bad, notes
    pattrs, pcmds, pprops = parsed

    for label, x, p in (("attribute", xattrs, pattrs),
                        ("command", xcmds, pcmds),
                        ("property", xprops, pprops)):
        for k in sorted(set(x) - set(p)):
            bad.append("%s %s: in the .xmi, missing from the .py" % (label, k))
        for k in sorted(set(p) - set(x)):
            bad.append("%s %s: in the .py, missing from the .xmi" % (label, k))
        for k in sorted(set(x) & set(p)):
            xv, pv = x[k], p[k]
            if label == "attribute":
                if xv[0] != pv[0]:
                    bad.append("attribute %s: dtype %s in the .xmi, %s in the .py"
                               % (k, xv[0], pv[0]))
                if xv[1] != pv[1]:
                    bad.append("attribute %s: %s in the .xmi, %s in the .py"
                               % (k, xv[1], pv[1]))
                # Not a divergence in itself, but this is what POGO turned into
                # a live polling_period when it regenerated SEAWaterflowmeter.
                if xv[2] and pv[2] is None:
                    notes.append("attribute %s: polledPeriod=%d in the .xmi, no "
                                 "polling_period in the .py (POGO would add it)"
                                 % (k, xv[2]))
                elif xv[2] != (pv[2] or 0):
                    notes.append("attribute %s: polledPeriod=%s in the .xmi, "
                                 "polling_period=%s in the .py"
                                 % (k, xv[2], pv[2]))
            elif label == "property":
                if xv[0] != pv[0]:
                    bad.append("property %s: %s in the .xmi, %s in the .py"
                               % (k, xv[0], pv[0]))
                xd, pd = xv[1], pv[1]
                if xd is UNCOMPARABLE or pd is UNCOMPARABLE:
                    notes.append("property %s: default spans several lines or "
                                 "is an expression; not compared" % k)
                elif xd is None and pd is None:
                    pass
                elif xd is None:
                    notes.append("property %s: default_value=%r in the .py, "
                                 "none in the .xmi" % (k, pd))
                elif pd is None:
                    notes.append("property %s: DefaultPropValue=%r in the .xmi, "
                                 "no default_value in the .py" % (k, xd))
                elif not same_default(xd, pd):
                    bad.append("property %s: default %r in the .xmi, %r in the "
                               ".py" % (k, xd, pd))
            elif xv != pv:
                bad.append("%s %s: %s in the .xmi, %s in the .py"
                           % (label, k, xv, pv))

    described = {k: v for k, v in xstates.items() if v}
    if described:
        notes.append("states with a description, worth keeping: "
                     + ", ".join("%s (%s)" % (k, v) for k, v in
                                 sorted(described.items())))
    return bad, notes


def servers(only, repo):
    found = []
    for sub in ROOTS:
        root = os.path.join(repo, sub)
        if not os.path.isdir(root):
            continue
        for entry in sorted(os.listdir(root)):
            if entry in SKIP or entry.startswith("."):
                continue
            d = os.path.join(root, entry)
            if not os.path.isdir(d):
                continue
            xmi = os.path.join(d, entry + ".xmi")
            py = os.path.join(d, entry, entry + ".py")
            if os.path.isfile(py) and (only is None or entry in only):
                found.append((entry, xmi if os.path.isfile(xmi) else None, py))
    return found


DEFAULT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main(argv):
    args = argv[1:]
    repo = DEFAULT_ROOT
    if "--root" in args:
        i = args.index("--root")
        try:
            repo = args[i + 1]
        except IndexError:
            print("--root needs a path")
            return 2
        del args[i:i + 2]
    only = set(args) or None

    found = servers(only, repo)
    if not found:
        print("no servers found under %s" % repo)
        return 2
    if repo != DEFAULT_ROOT:
        print("checking %s\n" % repo)

    clean = withdrift = nomodel = uncomparable = 0
    for name, xmi, py in found:
        if xmi is None:
            print("--  %-22s no .xmi (interface not documented)" % name)
            nomodel += 1
            continue
        bad, notes = compare(name, xmi, py)
        if any(n.startswith("old POGO template") for n in notes):
            print("--  %-22s %s" % (name, notes[0]))
            uncomparable += 1
            continue
        if bad:
            withdrift += 1
            print("\nXX  %s" % name)
            for b in bad:
                print("      %s" % b)
            for n in notes:
                print("    · %s" % n)
        else:
            clean += 1
            print("ok  %-22s model and code agree" % name)
            for n in notes:
                print("    · %s" % n)

    print("\n%d in step, %d with divergences, %d without a model, "
          "%d not comparable" % (clean, withdrift, nomodel, uncomparable))
    return 1 if withdrift else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
