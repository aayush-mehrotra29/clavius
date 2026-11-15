"""Prepare locally served lunar assets; retain elevation samples without quantization.

Inputs are NASA SVS CGI Moon Kit 2019 ldem_16_uint.tif and
lroc_color_poles_4k.tif. Usage: python3 scripts/prepare_lunar_assets.py DEM COLOR
"""
from pathlib import Path
from PIL import Image
import numpy as np
import hashlib, json, sys

out = Path(__file__).resolve().parent.parent / 'public/data'
out.mkdir(parents=True, exist_ok=True)
dem_path, color_path = map(Path, sys.argv[1:3])
dem = np.asarray(Image.open(dem_path), dtype='<u2')
assert dem.shape == (2880, 5760), dem.shape
assert dem.max() < 65535
(out / 'lola-elevation.bin').write_bytes(dem.tobytes())
Image.open(color_path).convert('RGB').save(out / 'lroc-color.jpg', quality=94, subsampling=0, optimize=True)
manifest = {
 'title': 'NASA SVS CGI Moon Kit (2019 maps)',
 'sourcePage': 'https://svs.gsfc.nasa.gov/4720/',
 'credit': "NASA’s Scientific Visualization Studio; LRO / LOLA and LROC instrument teams",
 'elevation': {
  'url': 'https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/ldem_16_uint.tif',
  'sourceSha256': hashlib.sha256(dem_path.read_bytes()).hexdigest(),
  'outputSha256': hashlib.sha256((out / 'lola-elevation.bin').read_bytes()).hexdigest(),
  'file': 'lola-elevation.bin', 'width':5760, 'height':2880,
  'encoding': 'little-endian uint16, row-major, north to south, west to east',
  'pixelsPerDegree':16, 'pixelRegistration':'pixel centers',
  'elevationMeters': 'sample * 0.5 - 10000',
  'referenceRadiusMeters':1737400,
  'minElevationMeters':float(dem.min())*.5-10000,
  'maxElevationMeters':float(dem.max())*.5-10000,
 },
 'imagery': {
  'url': 'https://svs.gsfc.nasa.gov/vis/a000000/a004700/a004720/lroc_color_poles_4k.tif',
  'sourceSha256': hashlib.sha256(color_path.read_bytes()).hexdigest(),
  'file':'lroc-color.jpg', 'width':4096, 'height':2048,
  'processing':'RGB JPEG, quality 94, no chroma subsampling',
  'limits':'Visualization mosaic. Polar latitudes beyond ±70° filled with LOLA albedo; source dropouts inpainted by NASA. Not scientific reflectance.',
 },
 'limits': 'Global visualization only. Mesh resamples the raster. Not wheel-scale terrain, validated hazard data, rover dynamics, or date-specific lighting.',
}
previous=json.loads((out/'manifest.json').read_text()) if (out/'manifest.json').exists() else {}
for key in ('simulation', 'landingPolarViews'):
    if key in previous:
        manifest[key] = previous[key]
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
print(json.dumps(manifest['elevation'], indent=2))

# Keep display derivatives and their linked hashes synchronized on re-import.
from derive_lunar_normals import main as derive_normals
derive_normals()

from render_landing_moon import main as render_landing_preview
render_landing_preview()
