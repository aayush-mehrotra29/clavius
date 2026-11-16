import test from 'node:test';
import assert from 'node:assert/strict';
import {Vector3} from 'three';
import {batteryBudget,parkedAttitude,parkedBudget} from '../src/parked-power.js';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
const json=path=>JSON.parse(readFileSync(new URL('../public/'+path,import.meta.url)));
const base={capacity:100,initialPct:50,load:10,chargeEfficiency:1,dischargeEfficiency:1};
function near(value,expected){assert.ok(Math.abs(value-expected)<1e-8,value+' vs '+expected);}
function balance(result,scenario){
  near(scenario.capacity*scenario.initialPct/100 + result.generated,
    result.end+result.demand-result.unmet+result.losses+result.curtailed);
}
test('parked heading uses site north, and tilt follows the terrain gradient',()=>{
  const q=parkedAttitude(90,.25,-.1);
  const forward=new Vector3(1,0,0).applyQuaternion(q);
  near(forward.z/forward.x,.25);near(forward.y,0);
  near(new Vector3(0,0,1).applyQuaternion(q).distanceTo(new Vector3(-.25,.1,1).normalize()),0);
  near(new Vector3(1,0,0).applyQuaternion(parkedAttitude(0,0,0)).y,1);
});
test('lossy deficit empties at the expected time and records unserved bus demand',()=>{
  const scenario={...base,dischargeEfficiency:.8};
  const r=batteryBudget([[0,0],[18000,0]],scenario);
  near(r.end,0);near(r.firstUnmet,14400);near(r.unmet,10);near(r.losses,10);balance(r,scenario);
});
test('a load reversal after saturation preserves both curtailment and discharge',()=>{
  const scenario={...base,initialPct:100};
  const r=batteryBudget([[0,20],[3600,0]],scenario);
  near(r.curtailed,2.5);near(r.end,97.5);assert.equal(r.firstUnmet,null);balance(r,scenario);
});
test('a rising deficit reaches empty inside the interval and can recover later',()=>{
  const scenario={...base,initialPct:1.25};
  const r=batteryBudget([[0,10],[3600,0],[7200,20]],scenario);
  near(r.firstUnmet,1800);near(r.minimum,0);near(r.end,2.5);near(r.unmet,6.25);balance(r,scenario);
});
test('empty initial pack under sunlight serves load and accepts charge with losses',()=>{
  const scenario={...base,initialPct:0,chargeEfficiency:.75};
  const r=batteryBudget([[0,30],[3600,30]],scenario);
  near(r.end,15);near(r.losses,5);assert.equal(r.firstUnmet,null);balance(r,scenario);
});
test('all six origin presets have hash-pinned coverage for the full 48 hours',()=>{
  const index=json('data/manifest.json').rover_drive;
  const array=json('robots/viper/source.json').solar_array;
  const capacity=json('robots/viper/battery.json').reference_capacity_wh;
  const scenario={...base,capacity,hours:48,heading:90,load:150,initialPct:75};
  for(const [site,epochs] of Object.entries(index.parked_sunlight)){
    assert.equal(Object.keys(epochs).length,3);
    for(const [start,entry] of Object.entries(epochs)){
      const bytes=readFileSync(new URL('../public'+entry.url,import.meta.url));
      assert.equal(createHash('sha256').update(bytes).digest('hex'),entry.sha256);
      const series=JSON.parse(bytes);
      assert.equal(series.start_utc,start);assert.equal(series.site_id,site);
      assert.equal(series.rows.length,577);
      const result=parkedBudget(series,array,scenario);
      balance(result,scenario);assert.ok(result.end>=0 && result.end<=capacity);
    }
  }
});

test('parked sampling report reproduces from the shipped scenarios and source identities',()=>{
  const evidence=JSON.parse(readFileSync(new URL('../docs/validation/viper-parked-sampling.json',import.meta.url)));
  const manifest=json('data/manifest.json').rover_drive;
  assert.equal(evidence.hardware_sha256,manifest.sources.rover.sha256);
  assert.equal(evidence.battery_sha256,manifest.sources.battery.sha256);
  assert.equal(evidence.cases.length,18);
  const hardware=json('robots/viper/source.json').solar_array;
  for(const c of evidence.cases){
    const entry=manifest.parked_sunlight[c.site][c.start];
    assert.equal(entry.sha256,c.environment_sha256);
    const r=parkedBudget(json(entry.url.slice(1)),hardware,{...evidence.scenario,heading:c.heading});
    near(r.end,c.production_end_wh);
    assert.ok(Math.abs(r.end-c.reference_end_wh)<=evidence.limits.energy_wh);
    assert.equal(c.passed,true);
  }
});
