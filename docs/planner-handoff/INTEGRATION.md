**Robot laboratory and planner integration agreement**

Version 0.1.0 is an initial contract for joint review. The accompanying JSON Schemas and examples can be consumed now; the proposed HTTP services and simulation adapters still need to be implemented.

**1. Shared messages**

| Message | Producer | Consumer | File |
| --- | --- | --- | --- |
| RobotCapabilitySpec | Robot laboratory | Planner | `contracts/v0.1/robot-capability.schema.json` |
| EnvironmentPackage | Planner | Robot laboratory | `contracts/v0.1/environment-package.schema.json` |
| PlanningRequest | Planner UI/client | Planner jobs | `contracts/v0.1/planning-request.schema.json` |
| PlanEvaluation | Planner | Both interfaces and exports | `contracts/v0.1/plan-evaluation.schema.json` |
| TransferCandidate | Orbital worker | Planner and export | `contracts/v0.1/transfer-candidate.schema.json` |
| VehicleSegmentRequest | Planner or robot experiment UI | Robot simulator | `contracts/v0.1/vehicle-segment-request.schema.json` |
| VehicleResponse | Robot simulator | Planner and replay | `contracts/v0.1/vehicle-response.schema.json` |

Every root message contains `schema_version`. Reject unsupported versions explicitly. For this pre-1.0 project, any incompatible change requires an agreed new contract version and migrations or an adapter; do not assume that a changed minor version is harmless. Unknown required fields, missing data, or unsupported robot families produce a structured issue.

The schemas validate structure. Semantic checks additionally enforce clocks, units, domains, asset hashes, geometry conventions and status consistency. The included validator applies both layers to the supplied fixtures; it is not a universal runtime validator for every production run.

**2. Coordinates and robot pose**

- Global surface geometry uses `MOON_ME_DE421`, in metres.
- Normalized local geometry is east/north/up: x east, y north, z up.
- Each environment stores its origin as a full body-fixed Cartesian position and a 3×3 matrix mapping local ENU vectors into the body-fixed frame.
- A point maps as `p_body_fixed = origin_body_fixed + R_enu_to_body_fixed @ p_enu`.
- The robot body frame is x forward, y left, z up. The imported model's root origin must be defined relative to its wheels/body and preserved by the exporter.
- Quaternions are `[x, y, z, w]`, normalized, and rotate body vectors into ENU. Identity means body forward east and left north.
- Lunar longitude is degrees east in [0, 360); latitude is degrees north in [-90, 90]. Named degree/radian suffixes are mandatory.
- Celestial direction vectors point from the observer toward the Sun/Earth, in ENU. They are unit vectors and use the declared geometric/apparent convention.

For an azimuth measured clockwise from north and elevation above the local horizontal, the ENU unit vector is `[cos(el)*sin(az), cos(el)*cos(az), sin(el)]`. Convert to radians before trigonometric functions.

GMAT orbital states retain their actual central body and frame ID; the worker converts kilometres and kilometres/second to contract metres and metres/second. Do not silently relabel an Earth-centred GMAT frame as a lunar body-fixed or local frame. Transform it using a recorded model if the UI needs a common scene.

The normalized terrain heightfield stores local up coordinates, not an arbitrary source's raw elevation values. The importer must derive that geometry from verified native horizontal and vertical definitions. A local tangent-plane representation must include the actual transformed surface shape; flattening a curved patch is an explicit approximation, not the default conversion.

**3. Time and sampling**

Each environment has `time_origin_utc` and samples at elapsed SI seconds `t_s`. All surface/robot messages for that environment use that same clock origin. A segment starts at `start_t_s`; its sample/control timestamps remain mission-relative and end at `start_t_s + duration_s`.

Convert UTC epochs through the chosen time library/SPICE internally; do not assume that civil-time string subtraction always represents elapsed SI seconds across leap seconds. Record the leap-second kernel and future time assumptions.

For a moved touchdown time, recompute the geometry/environment or issue a new version whose time coverage covers the new mission. Do not shift the labels on an old sunlight curve.

Samples must be strictly increasing. Version one uses left-constant loads/modes on `[t_i, t_(i+1))` for accounting. Include activity boundaries and refine environmental/constraint transitions. Endpoint values are for display/next-interval use, not an extra full timestep. A discontinuous mask cannot be smoothed away to create imaginary charging. Any interpolation policy for sky directions must normalize vectors and be versioned; near horizon crossings, refine geometry rather than trusting a coarse interpolated mask.

Use null plus an issue code for unavailable quantities. Do not use zero, NaN, infinity or an empty string as a stand-in for unknown physical data.

**4. Power accounting and vehicle response**

The planner owns the battery ledger and solar-generation model. The robot simulator supplies mobility behaviour and electrical response under its stated conditions.

`base_bus_power_w` is the standing vehicle load. `driving_bus_power_w` and response `mobility_bus_power_w` already include base plus mobility. Payload, radio and heater fields are incremental loads above that bus value. Thus:

```text
idle base = base_bus_power_w
driving base = response mobility_bus_power_w
              OR profile driving_bus_power_w as a declared fallback
total load = selected base + active science/radio/heater increments
```

Do not add the standing base twice. Do not add both a detailed mobility response and its coarse driving estimate. `mobility_bus_energy_wh` is the integral of the response's mobility-bus power only, not the full mission or net battery change.

Solar generation uses rated output scaled by irradiance, array orientation, terrain-relative solar visibility, and declared efficiency multipliers. The proposed simple visibility-times-incidence calculation is an approximation; record its policy. For a surplus, battery change is `eta_charge * surplus_w * dt_s / 3600`. For a deficit, it is `-deficit_w * dt_s / (3600 * eta_discharge)`. Enforce capacity and reserve events separately.

Initial energy is initial SOC times the scenario-adjusted usable capacity. A reduced-capacity scenario must not accidentally retain energy above its new capacity. The nominal reserve is a mission requirement; an impossible reserve/capacity combination must be reported, not silently lowered.

If battery voltage/SOC materially changes mobility, expand the response-model input domain and coupling. Until then, label the assumption that the response is valid across the modeled operating range. The detailed simulator must not independently overwrite mission SOC while also returning a load for the planner to integrate.

**5. Capability model and detailed simulation**

The robot laboratory first exports a supported reference profile and declared constant/table response. It can later export a calibrated lookup table or surrogate keyed by slope, speed, soil assumption, orientation and robot configuration.

Model metadata includes ID, version, profile hash, features, units, supported ranges, training/calibration sources, and known limitations. If a learned/table model asset is introduced, add an explicit content-hashed asset reference in the next agreed schema version. Do not resolve model names to mutable hidden data.

For batch planning, query the fast response model. For selected candidates, call the detailed segment simulator with robot/environment references, initial pose, controls, clock, soil assumptions and seed. Receive actual trajectory, power, elapsed times, and flags. If the response is outside its domain or discovers a new failure, invalidate dependent conclusions and rerun or report insufficient evidence.

The robot laboratory may render a selected mission using the planner's battery and environmental history. Rendering replay is not a new independent physical measurement. Detailed dynamic verification is identified separately by its engine/version and returned response.

**6. Orbital and surface assessment boundary**

`PlanningRequest.departure_screening` is enabled in version one. It refers to a trusted canonical GMAT family and a bounded epoch sweep. The permitted variables must be enforced. The request's spacecraft wet mass is independent of robot mass; null means launch-vehicle/propellant compatibility is not assessed. Do not infer launch mass from `RobotCapabilitySpec.mass_kg`.

`TransferCandidate` preserves actual departure/encounter/capture epochs, Earth-centred departure state, Moon-centred capture state, maneuver vectors, clearance, capture eccentricity, target residuals, supporting-file hashes and verification state. An accepted candidate requires convergence, valid event termination, physical clearance, target checks and repropagation checks. A status string alone is not evidence.

The top-level `PlanEvaluation` has separate transfer, surface and landing-access records. The supplied evaluation illustrates a valid synthetic surface accounting result with overall insufficient evidence because no transfer was executed. A valid V1 screening candidate can be supported only within its explicitly bounded scope, with capture-to-touchdown assumptions still exposed. Required unknowns inside that scope must produce insufficient evidence.

Capture-to-touchdown interval overlap is a schedule screen. Lunar orbit plane access, waiting fuel/thermal conditions and descent are unvalidated until implemented. Emit `assumed_not_dynamically_validated`, not a descent-success flag. Liftoff stays null if launch-to-departure timing is unknown.

**7. Proposed service endpoints**

These are implementation targets, not endpoints already running. Prefix APIs with `/v1` and generate the client types from the accepted schema/OpenAPI definitions.

| Method and path | Owner | Behaviour |
| --- | --- | --- |
| `POST /v1/robot-profiles` | Robot service or shared artifact service | Validate/store immutable RobotCapabilitySpec; return hash and asset URI |
| `GET /v1/robot-profiles/{id}` | Same | Return the exact versioned profile |
| `GET /v1/sites` | Planner | Curated sites, coverage and data quality |
| `POST /v1/environments` | Planner | Prepare a site/date/terrain scenario package; return job ID |
| `POST /v1/environment-samples` | Planner | Sample positions, heights, orientations and times; return visibility, directions and source/model IDs |
| `POST /v1/planning-runs` | Planner | Submit PlanningRequest for one candidate or a catalog sweep; return job ID |
| `POST /v1/departure-searches` | Planner orbital worker | Bounded trusted-template sweep; return job ID and candidate artifacts |
| `POST /v1/scenario-searches` | Planner | Run baseline/active failure discovery |
| `POST /v1/repair-searches` | Planner | Enumerate permitted repairs under fixed requirements |
| `POST /v1/robot-segments` | Robot service | Submit VehicleSegmentRequest; return job ID |
| `GET /v1/jobs/{id}` | Respective service | Status, progress, issue details and artifact references |
| `GET /v1/evaluations/{id}` | Planner | Scoped PlanEvaluation |
| `GET /v1/artifacts/{hash}` | Artifact service | Immutable authorized artifact bytes with checksum |

Version-one job states: `queued`, `running`, `completed`, `failed`, `cancelled`. Keep job completion distinct from physical constraint violation or solver nonconvergence. `completed` can return a useful failed-mission assessment.

Use structured errors with stable code, message, context and retryability. Examples: `UNSUPPORTED_SCHEMA_VERSION`, `UNKNOWN_VERTICAL_DATUM`, `MISSING_TERRAIN_COVERAGE`, `OUTSIDE_RESPONSE_DOMAIN`, `ORBITAL_NONCONVERGENCE`, `ORBITAL_GUARD_TERMINATION`, `UNVALIDATED_LANDING_ACCESS`, `ASSET_HASH_MISMATCH` and `TIME_RANGE_NOT_COVERED`.

**8. Assets, hashes and cache invalidation**

Large terrain/time-series assets are referenced, not copied into every request. Hash immutable stored file bytes with SHA-256. Transport those bytes without reformatting a JSON artifact if its hash is used; reserializing equivalent JSON may produce different bytes and a different hash. A changed hash creates a new artifact/version.

Fixture URIs resolve relative to `examples/integration`. Production URIs should be service/object-store references with deliberate access control, not arbitrary client filesystem paths. Validate size/type and path boundaries for imports. No arbitrary user script executes in GMAT workers. The validator resolves local fixture references only and makes no network requests.

Cache identity includes robot profile/model hashes, terrain and normalization hashes, kernel/script versions, date/time grid, activities, scenario, solver settings and seed. Any change invalidates dependent results. Training datasets must retain the identity of the simulator used to generate each label.

**9. Fixture workflow**

From the repository root:

```bash
uv run --with 'jsonschema[format]' python scripts/validate_handoff_contracts.py
```

Alternatively install `jsonschema[format]` in a project environment and invoke the script with that Python. The validator checks schema validity, all example messages, hashes, frame orthogonality, clocks, power conventions, analytical energy accounting and selected invalid cases.

The examples include:

- A hypothetical rover profile and synthetic flat terrain/environment.
- A stationary three-hour monitoring request with an enabled, unexecuted departure search.
- An exact synthetic energy example with prescribed lighting, independent of the placeholder sky vectors.
- A separate 200-second, 10 m driving segment and response at 120 W bus load.
- An explicit not-run orbital candidate with no fabricated maneuver or convergence results.

The fixtures are interface/analytical examples, not NASA terrain, ephemeris predictions, mobility experiments or solved transfers. The source class and notes must remain visible during development. Replace fixtures with real adapters individually while retaining them as deterministic contract checks.

**10. First integration milestone**

1. Both developers run the validator and import the same robot profile.
2. The planner displays the example request/evaluation with synthetic and not-run indicators.
3. The robot laboratory displays the normalized terrain and segment response using the shared coordinate/clock conventions.
4. Exchange a newly generated robot profile and verify hash invalidation.
5. Replace the flat environment with a normalized real site package; validate its frame/height mapping before rendering.
6. Replace the segment response with actual simulator output; reconcile time/power differences.
7. Populate orbital candidates only after the reference scripts execute and validation checks pass.

That sequence lets both systems develop independently while keeping integration observable from the beginning.
