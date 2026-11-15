"""Derive object-space surface normals from the existing LOLA DEM, not imagery.

Run: python3 scripts/derive_lunar_normals.py
Requires NumPy and Pillow. Heights are meters above the 1737.4 km sphere.
Central differences wrap at the longitude seam; latitude edges use one-sided
north/south differences. Output is a linear RGB8 PNG, never sRGB color data.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image

RADIUS_M = 1737400.0


def surface_normals(heights):
    """Return global XYZ unit normals, using spherical metric factors."""
    height, width = heights.shape
    dlon, dlat = 2 * np.pi / width, np.pi / height
    lat = np.pi / 2 - (np.arange(height) + .5) * dlat
    lon = -np.pi + (np.arange(width) + .5) * dlon
    coslat, sinlat = np.cos(lat)[:, None], np.sin(lat)[:, None]
    coslon, sinlon = np.cos(lon)[None, :], np.sin(lon)[None, :]
    radius = RADIUS_M + heights
    east_slope = (np.roll(heights, -1, axis=1) - np.roll(heights, 1, axis=1)) / (2 * dlon * radius * coslat)
    north_slope = -np.gradient(heights, axis=0) / (dlat * radius)
    normals = np.empty((height, width, 3), dtype=np.float32)
    normals[:, :, 0] = coslat * coslon + east_slope * sinlon + north_slope * sinlat * coslon
    normals[:, :, 1] = sinlat - north_slope * coslat
    normals[:, :, 2] = -coslat * sinlon + east_slope * coslon - north_slope * sinlat * sinlon
    normals /= np.linalg.norm(normals, axis=2, keepdims=True)
    return normals


def main():
    data = Path(__file__).resolve().parent.parent / 'public/data'
    manifest_path = data / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    elevation = manifest['elevation']
    samples = np.fromfile(data / elevation['file'], dtype='<u2').reshape(elevation['height'], elevation['width'])
    heights = samples.astype(np.float32) * .5 - 10000
    normals = surface_normals(heights)
    encoded = np.rint(np.clip(normals * .5 + .5, 0, 1) * 255).astype(np.uint8)
    output = data / 'lola-normals.png'
    Image.fromarray(encoded).save(output, optimize=True)
    manifest['derivatives'] = {
        'surfaceNormals': {
            'file': output.name,
            'sourceFile': elevation['file'],
            'sourceElevationSha256': elevation['outputSha256'],
            'outputSha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'width': elevation['width'], 'height': elevation['height'],
            'encoding': 'linear RGB8, normalized object-space XYZ encoded as normal * 0.5 + 0.5',
            'method': 'Central differences on native LOLA pixel centers, longitude wrapping, one-sided latitude edges; spherical physical spacing with radius 1737400 m + elevation.',
            'script': 'scripts/derive_lunar_normals.py',
            'limits': 'Shading derivative of the same 16 px/degree DEM. No new measured resolution or invented craters. RGB8 normals have quantization error; they are a display asset, not a scientific slope product.',
        }
    }
    manifest['display'] = {
        'defaultVerticalExaggeration': 1,
        'illumination': 'Illustrative directional lighting; adjustable solar elevation 5–70 degrees; not tied to a mission epoch.',
        'terrainShadows': 'Display shadow map on the regional mesh; not a validated illumination or permanently shadowed region product.',
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Wrote {output.name}: {output.stat().st_size / 1e6:.1f} MB; original elevation unchanged.')


if __name__ == '__main__':
    main()
