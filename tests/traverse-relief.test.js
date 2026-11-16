import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { terrainProjection, slopePalette } from '../src/traverse-relief.js';

const data = new URL('../public/data/', import.meta.url);
const read = path => readFileSync(new URL(path,data));
const json = path => JSON.parse(read(path));
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const catalog = json('drive/traverse-relief.json');
const terrain = json('drive/index.json');

test('both manifests pin the traverse layers', () => {
  for (const file of ['manifest.json','simulation-manifest.json']) {
    assert.equal(json(file).traverse_relief.sha256, hash(read('drive/traverse-relief.json')));
  }
});
for (const [id,site] of Object.entries(catalog.sites)) {
  test(id+' relief, slopes and waypoint picking share the nominal surface', () => {
    const grid = terrain.sites[id].levels.find(level => level.level === 'drive');
    const raw = read('drive/'+grid.file);
    assert.equal(site.terrain_sha256, hash(raw));
    const frame = terrainProjection({...grid,values:new Float32Array(Uint8Array.from(raw).buffer)}, catalog.tilt_deg);
    for (const east of [-12, -3.7, 0, 4, 12]) {
      for (const north of [-12, -.4, 0, 6.3, 12]) {
        const v = frame.ordinate(east,north);
        assert.ok(Math.abs(frame.northAt(east,v)-north) < .001);
      }
    }
    assert.ok(Number.isNaN(frame.northAt(2000,0)));
    for (const layer of [site.relief,site.slope]) {
      const png = read('drive/'+layer.file);
      assert.equal(hash(png),layer.sha256);
      assert.equal(png.readUInt32BE(16),2*catalog.half_extent_m/catalog.display_pitch_m);
      assert.equal(png.readUInt32BE(20),png.readUInt32BE(16));
    }
  });
}
test('missing slope has its own color and the legend saturates at 20 degrees', () => {
  const colors = slopePalette();
  assert.notDeepEqual(colors[0],colors[1]);
  assert.deepEqual(colors[81],colors[255]);
  assert.notDeepEqual(colors[41],colors[81]);
});
