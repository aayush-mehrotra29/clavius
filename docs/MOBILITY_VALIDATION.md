# Published wheel traction comparison

Clavius now has a source-pinned NASA Glenn wheel-test reference and an executed native discrepancy benchmark. This follows the user's priority: documented robots and defensible environment/physics behavior take precedence over broad importing. It does **not** establish lunar soil calibration or enable a flight-certified VIPER model.

Open **Simulation → Data & models → Review wheel comparison & limits**. The dialog separates rig-control checks, numerical refinement and agreement with published experimental points. The [published comparison](../public/data/mobility-validation.json), [source derivative](../public/data/mobility-reference.json), [source manifest](../public/data/mobility-reference-manifest.json) and [figure](../public/data/mobility-validation.png) are available separately. The global and simulation dataset manifests reference the same hashes.

## Source and experimental conditions

[Hu et al., NASA NTRS 20250001809](https://ntrs.nasa.gov/citations/20250001809), *A study demonstrating that using gravitational offset to prepare extraterrestrial mobility missions is misleading*, describes NASA Glenn SLOPE laboratory TREC and MGRU3 testing. The cached PDF is the 15 February 2025 preprint; NTRS records publication on 31 March 2025. The author repository is [crm_sim_nasa_exp_scripts](https://github.com/sjtumsd/crm_sim_nasa_exp_scripts), pinned at commit `54f74dc514b394d3a02e15d7508b1bf27a88d1a6`.

`scripts/prepare_mobility_reference.py` reads the three `numpy.array` literal lists from the original `images/figure4b.py` using Python's AST without executing it. It preserves all 18 TREC GRC-3, 6 MGRU3 2021 GRC-1 and 7 MGRU3 2022 GRC-1 points, including repeats, small negative values and original precision. Slip percentages convert to fractions exactly once. These are author-distributed **plotting coordinates**, not raw rig telemetry; sample counts and per-point uncertainties are not supplied. No error bars are invented.

The single-wheel VV-mode conditions in the paper's page 10/Figure 5 and source definition are outer radius **0.25 m**, width **0.2 m**, **24** grousers with **0.025 m** height and **0.005 m** tangential width, normal-loaded mass **17.5 kg**, imposed translation **0.2 m/s** and Earth gravity **9.81 m/s²**. Driving slip is `s = 1 − v/(ωR)`. Traction slope is `atan(drawbar pull / normal load)`, in degrees; it is distinct from terrain slope in the MGRU3 experiments. The wheel and vertically free axle each carry half the normal-loaded mass; the horizontal carriage's weight is supported by its guide.

The study warns that reducing vehicle weight or changing vehicle gravity alone does not reproduce low-gravity soil response. Its GPU continuum/SPH model is a different engine and material treatment. The original reproduction repository requires CUDA and describes a multi-day GPU campaign; it has not been executed on this Mac. We do not describe Clavius MuJoCo/Gazebo contact as that continuum model. The supplementary repository has no top-level license, so its scripts are not redistributed in the public derivative. The source files remain in the private research cache; the manifest records their URLs, commit, hashes and byte counts. Chrono's own BSD license is a separate license.

## Executed independent fixture

`planner/validation/mobility.py` builds an independent MuJoCo 4.0.1 wheel fixture from the published geometry/load/velocity conditions. It uses a cylindrical core and 24 box grousers on a **rigid plane**, declared Coulomb friction **0.7**, the existing rigid-contact family's contact dimensionality and 0.01 s contact time constant. Wheel envelope-cylinder inertia, guide masses and control implementation are declared approximations, not measured NASA flight tensors. Both translational and rotational velocities are imposed through feedback/contact-force compensation; no experimental traction points enter that controller.

The final benchmark executes every one of the 18 published TREC slip coordinates for 20 s and averages the last 10 s. Drawbar pull is independently measured as world longitudinal contact traction minus whole-rig translational inertia. Explicit velocity-servo force/torque remains diagnostic; it is not a measured motor-current or electrical-power channel. Complete sampled time histories and MJCFs are retained.

The policy is `clavius-trec-rigid-contact-discrepancy-v4`. Development targets were fixed separately from experimental values: translation error ≤0.002 m/s, angular-speed relative error ≤1%, average normal-load relative error ≤5%, traction RMS discrepancy ≤5°, maximum discrepancy ≤10°, and half-step mean traction change ≤1° at source indices 1, 7 and 16. These are development targets, not experimental uncertainties or mission-accuracy bounds. No friction or soil parameter was fitted.

Earlier 1 ms/0.5 ms runs failed numerical refinement. Those results remain preserved under `data/runtime/mobility/trec-rigid-v2` through `v4`; a failed first serialization preflight is `v1`. A separate staged time-step study is retained in `work/trec-timestep-study.log`. Refinement led to **31.25 μs** base and **15.625 μs** half-step repeats for the accepted numerical comparison, without changing the geometry, load, friction, experimental data or physical-error targets.

## Current result

| Assessment | Recorded result |
| --- | --- |
| All 18 rig controls/load checks | Passed |
| Maximum average translation error | 8.97 × 10⁻⁸ m/s |
| Maximum average normal-load relative error | 0.344% |
| Half-step mean traction changes, three tested slips | 0.660°, 0.0369°, 0.0183°; target passed at those slips only |
| RMS traction discrepancy, 18 published points | **12.8259°**, target failed |
| Maximum absolute discrepancy | **25.0372°**, target failed |
| Mean signed discrepancy | **+10.9434°** |
| Lunar soil calibration | **Not established** |

The rigid model approaches the Coulomb friction ceiling over much of the positive-slip range, whereas the published GRC-3 wheel data rises more gradually. Rig control and numerical agreement at three slips do not validate a deformable soil response. No measured-terrain mission or hypothetical R1 trajectory was replaced by this laboratory fixture. MGRU3 full-rover points are retained as separate future validation material; they are not treated as TREC observations or a tested full-rover response in this benchmark.

The subsequent [CPU Chrono SCM development campaign](SCM_VALIDATION.md) adds modeled sinkage and shear history with a frozen training/holdout split. Its eight-point held-out RMS is 9.6846° against this rigid model's 15.6027° on exactly those eight points. The separate 18-point rigid RMS above stays unchanged. SCM still fails its physical targets and two numerical-refinement targets; it is not calibrated lunar soil or an active app backend. The dialog exposes both reports and their distinct engine identities.

The complete local evidence archive is `data/runtime/mobility/trec-rigid-v5.zip`, **1,313,598 bytes**, SHA-256 `49ea0fb0bdd0a4fed63fbb3f1362a626b53f046e4bfb8db69565bf9f9b8e453a`. It contains the executed policy/source snapshots, hash-pinned derivative, all 18 MJCFs and traces, three refined traces and the full result/hash index. The published snapshot hash is recorded in both dataset manifests. Earlier preflights are not reported as accepted evidence.

## NASA robot selection

The [source audit](validation/nasa-robot-source-audit.json) pins three official JPL repositories. The Perseverance operations-visualization URDF has **115 zero-mass/zero-inertia links and no colliders**; it must not silently inherit R1 mechanics. Ingenuity is also an operations-visualization source and is not a lunar wheeled robot. The JPL Open Source Rover offers a documented ground hardware/control reference, but its Gazebo Classic model uses estimated mesh inertias and needs physical and kinematic reconciliation before Clavius can claim support.

The immediate physical validation family is therefore **VIPER-related TREC/MGRU3 ground tests**, with a curated rover model to follow. The present app still uses the explicitly hypothetical R1. A NASA visual asset, a reduced-mass prototype, a flight rover and an extrapolated lunar scenario are separate identities. Full suspension/actuator properties, deformable soil coupling, independent holdouts, electrical power and thermal calibration remain required for strong robot-specific predictions. Broad company schematic imports stay a future extension.

The [executed Chrono VIPER candidate audit and four rigid-floor probes](NASA_ROBOT_MODELS.md) now inspect an actual articulated upstream assembly. The component probes pass; mass/steering differences from dated NASA hardware and a verified left-wheel collider/COG-frame inconsistency remain unresolved. Component execution does not enable or certify a NASA flight model.

## Reproduce

Cache the original PDF and pinned author repository at the paths recorded in the manifest, then:

```sh
.venv/bin/python -m scripts.prepare_mobility_reference
npm run validate:mobility -- --output data/runtime/mobility/new-wheel-comparison
python -m scripts.render_mobility_validation data/runtime/mobility/new-wheel-comparison/comparison.json --output public/data/mobility-validation.png
.venv/bin/python -m scripts.publish_mobility_validation data/runtime/mobility/new-wheel-comparison
npm run test:mobility
```

The renderer requires Matplotlib; the executed figure used version 3.10.9. The publisher retains failed physical gates and requires complete original point indices and matching evidence hashes. Each run requires a fresh directory. The native benchmark supports a cancellation callback and preserves completed point checkpoints. It is an offline validation tool, separate from the app's persistent mission worker.

## Implementation verification

The final simulation/orbital/mobility suite passed **145 Python tests**; the frontend passed **9 tests** and the production build. The contract checker passed 8 schemas, 7 messages and four deliberately invalid rejection cases. These checks validate their bounded implementation cases and do not override the failed traction gate. [One independent native repetition](validation/mobility-reproduction.json) reproduced source index 1's MJCF, trace and mean traction exactly; it was not a full campaign repetition. [Browser acceptance](validation/mobility-browser.json) records the 1440 × 900 and 390 × 844 dialog, all 18 expanded rows, no horizontal document/dialog overflow, the table's own mobile scroller, separate physical/numerical statuses and a byte-identical 36,184-byte report download. The final unresolved state is amber and the full-size scientific plot remains accessible.
