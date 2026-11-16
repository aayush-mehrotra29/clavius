import { groundHeight } from './drive-ground.js';

// The packaged image and the pointer ray use the same orthographic projection.
export function terrainProjection(grid, tiltDegrees) {
  const radians = tiltDegrees * Math.PI / 180;
  const c = Math.cos(radians), s = Math.sin(radians);
  function ordinate(east, north) {
    return north * c + groundHeight(grid, east, north) * s;
  }
  function northAt(east, ordinateM) {
    let lo = -grid.half_extent_m, hi = grid.half_extent_m;
    if (Math.abs(east) > hi || ordinateM < ordinate(east, lo) || ordinateM > ordinate(east, hi)) return NaN;
    // The preparation step verifies a strictly increasing ordinate at every facet.
    for (let i = 0; i < 23; i++) {
      const mid = (lo + hi) / 2;
      if (ordinate(east, mid) < ordinateM) lo = mid;
      else hi = mid;
    }
    return (lo + hi) / 2;
  }
  return { ordinate, northAt };
}

const stops = [
  [0, 38, 47, 87], [3, 54, 104, 156], [6, 57, 166, 168],
  [10, 167, 204, 140], [15, 249, 194, 99], [20, 222, 104, 82],
];
export const slopeGradient = stops.map(([deg,r,g,b]) => `rgb(${r} ${g} ${b}) ${5*deg}%`).join(', ');
export function slopePalette() {
  const colors = [[63, 63, 63]];
  for (let dn = 1; dn <= 255; dn++) {
    const angle = Math.min((dn - 1) / 4, 20);
    const i = stops.findIndex(([deg], j) => j > 0 && deg >= angle);
    const low = stops[i-1], high = stops[i];
    const t = (angle - low[0]) / (high[0] - low[0]);
    colors.push(low.slice(1).map((v,k) => Math.round(v + t * (high[k+1] - v))));
  }
  return colors;
}
