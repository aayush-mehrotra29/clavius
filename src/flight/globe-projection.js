// Perspective silhouette of a sphere on one screen axis, in CSS pixels.
function extent(center, depth, radius, focal, screenCenter, limit) {
  if (depth <= radius) return [0, limit];
  const denominator = depth * depth - radius * radius;
  const half = radius * Math.sqrt(denominator + center * center);
  return [
    Math.max(0, Math.floor(screenCenter + focal * (center * depth - half) / denominator)),
    Math.min(limit, Math.ceil(screenCenter + focal * (center * depth + half) / denominator)),
  ];
}

export function globeBounds(center, r, focal, width, height) {
  const [left, right] = extent(center.x, -center.z, r, focal, width / 2, width);
  const [top, bottom] = extent(-center.y, -center.z, r, focal, height / 2, height);
  return {left, top, width: right - left, height: bottom - top};
}

// Both maps are north-up, east-positive, centered on Greenwich / lunar 0°.
// In Three's default SphereGeometry local frame, north = +Y, east = -Z at 0°.
export function mapPixel(x, y, z, width, height) {
  const u = 0.5 + Math.atan2(-z, x) / (2 * Math.PI);
  const v = 0.5 - Math.asin(Math.min(1, Math.max(-1, y))) / Math.PI;
  return 4 * (Math.min(height - 1, Math.floor(v * height)) * width + Math.floor(u * width) % width);
}
