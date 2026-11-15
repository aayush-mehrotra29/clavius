"""Build nested ENU display surfaces from the pinned nominal simulation sources."""
import hashlib
import json
from pathlib import Path
import numpy as np
from backend.clavius.terrain import Site, R, body_latlon, latlon_body, stereographic

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public/data/drive"
OUT.mkdir(exist_ok=True)
sites = {}
for identity in ("connecting-ridge", "shackleton-rim"):
    site = Site(identity)
    levels = []
    for name, spacing, half in (("drive", 5, 1280), ("horizon", 80, 20480)):
        axis = np.arange(-half, half+spacing, spacing)
        east, north = np.meshgrid(axis, axis)
        if name == "drive":
            heights = site.height(east, north)
            key = "local_asset_id"
        else:
            lat, lon = site.location(east, north)
            h = site.regional.sample(*stereographic(lat, lon))
            heights = ((latlon_body(lat, lon, R+h)-site.origin) @ site.rotation)[...,2]
            key = "regional_asset_id"
        if not np.isfinite(heights).all():
            raise ValueError(f"Missing terrain inside {identity} {name}")
        path = OUT / f"{identity}-{name}.bin"
        data = heights.astype("<f4").tobytes()
        path.write_bytes(data)
        asset = next(a for a in site.manifest["assets"] if a["id"]==site.definition[key])
        levels.append(dict(file=path.name, level=name, count=len(axis), spacing_m=spacing,
                           half_extent_m=half, sha256=hashlib.sha256(data).hexdigest(),
                           source=asset["id"], source_sha256=asset["sha256"]))
    sites[identity] = dict(name=site.name, latitude=site.lat, longitude=site.lon, levels=levels)
record = dict(sites=sites, encoding="little-endian float32 local up metres, rows south to north",
              script="scripts/prepare_drive_terrain.py",role="nominal terrain for kinematic drive visualization")
(OUT/"index.json").write_text(json.dumps(record,indent=2)+"\n")
