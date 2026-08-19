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
element at runtime. As of 19-ago-2026 `leem.jdw` names 11 devices, of which two
are **not in the Tango database**:

| Referenced | Status |
|---|---|
| `leem/vacuum/gaugeMCH` | missing — the DB has `gaugePCH` and `gaugeEvap`, no MCH |
| `leem/measurement/positionXY` | missing — the DB has `LEEM2k`, `Uview`, `sampleDVM` |

Both are long-standing: `gaugeMCH` is referenced as far back as the original
`LEEM.jdw`. Either the devices are yet to be registered on the new DB or the
drawing needs updating to the current names.
