# MFC

A minimal driver for **Bronkhorst** mass flow controllers, over RS-232 using
the Bronkhorst ASCII (FLOW-BUS / ProPar) protocol. On the sputtering rig, the
Ar and O₂ lines.

Manual on the wiki:
`MassFlowController_Bronkhorst_917027_manual_rs232_interface.pdf`.

Runs on **sputtering.lab**, server `MFC/1`, two devices:
`sputtering/vacuum/mfc_Ar`, `sputtering/vacuum/mfc_O2` (one per serial port).
**38400** 8N1.

## The protocol

Bronkhorst ASCII, `:`-framed, hex payload, `\r\n`-terminated. Node address
`80` (hex). The two parameters used:

| Parameter | |
|---|---|
| `0x0121` | setpoint |
| `0x0120` | measured flow |

Both are 16-bit, `0–32000` mapping to `0–100 %` of the controller's full
scale, so the DS divides / multiplies by **320** to get a percentage:

```
read setpoint :   :06800401210121\r\n   ->  reply, int(reply[11:15],16) / 320
write setpoint:   :0680010121<hhhh>\r\n  where hhhh = int(320 * percent)
read measure  :   :06800401210120\r\n
```

## Interface

- Property `SerialPort` (**mandatory**).
- Attributes `SetPoint` (read-write, %) and `Measure` (read, %).
- Command `Blink` — flashes the controller's LEDs (`:06800100600139`), for
  identifying which physical unit is which.

## Notes

- Everything is in **percent of full scale**. The actual sccm depends on the
  controller's calibrated range, which this DS does not know or read — put the
  gas and range in the device alias or a note.
- Not hardened beyond the port open: `write_SetPoint` and `Blink` still have a
  leftover `print(response)`, and there is no reconnect thread.
- One `MFC` **server** process serves both devices; each needs its own
  `SerialPort`.

Install: in `pyproject.toml`; needs `pyserial`.
