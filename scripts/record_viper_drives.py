"""Regenerate the two packaged native traverses after building workers/chrono/site-drive."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import numpy as np
from planner.validation.viper_frames import verified_runtime

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public/data/drive"
EXE = ROOT / "data/runtime/site-drive-build/clavius_site_drive"

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    runtime = verified_runtime()
    catalog = json.loads((OUT/"index.json").read_text())
    record = dict(engine="Project Chrono 9.0.1, SMC rigid contact, Bullet", model=runtime["id"],
                  runtime_identity=runtime["runtime_identity"], executable_sha256=sha(EXE),
                  worker_sha256=sha(ROOT/"workers/chrono/site-drive/main.cpp"),
                  gravity_m_s2=1.62, solver_step_s=.001, sample_period_s=.05, frame_count=401,
                  system_mass_kg=434.92111389444585, friction=.7, young_modulus_pa=2e7,
                  restitution=0, motor="ideal wheel angular speed: zero until 3 s, ramp to 0.4 rad/s by 4 s",
                  ground="20 m square near site origin, same nominal 5 m grid and triangle split as browser",
                  layout="little-endian float32. Each frame has chassis then LF, RF, LB, RB. Each corner has upper arm, lower arm, upright, wheel. Each body has ENU xyz metres, quaternion xyzw in the reference frame.",
                  flight_validated=False, soil_calibrated=False, sites={})
    with tempfile.TemporaryDirectory(dir=ROOT/"data/runtime") as temp:
        for site, info in catalog["sites"].items():
            near = info["levels"][0]
            grid = OUT/near["file"]
            if sha(grid) != near["sha256"]:
                raise ValueError("Terrain hash mismatch")
            path = Path(temp)/(site+"-replay.bin")
            result = subprocess.run([EXE, ROOT/"data/raw/robots/chrono/data", grid, path], check=True, timeout=900, capture_output=True, text=True)
            frames = np.fromfile(path, dtype="<f4").reshape(401,17,7)
            if not np.isfinite(frames).all() or np.abs(np.linalg.norm(frames[:,:,3:],axis=2)-1).max()>1e-5:
                raise ValueError("Invalid recorded body poses")
            record["sites"][site] = dict(file=path.name, sha256=sha(path), terrain_sha256=sha(grid),
                                         final_enu_m=frames[-1,0,:3].tolist(), checks=result.stdout.strip())
        for entry in record["sites"].values():
            (Path(temp)/entry["file"]).replace(OUT/entry["file"])
        (OUT/"replays.json").write_text(json.dumps(record,indent=2)+"\n")

if __name__ == "__main__":
    main()
