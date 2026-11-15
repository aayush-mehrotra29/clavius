import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {DriveSunlight,replaySunlight} from '../src/drive-sunlight.js';

const catalog=JSON.parse(readFileSync(new URL('../public/data/drive/sunlight.json',import.meta.url)));
const site='connecting-ridge', start=catalog.epochs[1], record=catalog.sites[site];
const context={site,start,native:true,replayHash:record.replay_sha256,elapsed:4.9,east:0,north:0};
test('packaged sunlight holds the preceding native sample only for the same run and epoch',()=>{
  const r=replaySunlight(catalog,context);
  assert.equal(r.elapsed,4);assert.deepEqual(r.sample,record.samples[start][4]);
  for(const change of [{native:false},{replayHash:'wrong'},{start:'other'},{elapsed:21}]){
    assert.equal(replaySunlight(catalog,{...context,...change}),null);
  }
});
test('an old HTTP response cannot relight a different site or time',async()=>{
  const events=[];let finish;
  const light=new DriveSunlight(r=>events.push(r),()=>new Promise(resolve=>{finish=resolve;}));
  light.update({...context,native:false},0);
  light.reset();light.catalog=catalog;light.update(context,1);
  finish({ok:true,json:async()=>({site_id:site,model:catalog.model,elapsed_s:context.elapsed,
    sample:{...record.samples[start][0],east_m:0,north_m:0}})});
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.deepEqual(events.map(r=>r?.source),[undefined,'Packaged replay']);
});
test('a missing service clears the numerical sample and exposes unavailability',async()=>{
  const events=[];
  const light=new DriveSunlight(r=>events.push(r),async()=>({ok:false}));
  light.update({...context,native:false},0);
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.deepEqual(events,[{unavailable:true}]);light.reset();
});

test('each native maneuver resolves only the sunlight sampled along its own chassis path',()=>{
  for(const [name,siteData] of Object.entries(catalog.sites)) {
    const crab=siteData.maneuvers.crab;
    const result=replaySunlight(catalog,{...context,site:name,replayHash:crab.replay_sha256,elapsed:20});
    assert.deepEqual(result.sample,crab.samples[start][20]);
    assert.ok(Math.abs(result.sample.north_m-siteData.samples[start][20].north_m)>.3);
  }
});

test('a custom native date downloads one series and samples it at the latest cursor',async()=>{
  let calls=0;const events=[];
  const ctx={...context,start:'2028-01-22T12:00:00Z'};
  const light=new DriveSunlight(r=>events.push(r),async(url)=>{
    calls++;
    assert.match(url,/drive-replay-environment/);
    return {ok:true,json:async()=>({model:catalog.model,site_id:site,start_utc:ctx.start,
      replay_sha256:ctx.replayHash,sample_interval_s:1,samples:record.samples[start]})};
  });
  light.update(ctx,0);
  await new Promise(resolve=>setTimeout(resolve,0));
  light.update({...ctx,elapsed:13},10);
  assert.equal(calls,1); assert.equal(events.at(-1).elapsed,13);
  light.reset();light.update({...ctx,elapsed:.6},11);
  assert.equal(calls,1); assert.equal(events.at(-1).elapsed,0);
});
