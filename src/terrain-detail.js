import {wrapLongitude} from './lunar.js';

const tileSize = 960, columns = 24, rows = 12;
const width = tileSize * columns, height = tileSize * rows;
const stepDegrees = 15;

export function tilesForRegion(lat, lon) {
  // The farthest point in the 400 km tangent patch is a corner. Add one
  // source cell on every side for bilinear interpolation at the boundary.
  const radius = Math.atan(Math.SQRT2 * 200 / 1737.4) * 180 / Math.PI + 2 / 64;
  const touchesPole = Math.abs(lat) + radius >= 90;
  const lonRadius = touchesPole ? 180 : Math.asin(Math.sin(radius * Math.PI/180) / Math.cos(lat * Math.PI/180)) * 180 / Math.PI;
  const y0 = Math.max(0, Math.floor((90 - lat - radius) / stepDegrees));
  const y1 = Math.min(rows - 1, Math.floor((90 - lat + radius) / stepDegrees));
  const ids = new Set();
  for (let y = y0; y <= y1; y++) {
    for (let x = Math.floor((lon - lonRadius + 180)/stepDegrees); x <= Math.floor((lon + lonRadius + 180)/stepDegrees); x++) {
      ids.add(((x % columns + columns) % columns) + '-' + y);
    }
  }
  return [...ids];
}

export function decodeTile(bytes, size = tileSize) {
  const count = size * size;
  if (bytes.length !== count * 2) throw new Error('Incomplete lunar elevation tile.');
  const values = new Uint16Array(count);
  for (let i = 0; i < count; i++) {
    const previous = i % size === 0 ? 0 : values[i-1];
    values[i] = previous + bytes[i] + 256 * bytes[count + i];
  }
  return values;
}

export async function loadRegionalGrid(lat, lon, signal) {
  const tiles = new Map(), queue = tilesForRegion(lat, lon);
  async function load() {
    while (queue.length) {
      const id = queue.pop();
      const response = await fetch('/data/lola64/' + id + '.bin.gz', {signal});
      if (!response.ok) throw new Error('Regional DEM download failed.');
      const bytes = new Uint8Array(await response.arrayBuffer());
      // Some hosts decode .gz automatically using Content-Encoding.
      const raw = bytes[0] === 31 && bytes[1] === 139
        ? new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer())
        : bytes;
      tiles.set(id, decodeTile(raw));
    }
  }
  await Promise.all(Array.from({length: Math.min(4,queue.length)}, load));
  const array = Array(columns*rows);
  for (const [id,tile] of tiles) {
    const [col,row] = id.split('-').map(Number);
    array[row*columns+col] = tile;
  }
  function at(x,y) {
    x=(x+width)%width;
    const tile=array[Math.floor(y/tileSize)*columns+Math.floor(x/tileSize)];
    return tile[(y%tileSize)*tileSize+x%tileSize];
  }
  return {sample(lat,lon) {
    const x=(wrapLongitude(lon)+180)*64-.5, y=Math.max(0,Math.min(height-1,(90-lat)*64-.5));
    const i=Math.floor(x),j=Math.floor(y), dx=x-i,dy=y-j,next=Math.min(j+1,height-1);
    const a=at(i,j)*(1-dx)+at(i+1,j)*dx, b=at(i,next)*(1-dx)+at(i+1,next)*dx;
    return (a*(1-dy)+b*dy)*.5-10000;
  }};
}
