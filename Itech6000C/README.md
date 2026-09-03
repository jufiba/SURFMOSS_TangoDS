# Itech6000C

Controls an **ITECH IT-6000C** series regenerative DC power supply over a raw
TCP socket, using SCPI. On the VSM it drives an electromagnet coil current.

Manuals on the wiki: `PowerSupply_ITech6000C.pdf`,
`PowerSupply_ITech6000C_programming.pdf` (the SCPI reference).

Runs on **pi-vsm**, server `Itech6000C/1`, device `vsm/power/coilcurrent2`,
`IP = PWSItech6000VSM.lab`, `Port = 30000`.

## The protocol

Plain SCPI, `\n`-terminated, over a persistent TCP connection.

| Sent | → attribute |
|---|---|
| `MEASure:SCALar:CURRent:DC?` / `:VOLTAGE:DC?` / `:POWER:DC?` | `Current` / `Voltage` / `Power` |
| `SOURce:VOLTAGE:LEVel:IMMediate:AMPLitude?` / ` <v>` | `SetVoltage` |
| `SOURce:CURRENT:LEVel:IMMediate:AMPLitude?` / ` <a>` | `SetCurrent` |
| `OUTPUT?` / `OUTPUT ON` / `OUTPUT OFF` | state / `OutputOn` / `OutputOff` |
| `SYST:VERS?` | `Identification` |

## Interface

- Properties `IP` (`PWSItech6000VSM.lab`), `Port` (30000), `Timeout` (5 s).
- Read attributes `Current` (A), `Voltage` (V), `Power` (W), `Identification`.
- Read-write `SetVoltage`, `SetCurrent`.
- Commands `OutputOn`, `OutputOff`, `sendCommand(str)` (write only, EXPERT),
  `SendQuery(str)` (EXPERT).

## Notes

Hardened: a supply that accepts the connection and then goes silent, or
answers `OUTPUT?` with nothing, faults with that fact instead of an
`IndexError` that took the server down. `connect()` is retried by `init_device`
but there is no background reconnect thread — a supply that drops needs an
Init.

Install: in `pyproject.toml`; standard library only (`socket`).
