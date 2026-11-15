"""Package reproducible, sample-and-hold sunlight for the two native replays."""
import hashlib
import json
from pathlib import Path

import numpy as np

from backend.clavius.drive_environment import MODEL, drive_sample, drive_sources, start_epoch
from backend.clavius.terrain import site

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public/data"
OUT = DATA / "drive"
EPOCHS = ["2028-01-01T12:00:00Z", "2028-01-21T12:00:00Z", "2028-01-27T12:00:00Z"]


def main():
    replays = json.loads((OUT / "replays.json").read_text())
    frequency = round(1 / replays["sample_period_s"])
    if frequency * replays["sample_period_s"] != 1:
        raise ValueError("One second must contain a whole number of recorded frames")
    record = {"model": MODEL, "sample_interval_s": 1, "epochs": EPOCHS, "sites": {}}
    for identity, replay in replays["sites"].items():
        raw = (OUT / replay["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != replay["sha256"]:
            raise ValueError("Native trace identity mismatch")
        frames = np.frombuffer(raw, dtype="<f4").reshape(replays["frame_count"], 17, 7)
        terrain = site(identity)
        samples = {}
        for utc in EPOCHS:
            et = start_epoch(utc)
            samples[utc] = [
                drive_sample(terrain, et + t, float(chassis[0]), float(chassis[1]))
                for t, chassis in enumerate(frames[::frequency, 0])
            ]
        record["sites"][identity] = {
            "replay_sha256": replay["sha256"], "sources": drive_sources(terrain), "samples": samples
        }
    output = (json.dumps(record, indent=2, allow_nan=False) + "\n").encode()
    (OUT / "sunlight.json").write_bytes(output)
    source = {
        "url": "/data/drive/sunlight.json", "sha256": hashlib.sha256(output).hexdigest(),
        "model": MODEL, "sample_interval_s": 1,
        "role": "Three selected UTC starts applied to the recorded traces; calculated nominal observer visibility."
    }
    for filename in ("manifest.json", "simulation-manifest.json"):
        path = DATA / filename
        manifest = json.loads(path.read_text())
        manifest["rover_drive"]["sources"]["sunlight"] = source
        path.write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
