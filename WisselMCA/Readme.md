# WisselMCA

Tango device server for the **WissEl CMCA-550 Data Acquisition Module**, the
multichannel analyser at the heart of the Mössbauer transmission spectrometer.
It talks to the card over USB (HID), exposes the pulse-height window, the
acquired spectrum and the acquisition mode as attributes, and adds the
Mössbauer-specific step the card firmware does not do over this interface:
folding a constant-acceleration spectrum about an auto-calibrated fold point.

Runs on **pi-rackmossbauer**, server `WisselMCA/1`, device
`mossbauer/measurement/mca_crio`.

## The instrument

The CMCA-550 (WissEl — Wissenschaftliche Elektronik GmbH,
<http://www.wissel-gmbh.de/>, *CMCA-550 Data Acquisition Module*) is a small
mains-powered box that sits between the detector chain and the PC. In a Wissel
Mössbauer setup it is one of: MVT-1000 velocity transducer → MR-360 drive unit
→ DFG-1000/1200 digital function generator (the triangular velocity waveform)
→ detector → preamp/amplifier/SCA → **CMCA-550** → PC. Its own DFG output is
**not** driven over the remote protocol used here; the sweep sync comes from the
external function generator.

Because it has its own power supply it keeps counting when the PC is off, and it
holds the acquired data for "more than 4 days" through a power failure.

### Modes

| Mode | What it does |
|------|--------------|
| **PHA** | Pulse-height analysis. The integrated ADC digitises 1–10 V analog input pulses (peak detection fully digital, 48 MHz sampling), one count into the channel for that pulse height. Used to set the SCA/energy window on the 14.4 keV line. |
| **MCS analog** | Multichannel scaling with the channel address driven by an analog ramp — the constant-acceleration Mössbauer mode. Up to 8192 channels per sweep. Counts the detector pulses that fall inside the PHA window vs. drive velocity. This is what `setMCAmode` selects (`Mode` byte = 2). |
| **MCS digital** | MCS with a digital channel-advance clock. Not used here. |

The PHA window (`setPHAmode`, then the window attributes) is what MCS analog
then gates on — set the window in PHA, switch to MCS analog to take the
spectrum. WISSOFT calls that windowed MCS mode **MCS[window]**; over this
protocol it is just mode 2 with a live PHA window.

### Specifications (from the WissEl datasheet)

| | |
|---|---|
| Inputs | 5 BNC: Analog In, Digital In, ADC, COUNT, START, CHA, CE |
| Indicators | 8 LEDs: DA ON, COUNT, ADC, START, POWER, CHA, CE, USB |
| PHA | 1–10 V analog input; 1024–8192 channels (8192 with oversampling/interpolation); 48 MHz sampling |
| MCS | max. 8192 channels/sweep; count frequency > 100 MHz; max. channel-advance ≈ 500 kHz |
| Ports | USB 1.1 (HID); RS-232C at 115 500 baud |
| Power | 7–9 V DC, 400 mA, from an external 100–240 VAC / 7.5 V DC 800 mA plug pack |
| Size / weight | 135 × 100 × 53 mm, 500 g |

## The USB protocol

USB HID, fixed **64-byte reports**. Host-initiated: the card never sends
unsolicited data. Every message is `[count][command][args…][checksum]`, where
`count` excludes itself and `checksum` is the low byte of the sum of all
preceding bytes (`cmca.code()` / `cmca.crc()`). If the first returned byte is
`0x00` the command failed and nothing else follows.

Commands the server uses:

| Byte | Purpose | Server method |
|------|---------|---------------|
| `0xF1` | read version / serial number | `model()` → `Model` |
| `0x84` / `0x04` | read / write Mode+Start/Stop byte | `readmode()` / `setmode()`, `start()`, `stop()` |
| `0x81` / `0x01` | read / write General Setup word | `readgeneral()` / `writegeneral()` → `Configuration` |
| `0x88` / `0x08` | read / write PHA settings (Hyst, LLD1, ULD1, LLD2, ULD2) | `readPHA()` / `writePHA()` → window attributes |
| `0x90` | read a 32-channel page (128-byte payload, spans 3 HID reports) | `readpage()` → `readspectrum_pages()` |
| `0x91` | read one channel (32-bit count) | `readchannel()` |
| `0x92` | read last non-zero channel | `readlastchannel()` → `ReadLastChannel` |
| `0x13` | clear RAM (block 0 = all of MCS + PHA) | `cleardata()` → `ClearMem` |

### Resolution and the two scales

`General Setup` bit field `Res[1:0]` selects the ADC resolution and therefore
the channel count: `0` = 13 bit / 8192 ch, `1` = 12 bit / 4096, `2` = 11 bit /
2048, `3` = 10 bit / 1024 (`phachannels()`).

The **PHA window levels are 14-bit input voltages**: `16383 = 0x3FFF = 10 V`,
`0 = 0 V` (protocol manual, page 4). So they are *not* channel numbers, and the
DS reports them in **mV** (`Lower_Window_Limit`, `Upper_Window_Limit`,
`Hysteresis`). A pulse of voltage V lands in channel `V / (10 V) · (8192 >>
Res)`, i.e. the width of one channel is

```
ChannelWidth = 10000 / (8192 >> Res)  mV     ( = 1.2208 mV at Res = 0 )
```

exposed as the `ChannelWidth` attribute (INVALID outside PHA). A window edge
therefore sits at channel `level_mV / ChannelWidth`, which is what
`LowerWindowChannel` / `UpperWindowChannel` report and why
`UpperWindowChannel == LastChannel - 1`. If a spectrum plotted against the raw
channel index seems to disagree with the window "by a factor of ~1.22", that
factor **is** `ChannelWidth`: mV vs channel index, not a bug. Multiply the
channel axis by `ChannelWidth` to line them up. A live write/read round-trip of
the window attributes returns the value exactly.

## How the server talks to the card

The card is on the shared read-only NFS root's Pi and gets power-cycled and its
USB re-enumerated often; several fixes exist so a hiccup does not need the
server restarted by hand (git history, Aug 2026):

- **Reconnect thread.** A failed USB open leaves the server FAULT and it retries
  every `RETRY_PERIOD` (10 s) from `always_executed_hook`, rather than staying
  FAULT until an operator Init.
- **Read deadline.** `hid.read()` on a blocking handle waits forever; a single
  lost reply would then park a thread in `hid_read_timeout` inside the Tango
  serialization monitor and the whole device would answer `IMP_LIMIT` to
  everything. Every read has a `READ_TIMEOUT` (1000 ms) deadline.
- **Resync on desync.** A reply that never came leaves the stream one step out,
  so every later command reads the previous one's leftovers and reports a wrong
  count. On any count mismatch the server drains what is queued (`drain()`,
  bounded to `DRAIN_REPORTS` / `DRAIN_SECONDS`, because a card that is
  *measuring* never stops producing reports) so the next command starts clean.
- **Multi-report reassembly.** A page reply is 131 bytes = 3 HID reports;
  asking `hid` for more than one report's worth returns only the first and
  queues the rest. `read_response()` keeps reading until the reply is complete.

Multiple cards on one Pi report an empty serial number, so `VendorID` /
`InstrumentID` cannot tell them apart — use `DevicePath` (the `hid.enumerate()`
topology path) instead.

## Attributes

| Attribute | Type | Access | Notes |
|-----------|------|--------|-------|
| `Lower_Window_Limit` | double, mV | RW | LLD1. `0–10000` |
| `Upper_Window_Limit` | double, mV | RW | ULD1 = LLD2 = ULD2 (single-window mode). Also sets `LastChannel`. |
| `Hysteresis` | double, mV | RW | discriminator hysteresis |
| `LowerWindowChannel` | uint16 | RO | `Lower_Window_Limit` as a channel index |
| `UpperWindowChannel` | uint16 | RO | `Upper_Window_Limit` as a channel index; `= LastChannel - 1` |
| `ChannelWidth` | double, mV | RO | mV per channel; INVALID outside PHA |
| `Spectrum` | uint64 spectrum | RO | counts, channels `firstchannel … lastchannel` |
| `LastChannel` | uint16 | RW (EXPERT) | how many channels `Spectrum` reads; follows the upper window, or `ReadLastChannel` |
| `Mode` | enum | RO | `None`, `MCS_digital`, `MCS_analog`, `PHA` |
| `ModeByte` | uint16 | RO (EXPERT) | raw mode byte |
| `Configuration` | uint16 | RW (EXPERT) | raw General Setup word |
| `Model` | string | RO (EXPERT) | `year week serialnumber` |
| `FoldedSpectrum` | double spectrum | RO | see *Folding* |
| `FoldPoint` | double | RW (memorized) | mirror point, channels, near N |
| `FoldPointAmbiguous` | bool | RO | flat mirror-χ² minimum → fold point unreliable |
| `FoldPointCurvature` | double | RO | sharpness of that minimum; the ratio `CalibrateFoldPoint` thresholds at 0.02 |

## Commands

| Command | Purpose |
|---------|---------|
| `Start` / `Stop` | set / clear the Start bit (counting) |
| `setPHAmode` | mode 3; refresh `LastChannel`, report the window and mV scale in the status |
| `setMCAmode` | mode 2 (MCS analog), `MCS_Channels` channels |
| `ClearMem` | clear all acquisition RAM |
| `SetFirstChannel` / `SetLastChannel` | window of channels `Spectrum` returns (EXPERT) |
| `ReadLastChannel` | ask the card for its last non-zero channel and use it as `LastChannel` (EXPERT) |
| `CalibrateFoldPoint` | mirror-χ² search for the fold point over the full raw sweep; stores it in `FoldPoint` |

## Properties

| Property | Default | Notes |
|----------|---------|-------|
| `VendorID` | `0x0925` | |
| `InstrumentID` | `0x0035` | 0x35 = CUSB550 |
| `DevicePath` | `""` | `hid.enumerate()` path, e.g. `1-1.1.2:1.0`. Empty = first card matching VendorID/InstrumentID. Needed only with more than one card. |
| `MCS_Channels` | `512` | channels in one full native MCS sweep (one drive period). Used by `setMCAmode` and as the N that folding folds over. `256` on some setups. |

## Folding

A constant-acceleration MCS spectrum holds two mirror halves of one drive
period. `CalibrateFoldPoint` runs the group's offline-pipeline fold-point
search (mirror-χ² minimisation — `WisselMCA/fold.py`, a **verbatim** copy of
`Normos-distri/gui/calibration.py`'s `fold()`, kept byte-identical so the server
and the offline fit agree channel-for-channel) over the full raw sweep and
stores the result in `FoldPoint` (memorised, near `MCS_Channels`, not an integer
in practice — 510.75/512 in one session). `FoldedSpectrum` refolds on every read
at the stored `FoldPoint` — `folded[i] = raw[i] + raw[(FoldPoint − i) mod N]`,
linearly interpolated, `i < N/2` — and does **not** recalibrate; call
`CalibrateFoldPoint` once per measurement, not in a loop.

Guards: `CalibrateFoldPoint` and `FoldedSpectrum` throw unless `Mode` is
MCS analog and the read window is the full untruncated sweep (`firstchannel = 0`
and `lastchannel ≥ MCS_Channels − 1`). The fold point can be flat/ambiguous
early in an acquisition when too few counts have accumulated — `FoldPointAmbiguous`
/ `FoldPointCurvature` expose that rather than trusting the automatic minimum
(the 0.02 threshold is an uncalibrated estimate, documented as such upstream).

## Install

`WisselMCA` is in the repo's `pyproject.toml` (`[project.scripts]`,
`[tool.setuptools] packages`, `package-dir`). On the shared NFS root:

```bash
sudo systemd-nspawn -D /nfs/pi-trixie
cd /opt/tango/SURFMOSS_TangoDS
pip install --no-deps --break-system-packages -e .
exit
```

Needs the `hid` module (hidapi binding) and `numpy`. Register server `WisselMCA/1`,
class `WisselMCA`, device `mossbauer/measurement/mca_crio`, host
pi-rackmossbauer, and set `DevicePath` if more than one card is connected.

`tools/check_xmi.py WisselMCA` must stay clean — the `.xmi` is documentation
kept in step by hand, POGO is not run on this server.

## Not done / known limits

- **`Configuration` / resolution is not exposed as an enum.** Change it via the
  raw General Setup word only, and re-check `ChannelWidth` afterwards.
- The window scale (`16383 = 10 V`) is from the manual and matches a live
  round-trip; the DFG/velocity axis of a folded spectrum is still channels, and
  a mV/velocity axis has to be applied client-side (`channel · ChannelWidth`),
  because a Tango spectrum attribute carries no x-axis and ATKPanel plots by
  index.
- `setPHAmode`'s status string ("window X – Y mV") is set once and not
  refreshed when the window is changed through the attributes afterwards.
