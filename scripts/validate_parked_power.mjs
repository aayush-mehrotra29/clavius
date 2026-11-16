// Refine only the solar sampling cadence. The same parked attitude and
// battery accounting are evaluated at both resolutions.
import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parkedBudget} from '../src/parked-power.js';
const json=path=>JSON.parse(readFileSync(path));
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const manifest=json('public/data/manifest.json').rover_drive;
const array=json('public'+manifest.sources.rover.url).solar_array;
const battery=json('public'+manifest.sources.battery.url);
const base={hours:48,capacity:battery.reference_capacity_wh,initialPct:75,load:150,
  chargeEfficiency:.95,dischargeEfficiency:.9};
const cases=[];
const limits={energy_wh:base.capacity*.01,first_unmet_s:300};
for(const [site,epochs] of Object.entries(manifest.parked_sunlight)){
  for(const [start,source] of Object.entries(epochs)){
    const raw=readFileSync('public'+source.url);
    if(sha(raw)!==source.sha256)throw new Error('Parked source identity mismatch');
    const coarse=JSON.parse(raw);
    const fine=JSON.parse(execFileSync('.venv/bin/python',['-c',
      'import sys,json; from backend.clavius.drive_environment import parked_sunlight; print(json.dumps(parked_sunlight(sys.argv[1],sys.argv[2],0,0,48,60),allow_nan=False))',
      site,start],{env:{...process.env,OPENBLAS_NUM_THREADS:'1'},maxBuffer:5e6}));
    for(const heading of [0,90,225]){
      const scenario={...base,heading};
      const a=parkedBudget(coarse,array,scenario), b=parkedBudget(fine,array,scenario);
      const residuals={};
      for(const name of ['generated','end','minimum','curtailed','unmet','losses'])residuals[name]=a[name]-b[name];
      const sameEvent=(a.firstUnmet===null)===(b.firstUnmet===null);
      const timing=a.firstUnmet!==null && b.firstUnmet!==null?a.firstUnmet-b.firstUnmet:null;
      const passed=sameEvent && Math.abs(timing??0)<=limits.first_unmet_s &&
        Object.values(residuals).every(r=>Math.abs(r)<=limits.energy_wh);
      cases.push({site,start,heading,environment_sha256:source.sha256,production_end_wh:a.end,
        reference_end_wh:b.end,production_first_unmet_s:a.firstUnmet,reference_first_unmet_s:b.firstUnmet,
        residuals_wh:residuals,first_unmet_difference_s:timing,passed});
    }
    console.log(site,start);
  }
}
const report={model:battery.model,array_model:array.model,production_step_s:300,reference_step_s:60,
  hardware_sha256:manifest.sources.rover.sha256,battery_sha256:manifest.sources.battery.sha256,scenario:base,limits,cases};
writeFileSync('docs/validation/viper-parked-sampling.json',JSON.stringify(report,null,2)+'\n');
if(cases.some(c=>!c.passed))process.exitCode=1;
