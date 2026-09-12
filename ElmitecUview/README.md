# ElmitecUview

Reads the LEEM/PEEM camera through **Elmitec's UView** acquisition program,
over UView's TCP remote-control socket. **UView must be running** on the camera
PC — this server is a client of it, not of the camera.

`scripts/LEEMmacros.py` drives this device for every acquisition (see
[`docs/LEEMmacros.md`](../docs/LEEMmacros.md)).

Manuals on the wiki: `Software_Uview.pdf`, `Software_UVIEWScript.pdf`,
`Software_UView_FileFormats_2017.pdf`.

Runs on **pi-leem**, server `ElmitecUview/1`, device `leem/measurement/Uview`,
`IP = tvips.lab`, `Port = 5570`.

## The protocol

TCP. On connect the server sends `asc` to start string mode; every reply is
read up to a terminating NUL (`TCPBlockingReceive`). Commands are short ASCII
tokens:

| Token | |
|---|---|
| `ext` / `ext <ms>` | read / set exposure |
| `avr` / `avr <n>` | read / set averaging |
| `aip` / `aip 0\|1` | continuous acquisition on/off (also the "acquisition in progress" query) |
| `giw` / `gih` / `bin` | image width / height / binning |
| `asi -1` | acquire a single image |
| `exp 0,0,<path>` / `exp 1,2,<path>` | save the current image as `.dat` / `.png` |
| `roi 1` / `roi 2` | ROI intensity → `IntensityROI1` / `IntensityROI2` (change events) |

## Interface

- Properties `IP` (`tvips.lab`), `Port` (5570), `Timeout` (5 s),
  `ReconnectPeriod` (10 s).
- Read attributes: `IntensityROI1`, `IntensityROI2`, `ImageWidth`,
  `ImageHeight`, `Binning`, `AcquisitionInProgress` (deprecated stub, always
  `True`).
- Read-write: `Exposure` (ms), `Average`, `ContinousAcquisition` (memorized).
- `ImageData` — declared (1024×1024 uint16) but **not implemented**; the reader
  is commented out.
- Commands: `AcquireSingleImage`, `SaveImageAsDAT(path)`, `SaveImageAsPNG(path)`,
  `sendCommand(str)` (EXPERT).

## Notes

- **`IntensityROI1`/`IntensityROI2` raised `AttributeError` on every read**
  (found 11-Sep-2026, `leem/measurement/Uview`): both called
  `self.getROIdata(roiid)`, a method that was never defined anywhere in the
  file. UView itself answered fine the whole time (`roi 1` / `roi 2` gave
  `0.350777` / `0.350592`, checked live through `sendCommand`); nothing was
  wrong with the instrument or the connection, only the missing method.
  `getROIdata` now sends `roi $ROIid` and returns the value exactly as UView
  reports it — a percentage of full range already, in this UView build,
  despite `Software_UViewScript.pdf`'s "ROIdata TCP" section describing an
  additional ×100 that this build's replies do not need. UView's own error
  replies (a negative value, or the text `ErrorCode $n`) raise
  `ElmitecUviewError` with the documented reason (intensity window not open
  / ROI invalid / ROI not active) rather than handing a client a number that
  reads as a valid, very wrong, intensity.
- **Reconnect thread.** UView is restarted often; a `_Reconnect` thread
  rebuilds the socket every `ReconnectPeriod` while it is down, so a UView
  restart no longer needs this server restarted.
- **One socket.** Every attribute and command shares it, serialized by Tango's
  monitor. `AcquisitionInProgress` was made a stub because it and
  `ContinousAcquisition` both sent `aip` and stepped on each other.
- The single-socket design and the `Continous` (sic) spelling are load-bearing
  — `LEEMmacros.py` depends on both. See `docs/LEEMmacros.md` before changing
  anything here.

Install: in `pyproject.toml`; standard library only (`socket`). `numpy` is
needed only if `ImageData` is ever implemented.
