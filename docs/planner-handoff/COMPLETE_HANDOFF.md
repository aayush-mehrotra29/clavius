**Lunar mission planning and Earth departure screening**

Complete standalone handoff for the planning developer · Version 0.1.0 · 14 November 2026

Build the planning system that connects Earth departure screening, lunar site/date selection, surface mission evaluation, failure analysis, and repair comparison to the separate robot simulation laboratory.

This single document includes the full specification, NASA/JPL datasets and APIs, integration conventions, prioritized tasks, and the complete text of the shared schemas, synthetic fixtures, and validator. No separate project documents or code attachments are required to read or share the handoff. External NASA datasets, kernels, and GMAT software must be obtained from the linked sources.

The application and scientific simulators still need implementation. Contract/analytical checks passed for the supplied examples; the examples do not represent observed lunar conditions or executed orbital solutions.

Read parts 1–4 for the build plan. Parts 5–7 contain the complete machine-readable contracts and examples. Paths in those appendices specify where to save each block if you want to recreate the validated starter files. Merely reading or forwarding this document does not require splitting it into files.


**1. Application specification**

Build the planning half of Lunar Failure Foundry. A user supplies a robot configuration, candidate lunar regions, a date range, and mission requirements. The application screens Earth departure opportunities, compares lunar surface conditions, evaluates a route/activity plan, explains failures, and proposes alternatives. The robot laboratory supplies vehicle capabilities and detailed mobility replays.

Version one includes Earth departure screening. Its supported orbital scope starts from a declared Earth parking orbit and ends at a modeled lunar encounter/capture. Lunar landing time remains a separate input or explicitly assumed interval after capture. Surface suitability, transfer convergence, and unmodeled orbital access must remain distinguishable in the results.

The sections and appendices below include the data/API inventory, integration agreement, prioritized backlog, JSON Schemas, synthetic example messages, and contract validator. These define interfaces; they do not implement or validate an orbital or surface simulator.

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

Start with NASA PGDA Product 78 Site01 Connecting Ridge and one comparison region, such as Site04 Shackleton rim. Obtain nominal terrain, measurement counts, height/slope errors, regions of interest, and the supplied error realizations. Use Product 90 regional terrain around each local patch for distant horizon blockers. Optional LROC stereo terrain and orthophotos add detail and visual context. Exact sources and files are included in part 2 below.

Build these functions:

- `ingest_dataset(source_id, version, selection)` downloads selected assets, verifies sizes/checksums where supplied, and creates a source manifest.
- `normalize_terrain(asset, source_metadata)` converts a documented native coordinate/height convention into the project's normalized geometry.
- `make_site_package(site_id, roi, resolutions)` packages analysis terrain, regional context, masks, and visualization assets.
- `inspect_site_quality(site_package)` reports effective resolution, interpolation/measurement support, nodata, and unmodeled hazards.

Preserve raw files. Record source URLs, product IDs, download timestamps, file hashes, horizontal frame/projection, vertical definition, units, nodata values, and pixel registration. Counts are not uncertainty, grid spacing is not guaranteed accuracy, and nodata must not become flat ground. Quantitative COG reads must use the intended resolution rather than a display overview.

Product 78's README describes surface height Z but does not fully resolve its vertical zero in the inspected text. Before merging it with Product 90, inspect GeoTIFF metadata, numeric ranges, original paper, and matching coordinates. Add a known-point conversion check. Do not automatically add a reference radius to an unverified Z quantity. The integration contract accepts normalized local geometry, not an undocumented raw raster.

**4. Geometry and surface conditions**

Use pinned SPICE kernels locally for repeatable batch calculations. The initial bundle in part 2 matches the MOON_ME/DE421 terrain convention. Horizons is useful for a prototype and cross-checks; record its returned ephemeris/frame because the service can use a different ephemeris generation.

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

Power conventions are defined in part 3 below. A detailed driving response includes base-plus-mobility bus load. Add payload, radio, and heater increments exactly once. Solar generation is computed separately by the planner.

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

Build order, task ownership, API endpoints, and the integration process are specified in parts 3 and 4 below. Start by making the contract validator pass and loading the synthetic example end to end; replace the synthetic environment and vehicle responses with validated adapters as they become available.

**2. Datasets and APIs**

Use the IDs below in manifests and run records. Public access is distinct from a promise of service uptime or a blanket reuse license. Preserve product citations, labels, and source-specific terms. NASA archives and the tested Horizons/ODE requests are publicly accessible without a NASA API key.

**1. Required surface datasets**

| ID | Source and exact entry point | Obtain | Purpose and limits |
| --- | --- | --- | --- |
| D01 | [LOLA local terrain and uncertainty, PGDA 78](https://pgda.gsfc.nasa.gov/products/78) | Nominal 5 m grids, counts, slope/height errors, ROI polygons, supplied terrain-error realizations | Local geometry and uncertainty. Statistical terrain realizations are not independent measured surfaces. Grid spacing is not wheel-scale hazard accuracy. |
| D02 | [LOLA regional terrain, PGDA 90](https://pgda.gsfc.nasa.gov/products/90) | Regional elevation COGs plus error/effective-resolution layers; optional roughness and permanently shadowed regions | Distant horizons and regional context. A cropped local patch cannot represent all horizon blockers. |
| D03 | [LROC Connecting Ridge SHACKRDGE02](https://data.lroc.im-ldi.com/lroc/view_rdr/NAC_DTM_SHACKRDGE02) | DTM, orthophoto, confidence map, labels, README | Local detail/visualization and sensitivity comparisons. DTM posting is 3.5 m; an orthophoto is available at 1.2 m/pixel. Stereo shadows and weak correlations can produce gaps/artifacts. This terrain is tied to LOLA. |
| D04 | [Lunar Polar Illumination, PGDA 69](https://pgda.gsfc.nasa.gov/products/69) | Average sunlight, average Earth visibility and permanent-shadow maps | Site shortlisting and reference comparison. These are modeled long-period statistics, not the requested date's sunlight timeline. Earth visibility can mean any part of Earth's disk is visible. |
| D05 | [NAC observations and simulated images, PGDA 90](https://pgda.gsfc.nasa.gov/products/90) | Published map-projected observed/model scene pairs and acquisition metadata | Observed-shadow validation. Compare boundaries/masks; observed I/F and modeled W/m² should not be compared as identical brightness quantities. |

Start with Site01 Connecting Ridge and a second region from D01. Specific first assets:

- [Site01 nominal terrain](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_final_adj_5mpp_surf.tif)
- [Site01 height RMS error](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_final_adj_5mpp_toterr.tif)
- [Site01 ROI polygons](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Site01_ROIs.tgz)
- [Site01 first error realization](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/Site01/Clones/Site01_final_adj_5mpp_0001_err.tif); obtain the rest from D01 and apply them according to their documented error-field convention.
- [Regional 80 m terrain](https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/LDEM_80S_80MPP_ADJ.TIF), with finer/coarser context as needed.
- [SHACKRDGE02 DTM GeoTIFF](https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/DATA/SDP/NAC_DTM/SHACKRDGE02/NAC_DTM_SHACKRDGE02.TIF)
- [SHACKRDGE02 documentation](https://pds.lroc.im-ldi.com/data/LRO-L-LROC-5-RDR-V1.0/LROLRC_2001/DATA/SDP/NAC_DTM/SHACKRDGE02/NAC_DTM_SHACKRDGE02_README.TXT)
- [M1188426614LE observed scene](https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/M1188426614LE_20MPP.TIF) and [published rendering](https://pgda.gsfc.nasa.gov/data/LOLA_20mpp/M1188426614_20MPP_MODEL.TIF).

Both PGDA collections use south-polar stereographic horizontal coordinates in metres and MOON_ME/DE421. Product 78's [README](https://pgda.gsfc.nasa.gov/data/LOLA_5mpp/README) separately documents point-cloud XYZI coordinates in kilometres. Its Z wording needs an explicit importer check before radial conversion. Product 90's associated paper defines heights against a reference sphere; its projection radius is 1737.4 km. Record native and normalized vertical definitions separately. Never apply an Earth EPSG code to lunar data by convenience.

**2. Geometry data and calculation services**

| ID | Resource | Files or endpoint | Use |
| --- | --- | --- | --- |
| G01 | [NAIF SPICE toolkit](https://naif.jpl.nasa.gov/naif/toolkit.html) | Local library plus kernel files below | Reproducible Sun/Earth geometry; this is local computation, not an HTTP visibility API. |
| G02 | [JPL Horizons API docs](https://ssd-api.jpl.nasa.gov/doc/horizons.html) | `https://ssd.jpl.nasa.gov/api/horizons.api` | Prototype geometry and cross-checks. Local terrain occlusion must be computed separately. |
| G03 | [PDS ODE REST](https://oderest.rsl.wustl.edu/) | `https://oderest.rsl.wustl.edu/live2` | Discover products, footprints, observation times, labels, and download URLs. Not an energy/mission simulation service. |

For the initial DE421 surface-geometry bundle, pin these files and store their hashes:

- [de421.bsp](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/a_old_versions/de421.bsp)
- [moon_pa_de421_1900-2050.bpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de421_1900-2050.bpc)
- [moon_080317.tf](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_080317.tf)
- [naif0012.tls](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls)
- [pck00011.tpc](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc)

Select `MOON_ME_DE421` explicitly. Respect each kernel's actual coverage. The binary lunar orientation file's approximate coverage is 1900–2050. LRO spacecraft kernels are needed for spacecraft/image reconstruction tasks, not simply for a stationary surface observer. [Frame specification](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_080317.tf)

Horizons surface-observer example parameters:

```text
format=json
COMMAND='10'                 # Sun; use '399' for Earth
OBJ_DATA='NO'
EPHEM_TYPE='OBSERVER'
CENTER='coord@301'           # user coordinates on the Moon
COORD_TYPE='GEODETIC'
SITE_COORD='222.8,-89.44,0'   # east longitude deg, latitude deg, altitude km
START_TIME='2028-01-01'
STOP_TIME='2028-01-01 01:00'
STEP_SIZE='1 h'
QUANTITIES='4,13'            # azimuth/elevation and angular diameter
APPARENT='AIRLESS'
TIME_TYPE='UT'
CSV_FORMAT='YES'
```

Encode each value using a normal HTTP parameter encoder. The zero altitude is an illustrative reference-surface location, not the actual terrain height at these coordinates. Replace it with a verified altitude plus observer height. Parse service errors even when HTTP succeeds. JSON responses contain a textual `result` block that requires parsing. The prior sample query returned DE441 geometry; compare frames/conventions before comparing it to DE421 results. Apparent and geometric directions differ. [Horizons manual](https://ssd.jpl.nasa.gov/horizons/manual.html)

For ODE, start with the valid instrument/product-type listing:

```text
https://oderest.rsl.wustl.edu/live2?query=iipt&odemetadb=moon&output=JSON
```

Then construct searches using the returned codes and documented bounding-box/product parameters. Store the original labels and actual download URLs. Use pagination, modest request rates, timeouts, retries, and local caches. [ODE manual](https://oderest.rsl.wustl.edu/ODE_REST_V2.1.6.pdf)

**3. Earth departure resources required in version one**

| ID | Resource | Obtain and build |
| --- | --- | --- |
| O01 | [NASA GMAT R2026a release](https://github.com/nasa/GMAT/releases/tag/R2026a) | Supported binary/source distribution and its required data files; verify installation/bindings on the selected development OS. |
| O02 | [Fixed-epoch lunar example](https://github.com/nasa/GMAT/blob/R2026a/application/samples/Ex_GivenEpochGoToTheMoon.script) | Reproduce unchanged first. Then parameterize a bounded epoch/orbit family and archive actual convergence and maneuver outputs. |
| O03 | [Lunar transfer/capture example](https://github.com/nasa/GMAT/blob/R2026a/application/samples/Ex_LunarTransfer.script) | Second regression case with its own initial state, force model and target conditions. |
| O04 | [GMAT script API guide](https://github.com/nasa/GMAT/blob/R2026a/doc/SystemDocs/Tools/source/API/source/userguide/ScriptUsage.rst) | Adapter around loading a trusted template, running it, and extracting runtime objects/summary. |
| O05 | [NASA Launch Services performance site](https://elvperf.ksc.nasa.gov/) | Optional public vehicle-performance context under its stated configurations and NASA-contract assumptions. Capture source/date/configuration for manually imported performance data. |

GMAT examples are executable reference problems, not solved data labels for every date. Their actual numerical outputs must be generated and checked. For each job, pin the script, gravity/ephemeris data, integrator, solver settings, and GMAT version. Do not silently give GMAT the surface SPICE bundle if its reference example requires different supporting data.

The public [LSP query interface](https://elvperf.ksc.nasa.gov/Pages/Query.aspx) offers circular, elliptical and high-energy queries. Its high-energy C3 range is -10 to 100 km²/s². The site describes mission/configuration-specific limitations; it does not supply booked launch dates or a public launch-availability API. LEO payload mass cannot be treated as translunar capacity. Version one should default vehicle compatibility to `not_assessed` unless a matching, sourced performance assessment exists.

A launch-pad catalog, if displayed, needs sourced coordinates and provider/configuration assumptions. It remains contextual until ascent and orbital-plane accessibility are modeled. There is no need to add a generic NASA image API or an unrelated space-news API to perform this project's calculations.

**4. Environmental and science extensions**

| ID | Source | Add when |
| --- | --- | --- |
| E01 | [NASA Lunar Surface Data Book, M2M-30044, March 2025](https://ntrs.nasa.gov/api/citations/20250002845/downloads/M2M-30044%20Lunar%20Surface%20Data%20Book%20Baseline_Final.pdf) | Immediately as the environmental reference and source index; it is not robot telemetry. |
| E02 | [Diviner archive](https://pds-geosciences.wustl.edu/missions/lro/diviner.htm), especially [polar cumulative products](https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_pcp/) | Adding seasonal/diurnal thermal context or validating an explicit environmental thermal model. Product footprints/resolution must be preserved. It does not directly predict battery temperature. |
| E03 | [M³ Level-2 reflectance archive](https://pds.nasa.gov/ds-view/pds/viewProfile.jsp?dsid=CH1-ORB-L-M3-4-L2-REFLECTANCE-V1.0) | Adding mineralogical/hydration science targets. Reflectance/hydration is not a confirmed local extractable-ice inventory. |
| E04 | [ShadowCam archive](https://shadowcam.im-ldi.com/archive) | Adding imagery of shadowed terrain after confirming coverage/product suitability. Imagery alone does not supply height or traction labels. |
| E05 | [NASA POLAR Stereo](https://ti.arc.nasa.gov/dataset/IRG_PolarDB/) and [POLAR Traverse](https://ti.arc.nasa.gov/dataset/PolarTrav/) | Robot laboratory perception/localization extension. Images, calibration and LiDAR reference geometry do not calibrate lunar wheel–soil dynamics. |
| E06 | [RoSE mobility data](https://github.com/RoSE-Lab-Admin/Rover-Mobility-Dataset) | Robot laboratory mobility-model calibration on analog experiments; account for hardware, simulant and Earth gravity. Non-NASA source. |

**5. Inputs that come from the team or user**

The robot profile supplies battery, array, load and mobility parameters. The planner supplies required tasks, objectives, date ranges, search budgets, hard limits, permitted repairs, and assumed uncertainty distributions. Departure screening additionally needs the supported initial orbit, allowed orientation/maneuver variations, force model, target family, and capture-to-touchdown assumption.

Training labels for the mission surrogate are generated by the versioned simulator. Terrain is NASA-derived; the resulting battery/failure labels are simulated. Keep this distinction in manifests, exports, interface labels, and evaluation reports.

**6. Download and cache order**

1. D01 Site01 and one comparison region; inspect native coordinate/height conventions.
2. D02 regional context and G01 pinned geometry kernels.
3. D05 two observed/model reference scenes; D03 imagery/confidence as useful.
4. O01–O04 GMAT and both reference scripts; reproduce the unmodified cases.
5. E01 environmental reference and one declared robot profile.
6. D04 long-term comparison products, then feature-specific extensions.

Fetch catalog data during preparation. Run batch simulations from immutable local assets wherever practical. Cache keys must include source hashes, transformations, model versions and settings; a changed terrain or vehicle model must invalidate dependent results.

**3. Integration agreement**

Version 0.1.0 is an initial contract for joint review. The JSON Schemas and examples embedded in parts 5 and 6 can be consumed now; the proposed HTTP services and simulation adapters still need to be implemented.

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

The schemas validate structure. Semantic checks additionally enforce clocks, units, domains, asset hashes, geometry conventions and status consistency. The validator embedded in part 7 applies both layers to the supplied fixtures; it is not a universal runtime validator for every production run.

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

**4. Build tasks and acceptance checks**

Owner labels: P = planning developer, R = robot laboratory developer, J = joint decision/review. The ordering is based on dependencies; Earth departure screening is a version-one requirement. The schemas embedded in part 5 are a proposed initial contract and should be frozen jointly before implementation proceeds far.

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

**5. Complete JSON Schemas**

Save these blocks under the indicated paths to recreate the shared contracts. The `spaceapps.invalid` identifiers are local schema IDs; the validator resolves them from the registry without fetching them from the internet.

**File: `contracts/v0.1/common.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://spaceapps.invalid/contracts/v0.1/common.schema.json",
  "$defs": {
    "utc": {
      "type": "string",
      "format": "date-time",
      "pattern": "Z$"
    },
    "vec3": {
      "type": "array",
      "items": {
        "type": "number"
      },
      "minItems": 3,
      "maxItems": 3
    },
    "quaternion_xyzw": {
      "type": "array",
      "items": {
        "type": "number"
      },
      "minItems": 4,
      "maxItems": 4
    },
    "matrix3": {
      "type": "array",
      "items": {
        "type": "array",
        "items": {
          "type": "number"
        },
        "minItems": 3,
        "maxItems": 3
      },
      "minItems": 3,
      "maxItems": 3
    },
    "asset_ref": {
      "type": "object",
      "properties": {
        "uri": {
          "type": "string",
          "minLength": 1
        },
        "sha256": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        }
      },
      "required": [
        "uri",
        "sha256"
      ],
      "additionalProperties": false
    },
    "provenance": {
      "type": "object",
      "properties": {
        "source_class": {
          "enum": [
            "synthetic_contract_fixture",
            "nasa_derived",
            "analog_measurement",
            "declared_model",
            "mixed"
          ]
        },
        "model_id": {
          "type": "string",
          "minLength": 1
        },
        "model_version": {
          "type": "string",
          "minLength": 1
        },
        "notes": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "source_class",
        "model_id",
        "model_version",
        "notes"
      ],
      "additionalProperties": false
    },
    "assessment_status": {
      "enum": [
        "supported_under_assumptions",
        "constraint_violated",
        "insufficient_evidence"
      ]
    }
  }
}
```

**File: `contracts/v0.1/environment-package.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://spaceapps.invalid/contracts/v0.1/environment-package.schema.json",
  "title": "Normalized environment package",
  "type": "object",
  "properties": {
    "schema_version": {
      "const": "0.1.0"
    },
    "environment_id": {
      "type": "string",
      "minLength": 1
    },
    "site_id": {
      "type": "string",
      "minLength": 1
    },
    "global_frame": {
      "const": "MOON_ME_DE421"
    },
    "local_axes": {
      "const": "x_east_y_north_z_up"
    },
    "source_manifest_ref": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
    },
    "origin": {
      "type": "object",
      "properties": {
        "latitude_deg": {
          "type": "number",
          "minimum": -90,
          "maximum": 90
        },
        "longitude_east_deg": {
          "type": "number",
          "minimum": 0,
          "maximum": 360
        },
        "position_body_fixed_m": {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
        },
        "enu_to_body_fixed_rotation": {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/matrix3"
        }
      },
      "required": [
        "latitude_deg",
        "longitude_east_deg",
        "position_body_fixed_m",
        "enu_to_body_fixed_rotation"
      ],
      "additionalProperties": false
    },
    "terrain": {
      "type": "object",
      "properties": {
        "asset": {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
        },
        "horizontal_frame": {
          "const": "LOCAL_ENU"
        },
        "vertical_quantity": {
          "const": "local_up_m"
        },
        "grid_spacing_m": {
          "type": "number",
          "minimum": 1e-06
        },
        "raw_vertical_definition": {
          "type": "string",
          "minLength": 1
        },
        "normalization_notes": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "asset",
        "horizontal_frame",
        "vertical_quantity",
        "grid_spacing_m",
        "raw_vertical_definition",
        "normalization_notes"
      ],
      "additionalProperties": false
    },
    "gravity_m_s2": {
      "type": "number",
      "minimum": 0
    },
    "time_origin_utc": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
    },
    "elapsed_time_basis": {
      "const": "SI_seconds_from_time_origin"
    },
    "geometry_convention": {
      "const": "geometric_observer_to_body_unit_vectors"
    },
    "sky_samples": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "t_s": {
            "type": "number",
            "minimum": 0
          },
          "sun_direction_enu_unit": {
            "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
          },
          "earth_direction_enu_unit": {
            "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
          },
          "sun_angular_radius_rad": {
            "type": "number",
            "minimum": 0
          },
          "solar_irradiance_w_m2": {
            "type": "number",
            "minimum": 0
          }
        },
        "required": [
          "t_s",
          "sun_direction_enu_unit",
          "earth_direction_enu_unit",
          "sun_angular_radius_rad",
          "solar_irradiance_w_m2"
        ],
        "additionalProperties": false
      },
      "minItems": 2
    },
    "horizon_model_id": {
      "type": "string",
      "minLength": 1
    },
    "terrain_scenario_id": {
      "type": "string",
      "minLength": 1
    },
    "provenance": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/provenance"
    }
  },
  "required": [
    "schema_version",
    "environment_id",
    "site_id",
    "global_frame",
    "local_axes",
    "source_manifest_ref",
    "origin",
    "terrain",
    "gravity_m_s2",
    "time_origin_utc",
    "elapsed_time_basis",
    "geometry_convention",
    "sky_samples",
    "horizon_model_id",
    "terrain_scenario_id",
    "provenance"
  ],
  "additionalProperties": false
}
```

**File: `contracts/v0.1/plan-evaluation.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://spaceapps.invalid/contracts/v0.1/plan-evaluation.schema.json",
  "title": "Scoped plan evaluation",
  "type": "object",
  "properties": {
    "schema_version": {
      "const": "0.1.0"
    },
    "evaluation_id": {
      "type": "string",
      "minLength": 1
    },
    "request_id": {
      "type": "string",
      "minLength": 1
    },
    "robot_ref": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
    },
    "environment_ref": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
    },
    "assessment_scope": {
      "enum": [
        "surface_mission",
        "departure_and_surface_screening"
      ]
    },
    "status": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/assessment_status"
    },
    "scope_notes": {
      "type": "string",
      "minLength": 1
    },
    "surface_result": {
      "type": "object",
      "properties": {
        "status": {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/assessment_status"
        },
        "minimum_battery_wh": {
          "type": [
            "number",
            "null"
          ]
        },
        "battery_reserve_margin_wh": {
          "type": [
            "number",
            "null"
          ]
        },
        "longest_geometric_earth_outage_s": {
          "type": [
            "number",
            "null"
          ]
        },
        "required_tasks_completed": {
          "type": "array",
          "items": {
            "type": "string",
            "minLength": 1
          },
          "minItems": 0
        },
        "first_violation": {
          "anyOf": [
            {
              "type": "object",
              "properties": {
                "constraint_id": {
                  "type": "string",
                  "minLength": 1
                },
                "t_s": {
                  "type": "number",
                  "minimum": 0
                },
                "message": {
                  "type": "string",
                  "minLength": 1
                }
              },
              "required": [
                "constraint_id",
                "t_s",
                "message"
              ],
              "additionalProperties": false
            },
            {
              "type": "null"
            }
          ]
        },
        "samples": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "t_s": {
                "type": "number",
                "minimum": 0
              },
              "position_enu_m": {
                "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
              },
              "solar_power_w": {
                "type": "number",
                "minimum": 0
              },
              "total_load_w": {
                "type": "number",
                "minimum": 0
              },
              "battery_energy_wh": {
                "type": "number",
                "minimum": 0
              },
              "earth_center_visible": {
                "type": "boolean"
              }
            },
            "required": [
              "t_s",
              "position_enu_m",
              "solar_power_w",
              "total_load_w",
              "battery_energy_wh",
              "earth_center_visible"
            ],
            "additionalProperties": false
          },
          "minItems": 0
        }
      },
      "required": [
        "status",
        "minimum_battery_wh",
        "battery_reserve_margin_wh",
        "longest_geometric_earth_outage_s",
        "required_tasks_completed",
        "first_violation",
        "samples"
      ],
      "additionalProperties": false
    },
    "transfer_result": {
      "type": "object",
      "properties": {
        "status": {
          "enum": [
            "not_run",
            "converged",
            "no_solution_found_in_search",
            "nonconverged",
            "invalid_input"
          ]
        },
        "departure_utc": {
          "anyOf": [
            {
              "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
            },
            {
              "type": "null"
            }
          ]
        },
        "encounter_utc": {
          "anyOf": [
            {
              "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
            },
            {
              "type": "null"
            }
          ]
        },
        "capture_utc": {
          "anyOf": [
            {
              "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
            },
            {
              "type": "null"
            }
          ]
        },
        "total_maneuver_delta_v_m_s": {
          "type": [
            "number",
            "null"
          ]
        },
        "candidate_artifact": {
          "anyOf": [
            {
              "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
            },
            {
              "type": "null"
            }
          ]
        },
        "notes": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "status",
        "departure_utc",
        "encounter_utc",
        "capture_utc",
        "total_maneuver_delta_v_m_s",
        "candidate_artifact",
        "notes"
      ],
      "additionalProperties": false
    },
    "landing_access": {
      "type": "object",
      "properties": {
        "status": {
          "enum": [
            "not_evaluated",
            "assumed_not_dynamically_validated",
            "dynamically_validated"
          ]
        },
        "notes": {
          "type": "string",
          "minLength": 1
        }
      },
      "required": [
        "status",
        "notes"
      ],
      "additionalProperties": false
    },
    "issues": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      },
      "minItems": 0
    },
    "assumptions": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      },
      "minItems": 0
    },
    "provenance": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/provenance"
    }
  },
  "required": [
    "schema_version",
    "evaluation_id",
    "request_id",
    "robot_ref",
    "environment_ref",
    "assessment_scope",
    "status",
    "scope_notes",
    "surface_result",
    "transfer_result",
    "landing_access",
    "issues",
    "assumptions",
    "provenance"
  ],
  "additionalProperties": false
}
```

**File: `contracts/v0.1/planning-request.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://spaceapps.invalid/contracts/v0.1/planning-request.schema.json",
  "title": "Departure and surface planning request",
  "type": "object",
  "properties": {
    "schema_version": {
      "const": "0.1.0"
    },
    "request_id": {
      "type": "string",
      "minLength": 1
    },
    "robot_ref": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
    },
    "environment_ref": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
    },
    "surface": {
      "type": "object",
      "properties": {
        "site_id": {
          "type": "string",
          "minLength": 1
        },
        "touchdown_utc": {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
        },
        "duration_s": {
          "type": "number",
          "minimum": 0.001
        },
        "route_points_enu_m": {
          "type": "array",
          "items": {
            "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
          },
          "minItems": 1
        },
        "required_tasks": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "task_id": {
                "type": "string",
                "minLength": 1
              },
              "duration_s": {
                "type": "number",
                "minimum": 0.001
              },
              "location_enu_m": {
                "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
              },
              "power_mode": {
                "enum": [
                  "base",
                  "science",
                  "downlink"
                ]
              }
            },
            "required": [
              "task_id",
              "duration_s",
              "location_enu_m",
              "power_mode"
            ],
            "additionalProperties": false
          },
          "minItems": 1
        },
        "constraints": {
          "type": "object",
          "properties": {
            "max_slope_deg": {
              "type": "number",
              "minimum": 0,
              "maximum": 90
            },
            "max_geometric_earth_outage_s": {
              "type": "number",
              "minimum": 0
            },
            "contact_model": {
              "const": "earth_center_geometric"
            }
          },
          "required": [
            "max_slope_deg",
            "max_geometric_earth_outage_s",
            "contact_model"
          ],
          "additionalProperties": false
        }
      },
      "required": [
        "site_id",
        "touchdown_utc",
        "duration_s",
        "route_points_enu_m",
        "required_tasks",
        "constraints"
      ],
      "additionalProperties": false
    },
    "departure_screening": {
      "type": "object",
      "properties": {
        "enabled": {
          "const": true
        },
        "mode": {
          "const": "reference_transfer_family"
        },
        "reference_case_id": {
          "type": "string",
          "minLength": 1
        },
        "departure_start_utc": {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
        },
        "departure_end_utc": {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
        },
        "epoch_step_s": {
          "type": "number",
          "minimum": 0.001
        },
        "spacecraft_wet_mass_kg": {
          "anyOf": [
            {
              "type": "number",
              "minimum": 0.001
            },
            {
              "type": "null"
            }
          ]
        },
        "vehicle_performance_status": {
          "const": "not_assessed"
        },
        "permitted_variables": {
          "type": "array",
          "items": {
            "enum": [
              "epoch",
              "raan",
              "aop",
              "departure_burn",
              "capture_burn"
            ]
          },
          "minItems": 1
        },
        "launch_to_departure_offset_s": {
          "anyOf": [
            {
              "type": "number",
              "minimum": 0
            },
            {
              "type": "null"
            }
          ]
        },
        "capture_to_touchdown": {
          "type": "object",
          "properties": {
            "min_s": {
              "type": "number",
              "minimum": 0
            },
            "max_s": {
              "type": "number",
              "minimum": 0
            },
            "evidence": {
              "const": "assumed_not_dynamically_validated"
            }
          },
          "required": [
            "min_s",
            "max_s",
            "evidence"
          ],
          "additionalProperties": false
        }
      },
      "required": [
        "enabled",
        "mode",
        "reference_case_id",
        "departure_start_utc",
        "departure_end_utc",
        "epoch_step_s",
        "spacecraft_wet_mass_kg",
        "vehicle_performance_status",
        "permitted_variables",
        "launch_to_departure_offset_s",
        "capture_to_touchdown"
      ],
      "additionalProperties": false
    },
    "scenario": {
      "type": "object",
      "properties": {
        "scenario_id": {
          "type": "string",
          "minLength": 1
        },
        "seed": {
          "type": "integer",
          "minimum": 0
        },
        "terrain_realization_id": {
          "type": "string",
          "minLength": 1
        },
        "solar_output_multiplier": {
          "type": "number",
          "minimum": 0
        },
        "battery_capacity_multiplier": {
          "type": "number",
          "minimum": 1e-06
        },
        "drive_delay_multiplier": {
          "type": "number",
          "minimum": 1
        },
        "touchdown_delay_s": {
          "type": "number",
          "minimum": 0
        }
      },
      "required": [
        "scenario_id",
        "seed",
        "terrain_realization_id",
        "solar_output_multiplier",
        "battery_capacity_multiplier",
        "drive_delay_multiplier",
        "touchdown_delay_s"
      ],
      "additionalProperties": false
    },
    "search_budget": {
      "type": "object",
      "properties": {
        "surface_max_runs": {
          "type": "integer",
          "minimum": 1
        },
        "orbital_max_runs": {
          "type": "integer",
          "minimum": 1
        },
        "transfer_timeout_s": {
          "type": "number",
          "minimum": 0.001
        }
      },
      "required": [
        "surface_max_runs",
        "orbital_max_runs",
        "transfer_timeout_s"
      ],
      "additionalProperties": false
    },
    "provenance": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/provenance"
    }
  },
  "required": [
    "schema_version",
    "request_id",
    "robot_ref",
    "environment_ref",
    "surface",
    "departure_screening",
    "scenario",
    "search_budget",
    "provenance"
  ],
  "additionalProperties": false
}
```

**File: `contracts/v0.1/robot-capability.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://spaceapps.invalid/contracts/v0.1/robot-capability.schema.json",
  "title": "Robot capability profile",
  "type": "object",
  "properties": {
    "schema_version": {
      "const": "0.1.0"
    },
    "robot_id": {
      "type": "string",
      "minLength": 1
    },
    "name": {
      "type": "string",
      "minLength": 1
    },
    "family": {
      "const": "wheeled_rover"
    },
    "body_axes": {
      "const": "x_forward_y_left_z_up"
    },
    "mass_kg": {
      "type": "number",
      "minimum": 0.001
    },
    "dimensions_m": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
    },
    "center_of_mass_body_m": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
    },
    "wheel_count": {
      "type": "integer",
      "minimum": 2
    },
    "ground_clearance_m": {
      "type": "number",
      "minimum": 0
    },
    "power": {
      "type": "object",
      "properties": {
        "battery_capacity_wh": {
          "type": "number",
          "minimum": 0.001
        },
        "initial_soc_fraction": {
          "type": "number",
          "minimum": 0,
          "maximum": 1
        },
        "reserve_wh": {
          "type": "number",
          "minimum": 0
        },
        "charge_efficiency": {
          "type": "number",
          "minimum": 1e-06,
          "maximum": 1
        },
        "discharge_efficiency": {
          "type": "number",
          "minimum": 1e-06,
          "maximum": 1
        },
        "base_bus_power_w": {
          "type": "number",
          "minimum": 0
        },
        "science_increment_w": {
          "type": "number",
          "minimum": 0
        },
        "downlink_increment_w": {
          "type": "number",
          "minimum": 0
        },
        "heater_increment_w": {
          "type": "number",
          "minimum": 0
        },
        "solar_rated_power_w": {
          "type": "number",
          "minimum": 0
        },
        "solar_reference_irradiance_w_m2": {
          "type": "number",
          "minimum": 0.001
        },
        "array_normal_body_unit": {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
        }
      },
      "required": [
        "battery_capacity_wh",
        "initial_soc_fraction",
        "reserve_wh",
        "charge_efficiency",
        "discharge_efficiency",
        "base_bus_power_w",
        "science_increment_w",
        "downlink_increment_w",
        "heater_increment_w",
        "solar_rated_power_w",
        "solar_reference_irradiance_w_m2",
        "array_normal_body_unit"
      ],
      "additionalProperties": false
    },
    "mobility": {
      "type": "object",
      "properties": {
        "response_model_id": {
          "type": "string",
          "minLength": 1
        },
        "response_model_version": {
          "type": "string",
          "minLength": 1
        },
        "response_model_kind": {
          "enum": [
            "declared_constant",
            "lookup_table",
            "surrogate"
          ]
        },
        "nominal_speed_m_s": {
          "type": "number",
          "minimum": 1e-06
        },
        "max_supported_slope_deg": {
          "type": "number",
          "minimum": 0,
          "maximum": 90
        },
        "driving_bus_power_w": {
          "type": "number",
          "minimum": 0
        },
        "power_basis": {
          "const": "base_plus_mobility_excludes_payload_radio_heater"
        },
        "validity_domain": {
          "type": "object",
          "properties": {
            "slope_min_deg": {
              "type": "number",
              "minimum": -90,
              "maximum": 90
            },
            "slope_max_deg": {
              "type": "number",
              "minimum": -90,
              "maximum": 90
            },
            "speed_min_m_s": {
              "type": "number",
              "minimum": 0
            },
            "speed_max_m_s": {
              "type": "number",
              "minimum": 0
            },
            "soil_categories": {
              "type": "array",
              "items": {
                "type": "string",
                "minLength": 1
              },
              "minItems": 1
            }
          },
          "required": [
            "slope_min_deg",
            "slope_max_deg",
            "speed_min_m_s",
            "speed_max_m_s",
            "soil_categories"
          ],
          "additionalProperties": false
        }
      },
      "required": [
        "response_model_id",
        "response_model_version",
        "response_model_kind",
        "nominal_speed_m_s",
        "max_supported_slope_deg",
        "driving_bus_power_w",
        "power_basis",
        "validity_domain"
      ],
      "additionalProperties": false
    },
    "provenance": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/provenance"
    }
  },
  "required": [
    "schema_version",
    "robot_id",
    "name",
    "family",
    "body_axes",
    "mass_kg",
    "dimensions_m",
    "center_of_mass_body_m",
    "wheel_count",
    "ground_clearance_m",
    "power",
    "mobility",
    "provenance"
  ],
  "additionalProperties": false
}
```

**File: `contracts/v0.1/transfer-candidate.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://spaceapps.invalid/contracts/v0.1/transfer-candidate.schema.json",
  "title": "Orbital screening candidate",
  "type": "object",
  "properties": {
    "schema_version": {
      "const": "0.1.0"
    },
    "candidate_id": {
      "type": "string",
      "minLength": 1
    },
    "request_id": {
      "type": "string",
      "minLength": 1
    },
    "reference_case_id": {
      "type": "string",
      "minLength": 1
    },
    "candidate_status": {
      "enum": [
        "accepted_for_screening",
        "rejected",
        "not_run",
        "nonconverged"
      ]
    },
    "solver_status": {
      "enum": [
        "converged",
        "nonconverged",
        "not_run"
      ]
    },
    "termination_event": {
      "type": "string",
      "minLength": 1
    },
    "departure_utc": {
      "anyOf": [
        {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
        },
        {
          "type": "null"
        }
      ]
    },
    "encounter_utc": {
      "anyOf": [
        {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
        },
        {
          "type": "null"
        }
      ]
    },
    "capture_utc": {
      "anyOf": [
        {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
        },
        {
          "type": "null"
        }
      ]
    },
    "departure_state": {
      "anyOf": [
        {
          "type": "object",
          "properties": {
            "epoch_utc": {
              "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
            },
            "central_body": {
              "enum": [
                "EARTH",
                "MOON"
              ]
            },
            "frame_id": {
              "type": "string",
              "minLength": 1
            },
            "position_m": {
              "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
            },
            "velocity_m_s": {
              "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
            }
          },
          "required": [
            "epoch_utc",
            "central_body",
            "frame_id",
            "position_m",
            "velocity_m_s"
          ],
          "additionalProperties": false
        },
        {
          "type": "null"
        }
      ]
    },
    "capture_state": {
      "anyOf": [
        {
          "type": "object",
          "properties": {
            "epoch_utc": {
              "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
            },
            "central_body": {
              "enum": [
                "EARTH",
                "MOON"
              ]
            },
            "frame_id": {
              "type": "string",
              "minLength": 1
            },
            "position_m": {
              "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
            },
            "velocity_m_s": {
              "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
            }
          },
          "required": [
            "epoch_utc",
            "central_body",
            "frame_id",
            "position_m",
            "velocity_m_s"
          ],
          "additionalProperties": false
        },
        {
          "type": "null"
        }
      ]
    },
    "maneuvers": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "epoch_utc": {
            "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
          },
          "frame_id": {
            "type": "string",
            "minLength": 1
          },
          "delta_v_m_s": {
            "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
          }
        },
        "required": [
          "epoch_utc",
          "frame_id",
          "delta_v_m_s"
        ],
        "additionalProperties": false
      },
      "minItems": 0
    },
    "total_maneuver_delta_v_m_s": {
      "type": [
        "number",
        "null"
      ]
    },
    "minimum_lunar_clearance_m": {
      "type": [
        "number",
        "null"
      ]
    },
    "capture_eccentricity": {
      "type": [
        "number",
        "null"
      ]
    },
    "target_residuals": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": {
            "type": "string",
            "minLength": 1
          },
          "residual": {
            "type": "number"
          },
          "tolerance": {
            "type": "number",
            "minimum": 0
          },
          "unit": {
            "type": "string",
            "minLength": 1
          }
        },
        "required": [
          "name",
          "residual",
          "tolerance",
          "unit"
        ],
        "additionalProperties": false
      },
      "minItems": 0
    },
    "verification_status": {
      "enum": [
        "passed",
        "failed",
        "pending",
        "not_run"
      ]
    },
    "gmat_version": {
      "type": "string",
      "minLength": 1
    },
    "script_sha256": {
      "anyOf": [
        {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        },
        {
          "type": "null"
        }
      ]
    },
    "supporting_assets": {
      "type": "array",
      "items": {
        "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
      },
      "minItems": 0
    },
    "assumptions": {
      "type": "array",
      "items": {
        "type": "string",
        "minLength": 1
      },
      "minItems": 0
    },
    "provenance": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/provenance"
    }
  },
  "required": [
    "schema_version",
    "candidate_id",
    "request_id",
    "reference_case_id",
    "candidate_status",
    "solver_status",
    "termination_event",
    "departure_utc",
    "encounter_utc",
    "capture_utc",
    "departure_state",
    "capture_state",
    "maneuvers",
    "total_maneuver_delta_v_m_s",
    "minimum_lunar_clearance_m",
    "capture_eccentricity",
    "target_residuals",
    "verification_status",
    "gmat_version",
    "script_sha256",
    "supporting_assets",
    "assumptions",
    "provenance"
  ],
  "additionalProperties": false
}
```

**File: `contracts/v0.1/vehicle-response.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://spaceapps.invalid/contracts/v0.1/vehicle-response.schema.json",
  "title": "Detailed vehicle segment response",
  "type": "object",
  "properties": {
    "schema_version": {
      "const": "0.1.0"
    },
    "response_id": {
      "type": "string",
      "minLength": 1
    },
    "segment_id": {
      "type": "string",
      "minLength": 1
    },
    "segment_request_ref": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
    },
    "robot_ref": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
    },
    "environment_ref": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
    },
    "time_origin_utc": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
    },
    "local_axes": {
      "const": "x_east_y_north_z_up"
    },
    "quaternion_convention": {
      "const": "xyzw_body_to_enu"
    },
    "response_model_id": {
      "type": "string",
      "minLength": 1
    },
    "response_model_version": {
      "type": "string",
      "minLength": 1
    },
    "power_basis": {
      "const": "base_plus_mobility_excludes_payload_radio_heater"
    },
    "mobility_bus_energy_wh": {
      "type": "number",
      "minimum": 0
    },
    "validity_status": {
      "enum": [
        "within_domain",
        "outside_domain",
        "unknown"
      ]
    },
    "samples": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "t_s": {
            "type": "number",
            "minimum": 0
          },
          "position_enu_m": {
            "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
          },
          "orientation_body_to_enu_xyzw": {
            "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/quaternion_xyzw"
          },
          "actual_speed_m_s": {
            "type": "number",
            "minimum": 0
          },
          "mobility_bus_power_w": {
            "type": "number",
            "minimum": 0
          },
          "flags": {
            "type": "array",
            "items": {
              "type": "string",
              "minLength": 1
            },
            "minItems": 0
          }
        },
        "required": [
          "t_s",
          "position_enu_m",
          "orientation_body_to_enu_xyzw",
          "actual_speed_m_s",
          "mobility_bus_power_w",
          "flags"
        ],
        "additionalProperties": false
      },
      "minItems": 2
    },
    "provenance": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/provenance"
    }
  },
  "required": [
    "schema_version",
    "response_id",
    "segment_id",
    "segment_request_ref",
    "robot_ref",
    "environment_ref",
    "time_origin_utc",
    "local_axes",
    "quaternion_convention",
    "response_model_id",
    "response_model_version",
    "power_basis",
    "mobility_bus_energy_wh",
    "validity_status",
    "samples",
    "provenance"
  ],
  "additionalProperties": false
}
```

**File: `contracts/v0.1/vehicle-segment-request.schema.json`**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://spaceapps.invalid/contracts/v0.1/vehicle-segment-request.schema.json",
  "title": "Detailed vehicle segment request",
  "type": "object",
  "properties": {
    "schema_version": {
      "const": "0.1.0"
    },
    "segment_id": {
      "type": "string",
      "minLength": 1
    },
    "robot_ref": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
    },
    "environment_ref": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/asset_ref"
    },
    "time_origin_utc": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/utc"
    },
    "scenario_id": {
      "type": "string",
      "minLength": 1
    },
    "seed": {
      "type": "integer",
      "minimum": 0
    },
    "soil_category": {
      "type": "string",
      "minLength": 1
    },
    "start_t_s": {
      "type": "number",
      "minimum": 0
    },
    "duration_s": {
      "type": "number",
      "minimum": 0.001
    },
    "initial_state": {
      "type": "object",
      "properties": {
        "position_enu_m": {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/vec3"
        },
        "orientation_body_to_enu_xyzw": {
          "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/quaternion_xyzw"
        },
        "speed_m_s": {
          "type": "number",
          "minimum": 0
        }
      },
      "required": [
        "position_enu_m",
        "orientation_body_to_enu_xyzw",
        "speed_m_s"
      ],
      "additionalProperties": false
    },
    "controls": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "start_t_s": {
            "type": "number",
            "minimum": 0
          },
          "duration_s": {
            "type": "number",
            "minimum": 0.001
          },
          "mode": {
            "enum": [
              "drive",
              "idle"
            ]
          },
          "speed_setpoint_m_s": {
            "type": "number",
            "minimum": 0
          }
        },
        "required": [
          "start_t_s",
          "duration_s",
          "mode",
          "speed_setpoint_m_s"
        ],
        "additionalProperties": false
      },
      "minItems": 1
    },
    "provenance": {
      "$ref": "https://spaceapps.invalid/contracts/v0.1/common.schema.json#/$defs/provenance"
    }
  },
  "required": [
    "schema_version",
    "segment_id",
    "robot_ref",
    "environment_ref",
    "time_origin_utc",
    "scenario_id",
    "seed",
    "soil_category",
    "start_t_s",
    "duration_s",
    "initial_state",
    "controls",
    "provenance"
  ],
  "additionalProperties": false
}
```

**6. Complete synthetic messages and assets**

These files form one consistent fixture bundle. Preserve their bytes when verifying the supplied asset hashes. The driving segment is independent of the stationary monitoring mission. The orbital candidate is deliberately marked not run.

**File: `examples/integration/assets/source-manifest.json`**

```json
{
  "schema_version": "0.1.0",
  "source_class": "synthetic_contract_fixture",
  "dataset_ids": [],
  "kernel_assets": [],
  "notes": "No NASA assets or kernels were used to generate this synthetic environment.",
  "terrain_asset": {
    "uri": "assets/synthetic-terrain.json",
    "sha256": "853c7ae19da5c3dfb72ff5104b4584a55009dcb2bd0a8092da1f0d275a9e67ce"
  },
  "normalization": "Explicit flat local tangent plane at an artificial sphere point."
}
```

**File: `examples/integration/assets/synthetic-terrain.json`**

```json
{
  "description": "Synthetic local tangent-plane fixture. No NASA terrain is embedded.",
  "x_min_m": 0,
  "y_min_m": -10,
  "grid_spacing_m": 5,
  "height_quantity": "local_up_m",
  "heights_m": [
    [
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0
    ],
    [
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0
    ],
    [
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0
    ],
    [
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0
    ],
    [
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0,
      0
    ]
  ]
}
```

**File: `examples/integration/environment-package.json`**

```json
{
  "schema_version": "0.1.0",
  "environment_id": "fixture-environment-001",
  "site_id": "synthetic-connecting-ridge-location",
  "global_frame": "MOON_ME_DE421",
  "local_axes": "x_east_y_north_z_up",
  "source_manifest_ref": {
    "uri": "assets/source-manifest.json",
    "sha256": "78f4e3b7af9916b09e24da8849bcc7b0ca2247d50874b1c98924657f753f0b2a"
  },
  "origin": {
    "latitude_deg": -89.44,
    "longitude_east_deg": 222.8,
    "position_body_fixed_m": [
      -12459.324395556354,
      -11537.460892735617,
      -1737317.01546717
    ],
    "enu_to_body_fixed_rotation": [
      [
        0.6794413042615165,
        -0.7336948189002349,
        -0.007171246918128441
      ],
      [
        -0.7337298645028764,
        -0.6794088516776443,
        -0.0066406474575432355
      ],
      [
        0,
        0.009773688199249151,
        -0.9999522363688097
      ]
    ]
  },
  "terrain": {
    "asset": {
      "uri": "assets/synthetic-terrain.json",
      "sha256": "853c7ae19da5c3dfb72ff5104b4584a55009dcb2bd0a8092da1f0d275a9e67ce"
    },
    "horizontal_frame": "LOCAL_ENU",
    "vertical_quantity": "local_up_m",
    "grid_spacing_m": 5,
    "raw_vertical_definition": "Synthetic tangent-plane height, zero at the local origin.",
    "normalization_notes": "No real raster was transformed. The sphere point and flat patch are artificial."
  },
  "gravity_m_s2": 1.62,
  "time_origin_utc": "2028-01-01T00:00:00Z",
  "elapsed_time_basis": "SI_seconds_from_time_origin",
  "geometry_convention": "geometric_observer_to_body_unit_vectors",
  "sky_samples": [
    {
      "t_s": 0,
      "sun_direction_enu_unit": [
        0.6,
        0,
        0.8
      ],
      "earth_direction_enu_unit": [
        0.8,
        0,
        0.6
      ],
      "sun_angular_radius_rad": 0.00465,
      "solar_irradiance_w_m2": 1361
    },
    {
      "t_s": 3600,
      "sun_direction_enu_unit": [
        0.6,
        0,
        0.8
      ],
      "earth_direction_enu_unit": [
        0.8,
        0,
        0.6
      ],
      "sun_angular_radius_rad": 0.00465,
      "solar_irradiance_w_m2": 1361
    },
    {
      "t_s": 7200,
      "sun_direction_enu_unit": [
        0.6,
        0,
        0.8
      ],
      "earth_direction_enu_unit": [
        0.8,
        0,
        0.6
      ],
      "sun_angular_radius_rad": 0.00465,
      "solar_irradiance_w_m2": 1361
    },
    {
      "t_s": 10800,
      "sun_direction_enu_unit": [
        0.6,
        0,
        0.8
      ],
      "earth_direction_enu_unit": [
        0.8,
        0,
        0.6
      ],
      "sun_angular_radius_rad": 0.00465,
      "solar_irradiance_w_m2": 1361
    }
  ],
  "horizon_model_id": "synthetic-not-computed",
  "terrain_scenario_id": "synthetic-flat",
  "provenance": {
    "source_class": "synthetic_contract_fixture",
    "model_id": "fixture-environment",
    "model_version": "0.1.0",
    "notes": "Synthetic geometry for decoding and coordinate checks; no ephemeris, horizon, or lunar observation was evaluated."
  }
}
```

**File: `examples/integration/plan-evaluation.json`**

```json
{
  "schema_version": "0.1.0",
  "evaluation_id": "fixture-evaluation-001",
  "request_id": "fixture-planning-request-001",
  "robot_ref": {
    "uri": "robot-capability.json",
    "sha256": "4cb9354aa1f384e350aa6e7591192e5760f0fe8d7ef0c29a906e658d74c80c58"
  },
  "environment_ref": {
    "uri": "environment-package.json",
    "sha256": "face53148ae395baaf3d4bfa22b13c708995e71c3e4ba4ca6d22f0eb9f3cdfba"
  },
  "assessment_scope": "departure_and_surface_screening",
  "status": "insufficient_evidence",
  "scope_notes": "Only synthetic energy accounting is populated. No Earth-to-Moon or landing-access solve was run.",
  "surface_result": {
    "status": "supported_under_assumptions",
    "minimum_battery_wh": 800.0,
    "battery_reserve_margin_wh": 600.0,
    "longest_geometric_earth_outage_s": 0,
    "required_tasks_completed": [
      "monitor"
    ],
    "first_violation": null,
    "samples": [
      {
        "t_s": 0,
        "position_enu_m": [
          0,
          0,
          0
        ],
        "solar_power_w": 160,
        "total_load_w": 40,
        "battery_energy_wh": 800.0,
        "earth_center_visible": true
      },
      {
        "t_s": 3600,
        "position_enu_m": [
          0,
          0,
          0
        ],
        "solar_power_w": 0,
        "total_load_w": 40,
        "battery_energy_wh": 914.0,
        "earth_center_visible": true
      },
      {
        "t_s": 7200,
        "position_enu_m": [
          0,
          0,
          0
        ],
        "solar_power_w": 0,
        "total_load_w": 40,
        "battery_energy_wh": 871.8947368421052,
        "earth_center_visible": true
      },
      {
        "t_s": 10800,
        "position_enu_m": [
          0,
          0,
          0
        ],
        "solar_power_w": 0,
        "total_load_w": 40,
        "battery_energy_wh": 829.7894736842104,
        "earth_center_visible": true
      }
    ]
  },
  "transfer_result": {
    "status": "not_run",
    "departure_utc": null,
    "encounter_utc": null,
    "capture_utc": null,
    "total_maneuver_delta_v_m_s": null,
    "candidate_artifact": null,
    "notes": "Reference-script outputs must be generated by a real GMAT run."
  },
  "landing_access": {
    "status": "not_evaluated",
    "notes": "No capture candidate exists in this fixture; orbit phasing and descent remain unmodeled."
  },
  "issues": [
    "SYNTHETIC_FIXTURE",
    "TRANSFER_NOT_RUN",
    "LANDING_ACCESS_NOT_EVALUATED"
  ],
  "assumptions": [
    "Solar power is prescribed as 160 W for one hour and zero for two hours.",
    "The artificial lighting steps are independent of the environment sky-vector fixture.",
    "A baseline monitoring task consumes the declared 40 W bus load.",
    "Samples use left-constant power over each following interval."
  ],
  "provenance": {
    "source_class": "synthetic_contract_fixture",
    "model_id": "analytical-energy-fixture",
    "model_version": "0.1.0",
    "notes": "Exact synthetic accounting example. Not a lunar lighting prediction, robot experiment, or orbital result."
  }
}
```

**File: `examples/integration/planning-request.json`**

```json
{
  "schema_version": "0.1.0",
  "request_id": "fixture-planning-request-001",
  "robot_ref": {
    "uri": "robot-capability.json",
    "sha256": "4cb9354aa1f384e350aa6e7591192e5760f0fe8d7ef0c29a906e658d74c80c58"
  },
  "environment_ref": {
    "uri": "environment-package.json",
    "sha256": "face53148ae395baaf3d4bfa22b13c708995e71c3e4ba4ca6d22f0eb9f3cdfba"
  },
  "surface": {
    "site_id": "synthetic-connecting-ridge-location",
    "touchdown_utc": "2028-01-01T00:00:00Z",
    "duration_s": 10800,
    "route_points_enu_m": [
      [
        0,
        0,
        0
      ]
    ],
    "required_tasks": [
      {
        "task_id": "monitor",
        "duration_s": 10800,
        "location_enu_m": [
          0,
          0,
          0
        ],
        "power_mode": "base"
      }
    ],
    "constraints": {
      "max_slope_deg": 15,
      "max_geometric_earth_outage_s": 3600,
      "contact_model": "earth_center_geometric"
    }
  },
  "departure_screening": {
    "enabled": true,
    "mode": "reference_transfer_family",
    "reference_case_id": "GMAT_R2026a_fixed_epoch_family",
    "departure_start_utc": "2027-12-26T00:00:00Z",
    "departure_end_utc": "2027-12-28T00:00:00Z",
    "epoch_step_s": 86400,
    "spacecraft_wet_mass_kg": null,
    "vehicle_performance_status": "not_assessed",
    "permitted_variables": [
      "epoch",
      "raan",
      "aop",
      "departure_burn",
      "capture_burn"
    ],
    "launch_to_departure_offset_s": null,
    "capture_to_touchdown": {
      "min_s": 43200,
      "max_s": 172800,
      "evidence": "assumed_not_dynamically_validated"
    }
  },
  "scenario": {
    "scenario_id": "fixture-scenario-001",
    "seed": 42,
    "terrain_realization_id": "synthetic-flat",
    "solar_output_multiplier": 1,
    "battery_capacity_multiplier": 1,
    "drive_delay_multiplier": 1,
    "touchdown_delay_s": 0
  },
  "search_budget": {
    "surface_max_runs": 200,
    "orbital_max_runs": 20,
    "transfer_timeout_s": 120
  },
  "provenance": {
    "source_class": "synthetic_contract_fixture",
    "model_id": "fixture-request",
    "model_version": "0.1.0",
    "notes": "A synthetic stationary surface mission and unexecuted transfer search, for interface testing only."
  }
}
```

**File: `examples/integration/robot-capability.json`**

```json
{
  "schema_version": "0.1.0",
  "robot_id": "fixture-rover-001",
  "name": "Hypothetical reference rover",
  "family": "wheeled_rover",
  "body_axes": "x_forward_y_left_z_up",
  "mass_kg": 120,
  "dimensions_m": [
    1.8,
    1.6,
    1.0
  ],
  "center_of_mass_body_m": [
    0,
    0,
    0.35
  ],
  "wheel_count": 6,
  "ground_clearance_m": 0.25,
  "power": {
    "battery_capacity_wh": 1000,
    "initial_soc_fraction": 0.8,
    "reserve_wh": 200,
    "charge_efficiency": 0.95,
    "discharge_efficiency": 0.95,
    "base_bus_power_w": 40,
    "science_increment_w": 30,
    "downlink_increment_w": 20,
    "heater_increment_w": 0,
    "solar_rated_power_w": 200,
    "solar_reference_irradiance_w_m2": 1361,
    "array_normal_body_unit": [
      0,
      0,
      1
    ]
  },
  "mobility": {
    "response_model_id": "fixture-constant-mobility",
    "response_model_version": "0.1.0",
    "response_model_kind": "declared_constant",
    "nominal_speed_m_s": 0.05,
    "max_supported_slope_deg": 15,
    "driving_bus_power_w": 120,
    "power_basis": "base_plus_mobility_excludes_payload_radio_heater",
    "validity_domain": {
      "slope_min_deg": -15,
      "slope_max_deg": 15,
      "speed_min_m_s": 0,
      "speed_max_m_s": 0.05,
      "soil_categories": [
        "synthetic_flat"
      ]
    }
  },
  "provenance": {
    "source_class": "synthetic_contract_fixture",
    "model_id": "fixture-robot-profile",
    "model_version": "0.1.0",
    "notes": "Declared hypothetical parameters for interface testing; not NASA rover specifications."
  }
}
```

**File: `examples/integration/transfer-candidate.json`**

```json
{
  "schema_version": "0.1.0",
  "candidate_id": "fixture-transfer-not-run",
  "request_id": "fixture-planning-request-001",
  "reference_case_id": "GMAT_R2026a_fixed_epoch_family",
  "candidate_status": "not_run",
  "solver_status": "not_run",
  "termination_event": "NOT_EXECUTED",
  "departure_utc": null,
  "encounter_utc": null,
  "capture_utc": null,
  "departure_state": null,
  "capture_state": null,
  "maneuvers": [],
  "total_maneuver_delta_v_m_s": null,
  "minimum_lunar_clearance_m": null,
  "capture_eccentricity": null,
  "target_residuals": [],
  "verification_status": "not_run",
  "gmat_version": "R2026a-reference-not-executed",
  "script_sha256": null,
  "supporting_assets": [],
  "assumptions": [
    "No orbital output is fabricated for this handoff.",
    "Trajectory screening and launch-vehicle capability are separate assessments."
  ],
  "provenance": {
    "source_class": "synthetic_contract_fixture",
    "model_id": "fixture-transfer-not-run",
    "model_version": "0.1.0",
    "notes": "Structured not-run result; use an actual GMAT run to populate states, burns, residuals and hashes."
  }
}
```

**File: `examples/integration/vehicle-response.json`**

```json
{
  "schema_version": "0.1.0",
  "response_id": "fixture-vehicle-response-001",
  "segment_id": "independent-synthetic-driving-segment",
  "segment_request_ref": {
    "uri": "vehicle-segment-request.json",
    "sha256": "f06138e099022221717c211f69c13524c60cd5d3beab0a16c3f30355073e98d8"
  },
  "robot_ref": {
    "uri": "robot-capability.json",
    "sha256": "4cb9354aa1f384e350aa6e7591192e5760f0fe8d7ef0c29a906e658d74c80c58"
  },
  "environment_ref": {
    "uri": "environment-package.json",
    "sha256": "face53148ae395baaf3d4bfa22b13c708995e71c3e4ba4ca6d22f0eb9f3cdfba"
  },
  "time_origin_utc": "2028-01-01T00:00:00Z",
  "local_axes": "x_east_y_north_z_up",
  "quaternion_convention": "xyzw_body_to_enu",
  "response_model_id": "fixture-constant-mobility",
  "response_model_version": "0.1.0",
  "power_basis": "base_plus_mobility_excludes_payload_radio_heater",
  "mobility_bus_energy_wh": 6.666666666666667,
  "validity_status": "within_domain",
  "samples": [
    {
      "t_s": 0,
      "position_enu_m": [
        0.0,
        0,
        0
      ],
      "orientation_body_to_enu_xyzw": [
        0,
        0,
        0,
        1
      ],
      "actual_speed_m_s": 0.05,
      "mobility_bus_power_w": 120,
      "flags": []
    },
    {
      "t_s": 100,
      "position_enu_m": [
        5.0,
        0,
        0
      ],
      "orientation_body_to_enu_xyzw": [
        0,
        0,
        0,
        1
      ],
      "actual_speed_m_s": 0.05,
      "mobility_bus_power_w": 120,
      "flags": []
    },
    {
      "t_s": 200,
      "position_enu_m": [
        10.0,
        0,
        0
      ],
      "orientation_body_to_enu_xyzw": [
        0,
        0,
        0,
        1
      ],
      "actual_speed_m_s": 0.05,
      "mobility_bus_power_w": 120,
      "flags": []
    }
  ],
  "provenance": {
    "source_class": "synthetic_contract_fixture",
    "model_id": "fixture-constant-mobility",
    "model_version": "0.1.0",
    "notes": "Independent analytical 10 m driving segment at 0.05 m/s and 120 W. Not the stationary planning mission."
  }
}
```

**File: `examples/integration/vehicle-segment-request.json`**

```json
{
  "schema_version": "0.1.0",
  "segment_id": "independent-synthetic-driving-segment",
  "robot_ref": {
    "uri": "robot-capability.json",
    "sha256": "4cb9354aa1f384e350aa6e7591192e5760f0fe8d7ef0c29a906e658d74c80c58"
  },
  "environment_ref": {
    "uri": "environment-package.json",
    "sha256": "face53148ae395baaf3d4bfa22b13c708995e71c3e4ba4ca6d22f0eb9f3cdfba"
  },
  "time_origin_utc": "2028-01-01T00:00:00Z",
  "scenario_id": "fixture-flat-driving",
  "seed": 42,
  "soil_category": "synthetic_flat",
  "start_t_s": 0,
  "duration_s": 200,
  "initial_state": {
    "position_enu_m": [
      0,
      0,
      0
    ],
    "orientation_body_to_enu_xyzw": [
      0,
      0,
      0,
      1
    ],
    "speed_m_s": 0.05
  },
  "controls": [
    {
      "start_t_s": 0,
      "duration_s": 200,
      "mode": "drive",
      "speed_setpoint_m_s": 0.05
    }
  ],
  "provenance": {
    "source_class": "synthetic_contract_fixture",
    "model_id": "fixture-driving-request",
    "model_version": "0.1.0",
    "notes": "Independent constant-speed flat-ground integration fixture; no dynamics or soil experiment."
  }
}
```

**7. Validator and validation record**

To run the checks, recreate the indicated files and folders, install the requirements in a project environment, and run the validator from the project root. The code and dependencies are included here; no other handoff attachment is needed.

**File: `requirements-contracts.txt`**

```text
jsonschema[format]==4.26.0
referencing==0.37.0
```

**File: `scripts/validate_handoff_contracts.py`**

```python
"""Validate handoff fixtures and cross-message scientific interface conventions.

Run: uv run --with 'jsonschema[format]' python scripts/validate_handoff_contracts.py
This does not execute GMAT, calculate ephemerides, or validate lunar physics.
"""
from pathlib import Path
from datetime import datetime
from copy import deepcopy
import hashlib
import json
import math

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / 'contracts/v0.1'
EXAMPLES = ROOT / 'examples/integration'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    def invalid_constant(value):
        raise ValueError(f'Non-finite JSON number: {value}')
    return json.loads(path.read_text(), parse_constant=invalid_constant)


def finite(value):
    if isinstance(value, float):
        require(math.isfinite(value), 'Non-finite number')
    elif isinstance(value, dict):
        for child in value.values():
            finite(child)
    elif isinstance(value, list):
        for child in value:
            finite(child)


def unit(vector):
    require(abs(sum(x*x for x in vector) - 1) < 1e-9, 'Expected a unit vector/quaternion')


def ordered(samples):
    times = [sample['t_s'] for sample in samples]
    require(all(b > a for a, b in zip(times, times[1:])), 'Times must strictly increase')


def dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def verify_assets(value):
    if isinstance(value, dict):
        if set(value) == {'uri', 'sha256'}:
            path = (EXAMPLES / value['uri']).resolve()
            require(path.is_relative_to(EXAMPLES.resolve()), 'Fixture asset escapes bundle')
            require(path.is_file(), f'Missing fixture asset: {path}')
            require(hashlib.sha256(path.read_bytes()).hexdigest() == value['sha256'],
                    f'Asset hash mismatch: {path.name}')
        for child in value.values():
            verify_assets(child)
    elif isinstance(value, list):
        for child in value:
            verify_assets(child)


def robot_checks(robot):
    p = robot['power']
    require(p['reserve_wh'] <= p['battery_capacity_wh'], 'Reserve exceeds nominal capacity')
    require(all(x > 0 for x in robot['dimensions_m']), 'Robot dimensions must be positive')
    unit(p['array_normal_body_unit'])
    domain = robot['mobility']['validity_domain']
    require(domain['slope_min_deg'] <= domain['slope_max_deg'], 'Invalid slope domain')
    require(domain['speed_min_m_s'] <= domain['speed_max_m_s'], 'Invalid speed domain')


def transfer_checks(candidate):
    if candidate['candidate_status'] == 'accepted_for_screening':
        require(candidate['solver_status'] == 'converged', 'Accepted candidate has not converged')
        require(candidate['verification_status'] == 'passed', 'Accepted candidate is unverified')
        for field in ['departure_utc', 'encounter_utc', 'capture_utc', 'departure_state',
                      'capture_state', 'script_sha256', 'total_maneuver_delta_v_m_s',
                      'minimum_lunar_clearance_m', 'capture_eccentricity']:
            require(candidate[field] is not None, f'Accepted candidate missing {field}')
        require(dt(candidate['departure_utc']) < dt(candidate['encounter_utc']) <= dt(candidate['capture_utc']),
                'Invalid departure/encounter/capture order')
        require(candidate['minimum_lunar_clearance_m'] > 0, 'Nonpositive lunar clearance')
        require(0 <= candidate['capture_eccentricity'] < 1, 'Capture is not an elliptic orbit')
        require(candidate['target_residuals'], 'Accepted candidate has no residuals')
        require(all(abs(r['residual']) <= r['tolerance'] for r in candidate['target_residuals']),
                'Candidate residual exceeds tolerance')
        require(candidate['departure_state']['central_body'] == 'EARTH', 'Departure origin mismatch')
        require(candidate['capture_state']['central_body'] == 'MOON', 'Capture origin mismatch')
        require(candidate['departure_state']['epoch_utc'] == candidate['departure_utc'],
                'Departure state epoch mismatch')
        require(candidate['capture_state']['epoch_utc'] == candidate['capture_utc'],
                'Capture state epoch mismatch')
        require(candidate['maneuvers'], 'Accepted candidate has no maneuvers')
        total = sum(math.sqrt(sum(x*x for x in m['delta_v_m_s'])) for m in candidate['maneuvers'])
        require(math.isclose(total, candidate['total_maneuver_delta_v_m_s'], rel_tol=1e-8, abs_tol=1e-8),
                'Maneuver delta-v total mismatch')


def main():
    schemas = {p.name: read_json(p) for p in SCHEMAS.glob('*.schema.json')}
    for item in schemas.values():
        Draft202012Validator.check_schema(item)
    registry = Registry().with_resources([
        (s['$id'], Resource.from_contents(s)) for s in schemas.values()])
    messages = {}
    for path in sorted(EXAMPLES.glob('*.json')):
        value = read_json(path)
        validator = Draft202012Validator(schemas[path.stem + '.schema.json'],
                                        registry=registry, format_checker=FormatChecker())
        validator.validate(value)
        finite(value)
        verify_assets(value)
        messages[path.stem] = value

    robot = messages['robot-capability']
    environment = messages['environment-package']
    request = messages['planning-request']
    evaluation = messages['plan-evaluation']
    response = messages['vehicle-response']
    segment = messages['vehicle-segment-request']
    candidate = messages['transfer-candidate']
    robot_checks(robot)
    ordered(environment['sky_samples'])
    rotation = environment['origin']['enu_to_body_fixed_rotation']
    columns = list(zip(*rotation))
    for col in columns:
        unit(col)
    for i, a in enumerate(columns):
        for b in columns[i+1:]:
            require(abs(sum(x*y for x, y in zip(a, b))) < 1e-9, 'Frame matrix not orthogonal')
    east, north, up = columns
    cross = [east[1]*north[2]-east[2]*north[1], east[2]*north[0]-east[0]*north[2],
             east[0]*north[1]-east[1]*north[0]]
    require(sum(a*b for a, b in zip(cross, up)) > 0.999999, 'Frame is not right handed')
    for sample in environment['sky_samples']:
        unit(sample['sun_direction_enu_unit'])
        unit(sample['earth_direction_enu_unit'])
    for key in ['robot_ref', 'environment_ref']:
        require(request[key] == evaluation[key] == segment[key] == response[key],
                f'Immutable reference mismatch: {key}')
    require(evaluation['request_id'] == request['request_id'] == candidate['request_id'],
            'Request identity mismatch')
    require(request['surface']['site_id'] == environment['site_id'], 'Site mismatch')
    require(request['surface']['touchdown_utc'] == environment['time_origin_utc'], 'Time origin mismatch')
    require(environment['sky_samples'][0]['t_s'] == 0, 'Environment must cover start')
    require(environment['sky_samples'][-1]['t_s'] >= request['surface']['duration_s'],
            'Environment does not cover the mission')
    departure = request['departure_screening']
    require(dt(departure['departure_start_utc']) <= dt(departure['departure_end_utc']),
            'Departure interval is reversed')
    delay = departure['capture_to_touchdown']
    require(delay['min_s'] <= delay['max_s'], 'Capture-to-touchdown interval is reversed')
    surface = evaluation['surface_result']
    ordered(surface['samples'])
    require(surface['samples'][0]['t_s'] == 0 and
            surface['samples'][-1]['t_s'] == request['surface']['duration_s'], 'Timeline span mismatch')
    energies = [s['battery_energy_wh'] for s in surface['samples']]
    require(math.isclose(min(energies), surface['minimum_battery_wh']), 'Battery minimum mismatch')
    require(math.isclose(surface['minimum_battery_wh'] - robot['power']['reserve_wh'],
                         surface['battery_reserve_margin_wh']), 'Reserve margin mismatch')
    require(max(energies) <= robot['power']['battery_capacity_wh'], 'Battery exceeds capacity')
    if surface['status'] == 'supported_under_assumptions':
        required = {t['task_id'] for t in request['surface']['required_tasks']}
        require(required <= set(surface['required_tasks_completed']), 'Required task missing')
        require(surface['first_violation'] is None, 'Supported fixture reports a violation')
    # The power fixture uses left-constant loads, no capacity clipping, and exact hour intervals.
    for a, b in zip(surface['samples'], surface['samples'][1:]):
        net = a['solar_power_w'] - a['total_load_w']
        delta_w = net * robot['power']['charge_efficiency'] if net >= 0 else net / robot['power']['discharge_efficiency']
        expected = a['battery_energy_wh'] + delta_w * (b['t_s'] - a['t_s']) / 3600
        require(math.isclose(expected, b['battery_energy_wh'], abs_tol=1e-8), 'Energy fixture accounting mismatch')
    require(response['segment_id'] == segment['segment_id'], 'Segment identity mismatch')
    require(response['time_origin_utc'] == segment['time_origin_utc'] == environment['time_origin_utc'],
            'Segment clock mismatch')
    require(response['power_basis'] == robot['mobility']['power_basis'], 'Power convention mismatch')
    ordered(response['samples'])
    require(response['samples'][0]['t_s'] == segment['start_t_s'] and
            response['samples'][-1]['t_s'] == segment['start_t_s'] + segment['duration_s'],
            'Segment duration mismatch')
    require(segment['start_t_s'] + segment['duration_s'] <= environment['sky_samples'][-1]['t_s'],
            'Environment does not cover segment')
    controls = segment['controls']
    require(controls[0]['start_t_s'] == segment['start_t_s'], 'Control start mismatch')
    for a, b in zip(controls, controls[1:]):
        require(math.isclose(a['start_t_s'] + a['duration_s'], b['start_t_s']),
                'Controls have gaps or overlaps')
    require(math.isclose(controls[-1]['start_t_s'] + controls[-1]['duration_s'],
                         segment['start_t_s'] + segment['duration_s']), 'Control end mismatch')
    unit(segment['initial_state']['orientation_body_to_enu_xyzw'])
    for sample in response['samples']:
        unit(sample['orientation_body_to_enu_xyzw'])
    energy = sum(a['mobility_bus_power_w'] * (b['t_s']-a['t_s']) / 3600
                 for a, b in zip(response['samples'], response['samples'][1:]))
    require(math.isclose(energy, response['mobility_bus_energy_wh']), 'Mobility energy mismatch')
    transfer_checks(candidate)

    # Ensure semantic checks reject representative integration mistakes.
    negative_cases = 0
    bad = deepcopy(robot)
    bad['power']['reserve_wh'] = 2000
    try:
        robot_checks(bad)
    except ValueError:
        negative_cases += 1
    else:
        raise ValueError('Failed to reject impossible nominal reserve')
    bad = deepcopy(candidate)
    bad['candidate_status'] = 'accepted_for_screening'
    try:
        transfer_checks(bad)
    except ValueError:
        negative_cases += 1
    else:
        raise ValueError('Failed to reject fabricated accepted transfer')
    try:
        ordered([{'t_s': 1}, {'t_s': 1}])
    except ValueError:
        negative_cases += 1
    else:
        raise ValueError('Failed to reject duplicate timestamps')
    try:
        unit([1, 1, 0])
    except ValueError:
        negative_cases += 1
    else:
        raise ValueError('Failed to reject a non-unit vector')

    print(f'PASS: {len(schemas)} schemas; {len(messages)} messages; hashes, frames, clocks, power and statuses checked.')
    print(f'PASS: {negative_cases} deliberately invalid cases rejected.')
    print('Scope: interface and analytical fixtures only; GMAT, ephemeris and lunar physics are not executed.')


if __name__ == '__main__':
    main()
```

**File: `docs/planner-handoff/VALIDATION.txt`**

```text
Handoff validation record
Date: 2026-11-14

PASS: 8 JSON Schema files checked against Draft 2020-12.
PASS: 7 synthetic example messages validate against their schemas.
PASS: referenced local fixture assets exist and their SHA-256 hashes match.
PASS: ENU rotation is orthonormal and right handed; vectors/quaternions are normalized.
PASS: shared request IDs, immutable references, clocks, segment spans and controls align.
PASS: synthetic solar/battery accounting and mobility-bus energy are consistent.
PASS: 4 representative invalid cases are rejected.
PASS: local Markdown documentation links resolve.

Validator environment: jsonschema 4.26.0; referencing 0.37.0.
Requirements for this validator are in requirements-contracts.txt.

Scope: interface and analytical fixtures only. No GMAT propagation, ephemeris
generation, observed-shadow comparison, terrain normalization, mobility physics,
ML training, or hosted application was executed or implemented by this handoff.
Those checks and implementation tasks are specified in the build backlog.

GMAT reference scripts and official data/API documentation were inspected.
Numerical GMAT convergence and solved reference outputs must be established
by the planning developer before publishing Earth-departure screening results.
```
