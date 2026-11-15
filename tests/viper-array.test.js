import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {Quaternion, Vector3} from 'three';
import {arrayPower, manualBodyToEnu, replayArrayEnergy} from '../src/viper-array.js';

const json = name => JSON.parse(readFileSync(new URL('../public/'+name,import.meta.url)));
const hardware = json('robots/viper/source.json').solar_array;
const sample = (direction, fraction=1, distance=149597870.7) => ({
  sun_site_enu: direction, disk_fraction:fraction, sun_distance_km:distance
});
const identity = new Quaternion();
function near(value, expected) {assert.ok(Math.abs(value-expected)<1e-8, value+' vs '+expected);}

test('three one-sided faces match cardinal illumination and the published corner configuration',()=>{
  for (const [name,dir] of Object.entries(hardware.faces)) {
    const watts=arrayPower(hardware,sample(dir),identity);
    near(watts.total,320); near(watts.faces[name],320);
  }
  near(arrayPower(hardware,sample([1,0,0]),identity).total,0);
  const corner=arrayPower(hardware,sample([-Math.SQRT1_2,Math.SQRT1_2,0]),identity);
  near(corner.total,320*Math.SQRT2);
  assert.ok(Math.abs(corner.total-hardware.rating_source.corner_reference_w)<3);
  near(arrayPower(hardware,sample([0,-1,0],.5,2*149597870.7),identity).total,40);
  near(arrayPower(hardware,sample([0,1,0],0),identity).total,0);
  assert.equal(arrayPower(hardware,{...sample([1,0,0]),sun_distance_km:null},identity),null);
});

test('manual scene and native ENU orientations give the same power with yaw, pitch and roll',()=>{
  const body=new Quaternion().setFromAxisAngle(new Vector3(1,2,3).normalize(),1.31);
  const scene=new Quaternion().setFromAxisAngle(new Vector3(1,0,0),-Math.PI/2).multiply(body);
  const sun=sample(new Vector3(-1,0,0).applyQuaternion(body).toArray());
  for(const orientation of [body,manualBodyToEnu(scene,new Quaternion())]){
    const watts=arrayPower(hardware,sun,orientation);
    near(watts.faces.aft,320);near(watts.total,320);
  }
});

test('scrubbing integrates the lit intervals without smearing a held horizon crossing',()=>{
  const poses=new Float32Array(41*119);
  for(let i=0;i<41;i++)poses[i*119+6]=1;
  const energy=replayArrayEnergy(hardware,[sample([0,1,0]),sample([0,1,0],0),sample([0,1,0])],poses);
  near(energy(2),320/3600); near(energy(.375),.375*320/3600);
  near(energy(1.5),320/3600); near(energy(0),0);
});

test('all packaged traverses produce finite cumulative Wh, including the shadowed ridge epoch',()=>{
  const replays=json('data/drive/replays.json'), sunlight=json('data/drive/sunlight.json');
  const audit=JSON.parse(readFileSync(new URL('../docs/validation/viper-array-sampling.json',import.meta.url)));
  for(const [filename,hash] of [['data/drive/sunlight.json',audit.sunlight_sha256],['robots/viper/source.json',audit.hardware_sha256]]) {
    const bytes=readFileSync(new URL('../public/'+filename,import.meta.url));
    assert.equal(createHash('sha256').update(bytes).digest('hex'),hash);
  }
  assert.equal(audit.cases.length,12);
  for(const [name,primary] of Object.entries(replays.sites)){
    for(const maneuver of ['turn','crab']){
      const trace=maneuver==='turn'?primary:primary.maneuvers.crab;
      const bytes=readFileSync(new URL('../public/data/drive/'+trace.file,import.meta.url));
      const poses=new Float32Array(bytes.buffer,bytes.byteOffset,bytes.length/4);
      const site=sunlight.sites[name], light=maneuver==='turn'?site:site.maneuvers.crab;
      for(const [epoch,samples] of Object.entries(light.samples)){
        const energy=replayArrayEnergy(hardware,samples,poses);
        let last=0;
        for(let t=0;t<=20;t+=.25){const value=energy(t);assert.ok(value>=last);last=value;}
        const result=audit.cases.find(c=>c.trace_sha256===trace.sha256 && c.start_utc===epoch);
        near(last,result.held_wh);
        assert.ok(Math.abs(last-result.refined_wh)<=audit.energy_tolerance_wh);
        assert.ok(result.max_point_difference_w<=audit.point_tolerance_w);
        if(name==='connecting-ridge' && epoch.startsWith('2028-01-21'))near(last,0);
        if(epoch.startsWith('2028-01-01'))assert.ok(last>0);
      }
    }
  }
});
