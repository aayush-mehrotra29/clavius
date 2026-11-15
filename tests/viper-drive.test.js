import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import * as THREE from 'three';
import {advanceDrive,parkedDrive} from '../src/viper-drive.js';
import {applyReplay} from '../src/viper-replay.js';
import {groundHeight} from '../src/drive-ground.js';

test('ideal four-wheel drive follows straight, reverse and constant-curvature commands',()=>{
  const state=advanceDrive(parkedDrive(),1,0,10);
  assert.equal(state.east,1);assert.equal(state.north,0);assert.equal(state.wheels[0].spin,4);
  const reverse=advanceDrive(state,-1,0,10);
  assert.equal(reverse.east,0);assert.equal(reverse.distance,2);
  const arc=advanceDrive(parkedDrive(),1,1,10);
  assert.ok(arc.north>0 && arc.wheels[0].steer>0 && arc.wheels[2].steer<0);
  assert.ok(arc.wheels[0].spin<arc.wheels[1].spin);
});
test('driver uses the actual triangle under the wheels, including edges',()=>{
  const grid={count:2,spacing_m:2,half_extent_m:1,values:[0,2,4,12]};
  assert.equal(groundHeight(grid,-.5,-.5),1.5);
  assert.equal(groundHeight(grid,.5,.5),7.5);
  assert.equal(groundHeight(grid,1,1),12);
  assert.throws(()=>groundHeight(grid,-1.01,0),RangeError);
});
const dir=new URL('../public/data/drive/',import.meta.url);
const read=name=>readFileSync(new URL(name,dir));
const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const recordings=JSON.parse(read('replays.json')), imagery=JSON.parse(read('imagery.json')),catalog=JSON.parse(read('index.json'));
for(const [id,entry] of Object.entries(recordings.sites))test(id+' replay matches its terrain, images and last native pose',()=>{
  const local=catalog.sites[id].levels[0];
  assert.equal(digest(read(local.file)),entry.terrain_sha256);
  for(const texture of Object.values(imagery.sites[id]))assert.equal(digest(read(texture.file)),texture.sha256);
  const bytes=read(entry.file);assert.equal(digest(bytes),entry.sha256);assert.equal(bytes.length,401*17*28);
  const poses=new Float32Array(bytes.buffer,bytes.byteOffset,bytes.length/4),group=new THREE.Group();
  for(let i=0;i<17;i++)group.add(new THREE.Group());
  applyReplay(group,{poses,distance:new Float64Array(401)},20);
  assert.deepEqual(group.children[0].position.toArray(),entry.final_enu_m);
  for(const part of group.children)assert.ok(Math.abs(part.quaternion.length()-1)<1e-5);
});
