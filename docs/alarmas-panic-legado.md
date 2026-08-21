# Legacy alarm system (PANIC / PyAlarm)

What the old alarm system actually watched, recovered from the database of the
retired network. **This document replaces the PANIC source tree as the
reference**: the code is third-party, Python 2 + Qt5, and is not being ported,
but the alarms it carried are the accumulated knowledge of what can go wrong in
these laboratories and why. That is worth keeping regardless of what implements
it next.

_Extracted August 2026 from `tango-backup-2026-08-08.sql`, the dump of the Tango
database on the old 10.10.99.x network, tables `property_device` and
`property`._

Two PyAlarm instances carried everything: `PyAlarm/1` watched LEEM, XPS **and**
VSM from a single device, reaching across the network with references such as
`10.10.99.1:10000/xps/...`, and `PyAlarm/2` watched the Mössbauer setup.

---

## `leem/safety/alarm` — server `PyAlarm/1`

| # | Alarm | Condition (`AlarmList`) | Severity | Receivers | Description |
|---|---|---|---|---|---|
| 1 | `LEEM_ROUGING_VALVE` | `leem/vacuum/roughingvalve == OFF` | WARNING | `%SURFMOSS_TELEGRAM`, `%SURFMOSS` | Roughing valve in LEEM is closed |
| 2 | `LEEM_TURBO_TEMP` | `leem/vacuum/turboPCH/TemperatureBearing > 35` | ALARM | `%TELEGRAM` | Preparation turbopump is too hot |
| 3 | `LEEM_POWER` | `leem/safety/ups/UpsStatus == "OnBattery"` | ALARM | `%SURFMOSS_TELEGRAM`, `%SURFMOSS` | LEEM UPS supply is on battery |
| 4 | `LEEM_P2_Water` | `leem/safety/water/channel3 < 0.2` **AND** `leem/measurement/LEEM2k/P2Lens > 1550` | ALARM | `%SURFMOSS_TELEGRAM`, `%SURFMOSS` | There is not enough cooling water for the current value of P2 |
| 5 | `LEEMTURBOWATER` | `leem/safety/water/channel0 < 0.5` | ALARM | `%SURFMOSS_TELEGRAM`, `%SURFMOSS` | Not enough water for cooling turbo |
| 6 | `LEEM_WATER_DOSER1` | `leem/safety/water/channel2 < 0.5` **AND** `leem/power/hv1/power > 1.0` | ALARM | `%SURFMOSS_TELEGRAM`, `%SURFMOSS`, **`ACTION(alarm:command,leem/power/hv1/OutputOff)`** | No water while using doser with HV1 |
| 7 | `LEEM_WATER_DOSER2` | `leem/safety/water/channel2 < 0.5` **AND** `leem/power/hv2/power > 1.0` | ALARM | `%SURFMOSS_TELEGRAM`, `%SURFMOSS` | No water while using doser with HV2 |
| 8 | `XPS_Humidity` | `xps/safety/hygrometer/Humidity > 80` | ALARM | `%SURFMOSS_TELEGRAM` | Humidity too high in XPS laboratory, water on the floor? |
| 9 | `LEEM_Humidity` | `leem/safety/hygrometer/Humidity > 80` | ALARM | `%SURFMOSS_TELEGRAM` | Humidity too high in LEEM laboratory, water on the floor? |
| 10 | `VSM_MAGNET_WATER` | `vsm/safety/water/channel1 < 3.5` **AND** `vsm/power/coilcurrent2/Power > 50` | WARNING | `%SURFMOSS_TELEGRAM` | Not enough water flow on magnet with power applied |

### ⚠️ Alarm 6 is the only one that acted

Every other entry in this table sends a message and nothing else. `LEEM_WATER_DOSER1`
carries an `ACTION(alarm:command,...)` receiver, so on firing it **switched the
HV1 supply off** by calling `OutputOff` on it. That is the only automatic
intervention the old system performed, and any replacement has to decide
deliberately whether to keep it.

### The asymmetry between DOSER1 and DOSER2

Alarms 6 and 7 watch the same water channel for the same two dosers, on the same
threshold, at the same severity — but **7 does not switch HV2 off**. Nothing in
the database explains why. It is most likely that the action was added to DOSER1
after an incident and never mirrored, rather than a considered decision that HV2
is safe without water. Treat the pair as one requirement when reimplementing,
and settle which behaviour is the intended one.

### Other properties of `leem/safety/alarm`

| Property | Value |
|---|---|
| `AlertOnRecovery` | `True` |
| `MaxMessagesPerAlarm` | `5` |
| `FromAddress` | `labrg@iqfr.csic.es` |

---

## `mossbauer/safety/alarm` — server `PyAlarm/2`

| Alarm | Condition | Severity | Receivers | Description |
|---|---|---|---|---|
| `MOSSBAUER_COMP_WATER` | `mossbauer/safety/waterflow/channel0 < 5` | WARNING | `%SURFMOSS_TELEGRAM`, `%SURFMOSS` | no enough water in compressor of Mossbauer Criostat |

`FromAddress = labrg@iqfr.csic.es`, `MaxMessagesPerAlarm = 5`.

---

## Phonebook

A free property of the `PANIC` object in the database, resolving the `%NAME`
receivers used above.

| Entry | Resolves to |
|---|---|
| `%SURFMOSS` | surfmoss@googlegroups.com |
| `%SURFMOSS_TELEGRAM` | `TG:-259679457` (group) |
| `%TELEGRAM` | `TG:8634682` |
| `%JUAN_TELEGRAM` | `TG:8634682` |
| `%GUIO` | gdelgadosoria@iqfr.csic.es |
| `%JUAN DE LA FIGUERA` | juan.delafiguera@gmail.com |

---

## ⛔ What is **not** in the backup

Two things are missing, and without them nothing gets delivered no matter how
faithfully the conditions are reimplemented:

- **The Telegram bot token.** The chat IDs are all above, but a chat ID without
  a token sends nothing. The token lived in PANIC's own configuration, outside
  the database, and is not in the dump.
- **The SMTP configuration**, i.e. how mail was actually sent.

If the same Telegram group is to be reused, the token has to be recovered from
the old system before it is decommissioned. Otherwise a new bot is created and
added to the group, and only the chat IDs above are still useful.

---

## Taxonomy for the redesign around `AnalogInterlock`

Eleven alarms, in three shapes plus one gap.

### Simple analogue threshold — 5 of 11

Alarms **2, 5, 8, 9** and the Mössbauer one. `AnalogInterlock` covers these
directly, and covers them **better** than PANIC did: it has hysteresis, so a
value sitting on the threshold does not chatter, and staleness detection, so a
publisher that froze on its last good reading is caught instead of being
believed.

### Two analogue attributes conjoined — 4 of 11

Alarms **4, 6, 7, 10**, all of the same shape: *low flow* **AND** *power being
applied*. The second term is what stops them firing every time the equipment is
switched off, which is most of the time.

`AnalogInterlock` reads a single attribute, so as it stands these are out of
reach. Covering them needs a conditioning input — an `EnableAttribute` with its
own threshold, so the interlock only arms when the equipment is actually
powered — or they stay outside the new system.

### Discrete, not analogue — 2 of 11

Alarm **1** tests a valve for state `OFF`, and alarm **3** compares the string
`UpsStatus == "OnBattery"`. Neither is a number against a threshold. They need a
sibling — a `DiscreteInterlock` or `StateInterlock` — or the condition moves
into the device server itself, exposed as a boolean attribute that an
`AnalogInterlock`-style watcher can act on.

### The gap: notification

`AnalogInterlock` drops a permissive and records why. It does **not** send a
Telegram message or an email. That is the whole delivery half of what PANIC did,
and nothing in the new stack provides it yet.

This connects to two open threads: the outstanding msmtp/Gmail work on
wolframite, and Option D — a minimal alarm device server subscribed to the
`State` and `Trip` events of the individual `AnalogInterlock` instances, whose
only job is to notify.

### Architectural note

Distributing the watching across the Pis removes the cross-network references
(`10.10.99.1:10000/...`): each Pi watches its own instruments, and an alarm no
longer depends on a single device being up and able to reach three laboratories.

What is lost is the **consolidated view**. PANIC could show every alarm in one
place; a set of independent interlocks cannot. That, rather than the watching
itself, is what would justify a lightweight aggregator.

---

## Appendix: alarms that existed and were retired

From `property_hist`. Names only — the formulas were not recovered, and these
were already gone before the dump.

- `LEEM_P2_WATERLOW`
- `MOSSBAUER_WATER`
- `MOSSBAUERWATER`
- `XPS_water_runing_and_gun_off`

The near-duplicate pair `MOSSBAUER_WATER` / `MOSSBAUERWATER`, and
`LEEM_P2_WATERLOW` against the surviving `LEEM_P2_Water`, suggest alarms were
renamed rather than edited in place.
