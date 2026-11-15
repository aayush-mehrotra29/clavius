"""Prepare lossless regional DEM tiles and the explorer's 8k albedo from NASA TIFFs."""
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public/data"
URL = "https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/"
DEM = "ldem_64_uint.tif"
COLOR = "lroc_color_poles_8k.tif"
SIZE = 960


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source(name, expected):
    path = ROOT / "data/raw" / name
    if sha(path) != expected:
        raise ValueError(f"Unexpected NASA source bytes for {name}")
    return path, {"url": URL + name, "sourceSha256": expected}


def main():
    dem, elevation = source(DEM, "0f40bce8b42864deddb6943a38474879e691d5b20647aa5e54c2612b23106499")
    color, imagery = source(COLOR, "4af8b0cd4d50c30851359d98e7e72040240dd8d03256b58b345b5b76e9edb4ef")
    # Allow the known, hash-verified large NASA TIFF.
    Image.MAX_IMAGE_PIXELS = 23040 * 11520
    directory = OUT / "lola64"
    directory.mkdir(exist_ok=True)
    tiles = {}
    with Image.open(dem) as image:
        assert image.size == (23040, 11520)
        for row in range(12):
            for col in range(24):
                block = np.asarray(image.crop((col*SIZE, row*SIZE, (col+1)*SIZE, (row+1)*SIZE)), dtype="<u2")
                delta = block.copy()
                delta[:, 1:] -= block[:, :-1]
                raw = delta.view(np.uint8).reshape(-1, 2).T.tobytes()
                name = f"{col}-{row}.bin.gz"
                (directory / name).write_bytes(gzip.compress(raw, compresslevel=6, mtime=0))
                tiles[name] = sha(directory / name)
    elevation.update(width=23040, height=11520, pixelsPerDegree=64, tileSize=SIZE,
                     encoding="gzip, rowwise uint16 differences modulo 65536, low-byte plane followed by high-byte plane",
                     elevationMeters="sample * 0.5 - 10000", referenceRadiusMeters=1737400, tiles=tiles)
    with Image.open(color) as image:
        assert image.size == (8192, 4096)
        image.convert("RGB").save(OUT/"lroc-color-8k.jpg", quality=92, subsampling=0, optimize=True)
    imagery.update(file="lroc-color-8k.jpg", width=8192, height=4096, outputSha256=sha(OUT/"lroc-color-8k.jpg"))
    manifest = OUT / "manifest.json"
    sources = json.loads(manifest.read_text())
    sources["explorerDetail"] = {"elevation": elevation, "imagery": imagery, "script":"scripts/prepare_explorer_detail.py"}
    manifest.write_text(json.dumps(sources, indent=2)+"\n")


if __name__ == "__main__":
    main()
