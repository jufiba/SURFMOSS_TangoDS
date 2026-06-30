# Deprecated device servers

These device servers are retired because their **hardware is dead or gone**. They
are kept here for reference and git history only. They are:

- **not** installed (excluded from `packages.find`, absent from `[project.scripts]`)
- **not** registered in the Tango database (death by omission at the clean-DB import)

If hardware ever returns, a server can be moved back up to the repo root, re-added
to `[project.scripts]`, re-registered in the DB, and assigned to a Starter — but
each would need testing against the new hardware first.

| Server | Reason retired |
|---|---|
| MitutoyoPostable | Serial interface to the Mitutoyo/Elmitec manipulator micrometers died. |
| SpecsXRC1000 | XRC1000 x-ray electronics are dead. |
| VarianMultiGauge | The last Varian MultiGauge unit died. |

_Distinct from `inactive/`: those are paused but potentially revivable; these are
considered dead._
