"""Package two-site stationary solar geometry for the hackathon UTC presets."""
import argparse
import hashlib
import json

from backend.clavius.drive_environment import parked_sunlight
from scripts.prepare_drive_sunlight import EPOCHS, DATA, OUT


def main(realization="nominal"):
    suffix = "" if realization=="nominal" else "-"+realization
    sources = {}
    for identity in ("connecting-ridge", "shackleton-rim"):
        entries = {}
        for start in EPOCHS:
            result = parked_sunlight(identity, start, 0., 0., 48, realization=realization)
            path = OUT / f"{identity}{suffix}-parked-{start[:10]}.json"
            raw = (json.dumps(result,separators=(",",":"),allow_nan=False)+"\n").encode()
            path.write_bytes(raw)
            entries[start] = {"url":"/data/drive/"+path.name,"sha256":hashlib.sha256(raw).hexdigest()}
        sources[identity] = entries
    for filename in ("manifest.json","simulation-manifest.json"):
        path = DATA / filename
        manifest = json.loads(path.read_text())
        battery = DATA.parent / "robots/viper/battery.json"
        manifest["rover_drive"]["sources"]["battery"] = {
            "url":"/robots/viper/battery.json", "sha256":hashlib.sha256(battery.read_bytes()).hexdigest()
        }
        if realization == "nominal":
            manifest["rover_drive"]["parked_sunlight"] = sources
        else:
            manifest["rover_drive"].setdefault("parked_sunlight_realizations",{})[realization]=sources
        path.write_text(json.dumps(manifest,indent=2)+"\n")


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--realization",choices=["nominal","pgda78-0001"],default="nominal")
    main(parser.parse_args().realization)
