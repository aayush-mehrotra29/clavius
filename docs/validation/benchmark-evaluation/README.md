# Clavius benchmark evaluation

Evaluated the public landing page, its expandable benchmark section, Simulation → Data & models → Review wheel comparison & limits, and the hosted Shackleton rim VIPER replay. The public app served the same five scientific reports (wheel, SCM, Horizons, shadows and GMAT) as the tested local copy. The production site serves recorded evidence and replays. Native reruns used the prepared local Mac, with Gazebo in its Linux VM. The public mission workspace reported its live service unavailable. [Production app](https://clavius-space.vercel.app/)

## Strongest demo claim

**On two south-polar image footprints, Clavius classified sunlit and shadowed terrain with 98.2–98.5% balanced accuracy against NASA LROC brightness proxies. Using solar elevation alone scored 50% on both.** The flat-horizon rule called every assessed point sunlit on these dates. Terrain screening located shadows cast by the surrounding landscape.

| Scene and terrain | Matched confident samples | Clavius | Flat horizon | Clavius, any direct light | Published PGDA rendering, positive irradiance |
| --- | ---: | ---: | ---: | ---: | ---: |
| M1188426614, regional | 5,459 | 98.46% | 50.00% | 99.47% | 99.56% |
| M139729686, regional | 9,111 | 98.16% | 50.00% | 97.32% | 98.48% |
| Same image, Connecting Ridge local grid | 1,729 | 98.82% | 50.00% | 98.46% | 98.73% |
| Same image, Shackleton rim local grid | 2,002 | 98.32% | 50.00% | 97.93% | 97.77% |
| M1311409938 | 0 | Unknown | Unknown | Unknown | Unknown |

For the first comparison, both methods use the same Sun position, acquisition epoch, surface locations and observation mask. The positive class is at least half the solar disk above the modeled horizon. With a level horizon at 0°, the equivalent decision is solar elevation ≥0°. Balanced accuracy gives equal weight to recall of confidently bright and confidently dark pixels. Primary labels use observed I/F ≤0.001 for dark and ≥0.005 for lit. The two regional Clavius results ranged from 96.98% to 99.29% over the full set of three previously specified brightness thresholds. The third scene lacks matching terrain-ray coverage. The two local grids cover subsets of the same acquisition. [All thresholds, counts and paired scores](shadow-baselines.json)

The last two columns compare each model's indication of *any* direct sunlight with the same observed labels, using positive rendered W/m² for PGDA. This avoids equating irradiance with disk fraction. At Shackleton rim Clavius classified 20 dark samples as lit and 20 lit samples as dark. The published rendering had 31 and 8 respectively. The resulting 0.17 percentage-point local lead in balanced accuracy reverses under ordinary accuracy (40 versus 39 errors). PGDA also leads on both regional footprints at the primary thresholds. These cases support the terrain-versus-flat-horizon claim. They do not establish general superiority over NASA's rendering. Albedo and scattering affect the proxy labels, and adjacent grid samples are spatially correlated. The scores are a retrospective analysis of previously examined scenes. Some terrain refinement targets still fail. [Source product](https://pgda.gsfc.nasa.gov/products/90) · [Observation and numerical protocol](../../ILLUMINATION_VALIDATION.md)

## Other results from the rerun

| Benchmark | Result and interpretation |
| --- | --- |
| NASA Glenn wheel traction | The MuJoCo rigid-plane fixture passed its control checks and three timestep refinements. Its 18-point RMS traction-angle error was 12.83°, above the 5° target. |
| Deformable soil | Reused the selection frozen on ten training points. On fresh native runs at all eight held-out points, Chrono SCM had lower absolute error at **8 of 8**, with **9.68° RMS versus 15.60°** for the fresh rigid runs at the same points (37.9% reduction). Both exceed 5°. Six numerical refinements were also rerun, with the time and grid changes at 40% slip exceeding 1°. This is an offline Earth-gravity GRC-3 wheel experiment. The public rover replay uses rigid contact. |
| VIPER mechanics | All bounded correction gates passed. The original upstream assembly showed a 27.59 mm wheel center-of-gravity frame discrepancy. The corrected assembly reduced it below 0.001 mm. The 14-case protocol includes original-model failures, deliberate wrong-axis controls and four rigid-floor runs. Flight and soil calibration remain open. |
| Sky geometry | Offline comparison against seven archived JPL Horizons replies passed for all 32 target/site/time cases. Maximum difference in Sun or Earth direction was 0.038 arcseconds, rounded up. This establishes agreement with a reference ephemeris. |
| Flight references | Both NASA GMAT examples converged and passed their endpoint checks when executed again. These cases supply reference trajectories. |
| Gazebo | The live Gazebo / ROS 2 worker passed the native flat-driving, lunar free-fall and telemetry benchmark for its recorded runtime. |

## Reproducing the headline

From the repository root with the documented source assets and Python environment installed, use a fresh output directory.

```sh
npm run validate:illumination -- --output work/shadow-rerun/observed-shadow-comparison.json
.venv/bin/python scripts/score_shadow_baselines.py work/shadow-rerun/observed-shadow-comparison.json
```

The three rerun sample archives matched the SHA-256 hashes in the published illumination report. The scorer checks each archive against its source run, keeps every available scope, evaluates the primary and both sensitivity thresholds, and reports null when a class has no eligible samples. [Wheel benchmark](../../MOBILITY_VALIDATION.md) · [SCM protocol](../../SCM_VALIDATION.md) · [VIPER validation](../../NASA_ROBOT_MODELS.md)
