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
| `OUTPUT?` / `OUTPUT ON` / `OUTPUT OFF` | state / `OutputOn` / `OutputOff` / the deadman |
| `SYST:VERS?` | `Identification` |

## Interface

- Properties `IP` (`PWSItech6000VSM.lab`), `Port` (30000), `Timeout` (5 s),
  `DeadmanTimeout` (0 = disabled).
- Read attributes `Current` (A), `Voltage` (V), `Power` (W), `Identification`,
  `TimeSinceKeepalive` (s), `DeadmanTripped`.
- Read-write `SetVoltage`, `SetCurrent`.
- Commands `OutputOn`, `OutputOff`, `Keepalive`, `sendCommand(str)` (write
  only, EXPERT), `SendQuery(str)` (EXPERT).

## Keepalive and deadman

An interlock cannot watch itself: if its process dies it stops looking, and it
also stops saying that it stopped looking. The keepalive/deadman pair closes
that hole by splitting the job between two processes. While the permissive is
granted, `vsm/safety/interlockmagnetwater` sends a `Keepalive` on every cycle —
not an order to switch on, a sign of life: *I am still here and I still see
water*. This server runs a deadman thread that times how long it has been since
the last one, and if more than `DeadmanTimeout` seconds pass it **switches the
output off on its own**, doing what `OutputOff` does. So if the Pi running the
interlock is powered down, hangs, or has its process killed, the magnet does not
keep its current waiting for an order that will never arrive. Silence, not a
message, is what triggers the protection: it is the only signal a dead process
can still send.

`Keepalive` never touches the output — recovering from a deadman trip needs an
explicit `OutputOn`, which also clears `DeadmanTripped`. `DeadmanTimeout = 0`
(the default) disables the thread entirely, so an instance nobody supervises is
unaffected. Set it comfortably above the restart time of whatever sends the
keepalives, or a routine restart of that server drops the output by itself;
10 s against the interlock's 1 s poll is the value used on the VSM, matching
`FUGMCP` and `RaspberryButton`.

## Notes

- **One socket, one lock.** Every exchange goes through `_send` (a command with
  no reply) or `_ask` (a query), both under `_io_lock`. The deadman thread runs
  outside Tango's serialization monitor, so without the lock its `OUTPUT OFF`
  could interleave with a client's half-finished query and both would read the
  wrong answer — on the supply that feeds the magnet. Same reason `FUGMCP` has
  `_txn`.
- The bodies of `OutputOn`, `OutputOff` and `Keepalive` live in `do_output_on`,
  `do_output_off` and `do_keepalive`, outside the `@command` wrappers, so they
  can be exercised without a Tango logger — as `AnalogInterlock.do_bypass` is.
- Hardened: a supply that accepts the connection and then goes silent, or
  answers `OUTPUT?` with nothing, faults with that fact instead of an
  `IndexError` that took the server down. `connect()` is retried by
  `init_device` but there is no background reconnect thread — a supply that
  drops needs an Init.
- Tests: `tools/test_itech6000c.py`, against a stub socket. No supply is
  contacted.

Install: in `pyproject.toml`; standard library only (`socket`, `threading`).
