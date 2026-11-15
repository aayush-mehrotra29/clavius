# Clavius Gazebo / ROS 2 worker

This worker targets **Ubuntu 24.04, its system Python 3.12, ROS 2 Jazzy and Gazebo Harmonic (`gz.sim8`)**, with DART rigid contact. On 15 November 2026 it built and executed on this Apple Silicon Mac inside a local Colima Linux VM. Native flat driving, analytical free fall and ROS 2 clock reception passed; a linked 20-second probe also executed on the measured NASA terrain. Evidence is in `docs/validation/gazebo-native-benchmark.json` and `gazebo-local-runtime.json`. The app keeps this engine disabled until the connected runtime passes the benchmark.

## Run on this Mac

The local tools are installed. For another Apple Silicon Mac, install them with `brew install colima docker docker-buildx`. From the repository root:

```bash
npm run gazebo:start
npm run gazebo:benchmark
npm run dev:simulation
```

The launcher uses a named `clavius` VM: two CPUs, 4 GiB RAM, an 8 GiB sparse container disk and a 4 GiB root disk limit. Host directory mounts, SSH agent forwarding and automatic Docker context switching are disabled. The container is limited to 2 GiB RAM and listens on `127.0.0.1:8002`. Its private token is generated in the ignored, mode-600 `data/runtime/gazebo-local.env`; the app launcher reads only its two worker settings. An existing backend started without those settings needs restarting once. No separate Linux machine or SSH tunnel is needed for this setup.

Use `npm run gazebo:status` to inspect readiness. Run `npm run gazebo:start -- --build` after editing worker code, then rerun the benchmark. This reuses the installed SDK image; `--fresh-sdk` rebuilds from the official ROS base instead. Source/native-library changes invalidate the stored benchmark. `npm run gazebo:stop` stops the container and VM to release their resources; its data volume retains the evidence for the next start. The launcher starts neither a login service nor a Gazebo GUI.

## Start on a Linux machine

Copy this repository's source to the Linux host. Docker Engine and Compose must already be installed. The worker does not need the raw NASA cache: each measured-terrain request carries a bounded, content-hashed grid, source manifest and original robot upload. Start from the repository root:

```bash
export CLAVIUS_GAZEBO_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose -f workers/gazebo/compose.yaml build
docker compose -f workers/gazebo/compose.yaml up -d
docker compose -f workers/gazebo/compose.yaml logs --tail=80 gazebo
```

Keep the token private and reuse it in the app backend's environment. Compose binds only `127.0.0.1:8002`; use an SSH tunnel from the Mac instead of exposing this HTTP service publicly:

```bash
ssh -N -L 8002:127.0.0.1:8002 user@linux-host
```

The initial image uses the official `ros:jazzy-ros-base-noble` tag, OSRF's stable Noble package repository, `gz-sim8-cli`, `python3-gz-sim8`, `libgz-sim8-plugins` and `libgz-physics7-dartsim`. The system-plugin package supplies the loader aliases; DART's versioned runtime plugin is selected explicitly in SDF. The Python venv includes system site packages so the compiled Gazebo and ROS modules stay accessible. Python dependencies use the repository's exact pins. The ROS tag and apt repository are mutable; for a retained deployment, set `CLAVIUS_ROS_IMAGE` to the pulled image's digest. The worker records installed Gazebo/DART/ROS package versions, numerical libraries, Python, platform and source SHA in its runtime identity. Changing that identity invalidates its prior benchmark.

## Execute the acceptance gate

On the Mac, set the same token, use the tunnel, and run:

```bash
export CLAVIUS_GAZEBO_URL=http://127.0.0.1:8002
export CLAVIUS_GAZEBO_TOKEN='the-private-token-from-the-Linux-host'
.venv/bin/python scripts/benchmark_gazebo_worker.py --output docs/validation/gazebo-native-benchmark.json
```

The CLI submits the unmodified reference rover twice to the native process: five seconds of flat driving at 0.05 m/s, then 0.5 seconds of free fall under 1.62 m/s² gravity. The worker evaluates speed, distance, root height, attitude, analytical fall position/velocity, motor torque limits and actual ROS 2 clock reception through DDS. It stores completed job IDs and input/result hashes. No manual `passed` flag is accepted. The retained file now contains actual passing native jobs from the local Linux VM.

After the benchmark passes, restart the Clavius app backend with the URL/token environment above and reload the page. **Detailed segment → Engine → Gazebo / ROS 2** becomes selectable. Ordinary Gazebo jobs remain rejected by the app when the worker is unconfigured, unreachable, has changed version, or has no matching benchmark. MuJoCo stays a separately selected local engine. API-only protocol tests use clearly identified fixtures and cannot certify Gazebo physics.

## What runs

The broker launches one isolated `gz.sim8.TestFixture` process per job with its own ROS domain and Gazebo partition. A fixed 5 ms controller applies torque through `Joint.set_force`, using the shared wheel mapping, commanded velocity, imported effort/velocity limits and declared friction. It queries actual link/joint state and publishes `/clock`, `/clavius/pose`, and `/clavius/joints` at the replay cadence. ROS 2 is currently a telemetry path; arbitrary external ROS controllers, sensors and uploaded plugins are not supported by this adapter. Cancelling a job signals its process at a bounded step boundary; partial data is explicitly marked and never accepted as a completed run. Worker restarts mark unfinished jobs failed.

The input archive and source SHA bind the original URDF/meshes, physical revisions, capability profile, request and conditioned terrain. The worker reimports the data and checks identities before generating its own SDF. Mesh sampling is 0.5 m for a 40 m patch, interpolated from **5 m measured posting**; it adds no measured detail. The Collada mesh includes normals derived from the sampled height gradient, as required by DART's mesh consumer. Absolute mesh URIs in an exported review SDF are regenerated on the worker from the packet. Missing native channels fail execution; callback errors are retained and raised after a bounded step block so they cannot escape across the C++ callback boundary. Contact force/count channels are null in this Gazebo adapter until independently instrumented and verified. MuJoCo and DART contact models differ; benchmark acceptance does not establish cross-engine agreement or calibrated lunar soil performance.

Job input, SDF, progress, log, result, cancellation marker and captured source live in the named `gazebo-state` volume. Keep the volume to retain evidence. Application evidence exports include worker input and code snapshots after a successful remote run. Reproduction requires the recorded worker code version as well as a configured, verified native runtime; it never silently substitutes MuJoCo.

## Source references

- [Official ROS Docker tags and architecture list](https://github.com/docker-library/official-images/blob/master/library/ros)
- [Colima VM, resources, mounts and port forwarding](https://colima.run/docs/configuration/)
- [Harmonic binaries for Ubuntu Noble and OSRF repository setup](https://gazebosim.org/docs/harmonic/install_ubuntu/)
- [Supported ROS/Gazebo pairings](https://gazebosim.org/docs/harmonic/ros_installation/)
- [OSRF Noble amd64 package metadata](https://packages.osrfoundation.org/gazebo/ubuntu-stable/dists/noble/main/binary-amd64/Packages.gz) checked 14 November 2026: `python3-gz-sim8` 8.15.0, `python3-gz-math7` 7.7.0, `libgz-physics7-dartsim` 7.9.0. This check is dependency metadata, not a container build.
- [Gazebo 8 fixture example](https://github.com/gazebosim/gz-sim/blob/gz-sim8/examples/scripts/python_api/testFixture.py), [Joint binding](https://github.com/gazebosim/gz-sim/blob/gz-sim8/python/src/gz/sim/Joint.cc), [Link binding](https://github.com/gazebosim/gz-sim/blob/gz-sim8/python/src/gz/sim/Link.cc)
- [Gazebo Math 7 seed tests](https://github.com/gazebosim/gz-math/blob/gz-math7/src/python_pybind11/test/Rand_TEST.py)
- [Physics engine selection](https://gazebosim.org/api/sim/9/physics.html); native Harmonic execution remains the acceptance test for this worker.
