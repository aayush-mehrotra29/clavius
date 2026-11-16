"""Package two-site stationary solar geometry for the hackathon UTC presets."""
import hashlib
import json

from backend.clavius.drive_environment import parked_sunlight
from scripts.prepare_drive_sunlight import EPOCHS, DATA, OUT


def main():
    sources = {}
    for identity in ("connecting-ridge", "shackleton-rim"):
        entries = {}
        for start in EPOCHS:
            result = parked_sunlight(identity, start, 0., 0., 48)
            path = OUT / f"{identity}-parked-{start[:10]}.json"
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
        manifest["rover_drive"]["parked_sunlight"] = sources
        path.write_text(json.dumps(manifest,indent=2)+"\n")


if __name__ == "__main__":
    main()
