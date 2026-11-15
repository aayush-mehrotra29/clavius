import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { ElevationGrid, latLonToXYZ, xyzToLatLon, wrapLongitude } from '../src/lunar.js';

test('NASA texture convention aligns near side, far side and poles',()=>{
  const close=(a,b)=>assert.ok(Math.abs(a-b)<1e-8,`${a} ≠ ${b}`);
  for(const [lat,lon] of [[0,0],[0,90],[0,-90],[-58.4,-14.4],[-89.44,-137.2],[9.62,-20.08],[-44.45,175.9]]){
    const p=latLonToXYZ(lat,lon,1737.4),r=xyzToLatLon(...p);
    close(r.lat,lat);close(r.lon,lon);close(Math.hypot(...p),1737.4);
  }
  assert.deepEqual(latLonToXYZ(0,0),[1,0,-0]);
  close(latLonToXYZ(0,90)[2],-1);
  close(latLonToXYZ(90,0)[1],1);
});
test('height decoding uses NASA half-meter units and the 10 km unsigned offset',()=>{
  const data=new Uint16Array([20000,22000,16000,24000,18000,26000,12000,28000]);
  const grid=new ElevationGrid(data.buffer,4,2);
  assert.equal(grid.sample(45,-135),0);
  assert.equal(grid.sample(45,-45),1000);
  assert.equal(grid.sample(-45,45),-4000);
  assert.equal(grid.sample(0,-135),-500);
});
test('longitude wraps and interpolation is continuous across the texture seam',()=>{
  const data=new Uint16Array([20000,22000,24000,26000,20000,22000,24000,26000]);
  const grid=new ElevationGrid(data.buffer,4,2);
  assert.equal(grid.sample(0,-180),1500);
  assert.equal(grid.sample(0,180),1500);
  assert.equal(grid.sample(0,540),1500);
  assert.equal(wrapLongitude(222.8),-137.2);
  assert.ok(Math.abs(grid.sample(0,-180.00001)-grid.sample(0,-179.99999))<.01);
});
test('north and south edge samples clamp instead of crossing the opposite pole',()=>{
  const grid=new ElevationGrid(new Uint16Array([20000,20000,24000,24000]).buffer,2,2);
  assert.equal(grid.sample(90,0),0);
  assert.equal(grid.sample(-90,0),2000);
});
test('bundled elevation exactly matches recorded bytes and documented physical range',()=>{
  const bytes=readFileSync(new URL('../public/data/lola-elevation.bin',import.meta.url));
  const manifest=JSON.parse(readFileSync(new URL('../public/data/manifest.json',import.meta.url),'utf8'));
  assert.equal(bytes.byteLength,5760*2880*2);
  assert.equal(createHash('sha256').update(bytes).digest('hex'),manifest.elevation.outputSha256);
  const grid=new ElevationGrid(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
  for(const [lat,lon] of [[-58.4,-14.4],[-89.54,0],[8.5,31.4],[0,180],[90,0]]){
    const height=grid.sample(lat,lon);
    assert.ok(Number.isFinite(height));
    assert.ok(height>=manifest.elevation.minElevationMeters&&height<=manifest.elevation.maxElevationMeters);
  }
});
test('invalid elevation byte length is rejected',()=>{
 assert.throws(()=>new ElevationGrid(new ArrayBuffer(10),4,2),/file size/);
});

test('surface-normal provenance links to the exact active DEM and output bytes',()=>{
  const manifest=JSON.parse(readFileSync(new URL('../public/data/manifest.json',import.meta.url),'utf8'));
  const normal=manifest.derivatives.surfaceNormals;
  const bytes=readFileSync(new URL(`../public/data/${normal.file}`,import.meta.url));
  assert.equal(normal.sourceElevationSha256,manifest.elevation.outputSha256);
  assert.equal(createHash('sha256').update(bytes).digest('hex'),normal.outputSha256);
  assert.equal(normal.width,manifest.elevation.width);
  assert.equal(normal.height,manifest.elevation.height);
  assert.equal(manifest.display.defaultVerticalExaggeration,1);
});
