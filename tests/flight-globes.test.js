import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';
import {readFileSync} from 'node:fs';
import {globeBounds, mapPixel} from '../src/flight/globe-projection.js';

test('software globe maps prime meridian, east, poles and seam to the same UVs as SphereGeometry', () => {
  const cell = (...direction) => mapPixel(...direction, 360, 180) / 4;
  assert.equal(cell(1, 0, 0), 90*360 + 180);
  assert.equal(cell(0, 0, -1), 90*360 + 270);
  assert.equal(cell(-1, 0, 0), 90*360);
  assert.equal(cell(-1, 0, -0), 90*360);
  assert.equal(Math.floor(cell(0, 1, 0)/360), 0);
  assert.equal(Math.floor(cell(0, -1, 0)/360), 179);
  assert.deepEqual(globeBounds({x: 0,y: 0,z: -10}, 2, 100, 200, 200),
    {left: 79, top: 79, width: 42, height: 42});
});

test('both flight maps match their recorded NASA asset hashes', () => {
  const {flightGlobes} = JSON.parse(readFileSync('public/data/manifest.json'));
  for (const map of [flightGlobes.earth, flightGlobes.moon]) {
    assert.equal(createHash('sha256').update(readFileSync('public/data/'+map.file)).digest('hex'), map.sha256);
  }
});
