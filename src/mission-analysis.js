import './mission-analysis.css';
import { driveTotals, envelope, nextEvent, selectedScenario } from './mission-series.js';
import { sky } from './landing-planner.js';

const fmt = (v, digits=1) => Number.isFinite(v) ? v.toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits}) : '—';
const unit = (v,u,d=1) => Number.isFinite(v) ? fmt(v,d)+' '+u : 'Unavailable';
const raw = id => '/api/v1/runs/'+encodeURIComponent(id);
const stat = (label,value) => `<div><span>${label}</span><strong>${value}</strong></div>`;
const tabs = (labels,name) => `<div class="ma-switch" role="group" aria-label="${name}">${labels.map((l,i)=>`<button type="button" aria-pressed="${i===0}">${l}</button>`).join('')}</div>`;
function bindSwitch(host, change) {
  const buttons=host.querySelectorAll('.ma-switch button');
  buttons.forEach((button,i)=>button.onclick=()=>{
    buttons.forEach((b,k)=>b.setAttribute('aria-pressed',String(i===k)));
    change(i);
  });
}

function lineChart(rows,key,u,index) {
  const pts=envelope(rows,key);
  if(!pts.length)return '<p>This channel was not recorded.</p>';
  const vals=pts.map(r=>r[key]);
  let low=Math.min(...vals), high=Math.max(...vals);
  if(low===high){const pad=Math.max(Math.abs(low)*.01,.01);low-=pad;high+=pad;}
  const duration=rows.at(-1).t_s;
  const x=t=>60+372*t/(duration||1),y=v=>125-100*(v-low)/(high-low);
  const d=pts.map((r,i)=>(i?'L':'M')+x(r.t_s).toFixed(2)+' '+y(r[key]).toFixed(2)).join(' ');
  const selected=rows[index];
  return `<svg viewBox="0 0 448 152" role="img" aria-label="${key} over ${fmt(duration)} seconds. Range ${fmt(Math.min(...vals),3)} to ${fmt(Math.max(...vals),3)} ${u}.">
    ${[low,(low+high)/2,high].map(v=>`<path d="M60 ${y(v)}H432" class="ma-gridline"/><text x="54" y="${y(v)+4}" text-anchor="end">${fmt(v,high-low<.15?3:high-low<3?2:1)}</text>`).join('')}
    <path d="${d}" class="ma-series"/><path d="M${x(selected.t_s)} 20V125" class="ma-cursor"/>
    ${Number.isFinite(selected[key])?`<circle cx="${x(selected.t_s)}" cy="${y(selected[key])}" r="3.8" fill="#fff"/>`:''}
    <text x="60" y="146">0 s</text><text x="432" y="146" text-anchor="end">${fmt(duration,1)} s</text></svg>`;
}

function routeChart(run) {
  const origin=run.landing, goals=run.request.waypoints, trace=run.trace;
  const points=[origin,...goals,...trace];
  let left=Infinity,right=-Infinity,bottom=Infinity,top=-Infinity;
  for(const p of points){
    left=Math.min(left,p.east_m);right=Math.max(right,p.east_m);bottom=Math.min(bottom,p.north_m);top=Math.max(top,p.north_m);
  }
  const scale=Math.min(370/Math.max(right-left,1),125/Math.max(top-bottom,1));
  const xy=p=>[222+(p.east_m-(left+right)/2)*scale,95-(p.north_m-(bottom+top)/2)*scale];
  const path=points=>points.map(p=>xy(p).map(v=>v.toFixed(2)).join(',')).join(' ');
  const reached=new Set(run.route_events.map(e=>e.waypoint));
  const [ox,oy]=xy(origin);
  const svg=`<svg viewBox="0 0 448 181" role="img" aria-label="Planned waypoints and simulated rover ground track. North is up.">
    <text x="14" y="22">N ↑</text><polyline points="${path([origin,...goals])}" class="ma-planned"/>
    <polyline points="${path(trace)}" class="ma-series"/>
    <circle cx="${ox}" cy="${oy}" r="4" fill="white"/><text x="${ox}" y="${oy+17}" text-anchor="middle">Landing</text>
    ${goals.map((p,i)=>{const [x,y]=xy(p);return `<circle cx="${x}" cy="${y}" r="8" fill="${reached.has(i+1)?'#326bf0':'#242424'}" stroke="#888"/><text x="${x}" y="${y+3.5}" text-anchor="middle" class="ma-point">${i+1}</text>`;}).join('')}
    <circle class="ma-rover" r="4.5" fill="#75acff" stroke="white"/></svg>`;
  return {svg,xy};
}

function timeBands(label,windows,duration,hours) {
  return `<div class="ma-band"><span>${label}</span><div>${windows.map(([a,b])=>
    `<i style="left:${100*a/duration}%;width:${100*(b-a)/duration}%"></i>`).join('')}</div><b>${unit(hours,'h')}</b></div>`;
}

function bindPlanning(host,plan,row,safe,dateLabel) {
  const site=plan.sites[row.site_id], hours=plan.request.surface_hours, duration=hours*3600;
  const intervals=rows=>rows.length?rows.map(([a,b])=>`<li>${dateLabel(a)} – ${dateLabel(b)}</li>`).join(''):'<li>None in this window</li>';
  const mount=plan.request.array_mount;
  host.innerHTML=`<article class="ma-card"><h2>Sky at the landing site</h2><p>${hours} hours from touchdown · 0.5 m observer</p>
    <div class="ma-sky"></div><output class="ma-sky-reading"></output>
    <input type="range" min="0" max="${row.samples.length-1}" value="0" aria-label="Time in landing window">
    <div class="ma-next"></div>${timeBands('Sun above terrain',row.sun_windows_s,duration,row.sun_hours)}${timeBands('Earth in view',row.contact_windows_s,duration,row.contact_hours)}
    <details><summary>Visibility windows</summary><p>Crossings are interpolated between ${row.sample_step_s/60}-minute samples. Short windows can be missed.</p>
    <h3>Sunlight</h3><ul>${intervals(row.sun_windows_utc)}</ul><h3>Earth contact</h3><ul>${intervals(row.contact_windows_utc)}</ul></details></article>
    <article class="ma-card ma-alternatives"><h2>Landing alternatives</h2><p>${plan.candidates.length} site/date options · ${safe(mount)} panel · ranked ${plan.ranked_keys.indexOf(row.key)+1} under ${safe(plan.request.priority.replace('_',' '))} priority</p>
    ${tabs(['Solar energy','Earth contact','Δv'],'Compare landing metric')}<div class="ma-bars"></div>
    <details><summary>Selected landing</summary><div class="ma-facts">
    ${stat('Sun above terrain',unit(row.sun_hours,'h'))}${stat('Equivalent full sunlight',unit(row.equivalent_sun_hours,'h'))}
    ${stat('Incident solar energy',unit(row[mount+'_solar_wh_m2'],'Wh/m²'))}${stat('Earth in view',unit(row.contact_hours,'h'))}
    ${stat('Longest Earth outage',unit(row.longest_outage_hours,'h'))}${stat('Local slope',unit(row.slope_deg,'°'))}
    ${stat('Height RMS',unit(site.height_rms_m,'m',2))}${stat('Native cell laser returns',fmt(site.native_return_count,0))}
    </div><a href="/app?plan=${encodeURIComponent(plan.id)}&option=${encodeURIComponent(row.key)}">Explore landing options</a></details></article>`;
  const slider=host.querySelector('input');
  function updateSky(){
    const s=row.samples[slider.value];host.querySelector('.ma-sky').innerHTML=sky(site,s);
    host.querySelector('.ma-sky-reading').textContent=`${dateLabel(s.utc)} · Sun ${fmt(s.sun_elevation_deg,2)}° (${fmt(100*s.disk_fraction,0)}% visible) · Earth ${fmt(s.earth_elevation_deg,2)}° (${s.earth_center_clearance_deg>0?'in view':'below terrain'})`;
    host.querySelector('.ma-next').innerHTML=`<span>Sun · ${nextEvent(row.sun_windows_s,s.t_s,duration,'Sunrise','Sunset')}</span><span>Earth · ${nextEvent(row.contact_windows_s,s.t_s,duration,'Earthrise','Earthset')}</span>`;
  }
  slider.oninput=updateSky;updateSky();
  const alternatives=host.querySelector('.ma-alternatives');
  const metrics=[[mount+'_solar_wh_m2','Wh/m²'],['contact_hours','h'],['delta_v_km_s','km/s']];
  function bars(i){
    const [key,u]=metrics[i];
    const max=Math.max(0,...plan.candidates.map(r=>r[key]).filter(Number.isFinite));
    alternatives.querySelector('.ma-bars').innerHTML=plan.candidates.map(r=>{
      const value=r[key], selected=r.key===row.key;
      return `<div class="ma-bar-row ${selected?'chosen':''}"><span>${safe(r.name)} · ${new Date(r.landing_utc).toLocaleDateString('en-GB',{timeZone:'UTC',day:'numeric',month:'short',year:'numeric'})}${selected?' · selected':''}</span>
        <b>${unit(value,u,i===2?2:1)}</b><div class="ma-track"><i style="width:${max&&Number.isFinite(value)?100*value/max:0}%"></i></div>
        ${r.unavailable||r.exclusions?.length?`<small>${safe(r.unavailable||r.exclusions.join(' · '))}</small>`:''}</div>`;
    }).join('');
  }
  bindSwitch(alternatives,bars);bars(0);
}

export function renderMissionAnalysis(host,{run,flight,plan,message,safe,dateLabel}) {
  const {metrics:m,trace,landing}=run, row=plan && selectedScenario(flight,plan);
  const selection=flight.planning_selection;
  const outcome=run.task_completed?(run.request.task==='science'?'Science dwell completed':'Parking dwell completed'):'Task unfinished';
  const reached=new Set(run.route_events.map(e=>e.waypoint)).size;
  const map=routeChart(run);
  const drive=driveTotals(trace);
  const sources=run.sources ?? {};
  const hashes=Object.entries({...sources.terrain_sha256,...sources.kernel_sha256});
  const maneuvers=Object.entries(flight.maneuvers_km_s), largest=Math.max(...maneuvers.map(([,v])=>v));
  const auditLinks=`<a href="/data/horizons-geometry.json" target="_blank" rel="noopener">Horizons direction checks</a> · <a href="/data/illumination-validation.json" target="_blank" rel="noopener">Observed shadow comparisons</a>`;
  host.innerHTML=`<header class="ma-heading"><div><h1>Mission analysis</h1><p>${safe(landing.name)} · Touchdown ${dateLabel(landing.utc)}</p></div><span class="ma-result">${outcome}</span></header>
    <div class="ma-totals">
      ${selection?stat('Earth in view · '+selection.surface_hours+' h window',unit(selection.contact_hours,'h')):stat('Flight Δv',unit(flight.total_delta_v_km_s,'km/s',2))}
      ${selection?stat('Incident energy · '+safe(selection.array_mount)+' panel',unit(selection.incident_wh_m2,'Wh/m²')):stat('Minimum battery',unit(m.minimum_battery_wh,'Wh',2))}
      ${stat('Distance driven',unit(m.distance_m,'m',2))}${stat('Waypoints confirmed',reached+' / '+run.request.waypoints.length)}
    </div>${run.issues.length?`<div class="ma-issues">${run.issues.map(v=>`<p>${safe(v)}</p>`).join('')}</div>`:''}
    <div class="ma-grid ma-planning"></div>
    <div class="ma-grid"><article class="ma-card ma-route"><h2>Rover traverse</h2><p>${safe(run.robot_snapshot.model.name)} · ${safe(run.engine.name)} · ${fmt(m.duration_s,1)} s</p>
      ${map.svg}<div class="ma-key"><span>Requested path</span><span>Simulated track</span></div>
      <details><summary>Waypoint events</summary><ul>${run.request.waypoints.map((p,i)=>{
        const event=run.route_events.find(e=>e.waypoint===i+1);
        return `<li>${i+1} · E ${fmt(p.east_m)} m / N ${fmt(p.north_m)} m · ${event?'Reached at '+unit(event.t_s,'s'):'No arrival event'}</li>`;
      }).join('')}</ul><p>Final task · ${safe(run.request.task)} · requested dwell ${run.request.dwell_s} s</p></details></article>
      <article class="ma-card ma-telemetry"><h2>Rover telemetry</h2><p>Inspect the recorded drive and its position on the route.</p>
      ${tabs(['Battery','Solar','Speed','Roll','Pitch'],'Telemetry channel')}<div class="ma-chart"></div>
      <div class="ma-reading"><output></output><span></span></div><input type="range" aria-label="Traverse sample" min="0" max="${trace.length-1}" value="${trace.length-1}">
      <details><summary>Run measurements</summary><div class="ma-facts">
      ${stat('Net displacement',unit(m.displacement_m,'m',2))}${stat('Peak absolute roll',unit(m.maximum_roll_deg,'°',2))}
      ${stat('Peak absolute pitch',unit(m.maximum_pitch_deg,'°',2))}${stat('Max. absolute slip ratio',fmt(m.maximum_abs_slip_ratio,2))}
      ${stat('Solar input during drive',unit(drive.solarWh,'Wh',4))}${stat('Earth in view during drive',unit(drive.contactSeconds,'s',1))}
      ${stat('Mobility bus energy',unit(m.mobility_bus_energy_wh,'Wh',3))}${stat('Minimum battery',unit(m.minimum_battery_wh,'Wh',2))}${stat('Battery capacity',unit(m.battery_capacity_wh,'Wh'))}
      ${stat('Arrival tolerance',unit(m.arrival_tolerance_m,'m',2))}${stat('Rigid contact observed',m.contacts_observed===true?'Yes':m.contacts_observed===false?'No':'Unavailable')}
      </div></details></article>
      <article class="ma-card"><h2>Flight budget</h2><p>From a 200 km Earth parking orbit to touchdown.</p>
      <div class="ma-bars">${maneuvers.map(([k,v])=>`<div class="ma-bar-row"><span>${safe(k.replaceAll('_',' '))}</span><b>${unit(v,'km/s',3)}</b><div class="ma-track"><i style="width:${largest?100*v/largest:0}%"></i></div></div>`).join('')}</div>
      <div class="ma-facts">${stat('Total Δv',unit(flight.total_delta_v_km_s,'km/s',3))}${stat('Departure',dateLabel(flight.departure_utc))}${stat('Total flight time',unit(flight.transfer_s/3600,'h',2))}</div>
      <details><summary>Flight assumptions</summary><p>${safe(flight.model)}</p></details></article>
      <article class="ma-card"><h2>Data and evidence</h2><p>Source identities and model limits for this mission.</p>
      <details><summary>Surface and imagery</summary><p>Local 5 m LOLA elevations drive contact and near-field horizons. The 80 m regional grid extends horizon coverage. Stereo relief and orthoimagery are planning display layers.</p>
      <a href="https://pgda.gsfc.nasa.gov/products/78" target="_blank" rel="noopener">PGDA 78</a> · <a href="https://pgda.gsfc.nasa.gov/products/90" target="_blank" rel="noopener">PGDA 90</a> · <a href="/data/drive/traverse-relief.json" target="_blank" rel="noopener">LROC display sources</a></details>
      <details><summary>Sun, Earth and validation</summary><p>DE421 SPICE geometry in ${safe(sources.frame ?? 'an unrecorded lunar frame')}. Earth contact measures geometric center visibility. Link margin, station access and relay coverage require additional modeling. Shadow comparisons retain unresolved terrain and sampling errors.</p>${auditLinks}</details>
      <details><summary>Rover and energy assumptions</summary><p>Rigid ground contact, assumed friction and a declared rover power profile. Incident energy at the landing site is per unit area. Rover solar watts include array orientation and the visible solar disk.</p></details>
      <details><summary>Recorded source hashes</summary>${hashes.map(([k,v])=>`<p>${safe(k)}<code>${safe(v)}</code></p>`).join('') || '<p>Unavailable for this run.</p>'}</details>
      <div class="ma-links"><a href="/#benchmarks" target="_blank" rel="noopener">Explore benchmarks</a><a href="${raw(run.id)}" target="_blank" rel="noopener">Traverse data</a><a href="${raw(flight.id)}" target="_blank" rel="noopener">Flight data</a>${plan?`<a href="${raw(plan.id)}" target="_blank" rel="noopener">Planning data</a>`:''}</div></article></div>`;
  const planning=host.querySelector('.ma-planning');
  if(row?.samples?.length && plan.sites[row.site_id]?.skyline_deg)bindPlanning(planning,plan,row,safe,dateLabel);
  else {
    const last=trace.at(-1);
    planning.innerHTML=`<article class="ma-card ma-window"><h2>Surface conditions</h2><p>${safe(message||'The saved comparison has no detailed sky samples.')}</p>
      <div class="ma-facts">${stat('Sun disk visible · final drive sample',unit(Number.isFinite(last.disk_fraction)?100*last.disk_fraction:null,'%',0))}
      ${stat('Earth center · final drive sample',last.earth_visible===true?'In view':last.earth_visible===false?'Below terrain':'Unavailable')}
      ${selection?stat('Saved landing window',unit(selection.surface_hours,'h',0))+stat('Saved Earth visibility',unit(selection.contact_hours,'h')):''}</div></article>`;
  }
  const telemetry=host.querySelector('.ma-telemetry'), slider=telemetry.querySelector('input');
  const channels=[['battery_wh','Wh',3],['solar_w','W',2],['speed_m_s','m/s',3],['roll_deg','°',2],['pitch_deg','°',2]];
  let channel=0;
  function update(){
    const i=Number(slider.value),sample=trace[i],[key,u,digits]=channels[channel];
    telemetry.querySelector('.ma-chart').innerHTML=lineChart(trace,key,u,i);
    telemetry.querySelector('output').textContent=unit(sample[key],u,digits);
    telemetry.querySelector('.ma-reading span').textContent=unit(sample.t_s,'s')+' · '+sample.activity;
    const marker=host.querySelector('.ma-rover'),[x,y]=map.xy(sample);
    marker.setAttribute('cx',x);marker.setAttribute('cy',y);
  }
  bindSwitch(telemetry,i=>{channel=i;update();});
  slider.oninput=update;update();
}
