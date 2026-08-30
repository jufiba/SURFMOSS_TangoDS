# Device server architecture: failing well, and being asked too often

_Written 28-Aug-2026, from an audit of the 35 live servers and measurements
against the running vacuum instruments. Updated 30-Aug-2026, when the last of
the seventeen was fixed._

Two problems that look unrelated and are the same question seen from two sides:
**what happens when the instrument cannot answer.** In one case nobody asked and
the server dies at start-up; in the other everybody asks at once and the
instrument stops answering.

Two more were added on 29-Aug-2026. One is a server that diagnoses the failure
correctly and then overwrites the diagnosis with a later line, which is how a
server can be wrong out loud for weeks without anybody being able to see why.
The other is a read with no deadline, which does not fail at all: it stops,
and takes the device with it.

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

### Which servers had the defect

**Seventeen, all now fixed.** Sixteen went in four batches (`caa0b20`,
`8b6bbc7`, `a4a56f2`, `168f860`, `544d09e`); `NetworkUPSTool` followed on
30-Aug-2026, once the separate question of `upsd` not starting on its own had
been settled. `python3 tools/audit_init_device.py` now scans the 35 and finds
nothing.

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

**All 35 protected.** AlarmNotifier and AnalogInterlock never needed it:
neither has anything risky in `init_device` to begin with.

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

## 3. A status that a later line overwrites

Found on 29-Aug-2026 in `AnalogInterlock`, and worth stating separately because
neither audit above can see it and the symptom points away from the cause.

`mossbauer/warn/watercompressor` reported

```
ALARM | No permit: newcompressor = 10.80, must rise above 9.00
```

with the flow at 10.8 l/min against a threshold of 9. The value was read
correctly, it was plainly above the threshold, and the server said it was not.

The device had no `OutputDevice` property at all. Every cycle: the value passed
`ThresholdOn`, so `grant()` ran; `grant()` called `send("On")`; `send()` could
not build a proxy to an empty device name, set FAULT and wrote a status saying
which command had failed and why — the correct diagnosis, first try. It then
returned `False`, `grant()` returned without granting, and control fell through
to the tail of `cycle()`, whose job is to say why the permissive is not held.
That tail set ALARM and "must rise above" unconditionally. The FAULT was
replaced by a lie a few microseconds after being set, so no client, log or
poll ever saw it.

The same function's `trip()` had guarded against this from the start:

```python
if self.get_state() != tango.DevState.FAULT or state == tango.DevState.FAULT:
```

`grant()` had not. The asymmetry is the whole bug.

**The pattern.** A function that sets state and status on failure has to tell
its caller, and the caller has to stop. `grant()` now returns a bool and
`cycle()` returns when it is `False`.

**The second lesson is about defaults.** An empty `OutputDevice` could have been
taken to mean "this one only watches" — which is genuinely what this device is
for, under the `warn/` domain. It is not taken to mean that: watching is now an
explicit `WatchOnly` property, and an empty `OutputDevice` without it is refused
at start-up. Inferring intent from a missing property makes a `safety/` device
that loses its `OutputDevice` demote itself to a bystander, silently, which is
the same failure again with worse consequences. Same reasoning for `Reverse`,
the new direction property: reading the direction off which threshold is larger
would turn a transposed pair from a start-up refusal into an inverted interlock.

How it was tested: `cycle()` driven directly against stubs for all four
combinations of `Reverse` x `WatchOnly` plus the refused-command case, and the
three start-up refusals against a real server run from a `-file=` database.
Neither test touches the live chains.

---

## 4. A read with no deadline, inside the serialization monitor

Tango serialises calls to a device: every attribute read, every command and
`state()` itself take the device's monitor. So a call that blocks does not
block one client, it blocks the device. The symptom is unmistakable once seen:

    ping         answers instantly
    info         answers instantly
    state()      IMP_LIMIT, "not able to acquire serialization monitor"
    every attr   the same

`ping` and `info` are answered by the admin device, which does not take that
monitor. Anything that does, waits. To the Starter and to Astor the server is
perfectly healthy, because that is what they check.

WisselMCA did this twice on 29-Aug-2026, for two different reasons, and it is
worth keeping both:

| | what blocked | what it looked like |
|---|---|---|
| first | `while self.dev.read(...)` in `drain()`, unbounded | 0.7% CPU, a thread in `ppoll`, a 50 ms timeout going round for ever |
| second | `hid.device.read(n)` with no timeout at all | 0.0% CPU, a thread in `hid_read_timeout` → `pthread_cond_wait` |

The second is the more insidious: fourteen calls were written that way, the
card answers all of them for hours, and one lost reply is enough. There was no
USB error in `dmesg` -- nothing broke, a reply simply never came.

**How to find it.** `gdb` is on the Pis and this needs no debug symbols:

```bash
sudo gdb -p $(pidof -s WisselMCA) -batch -ex "thread apply all bt 12"
```

The library names alone tell the story: one thread deep in the instrument
library (`hid_read_timeout`, `pthread_cond_wait`) and one or more parked in
`Tango::TangoMonitor::get_monitor()` from `AutoTangoMonitor`. The first holds
the monitor; the rest are the clients you can see timing out.

**The rule.** Every read from an instrument gets a deadline, and every reply
gets checked for being empty. Not most of them: one is enough to wedge the
device, and it will be the one that never fails in testing. `tools/audit_reads.py`
cannot see this -- it reports which attributes reach the instrument, not
whether the call can return.

**And what a timeout means afterwards.** A reply that never came leaves the
stream out of step, so every command after it reads the previous one's
leftovers and reports a wrong count. A deadline alone converts a wedge into a
permanent stream of nonsense. WisselMCA resynchronises at the point of failure,
with the same bounded drain, so the next command starts clean.

---

## 5. What to do

The two halves are independent and can be done in either order. Both are
tractable in batches.

**Robustness** — done, all seventeen:

- ✅ **Sputtering (7)** — `caa0b20`. The rig was switched off, which made it the
  one batch whose failure path could be tested rather than reasoned about.
- ✅ **Hygrometer, FUGMCP, CenterOneGauge** — `8b6bbc7`.
- ✅ **Networked (3)** — `a4a56f2` and `168f860`, with reconnection for the two
  Elmitec servers.
- ✅ **GPIO (3)** — `544d09e`.
- ✅ **NetworkUPSTool** — the last one, 30-Aug-2026. Left until now because it
  also needed `upsd` starting on its own, settled first with a
  `Wants=nut-server.service` drop-in (see `netboot-shared-root.md`). Guarding
  `init_device` was the smallest part of it again: PyNUT opens one session and
  never renews it, so a restart of `upsd` left this end holding a socket that
  answered `BrokenPipeError` for ever — found in exactly that state, ON with
  all four attributes failing and the last real reading hours old. It now
  re-establishes the session on the next read. And `ups.status` is a set of
  flags, not a word: `"OL CHRG"`, a healthy UPS recharging after a cut, was
  being reported as FAULT.

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
python3 tools/test_analoginterlock.py  # the interlock's decisions and refusals
python3 tools/test_wisselmca.py        # every MCA read carries a deadline
python3 tools/test_networkupstool.py   # starting without upsd, and surviving it
```

The last three need PyTango, so they run on a Pi or on wolframite rather than
on a laptop; the two audits parse with `ast` and run anywhere. All three drive
stubs and reach no instrument, which is what makes them runnable on a Pi whose
card is in the middle of a measurement or whose UPS is carrying the LEEM.

Both have a `--self-test` that runs anywhere. audit_init_device's regression
fixture is this repository's own history: HuttingerPFGDC must report at
`caa0b20^` and must not at `caa0b20`.

audit_reads is a survey, not a verdict -- reading live is the right shape for
an attribute nobody watches continuously, and it exits 0 either way.
