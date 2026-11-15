# Deformable soil development reference

Clavius now executes Project Chrono **9.0.1 CPU SCM** as an isolated native laboratory reference. It adds plastic sinkage and accumulated shear behavior to the earlier rigid-contact discrepancy study. It is separate from the app's MuJoCo/Gazebo mission dynamics and from the source paper's GPU continuum/SPH implementation. No calibrated lunar regolith or active flight-rover dynamics is implied.

## Source, model and runtime

The observations and fixture conditions are the same [NASA Glenn TREC GRC-3 published plot points](MOBILITY_VALIDATION.md), pinned in `public/data/mobility-reference-manifest.json`. The fixture uses the published 0.25 m outer radius, 0.2 m width, 24 grousers of 0.025 m height/0.005 m tangential width, 17.5 kg supported mass, 0.2 m/s translation and **Earth gravity 9.81 m/s²**. The wheel envelope-cylinder inertia and guide implementation are approximations. A full VIPER model, its collider width and its flight mass must not be substituted for this independent wheel rig.

Upstream [Project Chrono](https://github.com/projectchrono/chrono) is pinned to commit `2617649bf687456328a122b63dc0bb64df91394a`, with unchanged source and its BSD-3-Clause license retained. The local runtime identity is `b6893013760304c5d046a33fc9c27068e070eade0584278f97fb2865c5bae9cf`. The inventory includes actual executable/native-library hashes, compiler, build configuration and private dependency lock. [Build and execution instructions](../workers/chrono/README.md).

The C++ adapter uses native collision ray queries and SCM body forces. Translation and wheel angle are imposed by ideal constraints while vertical motion remains free. Longitudinal soil force is drawbar traction at constant translation; the opposite carriage reaction is retained independently. Rotation-motor reaction is a diagnostic, not electrical power or a measured motor-current model. Implicit linearized Euler/MINRES uses 200 maximum iterations and 1e-10 tolerance. Each case runs 20 s; the final 10 s is time-averaged.

SCM's Bekker-type pressure/sinkage and Janosi-type shear model is semi-empirical. Its 1 cm base grid discretizes the synthetic soil model; it is not measured lunar resolution. Plastic deformation and shear history do not establish the full gravity-dependent granular behavior studied by the paper's different GPU continuum model. Grousered wheels, large slip and deep sinkage particularly challenge the applicability of this approximation.

## Frozen protocol

`planner/validation/scm_protocol.json` was written before the first native preflight. Its SHA-256 is `ce7366e61fbba03d88002622361ec769205ca89e987785ef68eecb6f84fdbf4c`.

Four parameter sets combine friction angles **30°/42°** with shear lengths **0.015/0.05 m**. Other material values are fixed declared assumptions: Bekker Kφ 200,000, Kc 0, exponent 1.1, cohesion 0, elastic coefficient 40,000,000 and damping 30,000 in the native SI convention; bulldozing is disabled. These are not measured GRC-3 pressure/sinkage parameters. Traction observations alone cannot uniquely determine every stiffness, shear and density parameter. The [material-source review](validation/scm-material-source-review.json) rejects substituting unrelated JSC-1A bevameter values into this GRC-3 case.

Ten training points use original source indices **0, 4, 7, 8, 9, 11, 12, 13, 16, 17**. Eight held-out points use **1, 2, 3, 5, 6, 10, 14, 15**. All repeated observations in a nominal slip group stay together. Original coordinates and negative values remain unchanged. Candidates are selected only by training RMS discrepancy after passing the rig controls; ties use candidate index. The frozen selection, training evidence hash and timestamp are written before any holdout simulation starts. Campaign input/source changes abort execution.

Development targets are speed error ≤0.002 m/s, relative angular-speed error ≤1%, relative normal-load error ≤5% and absolute average vertical speed ≤0.002 m/s. Held-out traction targets are ≤5° RMS and ≤10° maximum discrepancy. At original source indices 1, 7 and 16, separate half-time-step (**0.5 ms**) and half-grid-spacing (**5 mm**) repeats must pass controls and change mean traction by ≤1°. Time and grid are refined separately; no untested joint-refinement claim is made. These thresholds are development gates, not experimental error bars or mission accuracy bounds.

Held-out points come from the same published Earth experiment. They are not an independent new campaign, full-rover validation or lunar measurement. Passing a fit would not identify unique soil physics, certify variable loads/steering, or validate battery/thermal response.

## Retained preflight

The first native preflight at source index 4 passed all four rig controls. Mean commanded/actual translation was 0.2 m/s, angular speed 1.000356 rad/s, normal force 171.4565 N against 171.675 N nominal, and traction slope **8.3830°**. The published point is approximately 20.1208°. The model's average center sinkage was 0.05852 m, not a measured NASA sinkage value.

The original trace at `data/runtime/scm/preflight-v1/trace.csv` and its independently repeated campaign case at `candidate-0/training-04/trace.csv` have the same SHA-256: `b084a1c0e88502b515b001a6be779ce593c2db3490f37d6b2c375aa150637702`. This is one repeated native case, not a repeated full campaign or external physical validation.

## Campaign assessment

The complete campaign executes **54 cases**: four candidates × ten training points, eight held-out points and six separate refinements. Candidate **0**, friction angle 30° / shear length 0.015 m, was frozen using training data alone at 21:26:09 UTC on 15 November 2026. Its training RMS discrepancy is 7.0317°. No holdout result selected or tuned it. The source paper's GRC-3 friction-angle scenarios are 37.8°/42°/47.8° at different densities; the selected effective 30° input is not a measured bulk material property.

| Assessment | Result |
| --- | --- |
| All 54 rig speed, angular-speed, load and settling checks | Passed |
| Held-out RMS discrepancy, eight points | **9.6846°**, target ≤5° failed |
| Held-out maximum absolute discrepancy | **15.4930°**, target ≤10° failed |
| Held-out mean signed discrepancy | −8.3360° |
| Rigid baseline on exactly the same eight points | 15.6027° RMS, 25.0372° maximum |
| Separate time/grid refinement gates | **Two of six failed** |
| Lunar calibration / active app dynamics | **Not established / not enabled** |

The lower base-discretization discrepancy than the rigid baseline does not establish convergence or physical validity. In particular, the model underpredicts low-slip traction substantially. The held-out observations are from the same Earth campaign, rather than a new independent experiment. No confidence interval is inferred from these eight points.

| Original source index / nominal slip | Half-step traction change | Half-grid traction change |
| --- | --- | --- |
| 1 / 5% | −0.097925°, passed | −0.349831°, passed |
| 7 / 40% | **+1.052307°, failed** | **+1.149842°, failed** |
| 16 / 80% | −0.039586°, passed | −0.006316°, passed |

The strict 1° thresholds remain unchanged. These are checks at three specific slips, not a global discretization error bound. No combined time-and-grid refinement was executed.

The verifier rescored every original native trace and checked all configurations, source coordinates, hashes, split membership, training-only selection, freeze ordering and unchanged selection bytes. [Published report](../public/data/scm-validation.json), [scientific figure](../public/data/scm-validation.png) and [retained reproduction checks](validation/scm-reproduction.json). The report is 53,233 bytes with SHA-256 `5b608ab2118bc5a57911358227ef8479103ae452327ce44a7014e3daffc7c3b9`. Both dataset manifests pin the same report under `scm_validation`, with an offline development role. Existing terrain, SPICE and mission-response inputs remain unchanged.

All native inputs/traces, original point/protocol/runtime snapshots, selection, candidate scores and the evidence index are retained in `data/runtime/scm/trec-development-v1.zip`, **10,441,865 bytes**, SHA-256 `f45023cda6e75cc0e043140749f18505074d44f0a81a293d31968119323ff6b8`. The published figure records the failed numerical targets directly. The original rigid-contact failure remains preserved separately.

Open **Simulation → Data & models → Review wheel comparison & limits**. The view presents the eight-point comparison, original rigid baseline, all held-out rows, and separate control/target statuses for six refinements. The SCM model remains an offline development fixture; no new mission engine or NASA flight robot is enabled. Matched independent normal/shear measurements, better material identification, wider convergence and full-rover validation remain required.

## Implementation and browser verification

The simulation suite passed **159 Python tests**, the frontend **13 tests**, and the production build. Interface fixtures passed 8 schemas, 7 messages and four intentional invalid rejections. These implementation checks do not override failed physical/numerical gates. [Verification record](validation/scm-implementation-checks.json).

[Browser acceptance](validation/scm-browser.json) records 1440 × 900 desktop and 390 × 844 mobile views, loaded scientific figures, all eight held-out rows and six refinement rows, no document/dialog horizontal overflow, and local table scrollers. Both failed refinement rows explicitly display **Not met** beside **Passed** rig controls. The downloaded 53,233-byte report is byte-identical to the pinned file. Missing or mismatched evidence remains rejected rather than displayed as valid.

Browser review also exposed Vite's broad `**/data/**` ignore rule hiding newly created public reports. The rule now targets the project's private runtime data only; a temporary new public asset was served correctly without a restart. This preserves the native-data watch exclusion while allowing published source/report assets to register. No report hash or physics threshold was relaxed.
