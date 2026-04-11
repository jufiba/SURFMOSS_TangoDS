## GammaVacuumSPCe

Device server for the **Gamma Vacuum DIGITEL SPCe** ion pump power supply.

Communicates over the Ethernet Telnet interface (TCP port 23) using the
SPCe text command protocol.

## Attributes

- **Pressure** — ion pump pressure in mbar (converted automatically from
  the unit configured on the device: Torr, mbar, or Pascal)
- **Current** — ion pump current in Amperes
- **Voltage** — high-voltage output in Volts
- **SupplyStatus** — status message reported by the front panel

## Commands

- **On** — enable high voltage (start the ion pump)
- **Off** — disable high voltage (stop the ion pump)
- **send_command** *(expert)* — send a raw two-digit hex command code,
  optionally followed by data (e.g. ``"0b"`` or ``"12 1200"``)

## Device Properties

- **Host** — IP address or hostname of the SPCe controller
- **Port** — TCP port (default: 23)

## Requirements

- PyTango >= 9
- Standard Python library (``socket``)

## Installation

::

    pip install .

## Usage

::

    GammaVacuumSPCe instance_name
