# Deprecated device servers

These device servers are retired because their **hardware is dead, gone, or
superseded**. They
are kept here for reference and git history only. They are:

- **not** installed (excluded from `packages.find`, absent from `[project.scripts]`)
- **not** registered in the Tango database (death by omission at the clean-DB import)

If hardware ever returns, a server can be moved back up to the repo root, re-added
to `[project.scripts]`, re-registered in the DB, and assigned to a Starter — but
each would need testing against the new hardware first.

| Server | Reason retired |
|---|---|
| MitutoyoPostable | Serial interface to the Mitutoyo/Elmitec manipulator micrometers died. |
| Motor | Replaced (18-ago-2026) by an Arduino driving a DRV8825 for the stepper motors — see `ArduinoMotor`. |
| SpecsXRC1000 | XRC1000 x-ray electronics are dead. |
| VarianMultiGauge | The last Varian MultiGauge unit died. |

_Distinct from `inactive/`: those are paused but potentially revivable; these are
considered dead._

## Separate case: PANIC (PyAlarm)

**PANIC is not a deprecated server like the four above.** Those are SURFMOSS
servers whose hardware died. PANIC is **third-party code** — ALBA's PyAlarm
alarm system, vendored into this repository — retired because it is not going to
be maintained here, not because an instrument stopped working.

| | |
|---|---|
| What it was | The alarm system for the old network: watched attributes across LEEM, XPS, VSM and Mössbauer and sent Telegram messages and email. Never had an entry point in `pyproject.toml`, so it was never installed from this repository. |
| Why it goes | Python 2 + Qt5, with no port to Python 3 / Qt6 planned. Not used on the new network. Its job is being taken over by our own device servers — `AnalogInterlock` and whatever follows it. |
| Upstream | https://github.com/ALBA-Synchrotron/panic |
| Its configuration | [`docs/alarms-panic-legacy.md`](../docs/alarms-panic-legacy.md) — every alarm it carried, recovered from the database of the old network. **That document, not the code, is the reference now.** |
| Cost of porting | [`docs/panic-python3-qt-port-estimate.md`](../docs/panic-python3-qt-port-estimate.md) |
| Last commit containing the tree | tag **`panic-final`** (`62afd93`) — `git show panic-final:PANIC/panic/alarmapi.py`, or `git checkout panic-final -- PANIC` to get the lot back |

⚠️ Local patches existed to make it work against Qt 5.5. They were never
committed to this repository and are **deliberately discarded**: they were
carrying a Python 2 application a little further, which is not where this is
going.

To consult the code itself rather than the configuration, take it from upstream
or from the last commit that contained it, above.
