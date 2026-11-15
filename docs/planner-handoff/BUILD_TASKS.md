**Planning implementation backlog and acceptance checks**

Owner labels: P = planning developer, R = robot laboratory developer, J = joint decision/review. The ordering is based on dependencies; Earth departure screening is a version-one requirement. The schemas are a proposed initial contract and should be frozen jointly before implementation proceeds far.

| Order | Task | Owner | Dependency | Acceptance check |
| --- | --- | --- | --- | --- |
| 0 | Agree on version-one scopes, units, frames, power conventions and unsupported outcomes | J | Handoff review | Both can explain departure vs encounter vs capture vs touchdown; one accepted example per message |
| 1 | Run contract validator; render synthetic environment, robot profile and sample result | P + R | 0 | Messages validate; both interfaces show synthetic-fixture labels |
| 2 | Install scientific dependencies and verify one site ingestion | P | 0 | Source manifest, hashes, coordinate/height checks, masks and reusable site package |
| 3 | Install GMAT and execute the two unmodified reference cases | P | 0 | Captured outputs, residuals, termination events, software/data versions; source guesses not reported as solved results |
| 4 | Export one reference robot capability profile and deterministic response fixture | R | 1 | Profile hash/version accepted by planner; model domain and power semantics documented |
| 5 | Implement pinned SPICE geometry and local-frame conversion | P | 2 | Analytical checks and matched-convention reference comparison pass |
| 6 | Implement regional horizon sampling and solar-disk visibility | P | 5 | Convergence checks and at least two observed-scene comparisons recorded |
| 7 | Implement activity and energy integration with geometric contact intervals | P | 4, 6 | Exact charge/discharge fixtures, reserve/capacity events, no double-counted power |
| 8 | Build fixed route/schedule evaluator for two curated regions | P | 7 | One complete nominal run with task completion, time series and constraint margins |
| 9 | Wrap the fixed-epoch GMAT family in a bounded departure search | P | 3 | Explicit allowed variables, candidate state/epochs, residuals, clearance and capture checks |
| 10 | Implement job API, persistent job states, caches and cancellable worker tasks | P | 1; evolves with 2–9 | API responds with job ID; CPU work does not block API; partial/nonconverged results preserved |
| 11 | Build date/site comparison and departure results UI | P | 8, 9, 10 | Separate transfer, surface, and assumed landing-access evidence; source quality visible |
| 12 | Join capture candidates to assumed touchdown intervals | P | 9, 11 | Arithmetic compatibility shown separately from orbital/descent validation |
| 13 | Generate bounded uncertainty scenarios and random baseline | P | 8 | Reproducible seed/configuration, separate audit set, explicit uncertainty assumptions |
| 14 | Implement failure explanations and constrained repair enumeration | P | 13 | First violation identified; repairs preserve required tasks and are retested on fresh scenarios |
| 15 | Connect a selected route segment to detailed robot simulation | P + R | 4, 8 | Same robot/environment/scenario references; timestamps and frames align; divergence recorded |
| 16 | Add evidence export and replay from immutable inputs | P | 11–15 | Export contains source/model versions, hashes, assumptions, results and limitations |
| 17 | Publish version-one validation report and recorded demonstration | J | 3, 6–16 | Full workflow replayed with bounded departure and surface analyses; unresolved landing access labeled |
| 18 | Train margin regressor baseline and optional neural ensemble | P | 13, stable simulator | Held-out metrics, near-failure errors and model-domain checks; labels trace to simulator version |
| 19 | Add active scenario selection | P | 18 | Equal-budget comparison against random testing; reported candidates rerun in simulator |
| 20 | Add automated time/energy-aware routing and scheduling | P | 8, 14 | Static routing baselines plus waiting/charging/deadline cases; discretization limitations recorded |

**Version one completion**

Tasks 0–17 define the first complete application. Predefined routes and a canonical transfer family are acceptable in this version. The demo must still include both Earth departure screening and the complete surface failure/repair loop. Tasks 18–20 extend the research and planning capabilities after the numerical foundation is reproducible.

If GMAT installation or a reference solve is blocked, preserve that as a visible blocker with source input/output logs. A simple synthetic trajectory may be used to connect the interface, but cannot be shown as an actual departure-screening result.

**Planning developer module layout**

```text
planner/
  schemas/            # load agreed contract versions
  catalog/            # source manifests, site catalog, immutable assets
  terrain/            # import, normalize, masks, levels of detail
  geometry/           # frames, SPICE, horizons, environment sampling
  surface/            # activities, mobility adapter, solar/battery, constraints
  orbital/            # GMAT adapter, reference cases, epoch sweeps, validation
  planning/           # route/schedule candidates, ranking, departure/surface joins
  scenarios/          # bounds, distributions, audit and adversarial experiments
  repair/             # permitted changes, cost policy, feasibility verification
  models/             # feature generation, labels, training, active selection
  jobs/               # worker execution, persistence, cancellation, artifacts
  api/                # HTTP handlers and generated client contract
  ui/                 # mission forms, maps, timelines, comparisons
```

This is a logical layout, not a requirement to deploy separate services. Begin with one backend and one scientific worker, plus the robot laboratory's adapter. SQLite and local files are sufficient for local collaboration; public hosting needs persistent/shared artifact storage appropriate to the deployment.

**Interface acceptance cases**

| Case | Expected behaviour |
| --- | --- |
| Departure solver does not converge | Keep surface results; report the bounded-search failure; do not call the mission physically impossible |
| Lunar capture exists, descent access unknown | Show conditional touchdown-date comparison and the unresolved connection |
| Required terrain lies outside supported data | Insufficient evidence for that assessment, with the missing region identified |
| Imported robot is outside a learned model's domain | Use a supported deterministic fallback or request new robot experiments |
| Date changes | Invalidate date-dependent geometry/plans and dependent results |
| Robot changes | Invalidate vehicle-dependent energy/mobility and surrogate results |
| Reserve is violated between recorded samples | Refine or interpolate consistently and report the crossing/event policy |
| Detailed replay discovers a new obstacle/clearance failure | Record the new evidence; invalidate/revise the candidate and rerun planning |
| Optional science is removed | Expose the loss; never remove required tasks implicitly |
| Same request is rerun | Identical immutable inputs and seeds give reproducible numerical results within declared tolerances |

**Integration cadence**

Freeze the agreed initial message types together, then integrate one fixture immediately. At each milestone, exchange one real output and one deliberate failure case. Review schema changes jointly and update examples and validators in the same change. The two interfaces should share stable IDs rather than attempting to infer state from filenames or screenshots.

For the demonstration, precompute a small validated case set and retain the ability to rerun it. Clearly identify cached results, new runs, synthetic interface fixtures and nonconverged searches.
