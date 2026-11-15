# Bounded surface repair and audit

Implemented and verified in the local app, 15 November 2026. This is a deterministic surface search, not a global mission optimizer. The scope preserves the original robot version, site, route, required activity sequence/durations, mission duration, reserve and maximum geometric Earth-outage limit.

Permitted proposals vary UTC calendar-day offset, an added wait at the first waypoint, usable-capacity/solar scenario gains and explicitly allowed heater state. Heater changes require an enabled thermal model. Capacity/solar gains are declared parameter scenarios, not hardware redesigns; mass, mechanics and thermal properties remain unchanged. Route/site alternatives are not yet searched.

The original request is rerun with the current captured implementation. The source's historical result remains distinct from this current baseline. All further nominal and audit missions use that same implementation. Required activities cannot be dropped, shortened or relocated. Added waiting consumes the existing duration and can create a deadline violation.

The finite candidate grid is deduplicated and ordered by an exposed cost: absolute date-change days, wait hours, percent capacity/solar gain and heater toggle, with explicit weights. A bounded number of nominal candidates is checked. The lowest-cost nominally supported candidates are **frozen before audit outcomes are read**. They receive identical independently generated audit perturbations, using a dedicated NumPy SeedSequence namespace. This audit stream is separate from the existing scenario-search RNG. Supported results require every selected audit case to be supported; incomplete or unsupported-domain cases never pass. Scenario factors are not clamped into the response domain.

Defaults audit capacity ×0.85–1, solar ×0.75–1, mobility power ×1–1.25, speed ×0.8–1, start delay 0–1800 elapsed SI seconds, and initial battery temperature ±3 °C when modeled. These are declared engineering sensitivity ranges, not measured distributions or real-world failure probabilities. The source surface remains fixed during nominal selection. Default audits use published correlated terrain surfaces 002/003, excluding the source surface; dedicated terrain RNGs and exact IDs are recorded. A surface can recur across hardware audit cases, and all candidates receive the same cases. Full ensemble tails, regional uncertainty, calibrated soil/dust, RF links and orbital/descent access remain unresolved. See [terrain uncertainty](TERRAIN_UNCERTAINTY.md).

The answer is labeled **smallest verified repair found** within the evaluated candidate/audit budgets. It is not globally optimal. Candidate-space size, checked/unsearched counts, audit selection and excluded nominal candidates remain visible. The report distinguishes a finished requested budget from exhaustive coverage of the finite grid. A failed bounded search does not establish physical impossibility.

Completed child missions retain replay, constraint states/margins and immutable exports. The parent export includes the source mission, all evaluated children, configuration, ranking policy, audit cases, source/model identities, robot, captured implementation and any referenced Diviner context. Reproduction compares every candidate/audit outcome as well as aggregate metrics. On cancellation, the last immutable checkpoint remains in the job and completed child missions remain available; a checkpoint is not accepted as a completed search.

## Interface reference lock

Direct build in the current Clavius dark workspace. The existing source/property modals, bounded-sweep results, comparison/replay controls and linked constraint events are the primary references. Refero's earlier live catalog attempts returned NO_SUBSCRIPTION; bundled form/focus/typography craft guidance supplements the existing product. No raster assets or separate visual system are needed.

| Choice | Existing reference | Reason |
| --- | --- | --- |
| Find alternatives beside recorded mission results | Existing detailed-probe action | Base a repair on a saved experiment, not an unsaved draft |
| Explicit permitted changes and budgets before launch | Existing scenario/property forms | Make scope and computational cost reviewable |
| Rank nominal cases, disclose fresh audits and retained requirements | Existing bounded-sweep comparison | Explain why an alternative qualifies and what was held fixed |
| Highlight only a candidate whose selected audit cases all pass | Existing constraint/status colors | Keep a nominal pass distinct from a verified sampled alternative |
| Nominal/audit replay links and parent evidence export | Existing shared-time replay | Let users inspect the specific constraint history |
| Scrollable candidate cards on a 390 px viewport | Existing modal/components | Keep details and actions accessible |

Desktop 1440 × 900 and mobile 390 × 844 controls/results were checked with no horizontal document overflow. A saved 12-hour January 14 mission violated its six-hour geometric Earth-outage limit. An explicit two-date search found the January 1 alternative and retained all science; its three audit cases passed. The 751,637-byte parent evidence ZIP reproduced every candidate/audit outcome and aggregate metric, and an independently exported child also reproduced in the test suite.

The default seven-date search completed 16 mission evaluations (seven nominal, nine audit) and found three sampled-audit-supported alternatives. Its lowest-cost result shifted the source by one calendar day to January 13, with all three audit cases supported. The original route, ten-minute science activity and six-hour outage limit were preserved. See `docs/validation/repair-default-search.json`.

Browser cancellation of a larger 28-candidate grid retained 12 checked nominal cases and one completed audit (13 total mission evaluations). No completed parent result was accepted. The 61,119-byte downloaded checkpoint matched its content identity, and completed child missions remained replayable. See `docs/validation/repair-cancellation.json`.

The 76-test backend suite also exercises a cold-battery repair that enables the thermostat, retains science and passes fresh cases, plus parent/child reproduction with a captured Diviner constant-boundary reference. Very large parent archives remain subject to the reproducer's existing 150 MB expanded-size guard; individual child exports provide a smaller reproduction unit.

The default search's 2,020,419-byte browser export also reproduced all 16 evaluated mission outcomes and aggregate metrics with no differences. The shared completed-report and partial-checkpoint URLs were reloaded successfully. Final build passed; the existing Three.js chunk-size advisory remains.
