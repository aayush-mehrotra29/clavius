# Executed NASA GMAT references

On 15 November 2026, both original tagged NASA GMAT R2026a lunar-transfer examples executed through the official Console and Python API on this Apple Silicon Mac. All original target loops converged and the recorded residual/event/endpoint checks passed. Reference execution is complete; the bounded departure search remains pending.

The [published summary](../public/data/gmat-reference-validation.json) records source hashes, solved states, native frames, burn vectors, residuals and checking tolerances. [The validation record](validation/gmat-reference-benchmark.json) is identical. The immutable local archive `data/runtime/gmat/benchmark-2026-11-15-v3.zip` has SHA-256 `374041f6a902d57e178ea8105b7a3afcb7eb74bec9bd3778778080749760d959`. It includes raw logs, individual command summaries, original references, adapter source, the installed-file inventory and a hash index. The large distribution is reacquired using its pinned download/hash.

## Software and conventions

- Official NASA R2026a signed universal macOS distribution, native build 26 March 2026 19:40:07; distribution SHA-256 `8a81d22ce2d39504eadc875d71494321adb49f60da92d266fdbe660de0f771d2`.
- Complete 2,060-file installation; original file bytes, binaries and scripts unchanged. Source/installed Console signatures verified. All distributed regular files are hashed; all symlinks stay inside the installation.
- Runtime identity `97c3f208072e53654eeb5a7c46e721abe9c71c7bda779fd6f24ab336379d03ed`; Python 3.13.13 / arm64.
- Native **DE405** and original supporting files, separate from the surface workspace's DE421. Original force models and solver tolerances retained.
- Native lunar radius **1,738.2 km**, gravitational parameter **4,902.8005821478 km³/s²**. The surface DEM's **1,737.4 km** sphere is a separate convention.
- Private startup files relocate paths/output, suppress plots, disable unused external SDK plugins and route updates away from numerical inputs. Original startup bytes remain available. Mission/force-model settings are unchanged.

The cases repeated with identical extracted states, burns and solver evidence. The final repeat ran after ejecting the DMG. Earlier incomplete compact installations and failed parser preflights remain separate from the accepted evidence.

## Actual solved cases

| Case | Physical departure UTC | Lunar encounter / insertion UTC | Target loops | Post-insertion coast |
| --- | --- | --- | --- | --- |
| `Ex_GivenEpochGoToTheMoon.script` | 15 July 2022 01:07:06.978 | 19 July 2022 15:17:22.067 | 37 coarse + 7 fine iterations | 4 days |
| `Ex_LunarTransfer.script` | 23 July 2014 20:48:49.867 | 28 July 2014 22:07:27.449 | 6 B-plane + 4 insertion iterations | 15 days |

The fixed-epoch case starts from the 6,563 km semi-major-axis Earth parking orbit. Its coarse initialization reaches the 4.5-day guard; the spacecraft is then reset before the fine solve. That initialization is excluded from physical transfer and maneuver accounting. The physical transfer takes **396,615.089 SI seconds**, stops before the 6-day/1,000 km guards and reaches lunar radius **15,000.000392 km**. TOI VNB/Earth Element1 is **3.133265205687565 km/s**; LOI VNB/Luna Element1 is **−0.634545446635383 km/s**. Computed insertion eccentricity is **0.010000075015**. The source eccentricity tolerance is **0.1**, not a precision-circularization claim. `MoonInertial` is Luna-centered **BodyInertial**. The final command's label says “.5 days”; its actual stop condition is **4 days**.

The second case starts on 22 July from an already distant Cartesian trajectory and reaches Earth perigee before departure. It is not the same parking-orbit example. Achieved BdotT is **14,998.6063605 km**, target 15,000.4401777 km; BdotR is **4,001.57939844 km**, target 4,000.59308992 km; each has a 3 km tolerance. Two human labels are swapped; checks use the actual expressions. LOI VNB/Luna Element1 is **−0.5530339388434146 km/s**, computed insertion eccentricity **8.9329 × 10⁻⁸**. Its actual lunar frame is **MoonMJ2000Eq**. Earth JGM2 and lunar LP165P degree/order 20 force models remain intact.

## Checks and limits

Checks require process/API success, both target loops, explicit convergence, consistent finite residuals within source tolerances and matching Console/API goals. Summaries select the intended spacecraft and preserve frame origin/axes. Cartesian values convert km and km/s to SI. Durations use native TAI modified-Julian differences, retaining original UTC strings.

Independent endpoint calculations check radius, radial velocity, energy, eccentricity and osculating periapsis. They check intended lunar periapsis, separation from alternate guards, insertion epoch/position continuity, observed impulse, bound capture/post-capture endpoints, osculating periapsis clearance above the native sphere and actual coast duration. Exact tolerances are in the summary.

**No screening candidate is accepted yet.** Full trajectory Earth/Moon clearance, tighter independent repropagation and a bounded epoch search remain pending. Endpoint checks do not prove continuous collision safety. Source masses are 850/1,000 kg, independent of rover mass. Burns do not decrement mass. Launch/propellant compatibility, launch-site access, descent and touchdown remain unassessed. The orbital benchmark is separate from MuJoCo/Gazebo rover dynamics and surface validation.

## Reproduce

Install from the pinned mounted macOS SDK with `.venv/bin/python scripts/install_gmat_macos.py --source <mounted-SDK-directory>`. The installer verifies the DMG and refuses to overwrite an existing installation.

```sh
npm run test:orbital
npm run gmat:references -- --output data/runtime/gmat/new-reference-run
.venv/bin/python -m scripts.publish_gmat_references data/runtime/gmat/new-reference-run
```

Each run uses a fresh output directory and per-process timeout. Uploaded GMAT scripts never execute. Recorded-output regression tests cover missing markers, malformed/nonfinite residuals, wrong frames/units, guard stops, unbound/intersecting states and timeouts. Original scripts, exact acquisition URLs and the Apache 2.0 license remain under `planner/orbital/references/`.
