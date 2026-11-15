**Lunar planning and Earth departure screening handoff**

Version 0.1.0 · Prepared 14 November 2026 · Recipient: planning-system developer

Build the planning half of Lunar Failure Foundry. A user supplies a robot configuration, candidate lunar regions, a date range, and mission requirements. The application screens Earth departure opportunities, compares lunar surface conditions, evaluates a route/activity plan, explains failures, and proposes alternatives. The robot laboratory supplies vehicle capabilities and detailed mobility replays.

Version one includes Earth departure screening. Its supported orbital scope starts from a declared Earth parking orbit and ends at a modeled lunar encounter/capture. Lunar landing time remains a separate input or explicitly assumed interval after capture. Surface suitability, transfer convergence, and unmodeled orbital access must remain distinguishable in the results.

The deliverables accompanying this handoff are a data/API inventory, an integration agreement, a prioritized backlog, JSON Schemas, synthetic example messages, and a contract validator. They define interfaces; they do not implement or validate an orbital or surface simulator.

**1. Product behaviour**

The first complete workflow is:

1. Import the robot laboratory's capability profile, or select a clearly labeled hypothetical reference rover.
2. Choose two curated lunar regions and candidate touchdown times.
3. Set the required activities, mission duration, reserve, mobility limits, and geometric communication assumptions.
4. Set a departure-epoch range and a supported parking-orbit/transfer family.
5. Compute surface illumination, geometric Earth visibility, and mission energy.
6. Run bounded departure/capture searches and show convergence and residuals.
7. Compare candidate site/time/plan combinations, retaining distinct transfer and surface results.
8. Apply plausible delays, terrain realizations, and hardware uncertainties.
9. Explain the first violated constraint and compare repairs.
10. Export configuration, source versions, assumptions, and results for replay.

Use three assessment outcomes: `supported_under_assumptions`, `constraint_violated`, and `insufficient_evidence`. Every outcome has an `assessment_scope`. A successful transfer solve does not establish safe descent, and geometric Earth visibility does not establish a usable or booked communication link.

**2. Ownership and boundaries**

| Responsibility | Planning developer | Robot laboratory developer |
| --- | --- | --- |
| Lunar datasets, normalization, site catalog | Owns | Consumes normalized environment packages |
| Ephemerides, terrain horizons, environmental conditions | Owns | Uses supplied conditions for replay |
| Earth departure/capture screening | Owns | Supplies mass/power capabilities where relevant |
| Mission routes, activities, constraints, repair search | Owns | Returns detailed segment behaviour |
| Solar generation and mission battery ledger | Owns one shared implementation | Displays returned values; supplies mobility bus power |
| Robot import, physical configuration, mobility dynamics | Consumes exported capability profile | Owns |
| Fast vehicle-response model | Consumes and checks validity domain | Exports versioned model or tables |
| ML for mission margins and active scenario selection | Owns | May separately fit a mobility surrogate |
| Global site/date interface | Owns | Owns robot laboratory and detailed replay controls |
| Schema and fixture changes | Joint review | Joint review |

These are two cooperating simulation layers. The planning model evaluates many missions cheaply. The detailed robot model investigates selected traverses and failures. Agreement is expected when both use the same response model and assumptions; additional dynamics can expose a new issue. Record that disagreement and rerun the plan rather than silently substituting results.

**3. Dataset ingestion and site packages**

Start with NASA PGDA Product 78 Site01 Connecting Ridge and one comparison region, such as Site04 Shackleton rim. Obtain nominal terrain, measurement counts, height/slope errors, regions of interest, and the supplied error realizations. Use Product 90 regional terrain around each local patch for distant horizon blockers. Optional LROC stereo terrain and orthophotos add detail and visual context. Exact sources and files are in `DATA_SOURCES.md`.

Build these functions:

- `ingest_dataset(source_id, version, selection)` downloads selected assets, verifies sizes/checksums where supplied, and creates a source manifest.
- `normalize_terrain(asset, source_metadata)` converts a documented native coordinate/height convention into the project's normalized geometry.
- `make_site_package(site_id, roi, resolutions)` packages analysis terrain, regional context, masks, and visualization assets.
- `inspect_site_quality(site_package)` reports effective resolution, interpolation/measurement support, nodata, and unmodeled hazards.

Preserve raw files. Record source URLs, product IDs, download timestamps, file hashes, horizontal frame/projection, vertical definition, units, nodata values, and pixel registration. Counts are not uncertainty, grid spacing is not guaranteed accuracy, and nodata must not become flat ground. Quantitative COG reads must use the intended resolution rather than a display overview.

Product 78's README describes surface height Z but does not fully resolve its vertical zero in the inspected text. Before merging it with Product 90, inspect GeoTIFF metadata, numeric ranges, original paper, and matching coordinates. Add a known-point conversion check. Do not automatically add a reference radius to an unverified Z quantity. The integration contract accepts normalized local geometry, not an undocumented raw raster.

**4. Geometry and surface conditions**

Use pinned SPICE kernels locally for repeatable batch calculations. The initial bundle in `DATA_SOURCES.md` matches the MOON_ME/DE421 terrain convention. Horizons is useful for a prototype and cross-checks; record its returned ephemeris/frame because the service can use a different ephemeris generation.

Implement:

1. Body-fixed surface point conversion and local east/north/up transforms.
2. Sun and Earth direction calculations for requested epochs.
3. Terrain horizon profiles for each candidate site, route sample, and observer/array height.
4. Finite solar-disk visibility above the terrain horizon.
5. Panel incidence using the robot's orientation and array normal.
6. Geometric Earth-centre line of sight as the version-one contact proxy.
7. Sunlight and contact intervals, including the longest interruption.

The environment API must sample a position and time. A single sunlight curve at the landing point cannot represent a moving rover. Route-dependent visibility must be sampled at the actual modeled positions.

Cache static horizon profiles by terrain hashes, point/height, algorithm version, resolution, and horizon policy. Cache celestial geometry by epoch/frame/kernel versions. Refine spatial, azimuth, and temporal resolution until key results converge. A small high-resolution tile needs regional terrain beyond its boundary.

The first communication output is named `earth_center_visible`; label its intervals as geometric visibility. Station-specific visibility, antenna gain, RF budgets, bandwidth, and service scheduling are later model layers.

**5. Vehicle capabilities and mission energy**

Read `RobotCapabilitySpec` from the robot laboratory. Version one supports a declared wheeled rover family. It supplies mass, dimensions, clearance, battery parameters, array configuration, base electrical load, activity increments, and a mobility-response model with a validity domain.

The planning implementation owns the mission battery ledger. For a net surplus, apply charge efficiency; for a deficit, account for discharge efficiency. Integrate with elapsed SI seconds converted to hours. Enforce battery capacity, curtail excess generation, locate reserve crossings, and stop or flag operations requiring unavailable energy.

Power conventions are defined in `INTEGRATION.md`. A detailed driving response includes base-plus-mobility bus load. Add payload, radio, and heater increments exactly once. Solar generation is computed separately by the planner.

Required activities contain duration, location/route, load mode, timing constraints, and required/optional status. The mission cannot become feasible by removing required science. Version-one thermal behaviour may use a declared heater-load assumption; actual battery temperature needs a separate thermal model.

**6. Route and activity planning**

Start with two or three predefined routes and schedule templates per region. This supports useful date/site/repair comparisons while the automatic planner is developed.

Then build a terrain graph with explicit blocked/unknown cells and mobility limits. Use the exported robot response model to estimate edge travel time and electrical load. Evaluate routes in position, time, and energy, with waiting/charging actions and activity deadlines. Bound time/energy discretization and search extent so the state space remains manageable.

Return the achieved science requirements, total duration, distance, minimum reserve, longest geometric outage, and unsupported terrain/model queries. Return `insufficient_evidence` when a required edge lies outside the supported response-model domain. Keep static path length and dynamic mission feasibility as separate metrics.

**7. Earth departure screening in version one**

Use a bounded canonical transfer family. The supported input is an initial parking-orbit definition and departure epoch, with explicitly permitted changes to orbit orientation and maneuvers. A launch-pad label may be displayed as context, but version one does not solve ascent, range safety, launch-provider scheduling, or pad-to-orbit injection.

Use NASA's tagged GMAT example `Ex_GivenEpochGoToTheMoon.script` as the initial reference adapter. First run it unchanged and save its actual output. The source starts at 2022-07-15 01:07:06.978 UTC with an EarthMJ2000Eq orbit of roughly 6563 km semi-major axis and 28.7 degrees inclination. It varies orbit orientation and burns, targets a lunar radius of 15000 km and a B-vector angle, then attempts insertion. The supplied insertion-eccentricity tolerance is loose and must not be interpreted as precise circular capture. Source guesses are not converged benchmark outputs. [Official sample](https://github.com/nasa/GMAT/blob/R2026a/application/samples/Ex_GivenEpochGoToTheMoon.script)

`Ex_LunarTransfer.script` is a second regression case. It begins from a different initial trajectory, targets lunar B-plane conditions, and performs insertion; it does not specify touchdown. Do not describe its initial state as the same parking-orbit example. [Official sample](https://github.com/nasa/GMAT/blob/R2026a/application/samples/Ex_LunarTransfer.script)

Build a GMAT worker adapter that:

1. Stores a versioned, trusted reference script/template and its data dependencies.
2. Accepts allowlisted numeric parameters; users cannot upload executable GMAT scripts through the public API.
3. Runs a bounded departure-epoch sweep and permitted orbit/target variations in isolated job directories.
4. Checks solver termination and target residuals, not merely process exit code.
5. Confirms the intended encounter event occurred instead of an alternate time/radius guard stop.
6. Rejects physical intersection with Earth/Moon, checks periapsis clearance, and verifies capture energy/orbit conditions.
7. Repropagates accepted candidates with tighter settings and records sensitivity.
8. Returns actual departure state/epoch, maneuver vectors, encounter/capture epochs, orbital elements, residuals, model versions, and convergence status.

The first supported transfer family may retain the example's high-altitude lunar target. A low-lunar-orbit target is a separate tested configuration. Varying parking-orbit RAAN/AOP freely means the solution is conditional on those orbit orientations; it does not prove accessibility from a chosen launch site.

The official GMAT API exposes `LoadScript`, `RunScript`, `GetRuntimeObject`, and `GetRunSummary`. Use a separate worker process for each isolated GMAT context. Verify the binary/Python binding setup on the team's chosen OS before building the web adapter. [API documentation](https://github.com/nasa/GMAT/blob/R2026a/doc/SystemDocs/Tools/source/API/source/userguide/ScriptUsage.rst)

Report `converged`, `no_solution_found_in_search`, `nonconverged`, `invalid_input`, or `not_run` separately. Search failure does not establish physical impossibility. Do not target the Moon's centre with a simple Earth-only Lambert solution and present it as a validated landing or capture calculation.

**8. Connecting departure opportunities to surface dates**

Store these epochs separately: liftoff, parking-orbit insertion, departure burn, lunar encounter, capture, touchdown, and surface mission end. Unknown epochs remain null.

For a departure candidate, generate a landing-time compatibility screen only under an explicit capture-to-touchdown interval. Version one accepts an assumed interval range supplied by the user. Its label is `assumed_not_dynamically_validated`. The arithmetic overlap between that interval and good surface windows is a useful schedule screen; it does not establish lunar-orbit access to the site, fuel for waiting, or a feasible descent.

Return separate records for transfer convergence, surface feasibility at a proposed touchdown, and landing-access evidence. Do not draw a dynamically continuous trajectory to the landing site while the connecting orbital/descent segment is assumed. If the UI offers a liftoff timestamp, expose its supplied ascent/coast offset from departure and label it accordingly.

**9. Finding suitable lunar sites and dates**

Select site/date candidates using hard constraints first. Evaluate local data support, terrain/slope restrictions, sunlight energy, maximum darkness, geometric Earth visibility, route/task completion, and any selected science targets. Distinguish landing-footprint screening from proof that a lander can descend safely.

After filtering, compare feasible alternatives on explicit preferences: science coverage, energy reserve, geometric contact availability, route length, schedule change, and terrain uncertainty. Show a Pareto set or a transparent user-weighted ranking with the component metrics. Unknown required evidence cannot be hidden inside a high average score. There is no universally ideal site independent of the robot and mission requirements.

Version one supports curated regions and touchdown-date sweeps. Precompute the surface grid independently of transfer searches, then join candidate time windows under the stated orbital assumptions. Reuse geometry across robot configurations when the geometry/height assumptions permit it.

The orchestration can follow this structure:

```text
surface_candidates = []
for site in supported_sites:
    package = prepare_and_validate_site(site)
    for touchdown in touchdown_grid:
        environment = prepare_environment(package, touchdown, mission_duration)
        for plan in supported_route_and_schedule_templates:
            nominal = simulate_surface(robot_profile, environment, plan, nominal_scenario)
            if required evidence is missing:
                retain an insufficient-evidence result
            elif nominal violates a hard requirement:
                retain the failure and permitted repair inputs
            else:
                audit = evaluate_frozen_scenarios(robot_profile, environment, plan)
                retain nominal metrics, scenario assumptions, and audit metrics

transfer_candidates = []
for departure_epoch in bounded_departure_grid:
    candidate = run_trusted_GMAT_family(departure_epoch, permitted_orbit_variables)
    retain convergence, event/clearance checks, residuals, and verification state

for accepted_transfer in transfer_candidates:
    assumed_touchdown_window = capture_epoch + declared_capture_to_touchdown_range
    match surface candidates whose touchdown lies in that window
    retain the assumed landing-access status rather than claiming a solved descent

filter by required evidence and hard constraints, then rank component trade-offs
```

Bound the total jobs, candidate grids, and per-solve runtime. Preserve partial results on cancellation. A complete sweep that finds nothing and a sweep stopped by its budget must have different completion metadata.

**10. Failure search and the learned model**

Build a deterministic scenario simulator and random-sampling baseline first. Vary timing, terrain realization, usable battery capacity, solar-output multiplier, and mobility delay within documented ranges. Separate physically measured inputs from assumed uncertainty distributions. Search signed constraint margins and preserve reproducible seeds.

The optional acceleration model predicts simulator-derived margins: minimum battery reserve, maximum geometric outage relative to its limit, and required-task deadline margins. Use inexpensive features available before the expensive scenario run. Start with a tree regressor; compare a small neural ensemble if useful. Do not train a single model that silently mixes transfer-solver convergence with surface robot survival.

Use the model to select simulations, then rerun proposed failures/repairs in the reference simulator. Track validity domains for both the mobility model and mission surrogate. A newly imported robot outside those domains needs fresh simulations, or an insufficient-evidence result. Hold out sites/dates/scenario families according to the generalization claim; keep related terrain realizations from leaking across site-level train/test partitions.

Compare random testing and learned selection at equal simulator budgets and report runtime. Keep a separate random audit set for repair evaluation. Adversarially selected failures are not a real-world mission failure probability.

**11. Repairs and explanations**

Version-one repairs enumerate supported site/date/route/schedule alternatives, waiting in sunlight, and explicitly allowed hardware changes. Required activities remain fixed. Rank feasible repairs by an exposed cost policy and show trade-offs. Label the answer `smallest repair found` unless optimality is established.

Every explanation includes the violated requirement, first violation epoch, causal state history, scenario changes from nominal, source/model versions, and residual unknowns. Templates can generate these explanations directly from event records. A repair is checked on fresh scenarios and, for selected traverses, replayed by the robot laboratory.

**12. Validation and delivery gates**

| Area | Required evidence before relying on results |
| --- | --- |
| Terrain ingestion | Known-point horizontal/vertical conversion; nodata and registration checks; frame/unit metadata |
| Geometry | Analytical ridge/sphere cases, sampled Horizons/SPICE comparisons with matched conventions, horizon/timestep convergence |
| Observed lighting | Two or more Product 90 observed/model scenes; shadow-boundary and false-sunlit errors with registration masks |
| Energy | Exact charging/discharging fixtures, capacity/reserve events, efficiency and activity-overlap checks |
| Transfer | Unmodified GMAT samples executed and outputs archived; event/clearance/capture/residual checks; tighter repropagation |
| Routing | Static baseline comparison, then fixed scenarios with waiting, deadlines, and energy constraints |
| Integration | Same immutable robot/environment inputs; aligned time, frames, power conventions and hashes |
| Failure/repair | Equal-budget baselines, repeated seeds, held-out repair scenarios and preserved requirements |

Tolerance values must reflect source resolution, registration uncertainty, and numerical convergence. Record them before comparing methods. The supplied contract fixtures are synthetic and are not these scientific validation results.

Build order, task ownership, API endpoints, and the integration process are specified in the other handoff files. Start by making the contract validator pass and loading the synthetic example end to end; replace the synthetic environment and vehicle responses with validated adapters as they become available.
