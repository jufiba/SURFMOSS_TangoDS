# Synoptics (JDraw)

One `.jdw` per instrument, opened by `launch`:

```bash
./launch leem        # runs synopticappli leem.jdw
```

so the file name must be **lowercase** and match the argument: `leem.jdw`,
`mossbauer.jdw`, `sputtering.jdw`, `xps.jdw`.

`LEEM_*.jdw` are sub-panels of the LEEM synoptic (chamber PCH, the two dosers,
the sample stage), not alternative versions of it.

## Versions live in git, not in the file name

`leem.jdw` was consolidated on 19-ago-2026 from a set of hand-numbered copies
(`LEEM.jdw`, `LEEM_v2`, `LEEM_v3`, `LEEM_v4`); the newest, v4, became
`leem.jdw`. All of them are in the history of the commit before that, so
recovering one is `git show <commit>:synoptics/LEEM_v3.jdw`. **Do not add
`_v5`** — commit the change to `leem.jdw` instead.

## Device references need checking against the DB

A drawing referring to a device that no longer exists shows up only as a dead
element at runtime, so it is worth checking rather than noticing by eye:

```bash
python3 tools/check_synoptics.py
```

It reads every reference out of the `.jdw` files and checks the device against
the Tango database and the attribute or command against the device itself.

**Resolved on 28-Aug-2026.** All 119 references across the eight drawings were
checked and six were broken:

| Referenced | What it was | Done |
|---|---|---|
| `leem/vacuum/gaugeMCH/Pressure_IG1` | the retired VarianMultiGauge's attribute | now `Pressure`, on the Granville Phillips 350 that replaced it |
| `mossbauer/termperature/criostat` | a misspelling, in two places | corrected to `temperature` |
| `leem/measurement/PositionXY` | retired hardware, twice and with two capitalisations | elements removed |
| `xps/measurement/xraygun` | retired hardware, twice | elements removed |

The remaining references all resolve, except those on `sputtering.jdw` and the
UPS on `leem.jdw`, whose devices are registered but not running — the drawings
are right, the instruments are switched off.
