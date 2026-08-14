# Inactive device servers

These device servers are **paused, not dead**. The hardware exists (or may), but
the server is not in use right now, or the code needs work before it can be
trusted. They are kept out of the default install:

- **not** installed (excluded from `packages.find`, absent from `[project.scripts]`)
- **not** registered in the Tango database until revived

To revive one: move it back to the repo root, add its entry point to
`[project.scripts]`, install its dependencies, register it in the DB, assign it to
the relevant Starter — and complete the work noted below first.

| Server | Why inactive | What reviving needs |
|---|---|---|
| GammaIonPump | Written for a previous version of the electronics | Likely needs updating to current electronics; test against the pump. |
| Keithley2100 | Not in use now | Re-add `usbtmc` (pip) + `python3-usb`/libusb; verify import on the Pi. |
| MCC1208LS | DAQ not in use | Build `usb_1208LS` from source (wjasper/Linux_Drivers) against libusb — the only from-source dependency. |
| PfeifferDCU002 | Not finished | Complete the implementation; test. |
| V4L2Camera | Camera not in use now | Re-add `python3-opencv` (apt, NOT pip on ARM). |
| VSMControlDevice | Not in use now | Needs `python3-numpy`; confirm which host runs it. |
| WebCam | Camera not in use now | (camera stack) |

## Separate case: PANIC (PyAlarm)

PANIC is the standard Alba Tango alarm system — **third-party**, not a SURFMOSS
server. It is still **Python 2 + Qt5** and has not been converted. It is not
installed from this repo and has no entry point in the pyproject. Reviving it is a
significant py2→py3 + Qt task, and it would be installed separately (its own
package), not via the SURFMOSS install. Kept on hand for that future work.
