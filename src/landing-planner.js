const policies = {
  balanced:'Maximize the smaller of relative solar energy and relative contact time',
  sunlight:'Maximize incident solar energy for the selected panel',
  contact:'Maximize Earth line-of-sight hours',
  delta_v:'Minimize required transfer Δv',
};
const number = (v, digits=1) => Number(v).toFixed(digits);
const utc = stamp => stamp.slice(0,16).replace('T',' ')+' UTC';

export function landingForm(form, draft, btn, onSearch, onManual) {
  const optional = (key,label,max,step) => `<label>${label}<input name="${key}" type="number" min="${key==='max_delta_v_km_s'?step:0}" max="${max}" step="${step}" placeholder="No limit"></label>`;
  form.insertAdjacentHTML('beforeend', `<form class="lp-form">
    <label>First landing <span>UTC</span><input name="landing_utc" type="datetime-local" min="2000-01-01T00:00" max="2049-12-31T23:59" required></label>
    <div class="exp-pair"><label>Compare dates<select name="date_spacing_days">${[1,3,7,30,90].map(d=>`<option value="${d}">${d}-day spacing</option>`).join('')}</select></label>
    <label>Surface window<select name="surface_hours">${[12,24,72,168,720].map(h=>`<option value="${h}">${h<100?h+' hours':h/24+' days'}</option>`).join('')}</select></label></div>
    <label>Mission priority<select name="priority"><option value="balanced">Balance sunlight and contact</option><option value="sunlight">Most solar energy</option><option value="contact">Most Earth contact</option><option value="delta_v">Lowest transfer Δv</option></select></label>
    <label>Solar panel<select name="array_mount"><option value="level">Level at the site</option><option value="tracking">Tracks the Sun</option></select></label>
    <details class="exp-notes lp-limits"><summary>Mission limits</summary>
    ${optional('min_sun_hours','Minimum equivalent sunlight (h)',720,.1)}
    ${optional('max_outage_hours','Maximum continuous Earth outage (h)',720,.1)}
    ${optional('max_slope_deg','Maximum local slope (°)',90,.1)}
    ${optional('max_delta_v_km_s','Maximum transfer Δv (km/s)',100,.01)}</details>
    <p>Compare Connecting Ridge and Shackleton rim on three landing dates, with 72, 96 and 120 hours to lunar approach.</p>
    ${btn('exp-search','Compare landing plans')}</form>
    <button class="exp-back" id="exp-manual">Plan a specific flight</button>`);
  const fields = form.querySelector('form');
  for(const [key,value] of Object.entries(draft)) fields.elements[key].value = key==='landing_utc'?value.slice(0,16):value??'';
  fields.onsubmit = event => {
    event.preventDefault();
    const data = new FormData(fields);
    const request = {landing_utc:data.get('landing_utc')+'Z',priority:data.get('priority'),array_mount:data.get('array_mount')};
    for(const key of ['surface_hours','date_spacing_days','min_sun_hours','max_outage_hours','max_slope_deg','max_delta_v_km_s']){
      request[key]=data.get(key) === '' && key!=='min_sun_hours' ? null : Number(data.get(key));
    }
    onSearch(request);
  };
  form.querySelector('#exp-manual').onclick=onManual;
}

function sky(site, s) {
  const steps=site.skyline_deg, sun=s.sun_elevation_deg, earth=s.earth_elevation_deg;
  const lo=Math.min(-3,Math.floor(Math.min(...steps,sun,earth)-1));
  const hi=Math.max(3,Math.ceil(Math.max(...steps,sun,earth)+1));
  const x=a=>40+a*1.8, y=e=>162-(e-lo)*140/(hi-lo);
  const poly=[...steps,steps[0]].map((h,i)=>`${x(i*site.skyline_step_deg)},${y(h)}`).join(' ');
  const marker=(az,el,label,fill)=>{
    const cx=x(az),cy=y(el);
    return `<circle cx="${cx}" cy="${cy}" r="5" fill="${fill}" stroke="#111" stroke-width="1.5"/><text text-anchor="${az>320?'end':'start'}" x="${cx+(az>320?-9:9)}" y="${cy-7}">${label}</text>`;
  };
  return `<svg viewBox="0 0 728 194" role="img" aria-label="Terrain skyline. Sun at ${number(sun)} degrees and Earth at ${number(earth)} degrees elevation.">
    <path d="M40 ${y(0)}H688" stroke="#686868" stroke-dasharray="3 4"/>
    <polygon points="40,162 ${poly} 688,162" fill="#303030"/><polyline points="${poly}" fill="none" stroke="#aaa"/>
    <text x="6" y="${y(0)+4}">0°</text>
    ${['N','E','S','W','N'].map((d,i)=>`<text text-anchor="middle" x="${x(i*90)}" y="184">${d}</text>`).join('')}
    ${marker(s.sun_azimuth_deg,sun,'Sun','#fff')}${marker(s.earth_azimuth_deg,earth,'Earth','#83a6ff')}</svg>`;
}

export function showLandingOptions({plan,form,host,btn,safe,icons,optionKey,onEdit,onUse}) {
  const request=plan.request, ranks=plan.ranked_keys;
  const sorted=[...plan.candidates].sort((a,b)=>(ranks.includes(a.key)?ranks.indexOf(a.key):999)-(ranks.includes(b.key)?ranks.indexOf(b.key):999));
  let selected=sorted.find(row=>row.key===optionKey)??sorted[0], sampleIndex=0;
  const delayLabel=r=>utc(r.landing_utc).slice(0,10);
  form.insertAdjacentHTML('beforeend',`<p class="lp-subtitle">${ranks.length} of ${sorted.length} site/date options meet your limits · ${request.surface_hours} h on the surface</p>
    <div class="lp-options" role="group" aria-label="Landing options">${sorted.map(r=>`<button type="button" data-option="${safe(r.key)}"><strong>${safe(r.name)}</strong><span>${delayLabel(r)}</span><small>${r.key===ranks[0]?'Best evaluated':r.unavailable?'Unavailable':r.exclusions?.length?'Outside limits':''}</small>${r.delta_v_km_s!=null?'<em>'+number(r[request.array_mount+'_solar_wh_m2']/1000,2)+' kWh/m² · '+number(r.contact_hours)+' h contact · '+number(r.delta_v_km_s,2)+' km/s</em>':''}</button>`).join('')}</div>
    <div id="lp-choice"></div><button class="exp-back" id="lp-edit">Edit search</button>`);
  const policy=`${policies[request.priority]}. Solar energy and contact hours are each relative to the best eligible value. Ties favor their greater combined fraction, then lower Δv and gentler slope. Each option uses its lowest-Δv solved transfer.`;
  form.querySelector('#lp-edit').onclick=onEdit;
  function render(){
    for(const b of form.querySelectorAll('[data-option]')) b.setAttribute('aria-pressed',String(b.dataset.option===selected.key));
    const r=selected, site=plan.sites[r.site_id];
    form.querySelector('#lp-choice').innerHTML=ranks.includes(r.key)?btn('lp-use','Use this flight'):'<p class="lp-subtitle">'+safe(r.unavailable||r.exclusions.join(' · '))+'</p>';
    const use=form.querySelector('#lp-use');
    if(use)use.onclick=async()=>{
      const buttons=form.querySelectorAll('button');
      buttons.forEach(button=>button.disabled=true);
      try{await onUse(r.key);}finally{buttons.forEach(button=>button.disabled=false);}
    };
    icons();
    if(!r.samples){
      host.innerHTML=`<div class="lp-report"><h2>${safe(r.name)}</h2><p>${safe(r.unavailable)}</p></div>`;
      return;
    }
    const intervals=(rows)=>rows.length?rows.map(([a,b])=>`<li>${utc(a)} – ${utc(b)}</li>`).join(''):'<li>None during this window</li>';
    const bands=(label,rows)=>`<div class="lp-band"><span>${label}</span><div aria-hidden="true">${rows.map(([a,b])=>`<i style="left:${100*a/(request.surface_hours*3600)}%;width:${100*(b-a)/(request.surface_hours*3600)}%"></i>`).join('')}</div></div>`;
    host.innerHTML=`<section class="lp-report"><header><h2>${safe(r.name)}</h2><p>Touchdown · ${utc(r.landing_utc)}</p></header>
      <dl class="lp-metrics">${[['Equivalent sunlight',number(r.equivalent_sun_hours)+' h'],['Earth in view',number(r.contact_hours)+' h'],['Longest outage',number(r.longest_outage_hours)+' h'],['Local slope',number(r.slope_deg)+'°'],['Incident · '+request.array_mount+' panel',number(r[request.array_mount+'_solar_wh_m2'],0)+' Wh/m²'],['Required Δv',r.delta_v_km_s!=null?number(r.delta_v_km_s,2)+' km/s':'Unavailable']].map(([k,v])=>`<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}</dl>
      <section class="lp-sky"><h3>Local horizon</h3><div class="lp-plot"></div>
      <input aria-label="Time after touchdown" type="range" min="0" max="${r.samples.length-1}" value="${sampleIndex}">
      <output></output><p class="lp-next"></p></section>
      ${bands('Sunlight',r.sun_windows_s)}${bands('Earth contact',r.contact_windows_s)}
      <details class="exp-notes"><summary>Visibility windows · UTC</summary><p>Times are interpolated from ${r.sample_step_s/60}-minute samples. Short transitions can fall between samples.</p><h4>Sun above terrain · ${number(r.sun_hours)} h</h4><ul>${intervals(r.sun_windows_utc)}</ul><h4>Earth center above terrain</h4><ul>${intervals(r.contact_windows_utc)}</ul></details>
      <details class="exp-notes"><summary>Compared transfers</summary><ul>${r.paths.map(p=>`<li>${p.transfer_hours} h to approach · ${p.unavailable?safe(p.unavailable):number(p.delta_v_km_s,3)+' km/s'} · departure ${utc(p.departure_utc)}</li>`).join('')}</ul></details>
      <details class="exp-notes"><summary>Ranking and data</summary><p>${policy}</p><p>Each transfer starts in a freely oriented 200 km Earth orbit and ends with a prescribed 15-minute descent. Landing-site safety, vehicle fuel limits and radio link margin are unassessed.</p>
      <p>DE421 ephemerides and NASA LOLA local 5 m and regional 80 m terrain. Observer height 0.5 m. Visibility uses rays at each body’s azimuth. The skyline drawing samples every 4°. Equivalent sunlight integrates the visible fraction of the Sun. Incident energy assumes your selected panel orientation and excludes conversion losses.</p>
      <p>Site origin · ${number(site.latitude_deg,5)}° latitude, ${number(site.longitude_deg,5)}° east. Height RMS ${site.height_rms_m==null?'unavailable':number(site.height_rms_m,2)+' m'}. Native-cell LOLA returns ${site.native_return_count??'unknown'}.</p>
      <a href="/api/v1/runs/${encodeURIComponent(plan.id)}" target="_blank" rel="noopener">Planning samples and source hashes ↗</a></details></section>`;
    const range=host.querySelector('input');
    const draw=()=>{
      sampleIndex=Number(range.value);const s=r.samples[sampleIndex];
      host.querySelector('.lp-plot').innerHTML=sky(site,s);
      host.querySelector('output').textContent=`${utc(s.utc)} · Sun ${number(s.sun_elevation_deg)}° (${number(s.disk_fraction*100,0)}% visible) · Earth ${number(s.earth_elevation_deg)}° (${s.earth_center_clearance_deg>0?'in view':'below terrain'})`;
      const next=(label,windows,on,off)=>{
        for(const [start,end] of windows){
          const change=s.t_s<start?[start,on]:s.t_s<end && end<request.surface_hours*3600?[end,off]:null;
          if(change)return label+' '+change[1]+' in ~'+Math.ceil((change[0]-s.t_s)/60)+' min';
        }
        return label+' · no further transition in window';
      };
      host.querySelector('.lp-next').textContent=next('Sun',r.sun_windows_s,'rises','sets')+' · '+next('Earth',r.contact_windows_s,'rises','sets');
    };
    range.oninput=draw;draw();
  }
  for(const b of form.querySelectorAll('[data-option]')) b.onclick=()=>{
    selected=sorted.find(r=>r.key===b.dataset.option);render();
  };
  render();
}
