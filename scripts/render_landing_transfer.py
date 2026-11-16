"""Draw the landing atlas transfer from the flight planner and its pinned SPICE kernels."""
import hashlib
import json
from pathlib import Path

import numpy as np

from backend.clavius.flight import FlightRequest, plan_flight, unit

ROOT = Path(__file__).resolve().parents[1]


def main():
    request = FlightRequest(site_id='connecting-ridge', departure_utc='2028-01-01T00:00:00Z',
                            transfer_hours=96)
    run = plan_flight(request, lambda *_: None, lambda: False)
    trace = run['trajectory_3d']
    moon = np.asarray(trace['moon_coords_km'])
    # Orthographic plane through Earth and the Moon at departure and touchdown.
    horizontal = unit(moon[-1])
    vertical = unit(moon[0] - horizontal * (moon[0] @ horizontal))
    basis = np.stack((horizontal, vertical))
    scale = .00112
    origin = np.array([59., 381.])

    def project(points):
        return origin + (points @ basis.T) * [scale, -scale]

    def path(points):
        return ' '.join(f'{x:.2f},{y:.2f}' for x, y in points)

    moon_xy = project(moon)
    ship_xy = project(np.asarray(trace['spacecraft_coords_km']))
    x0, y0 = moon_xy[0]
    x1, y1 = moon_xy[-1]
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 454">
  <title>Earth to Connecting Ridge, 1–5 January 2028</title>
  <desc>The simulated spacecraft travels from Earth to meet the moving Moon. Both tracks use the same projection and scale. Body markers are enlarged.</desc>
  <g fill="none" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="{path(moon_xy)}" stroke="#a7dcd9" stroke-width="2.6" stroke-dasharray="6 6"/>
    <polyline points="{path(ship_xy)}" stroke="#ffe4b6" stroke-width="3"/>
    <path d="M59 292 h{100000 * scale:.0f} m-112 -4 v8 m112 -8 v8" stroke="#b3bbd4"/>
    <path d="M60 65 h27" stroke="#ffe4b6" stroke-width="3"/>
    <path d="M60 95 h27" stroke="#a7dcd9" stroke-width="3" stroke-dasharray="5 5"/>
  </g>
  <circle cx="59" cy="381" r="9" fill="#92bbfb"/>
  <circle cx="{x0:.2f}" cy="{y0:.2f}" r="6" fill="#a7dcd9"/>
  <circle cx="{x1:.2f}" cy="{y1:.2f}" r="8" fill="#a7dcd9" stroke="#ffe4b6" stroke-width="2"/>
  <g fill="#f2f2ff" font-family="system-ui, sans-serif" font-size="17">
    <text x="99" y="71">Simulated flight</text>
    <text x="99" y="101">Moon · DE421</text>
    <text x="{x0 - 11:.2f}" y="{y0 - 10:.2f}" text-anchor="end">Moon at departure</text>
    <text x="{x1:.2f}" y="{y1 + 31:.2f}" text-anchor="middle">Moon at arrival</text>
    <text x="59" y="413" text-anchor="middle">Earth</text>
    <text x="59" y="282" font-size="14" fill="#d0d4e4">100,000 km</text>
  </g>
</svg>
'''
    output = ROOT / 'public/images/connecting-ridge-transfer.svg'
    output.write_text(svg)
    manifest_path = ROOT / 'public/data/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['landingTransfer'] = {
        'url': '/images/' + output.name, 'outputSha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'script': 'scripts/render_landing_transfer.py', 'sourceManifest': 'simulation-manifest.json',
        'flightRequest': request.model_dump(), 'touchdownUtc': run['landing']['utc'],
        'sourceHashes': run['sources'], 'samples': len(moon),
        'description': 'Clavius simulated spacecraft and DE421 Moon positions in Earth-centered J2000, projected onto the plane of the two endpoint Moon vectors. Uniform distance scale, enlarged body markers.'
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
