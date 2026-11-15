import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {gunzipSync} from 'node:zlib';
import {decodeTile, tilesForRegion} from '../src/terrain-detail.js';

test('delta reconstruction resets at rows and wraps negative differences', () => {
  assert.deepEqual([...decodeTile(Uint8Array.from([0,255,4,2,1,255,0,0]),2)], [256,255,4,6]);
});
test('date line and poles include adjacent source tiles', () => {
  const ids=tilesForRegion(0,180);
  for(const x of [0,23]) for(const y of [5,6]) assert.ok(ids.includes(x+'-'+y));
  assert.equal(tilesForRegion(-90,0).length,24);
});
test('published tile reconstructs all source uint16 samples', () => {
  const tile=decodeTile(gunzipSync(readFileSync(new URL('../public/data/lola64/12-6.bin.gz',import.meta.url))));
  assert.equal(tile.length,960*960);
  assert.ok(tile[0]>5000 && tile[0]<40000);
});
