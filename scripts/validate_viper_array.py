"""Compare the shipped 1-second environment against 20 Hz SPICE/terrain samples."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from backend.clavius.drive_environment import drive_sample, read_replay, start_epoch
from backend.clavius.terrain import site

ROOT = Path(__file__).resolve().parents[1]
DRIVE = ROOT / "public/data/drive"
AU_KM = 149597870.7
MAX_ENERGY_DIFFERENCE_WH = .02
MAX_POINT_DIFFERENCE_W = 15.


def generation(sample, rotation, normals, ref):
    direction = rotation.inv().apply(sample["sun_site_enu"])
    return ref * (AU_KM / sample["sun_distance_km"])**2 * sample["disk_fraction"] * np.maximum(0, normals @ direction).sum()


def main(realization="nominal"):
    clone = realization != "nominal"
    light_file = DRIVE / ("viper-terrain-comparison.json" if clone else "sunlight.json")
    hardware_file = ROOT / "public/robots/viper/source.json"
    hardware = json.loads(hardware_file.read_text())["solar_array"]
    normals = np.array(list(hardware["faces"].values()))
    ref = hardware["panel_reference_w"]
    catalog = json.loads(light_file.read_text())
    replays = json.loads((DRIVE/"replays.json").read_text())
    step = replays["sample_period_s"]
    cases = []
    for identity, primary in replays["sites"].items():
        terrain = site(identity,realization)
        entry = catalog["sites"][identity]
        if clone:
            primary, light = entry["replays"], entry["sunlight"]
        else:
            light = entry
        for maneuver, trace, observations in [("straight", primary, light), ("crab", primary["maneuvers"]["crab"], light["maneuvers"]["crab"])]:
            poses = read_replay(DRIVE, trace, replays["frame_count"])[:,0]
            attitudes = Rotation.from_quat(poses[:,3:])
            for epoch, samples in observations["samples"].items():
                start = start_epoch(epoch)
                coarse, fine, interval_ends = [], [], []
                for i, (pose, rotation) in enumerate(zip(poses, attitudes)):
                    exact = drive_sample(terrain,start+i*step,float(pose[0]),float(pose[1]))
                    held = samples[i//20]
                    coarse.append(generation(held,rotation,normals,ref))
                    fine.append(generation(exact,rotation,normals,ref))
                    if i+1<len(poses):
                        interval_ends.append(generation(held,attitudes[i+1],normals,ref))
                reference_wh = np.trapezoid(fine, dx=step)/3600
                shipped_wh = (sum(coarse[:-1])+sum(interval_ends))*step/7200
                max_w = float(np.abs(np.subtract(coarse, fine)).max())
                cases.append(dict(site=identity,maneuver=maneuver,start_utc=epoch,trace_sha256=trace["sha256"],
                    held_wh=float(shipped_wh),refined_wh=float(reference_wh),max_point_difference_w=max_w,
                    passed=bool(abs(reference_wh-shipped_wh)<=MAX_ENERGY_DIFFERENCE_WH and max_w<=MAX_POINT_DIFFERENCE_W)))
    report = dict(model=hardware["model"], sunlight_sha256=hashlib.sha256(light_file.read_bytes()).hexdigest(),
        hardware_sha256=hashlib.sha256(hardware_file.read_bytes()).hexdigest(),
        reference_step_s=step,production_environment_step_s=1,realization=realization,
        energy_tolerance_wh=MAX_ENERGY_DIFFERENCE_WH,point_tolerance_w=MAX_POINT_DIFFERENCE_W,
        scope="Time and position sampling comparison on the same selected terrain and pose traces. Physical electrical calibration is unresolved.",
        cases=cases)
    (ROOT/"docs/validation"/("viper-array-sampling"+("-"+realization if clone else "")+".json")).write_text(json.dumps(report,indent=2)+"\n")
    print(f"{sum(c['passed'] for c in cases)}/{len(cases)} cases pass the sampling comparison")
    if not all(c["passed"] for c in cases):
        raise SystemExit(1)


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--realization",choices=["nominal","pgda78-0001"],default="nominal")
    main(parser.parse_args().realization)
