# Native Chrono SCM reference worker

This isolated C++ worker investigates the rigid-soil discrepancy in `docs/MOBILITY_VALIDATION.md`. It uses the upstream Project Chrono **9.0.1** CPU Soil Contact Model, pinned to commit `2617649bf687456328a122b63dc0bb64df91394a`. Upstream code remains unchanged. The BSD-3-Clause license is retained under `third_party/`.

The first family is the published NASA Glenn TREC **single-wheel laboratory rig**, not a flight VIPER robot. Its wheel dimensions, grouser geometry, 17.5 kg supported mass and 0.2 m/s imposed translation match the retained source conditions. Envelope-cylinder inertia and guides remain declared approximations. The soil model implements semi-empirical pressure/sinkage and shear-displacement behavior. Its parameters are declared scenarios until bounded calibration/holdout checks establish a more limited claim.

Do not call this the paper's GPU continuum/SPH engine. Changing gravity while retaining fitted Earth parameters does not establish lunar calibration. MuJoCo, Gazebo/DART and Chrono/SCM identities remain separate.

`reference.cpp` accepts only an allowlisted numeric/boolean JSON configuration and emits native force, motion, sinkage and motor-reaction telemetry as CSV. It has no GUI, arbitrary script upload or network dependency. The Python orchestrator must preserve each input, binary/library identity, source snapshots, exit status and incomplete evidence. A completed process is not a passed physical assessment.

The independent rig follows the upstream `demo_VEH_SCMTerrain_RigidTire.cpp` and `demo_ROBOT_Viper_SCM.cpp` API patterns for collision geometry, moving patches and terrain force extraction. Those examples use demonstration material values, not calibrated lunar or NASA GRC-3 properties.

## Verified local build

The Apple Silicon build uses Apple Clang 21.0.0, CMake 3.31 and Eigen 3.4. The private CMake/Eigen prefix is `data/runtime/chrono-deps`, with exact conda-forge package URLs/SHA-256 locks in `build-dependencies-osx-arm64.lock`. Upstream lives at `data/raw/robots/chrono`; its sparse checkout needs `src`, `cmake`, both `template_project*` directories and `data/robot/viper`. No global dependency installation or Anaconda defaults terms acceptance is required.

```sh
/opt/miniconda3/bin/conda create --prefix "$PWD/data/runtime/chrono-deps" --override-channels -c conda-forge cmake=3.31 eigen=3.4 --no-default-packages -y
npm run chrono:build
```

For exact dependency reproduction, use the checked-in explicit lock with conda's `--file` option instead of solving package versions again. The core build enables Vehicle and native robot models, disables Vehicle Models, demos, tests, OpenMP and TBB, and retains Release shared libraries in `data/runtime/chrono-build`. The isolated adapter links those actual libraries. Upstream's CMake package may warn that the disabled `ChronoModels_vehicle` is absent; the required core, Vehicle and robot libraries are built and linked. No upstream source modification suppresses that warning.

`data/runtime/chrono-runtime.json` hashes the executable, actual libraries, source, configuration, compiler and dependency lock. Each case verifies the identity before execution. This CPU build is single-threaded and uses implicit linearized Euler with MINRES, 200 maximum iterations and 1e-10 tolerance.

## Frozen development campaign

`planner/validation/scm_protocol.json` fixes four friction-angle/shear-length candidates, ten training points and eight held-out points. Repeated nominal slip groups remain in one split. Stiffness, exponent, cohesion, damping and bulldozing are declared assumptions, not measured GRC-3 values. Selection freezes before holdout simulation; the holdout cannot tune candidates. A held-out subset of one Earth campaign is not an independent new experiment.

```sh
npm run validate:scm -- --output data/runtime/scm/new-development-campaign
/opt/miniconda3/bin/python -m scripts.render_scm_validation data/runtime/scm/new-development-campaign --output public/data/scm-validation.png
.venv/bin/python -m scripts.publish_scm_validation data/runtime/scm/new-development-campaign
npm run test:mobility
```

The renderer uses Matplotlib (3.10.9 in the local analysis environment). The publisher checks complete splits, native telemetry, hashes, selection order, original points and separate time/grid refinements. It retains failed development targets. Each campaign requires a fresh directory and takes tens of minutes on this Mac. Raw 20-second traces and all inputs remain in ignored runtime storage and the evidence archive. Publishing a report does not activate a new mission dynamics backend.

## VIPER candidate audit

`model-audit/` builds a separate native executable to inventory the unmodified upstream VIPER bodies and shafts. It does not change the wheel-reference executable or run a rover mission. `npm run audit:viper -- --output data/runtime/new-viper-audit` records source and mesh hashes and compares to a pinned dated NASA hardware briefing. See `docs/NASA_ROBOT_MODELS.md` for measured facts, model assumptions and unresolved differences.

`rover-probe/` additionally executes the assembled original model on a synthetic rigid floor. `npm run validate:viper-rigid -- --output data/runtime/new-viper-rigid-probe` runs Earth/lunar gravity at two steps with fixed component gates, source/mesh/binary hashes and per-case launch/exit/timeout records. The four retained component cases pass; the first lunar fine-step wall timeout and its unchanged-model retry are both archived. Ideal speed actuation, approximate flight mechanics and declared rigid contact do not establish flight capability or lunar soil validation. No NASA app robot is enabled by these probes.

The extended native audit independently recomputes wheel mass properties after the source's left-side collider rotation. It finds 27.5917 mm left-wheel COG-frame discrepancies while right wheels agree. A future adaptation must reconcile the COG and principal-axis frames before joint construction, and check drive-shaft axes in those resolved frames; changing a COG after constraints are initialized is not a sufficient correction. Keep the original source/libraries and failed evidence intact. Any adapted model needs a separate source/patch/build identity and new mechanics tests; it must retain unknown flight properties as explicit assumptions.

`viper-adapted/` now provides that separate mechanical correction. Its pinned patch rotates the left mass frames, derives shaft directions in resolved COM coordinates, and fixes the getter's omission of connector masses. `scripts/build_viper_adapted.py` copies/patches only two files under ignored runtime storage and builds a namespaced static model, baseline/repaired comparators and a repaired copy of the original floor fixture. It does not rebuild or replace core Chrono libraries. Fourteen native checks pass the correction protocol, including rejection of intentional wrong-axis controls; see `docs/NASA_ROBOT_MODELS.md`. Known 447 kg / 50° flight-reference differences and uncalibrated hardware/soil behavior remain pending.
