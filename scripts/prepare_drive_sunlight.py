"""Package reproducible, sample-and-hold sunlight for the native traverses at both sites."""
import hashlib
import json
from pathlib import Path


from backend.clavius.drive_environment import MODEL, drive_sources, read_replay, replay_samples
from backend.clavius.terrain import site

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public/data"
OUT = DATA / "drive"
EPOCHS = ["2028-01-01T12:00:00Z", "2028-01-21T12:00:00Z", "2028-01-27T12:00:00Z"]


def sample_trace(terrain, replay, frequency, frame_count):
    frames = read_replay(OUT, replay, frame_count)
    samples = {utc: replay_samples(terrain, utc, frames, frequency) for utc in EPOCHS}
    return {"replay_sha256": replay["sha256"], "samples": samples}


def main():
    replays = json.loads((OUT / "replays.json").read_text())
    frequency = round(1 / replays["sample_period_s"])
    if frequency * replays["sample_period_s"] != 1:
        raise ValueError("One second must contain a whole number of recorded frames")
    record = {"model": MODEL, "sample_interval_s": 1, "epochs": EPOCHS, "sites": {}}
    for identity, replay in replays["sites"].items():
        terrain = site(identity)
        primary = sample_trace(terrain, replay, frequency, replays["frame_count"])
        primary["sources"] = drive_sources(terrain)
        primary["maneuvers"] = {
            name: sample_trace(terrain, trace, frequency, replays["frame_count"])
            for name, trace in replay.get("maneuvers", {}).items()
        }
        record["sites"][identity] = primary
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
