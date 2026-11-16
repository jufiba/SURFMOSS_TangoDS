# ElmitecLEEM2k

Tango device server for the Elmitec LEEM2000 program, over its TCP text
protocol (port 5566, `asc` mode, NUL-terminated replies). Module values are
read and set with `val $index [$value]`. See also `ElmitecUview` and
`docs/LEEMmacros.md`.

## Error replies

LEEM2000 answers some requests with an error code instead of a value or "0"
(Software_LEEM2000Script.pdf, SetValueToModule/GetValueFromModule TCP):
-1 module name/index wrong, -2 value out of limits, -100 module in local mode,
-101 internal fault, -102 module ramping to new value. With "val" the manual
gives the reply as the bare integer; with "get", LEEM2000 38 was seen to
send "ErrorCode -101". Both forms are recognised by leem_error_code().

Until 16-Nov-2026 the reads did float(reply), so these codes came back as
values (a ramping StartVoltage read as -102 V), and the writes dropped the
reply. Now every read and write attribute goes through _read_value() /
_write_value(), which raise ElmitecLEEM2kError naming the code, e.g.
"LEEM2000 'val 38' -> ErrorCode -102: module ramping to new value".

- A ramp is raised, not waited out: a read that blocked through a ramp would
  run past the client's Tango timeout. LEEMmacros.leem_read() retries.
- On the SPLEEM's LEEM2000 (v38.11, Oct 2026) -101 was also the reply for the
  image equalizers whenever their value was exactly 0. Not yet checked here.
- write_P2Lens is deliberately unchanged: the deadman thread and the
  AnalogInterlock's P2lensOFF/P2lensON go through it, and a write that
  raised there would change how the interlock chain fails. Its read does
  raise now, which the PANIC alarm on P2Lens > 1550 will see as an error
  instead of a low value while P2 ramps.
