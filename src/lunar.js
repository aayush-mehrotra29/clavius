export const MOON_RADIUS_KM = 1737.4;
export const DEG = Math.PI / 180;
export const regions = [
  { id: 'clavius', name: 'Clavius', kind: 'Impact crater', lat: -58.4, lon: -14.4, group: 'near', diameter: '225 km', description: 'An ancient southern highland crater, distinguished by an arc of smaller craters across its broad floor.' },
  { id: 'shackleton', name: 'Shackleton', kind: 'South polar crater', lat: -89.54, lon: 0, group: 'polar', diameter: '21 km', description: 'A crater at the lunar south pole. Its rim and shadowed interior are important targets for polar exploration.' },
  { id: 'connecting-ridge', name: 'Connecting Ridge', kind: 'Polar exploration region', lat: -89.44, lon: -137.2, group: 'polar', diameter: null, description: 'A south polar ridge near Shackleton. The planning handoff identifies this region for future high-resolution terrain integration.' },
  { id: 'tycho', name: 'Tycho', kind: 'Impact crater', lat: -43.31, lon: -11.36, group: 'near', diameter: '85 km', description: 'A prominent young impact crater in the southern highlands, surrounded by an extensive bright ray system.' },
  { id: 'tranquillitatis', name: 'Mare Tranquillitatis', kind: 'Lunar mare', lat: 8.5, lon: 31.4, group: 'near', diameter: null, description: 'The Sea of Tranquility: a broad basaltic plain on the near side, home to the Apollo 11 landing region.' },
  { id: 'copernicus', name: 'Copernicus', kind: 'Impact crater', lat: 9.62, lon: -20.08, group: 'near', diameter: '93 km', description: 'A terraced impact crater on the eastern edge of Oceanus Procellarum, with a striking system of ejecta rays.' },
  { id: 'tsiolkovskiy', name: 'Tsiolkovskiy', kind: 'Far-side impact crater', lat: -20.4, lon: 128.9, group: 'far', diameter: '185 km', description: 'A far-side crater with a dark, mare-filled floor and a bright central peak.' },
  { id: 'von-karman', name: 'Von Kármán', kind: 'Far-side impact crater', lat: -44.45, lon: 175.9, group: 'far', diameter: '180 km', description: 'An impact crater within the South Pole–Aitken basin, and the landing region of Chang’e 4.' },
];
export const wrapLongitude = lon => ((lon + 180) % 360 + 360) % 360 - 180;
export function latLonToXYZ(lat, lon, radius = 1) {
  const p = lat * DEG, l = lon * DEG;
  return [radius * Math.cos(p) * Math.cos(l), radius * Math.sin(p), -radius * Math.cos(p) * Math.sin(l)];
}
export function xyzToLatLon(x, y, z) {
  const r = Math.hypot(x, y, z);
  return { lat: Math.asin(Math.max(-1, Math.min(1, y / r))) / DEG, lon: wrapLongitude(Math.atan2(-z, x) / DEG) };
}
export function formatCoordinate(value, latitude = true) {
  return `${Math.abs(value).toFixed(2)}° ${latitude ? (value < 0 ? 'S' : 'N') : (value < 0 ? 'W' : 'E')}`;
}
export class ElevationGrid {
  constructor(buffer, width = 5760, height = 2880) {
    if (buffer.byteLength !== width * height * 2) throw new Error('Unexpected LOLA elevation file size.');
    // The checked-in asset is explicitly little endian, independent of host byte order.
    const endian = new Uint8Array(new Uint16Array([1]).buffer)[0] === 1;
    this.data = endian ? new Uint16Array(buffer) : Uint16Array.from({length: width * height}, (_, i) => new DataView(buffer).getUint16(i * 2, true));
    this.width = width; this.height = height;
  }
  sample(lat, lon) {
    const x = (wrapLongitude(lon) + 180) / 360 * this.width - .5;
    const y = Math.max(0, Math.min(this.height - 1, (90 - lat) / 180 * this.height - .5));
    const x0 = Math.floor(x), y0 = Math.floor(y), dx = x - x0, dy = y - y0;
    const at = (xx, yy) => this.data[yy * this.width + ((xx % this.width) + this.width) % this.width];
    const a = at(x0, y0) * (1 - dx) + at(x0 + 1, y0) * dx;
    const b = at(x0, Math.min(y0 + 1, this.height - 1)) * (1 - dx) + at(x0 + 1, Math.min(y0 + 1, this.height - 1)) * dx;
    return (a * (1 - dy) + b * dy) * .5 - 10000;
  }
}
