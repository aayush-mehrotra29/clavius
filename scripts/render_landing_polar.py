"""Render two static Connecting Ridge illustrations with the simulation dependencies and Pillow."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from backend.clavius.geometry import directions, epoch
from backend.clavius.terrain import site

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / 'public/images'
UTC = '2026-11-15T12:00:00'


def relief(terrain):
    # Draw back-to-front in an oblique projection. Decimation applies only to this view.
    z = terrain.local.values[::16, ::16]
    rows, cols = np.indices(z.shape)
    x = 512 + (cols - rows) * 2.42
    base = 323 + (cols + rows) * 1.0
    vertical_pixels = np.sqrt(2 * (2.42**2 - 1.0**2))
    y = base - (z + 600) / 80 * vertical_pixels * 2.4
    points = np.stack((x, y), axis=-1).astype(int).tolist()
    image = Image.new('RGBA', (1024, 800))
    draw = ImageDraw.Draw(image)
    for edge, floor, color in [
        (points[-1], base[-1], '#39334c'),
        ([row[-1] for row in points], base[:, -1], '#24253f'),
    ]:
        bottom = [(pt[0], int(b + 5)) for pt, b in zip(edge, floor)]
        draw.polygon(edge + bottom[::-1], fill=color)

    palette = np.array([[36, 38, 86], [74, 71, 150], [137, 110, 178],
                        [213, 148, 149], [255, 216, 168]])
    levels = [-525, 100, 700, 1300, 1960]
    color = np.stack([np.interp(z, levels, c) for c in palette.T], axis=-1)
    dy, dx = np.gradient(z, 80)
    light = np.clip(.96 - .62 * dx - .4 * dy, .52, 1.18)
    rgb = np.clip(color * light[..., None], 0, 255).astype(np.uint8)
    for r in range(z.shape[0] - 1):
        for c in range(z.shape[1] - 1):
            corners = [points[r][c], points[r][c+1], points[r+1][c+1], points[r+1][c]]
            heights = [z[r, c], z[r, c+1], z[r+1, c+1], z[r+1, c]]
            draw.polygon(corners, fill=tuple(rgb[r, c]))
            # Interpolate the 200 m contours across the same projected surface.
            first = 200 * int(np.ceil(min(heights) / 200))
            for level in range(first, int(max(heights)) + 1, 200):
                crossings = []
                for i, h in enumerate(heights):
                    j = (i + 1) % 4
                    if (h <= level) != (heights[j] <= level):
                        fraction = (level - h) / (heights[j] - h)
                        crossings.append(tuple(a + fraction * (b - a) for a, b in zip(corners[i], corners[j])))
                ink = tuple((rgb[r, c] * .67 + np.array([247, 232, 224]) * .33).astype(int))
                for start, end in zip(crossings[::2], crossings[1::2]):
                    draw.line([start, end], fill=ink, width=1)
    path = IMAGES / 'connecting-ridge-relief.webp'
    image.crop(image.getbbox()).save(path, quality=90)
    return path


def horizon(terrain):
    profile = terrain.horizons(0, 0, observer_height=0.5, azimuth_step_deg=1)
    geometry = directions(epoch(UTC), terrain.lat, terrain.lon, terrain.origin_height_m + .5)
    # Unwrap the part of the sky that contains both bodies. Axes are in degrees.
    def x(azimuth):
        return 58 + (azimuth - 90) * 4.2

    def y(elevation):
        return 198 - elevation * 30

    ridge = ' '.join(f'{x(a):.1f},{y(profile["elevations_deg"][a]):.1f}' for a in range(90, 271))
    content = ['<svg xmlns="http://www.w3.org/2000/svg" width="860" height="396" viewBox="0 0 860 396">',
               '<defs><linearGradient id="ground" x2="0" y2="1" gradientUnits="objectBoundingBox">'
               '<stop stop-color="#a39bd9"/><stop offset="1" stop-color="#4d5785" stop-opacity=".24"/>'
               '</linearGradient></defs>',
               f'<polygon points="{ridge} 814,347 58,347" fill="url(#ground)"/>',
               f'<polyline points="{ridge}" fill="none" stroke="#ded8fa" stroke-width="2.5"/>',
               '<g font-family="system-ui,sans-serif" font-size="19" fill="#dedff4">']
    for degrees in (-4, -2, 0, 2, 4):
        py = y(degrees)
        content += [f'<path d="M58 {py}H814" stroke="#d8d8fb" stroke-opacity=".18" stroke-dasharray="2 7"/>',
                    f'<text x="40" y="{py+6}" text-anchor="end">{degrees}°</text>']
    for bearing, label in [(90, 'East'), (180, 'South'), (270, 'West')]:
        content.append(f'<text x="{x(bearing)}" y="380" text-anchor="middle">{label}</text>')
    for name, color in [('sun', '#ffde9b'), ('earth', '#a5e1ff')]:
        body = geometry[name]
        cx, cy = x(body['azimuth_deg']), y(body['elevation_deg'])
        content += [f'<circle cx="{cx}" cy="{cy}" r="19" fill="{color}" opacity=".13"/>',
                    f'<circle cx="{cx}" cy="{cy}" r="7" fill="{color}"/>',
                    f'<text x="{cx+16}" y="{cy-10}" fill="{color}">{name.title()}</text>']
    path = IMAGES / 'connecting-ridge-horizon.svg'
    path.write_text('\n'.join(content + ['</g></svg>']))
    return path


def main():
    terrain = site()
    block, sky = relief(terrain), horizon(terrain)
    manifest_path = ROOT / 'public/data/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['landingPolarViews'] = {
        'sourceManifest': 'simulation-manifest.json',
        'script': 'scripts/render_landing_polar.py',
        'assets': [
            {'url': '/images/' + block.name, 'outputSha256': hashlib.sha256(block.read_bytes()).hexdigest(),
             'sources': ['PGDA78-Site01'], 'sampleStride': 16, 'heightScale': 2.4, 'contourIntervalM': 200},
            {'url': '/images/' + sky.name, 'outputSha256': hashlib.sha256(sky.read_bytes()).hexdigest(),
             'sources': ['PGDA78-Site01', 'PGDA90-80m', 'DE421 kernel bundle'],
             'epochUtc': UTC + 'Z', 'observerHeightM': 0.5, 'latDeg': terrain.lat, 'lonDeg': terrain.lon,
             'azimuthStepDeg': 1, 'bearingRangeDeg': [90, 270]},
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
