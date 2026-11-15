"""Render a small orthographic Moon Kit preview for the landing dataset section."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def main():
    data = Path(__file__).resolve().parents[1] / 'public/data'
    manifest_path = data / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    size = 896
    rows, columns = np.indices((size, size), dtype=np.float32)
    east = (columns + 0.5 - size / 2) / (size / 2 - 1)
    north = (size / 2 - rows - 0.5) / (size / 2 - 1)
    radius = np.hypot(east, north)
    front = np.sqrt(np.maximum(0, 1 - radius**2))
    u = 0.5 + np.arctan2(east, front) / (2 * np.pi)
    v = 0.5 - np.arcsin(np.clip(north, -1, 1)) / np.pi

    def sample(filename):
        with Image.open(data / filename) as image:
            pixels = np.asarray(image)
            x = np.clip((u * image.width).astype(int), 0, image.width - 1)
            y = np.clip((v * image.height).astype(int), 0, image.height - 1)
            return pixels[y, x].astype(np.float32)

    imagery = manifest['imagery']['file']
    normals = manifest['derivatives']['surfaceNormals']['file']
    albedo = sample(imagery)
    normal = sample(normals) / 127.5 - 1
    sun = np.array([0.4, 0.32, 0.86], dtype=np.float32)
    illumination = np.maximum(0, normal @ (sun / np.linalg.norm(sun)))
    rgb = np.clip(albedo * (0.09 + 1.32 * illumination[..., None]**0.7), 0, 255)
    alpha = 255 * np.clip((1 - radius) * size / 2 + 0.5, 0, 1)
    output = data.parent / 'images/landing-moon.webp'
    Image.fromarray(np.dstack([rgb, alpha]).astype(np.uint8)).save(output, quality=87)
    manifest['landingPreview'] = {
        'url': '/images/landing-moon.webp',
        'sourceFiles': [imagery, normals],
        'outputSha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'script': 'scripts/render_landing_moon.py',
        'description': 'Orthographic near-side display with illustrative lighting. Uses the existing Moon Kit imagery and DEM-derived normals.',
    }
    elevation = manifest['elevation']
    samples = np.memmap(data / elevation['file'], dtype='<u2', mode='r',
                        shape=(elevation['height'], elevation['width']))
    rows = np.clip((v * elevation['height']).astype(int), 0, elevation['height'] - 1)
    cols = np.clip((u * elevation['width']).astype(int), 0, elevation['width'] - 1)
    meters = samples[rows, cols].astype(np.float32) * 0.5 - 10000
    stops = [-4500, -3000, -1500, 0, 1500, 3000, 4500]
    colors = np.array([[42, 31, 119], [58, 83, 204], [47, 161, 203], [124, 217, 191],
                       [248, 216, 147], [232, 127, 120], [198, 78, 139]])
    heat = np.stack([np.interp(meters, stops, channel) for channel in colors.T], axis=-1)
    shaded = heat * (0.69 + 0.31 * illumination[..., None])
    heatmap = data.parent / 'images/lunar-elevation.webp'
    Image.fromarray(np.dstack([shaded, alpha]).astype(np.uint8)).save(heatmap, quality=90)
    manifest['landingElevation'] = {
        'url': '/images/lunar-elevation.webp',
        'sourceFiles': [elevation['file'], normals],
        'outputSha256': hashlib.sha256(heatmap.read_bytes()).hexdigest(),
        'script': 'scripts/render_landing_moon.py',
        'description': 'Orthographic near-side elevation, with colors clamped at -4500 and +4500 m relative to the 1737.4 km sphere. Illustrative relief shading.',
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
