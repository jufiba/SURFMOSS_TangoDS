# SURFMOSS Tango Device Servers

A collection of [Tango Controls](https://www.tango-controls.org/) device servers developed for the SURFMOSS laboratory. The servers cover vacuum equipment, power supplies, motion control, sensors, cameras, and data acquisition hardware.

## Requirements

- Python 3
- [PyTango](https://pytango.readthedocs.io/) (the `pytango` pip package)
- A running Tango database

See `requirements.txt` for the full list of Python dependencies.

## Installation

Install dependencies:

```bash
pip install -r requirements.txt
```

Install an individual device server:

```bash
cd <DeviceServerDirectory>
pip install .
```

## Device Servers

### Vacuum & Gauges

| Directory | Description |
|---|---|
| `GammaIonPump` | Gamma Vacuum ion pump controllers |
| `LeyboldCenterOne` | Leybold CenterOne single-channel vacuum gauge |
| `LeyboldIG3` | Leybold IG3 gauge electronics |
| `MKSGauge` | MKS PDR9000 unit with 972B transducer |
| `PfeifferDCU002` | Pfeiffer DCU002 display unit |
| `PfeifferTC100` | Pfeiffer TC100 turbopump controller |
| `PfeifferTU400` | Pfeiffer TU400 turbopump controller |
| `VarianMultiGauge` | Varian Multigauge controller (hot cathode gauge) |

### Pumps & Flow

| Directory | Description |
|---|---|
| `PfeifferHiScroll` | Pfeiffer HiScroll scroll pump |
| `VarianTV301nav` | Varian/Agilent TV301 Navigator turbopump with integrated controller |
| `BronkhorstMFC` | Bronkhorst mass flow controllers |
| `SEAWaterflowmeter` | SEA YF-S201 water flow sensor via Raspberry Pi GPIO |
| `WaterSwitch` | Cooling water flow detection sensor |

### Power Supplies & High Voltage

| Directory | Description |
|---|---|
| `AGPolaritySwitch` | Arduino-based polarity switcher for high-current (up to 30 A) power supply |
| `AMLPGC1` | AML PGC1 pressure/gauge controller |
| `FUGMCP` | FUG MCP 140-1250 HV power supply (1250 V, 100 mA) via Probus |
| `HuttingerPFG-DC` | Huttinger PFG-DC1500 DC power supply for magnetron sputtering |
| `HuttingerPFG-RF` | Huttinger PFG-RF300 RF power supply for magnetron sputtering |
| `Itech6000C` | ITech 6000C power supply via Ethernet |
| `tti604` | RS TTI 604 digital multimeter |

### Motion & Positioning

| Directory | Description |
|---|---|
| `ArduinoMotor` | Arduino-based motor driver |
| `MitutoyoPostable` | Mitutoyo positionable stage |
| `Motor` | Generic motor device server |

### Sensors & Instruments

| Directory | Description |
|---|---|
| `ArduinoPt` | Arduino connected to a Pt100/Pt1000 temperature module |
| `CryoCon32` | Cryocon32 temperature controller (Mossbauer transmission setup) |
| `Hygrometer` | Arduino with YL-69/YL-38 humidity/moisture sensors |
| `Keithley2100` | Keithley 2100 6½-digit digital multimeter (USB-TMC) |
| `SRIlockin830` | SRI 830 lock-in amplifier |
| `TempSensorDS18B20` | DS18B20 1-wire temperature sensor via Raspberry Pi |

### Data Acquisition

| Directory | Description |
|---|---|
| `ArduinoDAC` | Arduino-based DAC interface |
| `MCC1208LS` | Measurement Computing MCC 1208LS USB DAQ box |
| `PIDController` | Generic PID controller device server |
| `VSMControlDevice` | VSM data acquisition and hysteresis cycle imaging |

### Cameras & Imaging

| Directory | Description |
|---|---|
| `ElmitecUview` | PEEM end-station data reader (requires UView running) |
| `V4L2Camera` | V4L2 camera frame grabber |
| `WebCam` | Webcam via V4L2/pygame |
| `WisselMCA` | Wissel Multichannel Analyzer for Mossbauer spectroscopy |

### LEEM / SPECS Equipment

| Directory | Description |
|---|---|
| `ElmitecLEEM2k` | Settings interface for Elmitec LEEM2000 |
| `SpecsXRC1000` | SPECS XRC1000 X-ray gun electronics status |

### Network & Infrastructure

| Directory | Description |
|---|---|
| `NetworkUPSTools` | Wrapper for NUT (Network UPS Tools) |
| `PANIC` | PANIC alarm system device server (fork of [tango-controls/PANIC](https://github.com/tango-controls/PANIC)) |

### Raspberry Pi

| Directory | Description |
|---|---|
| `RaspberryButton` | GPIO output pin control (e.g. relay) |
| `RaspberrySwitch` | GPIO input pin for reading a switch |

## Scripts

The `scripts/` directory contains Tango macros and utility scripts for instrument control (LEEM, VSM, sputtering, dosing).

## Synoptics

The `synoptics/` directory contains Tango synoptic panel definitions.
