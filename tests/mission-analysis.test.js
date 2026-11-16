import test from 'node:test';
import assert from 'node:assert/strict';
import {driveTotals, envelope, nextEvent, selectedScenario} from '../src/mission-series.js';

test('time-weighted drive energy and Earth visibility retain zeros and unknown samples',()=>{
  const rows=[{t_s:1,solar_w:0,earth_visible:true},{t_s:10,solar_w:400,earth_visible:false}];
  assert.deepEqual(driveTotals(rows),{solarWh:1,contactSeconds:1});
  assert.deepEqual(driveTotals([{t_s:3,solar_w:0,earth_visible:false}]),{solarWh:0,contactSeconds:0});
  assert.deepEqual(driveTotals([{t_s:3}]),{solarWh:null,contactSeconds:null});
});

test('the plot retains extrema in timestamp order and both end samples',()=>{
  const rows=[0,1,40,2,-10,1,0].map((power,t_s)=>({power,t_s}));
  assert.deepEqual(envelope(rows,'power',1).map(r=>r.t_s),[0,2,4,6]);
});

test('crossings respect the selected instant and the bounded forecast',()=>{
  const windows=[[1800,3600],[5400,7200]];
  assert.equal(nextEvent(windows,0,7200,'Rise','Set'),'Rise in ~30 min');
  assert.equal(nextEvent(windows,1800,7200,'Rise','Set'),'Set in ~30 min');
  assert.equal(nextEvent(windows,5400,7200,'Rise','Set'),'No further crossing in this window');
});

test('only the matching landing and transfer can supply the final planning window',()=>{
  const flight={landing:{site_id:'ridge',utc:'2028-01-08T00:00:00Z'},planning_selection:{plan_id:'p',candidate_key:'k',solved_flight_sha256:'abc'}};
  const row={key:'k',site_id:'ridge',landing_utc:flight.landing.utc,flight_sha256:'abc'};
  const plan={id:'p',kind:'landing_plan',candidates:[row]};
  assert.equal(selectedScenario(flight,plan),row);
  for(const changed of [{site_id:'rim'},{landing_utc:'2028-01-02T00:00Z'},{flight_sha256:'wrong'}]){
    assert.equal(selectedScenario(flight,{...plan,candidates:[{...row,...changed}]}),null);
  }
});
