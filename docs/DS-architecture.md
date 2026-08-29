# Device server architecture: failing well, and being asked too often

_Written 28-Aug-2026, from an audit of the 35 live servers and measurements
against the running vacuum instruments. Updated 29-Aug-2026, when sixteen of
the seventeen were fixed._

Two problems that look unrelated and are the same question seen from two sides:
**what happens when the instrument cannot answer.** In one case nobody asked and
the server dies at start-up; in the other everybody asks at once and the
instrument stops answering.

---

## 1. An exception in `init_device` takes the whole server down

Not just the device: **the process**. PyTango exits when `init_device` raises,
the Starter marks the server FAULT, and it stays dead until someone restarts it
by hand. A device server for a switched-off instrument should report that it
cannot talk to it, not disappear.

This is the single most common defect in this repository, and it has bitten
repeatedly: `PfeifferTU400` and `PfeifferHiscroll` and `PfeifferTC100`
(f018f5b), `TempSensorDS18B20`, `NetworkUPSTool`, `LeyboldIG3`.

### The pattern to follow

`LeyboldIG3` established it and five servers now use it. Everything that can
fail is caught and turned into FAULT with the reason in the status:

```python
def init_device(self):
    Device.init_device(self)
    self.ser = None
    try:
        self.ser = serial.Serial(self.SerialPort, ...)
    except serial.SerialException as e:
        self.set_state(DevState.FAULT)
        self.set_status("Can't open %s: %s" % (self.SerialPort, e))
        self.error_stream("Can't open %s: %s" % (self.SerialPort, e))
        return
    try:
        ...one exchange, to prove the instrument is there...
    except MyProtocolError as e:
        self.set_state(DevState.FAULT)
        self.set_status("No usable answer on %s: %s" % (self.SerialPort, e))
        return
    self.set_state(DevState.ON)
```

Two details that are easy to miss:

- **`delete_device` has to cope with a port that never opened.** Once the
  device survives `init_device`, `delete_device` is reached in a state it never
  used to be, and a bare `self.ser.close()` is then an `AttributeError`.
- **FAULT is not OFF, and the difference is decided.** FAULT means "I cannot
  talk to it". **OFF already means something else in this installation: on the
  FUG supplies it means the output is disabled.** An unreachable instrument
  reported as OFF would therefore read, on a synoptic, as a supply someone had
  switched off deliberately — which is a different fact and a dangerous one to
  confuse.

  So: **FAULT, with the reason in the status, whenever the instrument cannot be
  reached.** From software a switched-off instrument and an unplugged cable
  both give silence anyway, and FAULT is honest about that. OFF is reserved for
  when the instrument says so itself — as `GranvillePhillips350` does on its
  `9.90E+09` gauge-off marker, or `GammaVacuumDigitel` when command 61 answers
  NO.

### Which servers still have the defect

**One, as of 29-Aug-2026: `NetworkUPSTool`.** It was seventeen. Sixteen were
fixed in four batches (`caa0b20`, `8b6bbc7`, `a4a56f2`, `168f860`, `544d09e`),
and NetworkUPSTool is left because it needs the separate question of `upsd` not
starting on its own settled at the same time.

`HuttingerPFGDC` was the textbook case, and shows the intention was always
there:

```python
self.ser = serial.Serial(...)
(address, command, data) = self.parse_response(self.sendcommand(0, "4E", 4))
...
self.set_state(tango.DevState.OFF)
if (command != "ACK"):
    self.set_state(tango.DevState.FAULT)
```

With the supply switched off, `sendcommand` gets nothing, `parse_response`
raises while indexing, and the server is gone — three lines before the FAULT it
meant to set.

### What each batch turned out to need

Guarding `init_device` was the smallest part. Every batch turned up something
that only shows when the instrument is absent:

| Batch | Servers | What else was wrong |
|---|---|---|
| A, sputtering | HuttingerPFGDC, HuttingerPFGRF, VarianTV301nav, ArduinoPt, ArduinoMotor, MKSGauge, MFC | **ArduinoPt reported ON with nothing connected** — `readline()` returns an empty line on timeout and raises nothing, so silence fell through to "Pt resistor connected". **MFC opened its port with no timeout**, so a silent instrument blocked a read for ever |
| B | Hygrometer, FUGMCP, CenterOneGauge | Hygrometer set the status to "Connected" *before* checking the identity, so a mute board was reported connected and FAULT at once. FUGMCP guarded its identity exchange and then asked `>BON?` outside any try |
| C | ElmitecLEEM2k, ElmitecUview, Itech6000C | **`TCPBlockingReceive` spun at full CPU** when the program went away: its inner `while ReceivedLength == 0: recv(1)` never ends, because recv returns zero only at end of file. No socket timeout either. Itech6000C's copy had the whole loop as dead code behind an early `return` |
| D, GPIO | RaspberryButton, RaspberrySwitch, WaterSwitch | A different failure entirely: not a switched-off instrument but a pin the kernel holds, `lgpio.error: 'GPIO busy'` — the `w1-gpio` conflict on GPIO 4. RaspberrySwitch and WaterSwitch set no state at all, so they sat in UNKNOWN even when working |

Two servers also needed more than not dying:

- **ElmitecLEEM2k and ElmitecUview reconnect on their own now.** LEEM2000 and
  UView are restarted routinely, and until 29-Aug-2026 each restart meant
  restarting the device server by hand. A `_Reconnect` thread rebuilds the link
  every `ReconnectPeriod` seconds, and every send goes through a helper that
  marks the link down on failure. Itech6000C deliberately does *not* have this:
  its link has not dropped in practice, and the thread is not free.
- **RaspberryButton carries the X-ray gun permissive**, so failing safely
  matters more there than anywhere. It fails in the right direction: the pin is
  never claimed, so the server is not driving the permissive and cannot assert
  it, and the deadman is left unarmed because there would be nothing to drop.

### How the failure paths were tested

Without switching off any instrument, and without touching the database:

```bash
<Server> test -file=/tmp/props -ORBendPoint giop:tcp:127.0.0.1:12990
```

with a property file naming the device and pointing `SerialPort` at a path that
does not exist, or at a real adapter with nothing on the other end. Those are
the two shapes of "the instrument is not there", and they can be produced on any
Pi. For the networked servers a stand-in program that could be started and
killed at will showed the reconnection working end to end.

⚠️ **`-nodb` alone is not enough**: a property declared `mandatory=True` is
fetched by `Device.init_device()` before any of this code runs, and a missing
one raises there — which is itself a way to kill a server that no guard written
here can catch. `-file=` supplies the properties and avoids it.

**Already protected (32):** everything except NetworkUPSTool, AlarmNotifier and
AnalogInterlock, the last two having nothing risky in `init_device` to begin
with.

⚠️ **The count is a floor, not a ceiling.** The audit looks for calls that reach
hardware or the network. Any other exception kills the server just as dead:
`AnalogInterlock` counts as clean and still has an explicit `raise` in
`init_device` when its thresholds are inconsistent, and a missing mandatory
property kills it before `init_device` is even entered.

---

## 2. Live reads: the instrument answers once per client, per read

Most `read_<Attr>` methods talk to the instrument on every client request. The
cost therefore scales with **how many people are looking**, which is the one
variable the server does not control. Ten clients at 1 Hz are ten exchanges a
second down one serial port.

### The three patterns in use

**A. Live read.** 151 attributes across 28 servers. The largest:

```
HuttingerPFGDC 18   ElmitecLEEM2k 17   HuttingerPFGRF 16   VarianTV301nav 11
WisselMCA 10        SRIlockin830 8     FUGMCP 7            GammaVacuumDigitel 7
ElmitecUview 6      Itech6000C 6       PfeifferHiscroll 6  PfeifferTU400 5
```

**B. A background thread fills values; attributes return them.** 47 attributes:
SEAWaterflowmeter, PIDController, AnalogInterlock, AlarmNotifier,
TempSensorDS18B20, Hygrometer, RaspberryButton (mixed).

This is the right shape where the thread does something more than read —
SEAWaterflowmeter counts edges, PIDController regulates, AnalogInterlock
watches. As a cure for load it is reimplementing, in Python, what Tango already
does.

**C. Tango's own polling. Not in use anywhere.** Checked across every exported
device: the only `polled_attr` in the database belong to the Starters, which
set their own.

### Why C is the answer

With `polled_attr` set, the server's polling thread reads the attribute at a
fixed period and **clients read the buffer**. Traffic to the instrument becomes
constant and stops depending on the number of clients. It is configuration, not
code.

Verified rather than assumed: a `DeviceProxy`'s default source is `CACHE_DEV`,
so clients get the polled value without doing anything. A client that really
needs a fresh reading can ask for one with `set_source(DevSource.DEV)`, which
is how the measurements below were taken.

Polling also enables **events**, which is the proper way for many clients to
watch one value: they subscribe to `change` or `periodic` instead of asking.

### Measured cost of one sweep

Every attribute of each device, read straight from the hardware, median of
three sweeps (28-Aug-2026):

| Device | Server | Attrs | Sweep | Per attr |
|---|---|---|---|---|
| `leem/vacuum/gaugeMCH` | GranvillePhillips350 | 4 | **0.08 s** | 21 ms |
| `leem/vacuum/gaugePCH` | AMLPGC1 | 2 | **0.08 s** | 42 ms |
| `xps/vacuum/turboPCH` | PfeifferTC100 | 3 | **0.19 s** | 64 ms |
| `leem/vacuum/gaugeEvap` | CenterOneGauge | 1 | **0.22 s** | 219 ms |
| `leem/vacuum/turboPCH` | PfeifferTU400 | 5 | **0.28 s** | 56 ms |
| `leem/vacuum/scrollPump` | PfeifferHiscroll | 6 | **0.34 s** | 56 ms |
| `xps/vacuum/ionpump` | GammaVacuumDigitel (QPC) | 7 | **1.40 s** | 200 ms |
| `leem/vacuum/ColumnsIonPump` | GammaVacuumDigitel (SPCe) | 7 | **1.60 s** | 229 ms |

The two ion pumps are an order of magnitude slower than the rest, and not
because the instruments are slow: `GammaVacuumDigitel` waits 0.2 s between
exchanges because **the QPC will not take commands back to back** — measured,
30 reads with no gap gave 24 timeouts in 252 s, the same 30 with 0.2 s gave none
in 6.4 s.

**Two clients polling the QPC once a second would saturate it.** Its failure
mode is a 5 s timeout and a reconnect, which is exactly the avalanche worth
avoiding. This is the concrete case; the rest have room.

⚠️ The pacing is applied by the class, so the **SPCe pays it too and does not
need it** — 1.6 s a sweep for nothing. Worth making a per-device property if
the SPCe is ever polled hard.

### Suggested polling periods

From the measurements, with margin. The rule is that the period must be
comfortably longer than the sweep, or polls overlap and pile up — which
manufactures the very problem being solved.

| Device | Sweep | Period | Why |
|---|---|---|---|
| GammaVacuumDigitel (both) | 1.4–1.6 s | **5 s** | the QPC cannot go faster; nobody needs an ion pump at 1 Hz |
| PfeifferHiscroll, TU400, TC100 | 0.2–0.35 s | **3 s** | plenty; a pump's speed and temperature move slowly |
| CenterOneGauge | 0.22 s | **2 s** | |
| GranvillePhillips350, AMLPGC1 | 0.08 s | **1 s** | the fastest of the lot; the gauges people actually watch |

### Three caveats

1. **Polling loads the instrument even with no clients at all.** On a fragile
   or slow device that can be worse than live reads if it is rarely consulted.
   It is a trade of a variable cost for a fixed one.
2. **The polling thread walks a device's attributes in series.** One slow
   attribute delays the others. On the QPC, where each exchange costs 200 ms,
   that matters.
3. **Never set a period shorter than the sweep.** Polls then overlap and queue.

---

## 3. What to do

The two halves are independent and can be done in either order. Both are
tractable in batches.

**Robustness** — done, bar one:

- ✅ **Sputtering (7)** — `caa0b20`. The rig was switched off, which made it the
  one batch whose failure path could be tested rather than reasoned about.
- ✅ **Hygrometer, FUGMCP, CenterOneGauge** — `8b6bbc7`.
- ✅ **Networked (3)** — `a4a56f2` and `168f860`, with reconnection for the two
  Elmitec servers.
- ✅ **GPIO (3)** — `544d09e`.
- ⏳ **NetworkUPSTool** — left, because it also needs `upsd` starting on its own,
  which is still open (see `netboot-shared-root.md`). It runs today only
  because `upsd` was started by hand, so it will fail again at the next reboot
  of pi-leem.

✅ **Load** — `polled_attr` applied to the eight vacuum devices on
29-Aug-2026, at the periods above, and the servers restarted. The ion pumps'
setpoints were deliberately left unpolled: they are configuration, they change
very rarely, and each costs 200 ms of the controller's time.

Measured afterwards, reading four attributes with `DevSource.DEV` against
`DevSource.CACHE`:

| Device | To the hardware | From the buffer |
|---|---|---|
| `xps/vacuum/ionpump` | 0.80 s | 0.003 s |
| `leem/vacuum/ColumnsIonPump` | 0.80 s | 0.004 s |
| `leem/vacuum/scrollPump` | 0.21 s | 0.006 s |

The number that matters is not the speed but that the traffic to the instrument
is now constant, whatever the number of clients.

✅ **A safety net for both**, added 29-Aug-2026:

```bash
python3 tools/audit_init_device.py     # who can still die at start-up
python3 tools/audit_reads.py           # who reads the instrument per request
```

Both have a `--self-test` that runs anywhere. audit_init_device's regression
fixture is this repository's own history: HuttingerPFGDC must report at
`caa0b20^` and must not at `caa0b20`.

audit_reads is a survey, not a verdict -- reading live is the right shape for
an attribute nobody watches continuously, and it exits 0 either way.
