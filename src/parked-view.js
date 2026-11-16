import {readDriveSource} from './drive-sunlight.js';
import {parkedBudget} from './parked-power.js';

const chartWidth=550, chartHeight=128;
function drawCharge(canvas, rows, capacity) {
  const ctx=canvas.getContext('2d');
  if(!ctx)return;
  ctx.setTransform(2,0,0,2,0,0);
  ctx.clearRect(0,0,chartWidth,chartHeight);
  const left=39,right=chartWidth-12,top=10,bottom=chartHeight-22;
  const end=rows.at(-1)[0];
  ctx.font='11px sans-serif';ctx.fillStyle='#c3ceca';ctx.strokeStyle='#415050';ctx.lineWidth=1;
  for(const pct of [0,50,100]){
    const y=bottom-(bottom-top)*pct/100;
    ctx.fillText(pct+'%',2,y+3);ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();
  }
  ctx.fillText('0 h',left,bottom+16);ctx.fillText(end/3600+' h',right-24,bottom+16);
  ctx.beginPath();ctx.strokeStyle='#d7edb0';ctx.lineWidth=2;
  for(const [i,[time,energy]] of rows.entries()){
    const x=left+(right-left)*time/end,y=bottom-(bottom-top)*energy/capacity;
    if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);
  }
  ctx.stroke();
}

export function mountParkedPower(root, context) {
  const dialog=document.createElement('dialog');
  dialog.className='drive-info parked-dialog';
  dialog.setAttribute('aria-labelledby','parked-title');
  dialog.innerHTML=`<form><button type="button" data-close>Close</button><h2 id="parked-title">Parked power budget</h2>
  <p data-location></p><div class="parked-inputs">
  <label>Parking location<select name="position"><option value="origin">Site origin</option><option value="rover">Current rover position</option></select></label>
  <label>Start (UTC)<input name="start" type="datetime-local" list="parked-epochs" min="2000-01-01T00:00" max="2049-12-31T23:59" required></label>
  <datalist id="parked-epochs"><option value="2028-01-01T12:00"></option><option value="2028-01-21T12:00"></option><option value="2028-01-27T12:00"></option></datalist>
  <label>Duration (hours)<input name="hours" type="number" min="1" max="48" value="24" required></label>
  <label>Heading (° from site north)<input name="heading" type="number" min="0" max="360" value="90" step="any" required></label>
  <label>Initial charge (%)<input name="initial" type="number" min="0" max="100" value="75" step="any" required></label>
  <label>Assumed bus load (W)<input name="load" type="number" min="0" value="150" step="any" required></label>
  </div><details><summary>Battery assumptions</summary><p>Fixed 5,420 Wh capacity at beginning of life and 0 °C. Set a constant total load including heaters and electronics. Both efficiencies default to 100%. Temperature response, aging and restart behavior remain unresolved. <a href="/robots/viper/battery.json" target="_blank" rel="noreferrer">Battery source</a></p>
  <div class="parked-inputs"><label>Charge efficiency (%)<input name="charge" type="number" min="0.01" max="100" step="any" value="100" required></label>
  <label>Discharge efficiency (%)<input name="discharge" type="number" min="0.01" max="100" step="any" value="100" required></label></div></details>
  <button data-run type="submit">Evaluate scenario</button></form>
  <p role="status" data-status></p><section data-results hidden><h3>Estimated battery charge</h3>
  <canvas width="1100" height="256" aria-label="Estimated battery charge versus elapsed hours"></canvas>
  <dl><dt>Final charge</dt><dd data-end></dd><dt>Minimum charge</dt><dd data-min></dd>
  <dt>First unmet load</dt><dd data-first></dd><dt>Energy generated</dt><dd data-solar></dd>
  <dt>Requested load energy</dt><dd data-demand></dd><dt>Unserved load energy</dt><dd data-unmet></dd>
  <dt>Unused solar energy</dt><dd data-curtailed></dd><dt>Conversion losses</dt><dd data-loss></dd></dl><small data-source></small></section>`;
  root.append(dialog);
  const el=name=>dialog.querySelector('[data-'+name+']');
  const form=dialog.querySelector('form'), fields=form.elements;
  let position, request, cache;
  function clear(){
    request?.abort();request=null;el('results').hidden=true;el('status').textContent='';
    el('run').disabled=false;
  }
  async function evaluate(event){
    event?.preventDefault();clear();
    if(!form.reportValidity())return;
    const controller=request=new AbortController(), signal=controller.signal;
    const east=fields.position.value==='origin'?0:position.east;
    const north=fields.position.value==='origin'?0:position.north;
    const start=fields.start.value+':00Z', hours=Number(fields.hours.value);
    const key=JSON.stringify([position.site,start,east,north]);
    el('status').textContent='Calculating the solar and battery history…';el('run').disabled=true;
    try{
      if(cache?.key!==key || cache.environment.duration_hours<hours){
        const manifest=await fetch('/data/manifest.json',{signal});
        if(!manifest.ok)throw new Error('Drive dataset manifest unavailable.');
        const index=(await manifest.json()).rover_drive;
        const preset=east===0 && north===0 && index.parked_sunlight?.[position.site]?.[start];
        const params=new URLSearchParams({start_utc:start,east_m:east,north_m:north,hours});
        async function environment(){
          if(preset)return readDriveSource(preset,signal);
          const r=await fetch('/api/v1/sites/'+position.site+'/parked-sunlight?'+params,{signal});
          if(!r.ok || !r.headers.get('content-type')?.includes('application/json')){
            throw new Error('This location or UTC start needs the local simulation service and supported terrain coverage.');
          }
          return r.json();
        }
        const [sun,rover,battery]=await Promise.all([environment(),readDriveSource(index.sources.rover,signal),readDriveSource(index.sources.battery,signal)]);
        if(signal.aborted)return;
        if(sun.model!=='clavius-viper-parked-sun-v1' || sun.site_id!==position.site || sun.start_utc!==start ||
          sun.east_m!==east || sun.north_m!==north)throw new Error('Solar history does not match this scenario.');
        cache={key,environment:sun,array:rover.solar_array,battery,source:preset?'Packaged site geometry':'Live site geometry'};
      }
      const capacity=cache.battery.reference_capacity_wh;
      const budget=parkedBudget(cache.environment,cache.array,{capacity,hours,heading:Number(fields.heading.value),
        initialPct:Number(fields.initial.value),load:Number(fields.load.value),chargeEfficiency:Number(fields.charge.value)/100,
        dischargeEfficiency:Number(fields.discharge.value)/100});
      const wh=value=>value.toLocaleString(undefined,{maximumFractionDigits:1})+' Wh';
      const charge=value=>(100*value/capacity).toFixed(1)+'% · '+wh(value);
      el('end').textContent=charge(budget.end);el('min').textContent=charge(budget.minimum);
      el('first').textContent=budget.firstUnmet===null?'Load served throughout':(budget.firstUnmet/3600).toFixed(2)+' h after start';
      for(const [key,value] of Object.entries({solar:budget.generated,demand:budget.demand,unmet:budget.unmet,curtailed:budget.curtailed,loss:budget.losses}))el(key).textContent=wh(value);
      el('source').textContent=cache.source+' · '+cache.environment.step_s/60+' min solar samples · E '+east.toFixed(1)+' / N '+north.toFixed(1)+' m';
      el('status').textContent='';el('results').hidden=false;
      drawCharge(dialog.querySelector('canvas'),budget.timeline,capacity);
    }catch(error){if(!signal.aborted)el('status').textContent=error.message;}
    finally{if(request===controller)el('run').disabled=false;}
  }
  form.addEventListener('input',clear);form.addEventListener('submit',evaluate);
  el('close').onclick=()=>dialog.close();dialog.addEventListener('close',clear);
  return {
    open(){
      position=context();
      if(!position)return;
      el('location').textContent=position.name+' · fixed position and terrain-aligned attitude';
      fields.start.value=position.utc.slice(0,16);fields.heading.value=position.heading.toFixed(1);
      dialog.showModal();evaluate();
    },
    dispose(){clear();dialog.remove();}
  };
}
