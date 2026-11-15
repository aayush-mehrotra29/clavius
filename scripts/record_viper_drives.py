"""Regenerate the straight and crab traverses with the prepared Chrono runtime."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np
from scipy.spatial.transform import Rotation

from planner.validation.viper_frames import verified_runtime

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public/data/drive"
EXE = ROOT / "data/runtime/site-drive-build/clavius_site_drive"
WHEEL_INDICES = [4, 8, 12, 16]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_frames(path):
    frames = np.fromfile(path, dtype="<f4").reshape(401, 17, 7)
    if not np.isfinite(frames).all() or np.abs(np.linalg.norm(frames[:, :, 3:], axis=2)-1).max() > 1e-5:
        raise ValueError("Invalid recorded body poses")
    return frames


def check_crab(frames, straight):
    """Measure wheel pointing from actual axle frames, independent of spin phase."""
    travel = frames[-1, 0, :2] - frames[80, 0, :2]
    baseline = straight[-1, 0, :2] - straight[80, 0, :2]
    chassis = Rotation.from_quat(frames[80:, 0, 3:])
    largest_error = 0.
    for i in WHEEL_INDICES:
        axle = Rotation.from_quat(frames[80:, i, 3:]).apply([0, 1, 0])
        body_axle = chassis.inv().apply(axle)
        angles = np.degrees(np.arctan2(-body_axle[:, 0], body_axle[:, 1]))
        largest_error = max(largest_error, float(np.max(np.abs(angles-25.))))
    yaw = np.unwrap(np.arctan2(chassis.apply([1, 0, 0])[:, 1], chassis.apply([1, 0, 0])[:, 0]))
    yaw_excursion = float(np.degrees(np.abs(yaw-yaw[0]).max()))
    lateral_gain = float(travel[1] - baseline[1])
    if largest_error > 2 or yaw_excursion > 15 or lateral_gain < .3:
        raise ValueError(f"Crab control check failed: {largest_error=} {yaw_excursion=} {lateral_gain=}")
    return dict(max_wheel_heading_error_deg=largest_error, max_chassis_yaw_change_deg=yaw_excursion,
                north_gain_over_straight_m=lateral_gain, interval_s=[4, 20])


def main():
    runtime = verified_runtime()
    catalog = json.loads((OUT/"index.json").read_text())
    record = dict(engine="Project Chrono 9.0.1, SMC rigid contact, Bullet", model=runtime["id"],
                  runtime_identity=runtime["runtime_identity"], executable_sha256=sha(EXE),
                  worker_sha256=sha(ROOT/"workers/chrono/site-drive/main.cpp"),
                  gravity_m_s2=1.62, solver_step_s=.001, sample_period_s=.05, frame_count=401,
                  system_mass_kg=434.92111389444585, friction=.7, young_modulus_pa=2e7,
                  restitution=0, motor="ideal wheel angular speed: zero until 3 s, ramp to 0.4 rad/s by 4 s",
                  crab_command="All four wheel planes steer left from 0 to 25 degrees during 1–3 s; rear motor commands use reversed axes.",
                  ground="20 m square near site origin, same nominal 5 m grid and triangle split as browser",
                  layout="little-endian float32. Each frame has chassis then LF, RF, LB, RB. Each corner has upper arm, lower arm, upright, wheel. Each body has ENU xyz metres, quaternion xyzw in the reference frame.",
                  flight_validated=False, soil_calibrated=False, sites={})
    with tempfile.TemporaryDirectory(dir=ROOT/"data/runtime") as temp:
        for site, info in catalog["sites"].items():
            near = info["levels"][0]
            grid = OUT/near["file"]
            if sha(grid) != near["sha256"]:
                raise ValueError("Terrain hash mismatch")
            for mode in ("straight", "crab"):
                filename = site + ("-replay.bin" if mode == "straight" else "-crab.bin")
                path = Path(temp)/filename
                args = [EXE, ROOT/"data/raw/robots/chrono/data", grid, path]
                if mode == "crab":
                    args.append("crab")
                result = subprocess.run(args, check=True, timeout=900, capture_output=True, text=True)
                frames = read_frames(path)
                entry = dict(file=filename, sha256=sha(path), terrain_sha256=sha(grid),
                             final_enu_m=frames[-1, 0, :3].tolist(), checks=result.stdout.strip())
                if mode == "straight":
                    record["sites"][site] = entry
                    straight = frames
                else:
                    entry["steering_checks"] = check_crab(frames, straight)
                    record["sites"][site]["maneuvers"] = {"crab": entry}
        for path in Path(temp).glob("*.bin"):
            path.replace(OUT/path.name)
        (OUT/"replays.json").write_text(json.dumps(record, indent=2)+"\n")
    for filename in ("manifest.json", "simulation-manifest.json"):
        path = OUT.parent / filename
        manifest = json.loads(path.read_text())
        manifest["rover_drive"]["sources"]["recordings"]["sha256"] = sha(OUT/"replays.json")
        path.write_text(json.dumps(manifest, indent=2)+"\n")


if __name__ == "__main__":
    main()
