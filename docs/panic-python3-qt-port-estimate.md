# PANIC → Python 3 + current Qt — Work Estimate

_Estimate prepared 03-ago-2026. Context: PANIC/PyAlarm is listed as a "special case"
in `surfmoss-device-server-migration-reference.md` — third-party, still Python 2 +
Qt5, no entry point in the SURFMOSS `pyproject.toml`. This document estimates what
it would cost to bring it forward, and what the alternatives cost._

---

## 1. What would actually be ported

PANIC is three layers, and the visible one is the smallest.

| Layer | Content | Current state |
|---|---|---|
| `fandango` | Sergi Rubio's general Tango utility library (`functional`, `tango`, `dynamic`, `threads`, `objects`, `dicts`, `callbacks`, `log`, …) | Python 2-era. GitHub repo **archived**; moved to GitLab, then stalled |
| `panic` + `PyAlarm` | AlarmAPI, `TangoEval` formula engine, the device server itself | Still contains Python 2 syntax (`except Exception,e:`) and the old `PyTango.Device_4Impl` class model |
| `panic.gui` | Taurus + PyQt widgets (AlarmView, QAlarmPanel, AlarmForm, toolbar) | Written against **Taurus 4**, PyQt4 / early-PyQt5 idioms |

Upstream is effectively dead: the `tango-controls/PANIC` and `tango-controls/fandango`
GitHub repos were last touched in March 2022 and fandango is archived. The GitLab
mirrors exist but show no sustained activity. **Whatever is ported, we own permanently.**

The *dependency* side is not the blocker. Taurus 5.0 dropped Python 2 and Qt4
(Python ≥ 3.5, PyQt5/PySide2), Taurus 5.3.0 added Qt6 support, and 5.4.0 is current
on PyPI. PyTango 10.x is Python-3 only. The blocker is PANIC's own code plus fandango.

---

## 2. Effort — full port (fandango + panic + GUI)

One competent person who knows Tango. No meaningful upstream test suite to lean on,
so validation is empirical.

| Task | Days |
|---|---|
| **`fandango` core** (`functional`, `objects`, `dicts`, `tango`, `log`, `threads`) — a `2to3` pass is one day; the real work is bytes-vs-str on Tango string attributes, dict views used as lists, `sort(cmp=)` / `cmp()`, integer division, `exec`/`eval` scoping, pickling in `WorkerProcess` | 15–25 |
| **`panic` API + `PyAlarm` DS** — py3 syntax, modernise to the PyTango 9.5/10 device API, threading/process model | 8–12 |
| **`panic.gui` → Taurus 5.4 + Qt6** — Qt6 enum scoping (`Qt.ItemDataRole.DisplayRole`), old-style signal removal, `exec_()` → `exec()`, `QAction` relocation, Taurus 4 → 5 module moves. Realistically a partial rewrite, not a port | 20–30 |
| **Validation** — formula regression testing, mail/action paths, long-run stability under the Starter | 10–15 |
| **Total** | **≈ 55–80 person-days** (3–4 months elapsed at part-time effort) |

---

## 3. The hidden risk that drives the recommendation

Alarm formulas are `eval()`'d strings. Python 3 silently changes their semantics:

- `1/2` is `0` in Python 2, `0.5` in Python 3 → thresholds shift
- comparisons between incompatible types now raise instead of ordering
- `.keys()` returns a view, not a list
- serial/attribute reads may yield `bytes` where `str` was assumed

A mechanically-ported alarm system compiles, starts, and **quietly evaluates some
conditions differently than before**. An alarm that fails silently is worse than no
alarm at all. This is the same category of hazard flagged at the end of the device
server migration reference — `py_compile` clean certifies syntax, not runtime
behaviour — but here the failure mode is invisible rather than a red device in Astor.

This is why "run 2to3 on fandango and see what happens" is not a viable plan, and why
the validation line above is not padding.

---

## 4. Alternatives

### B — Server only, no GUI · ≈ 15–25 days

Vendor a trimmed subset of fandango (only the modules `panic`/`PyAlarm` actually
import), port it plus the API and device server, and **drop `panic.gui` entirely**.
Alarms are stored as device properties (`AlarmList`, `AlarmReceivers`,
`AlarmSeverities`), so Jive is a serviceable configuration editor and Astor already
shows device state. Removes the worst third of the work and the entire Taurus/Qt
dependency chain.

### C — Elettra AlarmHandler · ≈ 5 days

C++ device server, actively maintained at `gitlab.elettra.eu/cs/ds/alarm-handler`,
cmake build, CI with functional tests, deployed in the Elettra and FERMI control
systems. No Python at all, therefore immune to this entire problem class. Cost is
building it (x86 for wolframite; arm64 if it ever runs on a Pi), learning its rule
syntax, and re-expressing the alarms. Designed for facility scale — oversized for
SURFMOSS, and historically the PANIC GUI ↔ Elettra server pairing has been fragile.

### D — Write our own · ≈ 4–6 days

A single Tango device using the modern PyTango 10 `Device` / `attribute` decorator API:

- polling loop over a list of formulas (device properties, same shape as PyAlarm)
- one dynamic boolean attribute per alarm
- threshold/hysteresis counter to avoid flapping
- notification through the msmtp → Gmail relay already planned for smartmontools
- optional simple status panel later (Qt or a static page), not required for v1

300–400 lines. Lives in `SURFMOSS_TangoDS` alongside `PIDController`, installs through
the existing `pyproject.toml` entry-point mechanism, ships to the Pis through the shared
`/nfs/pi-trixie` root like everything else. Fully understood, fully ours.

---

## 5. Recommendation

**Option D**, with **C** as the fallback if the alarm count ever grows past what a
hand-rolled device can sensibly manage.

Rationale: PANIC's design point is a synchrotron. Elettra runs roughly 23,000 formula
evaluations per minute, FERMI around 60,000. SURFMOSS needs perhaps a dozen conditions
— vacuum, water flow, cryostat temperature, UPS state, chamber pressure. Paying two to
three person-months to inherit an unmaintained fork of fandango so that a dozen formulas
keep working is a poor trade against four days of code that fits the existing packaging,
deployment, and notification infrastructure.

If PANIC specifically is wanted — for its formula syntax, or for compatibility with
another site — do **B**, not the full port, and treat the GUI as permanently out of scope.

---

## 6. Decision inputs still missing

- How many alarm conditions are actually needed, per instrument?
- Is anyone outside SURFMOSS depending on PANIC-format alarm configuration?
- Does notification need anything beyond email (SMS, pop-up, speakers)?
- Should alarm history be logged to file, to Tango snapshots, or not at all?

The answers move option D between 4 and 8 days; they do not change the ranking.
