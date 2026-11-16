# NASA robot model evidence

Clavius prioritizes a small, documented robot library over broad company schematic importing. The mission-assessment rover is the hypothetical R1. The separate surface drive visualizes VIPER and four recorded native traverses across two sites. The first NASA hardware candidate is VIPER, supported by related NASA Glenn TREC/MGRU3 ground-test references. A candidate audit is not yet executable app support or validated flight prediction.

## VIPER source and native model audit

[Bill Bluethmann's 14 November 2024 NASA hardware briefing](https://ntrs.nasa.gov/citations/20240013903) provides a dated engineering reference. Page 2 distinguishes **447 kg roving** mass from **490 kg launch** mass including the lander interface. Page 4 gives four wheels, 0.5 m wheel diameter, 0.025 m grousers, 0.1 m/s nominal and 0.2 m/s top speed, ±50° steering, active wheel downforce with IMU control, and 0.07–0.43 m adjustable clearance. The 15° slope and 0.15 m obstacle values are design requirements, not Clavius-demonstrated capability.

The original 2,756,069-byte PDF is cached at `data/raw/robots/research/viper-mobility-hardware-2024.pdf`, SHA-256 `fde1179cbf7af0fa04bdf4d19bb2c133a6c551e616fa921bb69354c21ec18465`. Relevant pages were extracted and visually inspected. It is a source reference, not a new active lunar dataset.

Project Chrono's [VIPER implementation](https://github.com/projectchrono/chrono/blob/2617649bf687456328a122b63dc0bb64df91394a/src/chrono_models/robot/viper/Viper.cpp) is pinned at version **9.0.1**, commit `2617649bf687456328a122b63dc0bb64df91394a`. The original source is unchanged. Its BSD-3-Clause license is retained in `workers/chrono/third_party/Chrono-LICENSE.txt`. A separate native inspection executable instantiates its actual rigid bodies, closed suspension mechanisms, wheel colliders and shafts without stepping a mission.

The [recorded audit](validation/viper-model-audit.json) includes native output, source/mesh/library/executable hashes, hardware facts with page references, and an explicit assumption ledger. The native model has 21 rigid bodies and 28 links. Positive masses, principal inertias and inertia triangle inequalities pass; four wheels are present. These are structural checks, not experimental validation.

| Quantity | Dated NASA hardware reference | Executed upstream model |
| --- | --- | --- |
| Roving/system mass | 447 kg | **434.921114 kg**, 2.7022% lower |
| Upstream mass getter | Not applicable | 430.921114 kg; excludes four 1 kg connector bodies |
| Steering half-range | 50° | **30°** clamp |
| Flight inertia and COM distribution | Not supplied by this briefing | Estimated from mesh volumes and assumed part densities |
| Suspension control | Individual downforce and IMU feedback | Declared model springs and position commands; flight loops unvalidated |
| Motor torque/current response | Briefing gives controller current limits, not full maps | Source default 300 N·m stall and π rad/s no-load speed; uncalibrated |

The native collider's maximum radius is 0.250306 m and full lateral extent is 0.298045 m, including protrusions. These are mesh bounds, not independently measured flight-wheel dimensions. In particular, that lateral extent must not replace the separate TREC fixture's published 0.2 m width. The ground-test robot, flight hardware and upstream software model remain distinct identities.

A separate native geometry executable recomputes mass properties from the original wheel collider before and after the left-side π rotation. Right-wheel COGs agree with the instantiated bodies to floating-point precision. Both left-wheel COGs differ by **0.027591727 m** from the transformed-collider calculation, failing a declared 1 μm internal consistency tolerance. The source assigns the left mesh transform after its constructor computes mass properties, which explains this mismatch. This is a verified consistency issue inside the approximate model, not a measured flight-COM discrepancy. The current [audit record](validation/viper-model-audit.json) retains both native calculations, offsets and exact source/binary hashes. Upstream code is unchanged; correction and joint/shaft-frame reconciliation remain pending.

The complete extended source/calculation audit is retained in `data/runtime/viper-model-audit-v2.zip`, 14,571 bytes, SHA-256 `384a87f809bd18852dc47c147869a811641066618ed22a0281c66961727b0ff8`. The earlier assembly-only record remains separate from this added failed consistency check.

## Separate mass-frame correction

The **Clavius mechanical frame repair v1** corrects that inconsistency in a private copy of the two pinned upstream source files. Its [reviewable patch](../workers/chrono/viper-adapted/model.patch) retains the original BSD license and uses the separate `chrono::clavius_viper` namespace. The original checkout, shared libraries and earlier failed evidence remain unchanged.

The left-wheel center of mass and principal frame rotate with the collider before bodies/joints are constructed. Shaft directions are derived in each body's actual COM frame from negative CAD-reference Y, preserving the existing negative-shaft-load forward convention. The four existing connector bodies are stored in the already-declared member array and included by `GetRoverMass`; no mass or part inertia is changed. The corrected getter now matches the 434.921114 kg system sum.

[Fourteen native validation cases](validation/viper-frame-repair.json) cover original/repaired static and torque cases in identity and tilted world poses, two deliberate wrong-axis controls, and four repaired Earth/lunar rigid-floor repeats. Centers of mass and full reference-frame inertia tensors agree with independently transformed original colliders to numerical precision. All repaired frame/shaft/joint checks pass. Deliberately restoring the old shaft axes reverses the two left wheels under the same torque input; the validator detects and rejects both cases.

All four repaired rigid-floor runs and their two half-step comparisons pass the unchanged component protocol. Half-step final-position differences are 3.77 μm and 14.64 μm for Earth/lunar gravity. These remain numerical differences on a synthetic rigid floor, not physical error bounds. The original approximate total mass, 30° steering limit, spring and motor properties remain unchanged in this isolated correction. It is not yet an active NASA app robot or a calibrated flight model.

The separate runtime identity is `1f18c4a4faeb68faac1d849e14c0c2b5006a85619044af30c3322b4a960ac055`; the original Chrono reference identity remains unchanged. The 1,103,455-byte archive is `data/runtime/viper-frame-repair-v1.zip`, SHA-256 `6a66de27713a31384b481234a05109664cce0faef27ef6c6da95490b6fc19345`. It contains the patch, generated source, original protocols, all native results/traces, invocation identities and the evidence index. A subsequent stricter evidence verifier rescored all fourteen results identically; both source versions are identified explicitly.

```sh
.venv/bin/python -m scripts.build_viper_adapted
.venv/bin/python -m scripts.validate_viper_adapted --output data/runtime/new-viper-frame-check
.venv/bin/python -m scripts.publish_viper_repair data/runtime/new-viper-frame-check
```

Page 2's 5,420 W·h capacity applies at start of life and 0°C. It does not provide a discharge curve, motor efficiency or thermal network. The hardware's looped heat pipes, switched radiators and warm-box design also cannot be represented as a calibrated battery prediction by copying the app's single-node screening defaults.

## Acceptance still required

Before VIPER becomes an active curated dynamics option, reconcile the remaining hardware geometry, mass distribution, joint ranges and actual actuation; validate steering and suspension behavior; and run matched wheel/full-rover cases with numerical refinement. The separate frame correction above establishes internal consistency, not measured flight properties. Retain explicit assumptions wherever public measured values are unavailable. Do not rescale every body merely to match total mass and call its tensors measured. Do not use speed constraints as demonstrated motor capability.

The TREC reference tests drawbar traction under Earth gravity; the MGRU3 source points describe different full-rover tests. Neither directly validates a 447 kg flight rover on the Moon. CPU SCM development is also separate from the paper's GPU continuum/SPH engine and from the app's MuJoCo/Gazebo rigid contact. Lunar soil, wheel-scale hazards, power and thermal prediction remain unresolved.

The paper's separate modified Chrono 8 implementation scales seventeen bodies using a 440 kg denominator. That must not be applied blindly to this unmodified 9.0.1 assembly, whose actual system mass and helper accounting differ. The inspected author source is `demos/viper_real_slope/demo_ROBOT_Viper_RealSlope.cpp` at the retained supplementary commit, SHA-256 `75b02913f94eff699412a0b3f970302e6b56a970b485e9a6e3c3591e2f315cec`. It has not been executed here as the paper's GPU engine.

## Executed assembled-model component probe

[Four native rigid-floor cases](validation/viper-rigid-probe.json) execute the original articulated assembly at **9.81 and 1.62 m/s²**, with **1 ms and 0.5 ms** steps. The synthetic floor uses declared SMC friction 0.7 and Young modulus 2e7 Pa. An ideal wheel-speed driver waits 3 s, ramps for 1 s to 0.4 rad/s, then continues through 20 s. The last 10 s is assessed against the fixed `planner/validation/viper_rigid_protocol.json` criteria.

All four speed, load-balance, vertical-settling, lateral-drift and quaternion checks pass. The two refinement checks pass the declared speed, final-position and normal-load targets. These tests verify the assembled approximation's bounded mechanical/numerical behavior; they do not demonstrate actual flight motors, steering, terrain traversability or battery performance.

| Gravity / step | Average forward speed | Average normal force | Nominal weight |
| --- | --- | --- | --- |
| Earth / 1 ms | 0.101872 m/s | 4,269.705 N | 4,266.576 N |
| Earth / 0.5 ms | 0.101860 m/s | 4,264.412 N | 4,266.576 N |
| Lunar / 1 ms | 0.101918 m/s | 702.780 N | 704.572 N |
| Lunar / 0.5 ms | 0.101918 m/s | 704.969 N | 704.572 N |

Half-step final-position changes are **7.04 μm** and **17.40 μm** for Earth/lunar gravity. These are numerical differences on one ideal rigid-floor drive, not physical error bounds. No steering or terrain/soil case is covered.

The first lunar half-step attempt hit a **300 s wall-clock limit** at a fully recorded native time of 14.8905 s; it remains in `data/runtime/viper-rigid-probe-v1.zip`, SHA-256 `a3d6b35d1c3b5204df47c1d4e72bc03ac5fe491d84f48e2b02c5461c0ef69be9`. Its missing launch/exit metadata is explicitly identified rather than reconstructed as measured. A fresh identical native case completed in 45.40 s with a 900 s allowance; the three complete cases were independently rescored and retained. No physical/numerical criterion changed. The successful evidence archive is `data/runtime/viper-rigid-probe-v2.zip`, 1,049,502 bytes, SHA-256 `0e593777438befa7403fdbfef21cc18dfab55f0970bea26adecf0ca406011f61`. The record identifies where the executable hash was first retained; it is not retroactively claimed at the earlier launches.

Future runs now preserve source/input hashes and launch metadata before starting, including timeout status. The full probe is available as `npm run validate:viper-rigid -- --output data/runtime/new-viper-rigid-probe`. These are offline development tools; the app's current active robot remains R1.

The official JPL [Perseverance visualization URDF and Open Source Rover audit](validation/nasa-robot-source-audit.json) remains relevant for selecting a second curated candidate. Perseverance's zero masses/tensors and absent colliders preclude immediate physical use. The Open Source Rover is educational ground hardware, not flight equipment. A second model has not yet been accepted.

## Reproduce the audit

With the pinned Chrono checkout, private build dependencies and native reference libraries present:

```sh
.venv/bin/python -m scripts.audit_viper_reference --output data/runtime/new-viper-model-audit
```

The output directory must be fresh. This builds the isolated audit executable, verifies the pinned runtime and NASA PDF, and retains native JSON, logs and exact source identities. It does not alter or activate the app's rover dynamics.

## Interactive VIPER and recorded terrain traverses

The browser's **Rover drive** uses the eight original Project Chrono visual OBJ files, arranged as a chassis plus four upper arms, lower arms, uprights and wheels. Four-wheel steering and rotation in manual mode use ideal rolling kinematics and terrain-derived attitude. The mode supports forward/reverse, curved paths and accelerated visualization. Geometry provenance, retained BSD license and the dated hardware reference are provided alongside the model.

**Recorded dynamics** plays independently simulated 20 s rigid-contact traverses at Connecting Ridge and Shackleton rim. Each uses the separately frame-repaired source, a 20 m square from the same nominal 5 m mesh as the browser, lunar gravity, 1 ms solver steps and an ideal straight-ahead command after settling. The 17 visible body reference transforms are recorded at 20 Hz in ENU. Final east displacement was 1.530 m and 1.840 m respectively. Mean vertical wheel support over the last 10 s was 1.0344 and 1.0277 times model weight. Separate executions reproduced both files byte-for-byte. Replay keeps the source model's 434.92 kg mass, uncalibrated rigid contact, passive spring assumptions and unexercised 30° steering limit. Its trajectory does not establish flight performance. The mission and energy solver's built-in rover remains R1.

To reproduce on the prepared Chrono runtime, configure `workers/chrono/site-drive` with `Chrono_DIR=data/runtime/chrono-build/cmake`, `ADAPTED_SOURCE=data/runtime/viper-adapted-source` and `ADAPTED_LIBRARY=data/runtime/viper-adapted-build/libclavius_viper_repaired.a` (use absolute paths). Build in `data/runtime/site-drive-build`, then run `.venv/bin/python -m scripts.record_viper_drives`. The publisher verifies the adapted runtime, terrain hash, forward travel, support, frame count and normalized body rotations. [Replay provenance](../public/data/drive/replays.json)

### Crab steering on the two measured site meshes

The manual model now supports coordinated turns and crab translation. In a turn, each wheel is tangent to its own circle around the common turn center. The innermost wheel reaches ±50° at full steering input. In crab mode all four wheel planes stay parallel and the heading stays fixed. Both modes assume instantaneous steering and ideal rolling. The ±50° bound and independent steering come from pages 4–5 of the [dated NASA hardware briefing](https://ntrs.nasa.gov/citations/20240013903). The selected 25° demo angle is a Clavius scenario.

The native crab experiment uses the same nominal DEM, 434.92 kg assembly, 1.62 m/s² gravity, ideal speed motors, solver, contact and clock as the straight reference. During seconds 1–3, the front steering motors ramp to +25° and the reversed rear motor frames ramp to −25°. The wheels then drive forward with all four planes pointing left. No new flight actuation or soil parameters enter this comparison.

From seconds 4–20, the checks require every measured axle heading to stay within 2° of 25° relative to the chassis, chassis yaw to stay within 15° of its heading at second 4, and northward travel to exceed the straight run by at least 0.30 m. The headings are derived from the recorded body orientations, independent of steering commands. These are software control and repeatability checks.

| Site | Additional northward travel, 4–20 s | Maximum chassis yaw excursion | Maximum wheel-plane error |
| --- | ---: | ---: | ---: |
| Connecting Ridge | 0.695 m | 0.239° | <0.000003° |
| Shackleton rim | 0.652 m | 0.454° | <0.000003° |

In the drive view, select **Recorded dynamics → 25° crab traverse**. **Compare recorded paths** shows both trajectories on shared east/north axes, with positions in metres at the replay cursor. The steering readout follows the measured front-left axle. The native assembly still has a 30° steering limit, and its ideal positioning motors explain the small wheel-plane residuals. Two executions of each native crab experiment produced byte-identical pose files. Flight controller tracking and lateral soil resistance require hardware data.

### VIPER solar array estimate

The 2021 project information package places the arrays on the port, starboard and aft faces (section 3.1, p. 8). The November 2024 hardware briefing gives 320 W per array and approximately 450 W with a corner toward the Sun (pp. 2–3). The February 2025 technical briefing confirms both ratings (p. 46, PDF SHA-256 `7b1c8f53c0ecacec8815d343b58210bff7519b291da8f6a6ea483277e35aae35`). Clavius uses the later rating. The earlier package lists a provisional total. [2021 layout](https://science.nasa.gov/wp-content/uploads/2024/08/viper-pip-final.pdf) · [2024 hardware reference](https://ntrs.nasa.gov/citations/20240013903) · [2025 specifications](https://assets.science.nasa.gov/content/dam/science/psd/lunar-science/documents/2025-02-13_VIPER_Updated_Technical_Briefing_Presentation-Shared.pdf)

Clavius assumes 320 W under normal illumination at one astronomical unit. The three face normals are orthogonal to the chassis sides. For each face, multiply 320 W by the positive part of its normal dotted with the direction to the Sun, the visible solar disk fraction, and the inverse-square distance factor relative to 1 au. Under full illumination at 1 au with a horizontal Sun, this gives 320 W for one face and 452.55 W when the Sun bisects the port/aft corner. The published corner figure is rounded. The body axes, sources, hashes and assumptions are in the [robot model record](../public/robots/viper/source.json).

In manual drive the solar calculation uses the terrain-aligned chassis attitude captured when the live observation was requested. In recorded dynamics it uses the interpolated native chassis orientation. The viewer integrates gross generation in Wh through the replay cursor using trapezoids over the 20 Hz body records, with one-second terrain visibility and Sun samples held within each interval. Scrubbing and playback speed preserve simulated time. Custom replay epochs compute a complete sample series from the verified pose file on the service. The three packaged epochs use the same sampling routine.

The [sampling comparison](validation/viper-array-sampling.json) recomputes geometry and terrain visibility at every native frame for both maneuvers at both sites and all three packaged epochs. All twelve cases met the 0.02 Wh integrated and 15 W pointwise limits. The largest discrepancies were 0.00406 Wh over 20 s and 2.50 W at a single frame (rounded upward). Run `OPENBLAS_NUM_THREADS=1 .venv/bin/python -m scripts.validate_viper_array` to reproduce the evidence. The browser tests independently recover the coarse energy totals from the shipped attitude traces.

All panels share the 0.5 m observer horizon. The model omits panel-specific shading by terrain or rover hardware, dust, temperature response, electrical regulation and bus loads. It estimates gross array output. Battery charge, discharge and endurance still require their own electrical and thermal evidence.

### Parked VIPER power budget

The **Parked power** dialog holds a rover at one location for 1–48 hours. The heading is clockwise from the fixed site's north. Pitch and roll align the chassis with central terrain differences over ±5 m. The three-panel array model samples dated sunlight at 5-minute intervals. The user selects the heading, constant electrical load, initial state of charge and separate charge/discharge efficiencies. The default load of 150 W is a demonstration assumption. The hardware reference supplies 5,420 Wh at beginning of life and 0 °C. [Battery source record](../public/robots/viper/battery.json)

Generation serves the bus first. A surplus charges the battery until full, with any excess recorded as unused solar energy. During a deficit the battery supplies the bus subject to its discharge efficiency and the remaining energy. Clavius integrates a linear solar-power segment between adjacent samples, splitting at crossings of the specified load. The first unmet demand is timed within a segment. Later sunlight can restore stored energy in the scenario. The model assumes fixed capacity, continued demand and a functioning charger throughout. Actual low-voltage shutdown, restart, temperature-dependent capacity, component loads and thermal control still require validation.

For the 48 hours starting 21 January 2028 at noon UTC, a rover parked at the Shackleton rim origin facing site east, with 75% initial charge, a constant 150 W load and ideal conversion, first leaves demand unmet at 34.40 h. The battery later recharges and finishes with about 1,759 Wh. At Connecting Ridge, the same inputs serve the load throughout. Daylight differences in these calculations come from the site-specific ephemeris and terrain horizons.

The [stationary sampling check](validation/viper-parked-sampling.json) compares 300 s and 60 s solar sampling over 48 hours at both site origins, for three start dates and headings of 0°, 90° and 225°. All 18 comparisons met the 54.2 Wh ledger-difference limit (1% of reference capacity) and the 300 s first-unmet-time limit. The maximum final-charge difference was 0.047 Wh and the maximum first-unmet-time difference was 1.06 s. These results measure numerical sensitivity for the tested cases. Terrain horizon and electrical hardware accuracy require separate evidence. Reproduce with `node scripts/validate_parked_power.mjs`.

### Wheel measurements in recorded drives

The four straight/crab replays include per-wheel CAD hub positions and velocities, absolute angular velocities, CAD axle directions and net native contact forces sampled by the recorder at the end of each 1 ms solver step. The wheel file served to the browser contains trailing 50 ms reductions. Wheel order is left front, right front, left rear, right rear. Frame zero has no completed window.

The calculation projects native contact force onto the upward normal of the PGDA78 triangle below the hub and averages its compressive component over all 50 steps. The loaded percentage counts steps above 1 N. On those steps the forward tangent is the normalized cross product of the CAD axle and terrain normal. The lateral tangent points to the wheel's left. The estimator projects hub velocity into those two axes and multiplies absolute angular speed about the axle (signed component) by the assumed 0.25 m nominal radius. Signed rolling slip is `1 − mean forward hub speed / mean rim speed`. The viewer omits slip for unloaded windows and absolute mean rim speed at or below 0.02 m/s. Negative slip means the hub traveled faster than the nominal rim speed along the rolling direction.

The triangle under a wheel center approximates its local contact plane. Multiple grouser contacts, slope changes across the wheel footprint and effective rolling radius can all affect the result. The surface is rigid and the motor enforces a speed command. These measurements do not validate lunar soil slip, sinkage, electrical motor load or VIPER flight performance.

Regenerate the replay and wheel files with `python -m scripts.record_viper_drives` in the prepared simulation environment. At 4–20 s the validator integrates world-frame hub and angular velocities over each 50 ms window and compares them against independently sampled position and quaternion changes. Acceptance limits are 1 mm and 0.01 rad per interval. Every recorded hub position at a window endpoint must match its pose frame exactly. The four records contain the numerical residuals and digests of the native raw states, pose and wheel files. [Replay catalogue](../public/data/drive/replays.json)

### VIPER sensitivity to terrain reconstruction

Both sites now have straight and 25° crab drives on PGDA78 clone 001 in addition to the nominal runs. The solver, model parameters, commands, triangle construction and 1 ms timestep are identical across each pair. The rover starts at the same horizontal position with the same clearance above its local ground. The terrain and vehicle retain the nominal ENU origin. Each run recomputes wheel contact, attitude and suspension motion. The comparison shows signed east and north displacement between 4 and 20 s and per-wheel mean compressive load over the same interval.

Relative to the nominal result, the horizontal displacement vector changed by 14.9 cm (straight) and 12.9 cm (crab) at Connecting Ridge, and by 6.6 cm and 4.6 cm at Shackleton rim. The largest difference in mean load on any one wheel among the four pairs was 171 N, on the Shackleton straight traverse. These are paired outcomes under the assumed rigid contact and motor control. A single statistical reconstruction cannot establish a probability, total terrain error, or lunar soil performance. [Numerical results and source identities](../public/data/drive/viper-terrain-comparison.json)

All four cloned native runs were repeated with identical pose and raw wheel-state hashes. The clone sunlight packages also passed twelve 20 Hz comparisons for driving array power (largest instantaneous difference 3.10 W, rounded up) and eighteen one-minute comparisons for parked energy accounting (largest absolute energy residual below 0.37 Wh). These checks vary the sampling cadence while retaining the same terrain, illumination model and hardware assumptions. [Drive sampling](validation/viper-array-sampling-pgda78-0001.json) · [Parked sampling](validation/viper-parked-sampling-pgda78-0001.json)
