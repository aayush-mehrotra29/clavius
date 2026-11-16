import './expedition.css';
import { renderMissionAnalysis } from './mission-analysis.js';
import { selectedScenario } from './mission-series.js';
import {landingForm,showLandingOptions} from './landing-planner.js';
import {mountTraverseMap} from './traverse-map.js';
import {ExpeditionScene} from './expedition-scene.js';
import {formatCoordinate} from './lunar.js';

const safe=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const timeLabel=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
const dateLabel=stamp=>new Date(stamp).toLocaleString('en-GB',{timeZone:'UTC',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'})+' UTC';
const stages=['Flight','Traverse','Replay','Analysis'];

export function mountExpedition(root,{logo,icon,icons}){
  root.innerHTML=`<main class="expedition">
  <header class="exp-head"><a class="brand" href="/" aria-label="Clavius home">${logo}</a>
    <nav class="exp-steps" aria-label="Mission stages">${stages.map((s,i)=>`<button type="button" data-step="${i}">${s}</button>`).join('')}</nav>
  </header><div class="exp-layout"><section class="exp-panel"><div id="exp-form"></div><p class="exp-error" role="alert" hidden></p></section>
  <section class="exp-view" aria-label="Lunar mission viewer"><div class="exp-pin" aria-hidden="true" hidden></div>
    <div class="exp-surface-map" hidden></div><div class="exp-orbit" hidden></div><div class="exp-caption"><h2></h2><p></p></div><div class="exp-view-error" role="status" hidden></div>
    <div class="exp-player" hidden><button id="exp-play" aria-label="Pause playback">${icon('play','play-glyph')}${icon('pause','pause-glyph')}</button><time>0:00</time><input type="range" id="exp-scrub" min="0" value="0" step="any" aria-label="Replay time"><select aria-label="Playback speed" id="exp-speed"><option value="1">1×</option><option value="3" selected>3×</option><option value="8">8×</option></select><button id="exp-fly" title="Replay fly-in" aria-label="Replay fly-in">${icon('rotate-ccw')}</button></div>
  </section></div><section class="mission-analysis" aria-label="Mission analysis" hidden></section></main>`;
  const $=selector=>root.querySelector(selector),form=$('#exp-form'),error=$('.exp-error'),player=$('.exp-player');
  const abort=new AbortController(),signal=abort.signal;
  const mapHost=$('.exp-surface-map');
  const report=$('.mission-analysis');
  let surfaceMap,closeOrbit,viewVersion=0,savedPlan;
  let robots=[],sites=[],flight,run,scene,stage=0,busy=false;
  let siteId='connecting-ridge',departure='2028-01-01T00:00',hours=96,robotId='',route=[{east_m:2,north_m:0},{east_m:4,north_m:0}],task='science',dwell=5;
  let searchDraft={landing_utc:'2028-01-01T00:00Z',date_spacing_days:7,surface_hours:24,priority:'balanced',array_mount:'level'};
  const url=(key,id)=>history.replaceState({},'',id?'/app?'+new URLSearchParams({[key]:id}):'/app');
  const showError=message=>{error.textContent=message;error.hidden=!message;};
  const viewerError=message=>{const n=$('.exp-view-error');n.textContent=message;n.hidden=!message;};
  async function api(path,body){
    const response=await fetch('/api/v1/'+path,{signal,...(body instanceof FormData?{method:'POST',body}:body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});
    if(!response.headers.get('content-type')?.includes('application/json'))throw Error('Start the local simulation service with npm run dev, then retry.');
    const data=await response.json();
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:(data.detail?.[0]?.msg||'The simulation service could not complete this request.'));
    return data;
  }
  const btn=(id,text)=>`<button class="exp-primary" id="${id}">${text}</button>`;
  const metric=(label,value)=>`<div><dt>${label}</dt><dd>${safe(value)}</dd></div>`;
  function setStage(n,title){
    stage=n;viewVersion++;closeOrbit?.();closeOrbit=null;
    surfaceMap?.dispose();surfaceMap=null;mapHost.hidden=true;
    $('.exp-orbit').hidden=true;$('.exp-orbit').replaceChildren();$('.exp-caption').hidden=false;viewerError('');showError('');
    report.hidden=n!==3;report.replaceChildren();$('.exp-layout').hidden=n===3;
    syncTabs();
    form.innerHTML='<h1 tabindex="-1">'+title+'</h1>';player.hidden=true;
  }
  function syncTabs(){
    const recorded=run?.request;
    const matchesReplay=recorded && run.flight_id===flight?.id && recorded.robot_id===robotId &&
      recorded.task===task && recorded.dwell_s===dwell && recorded.waypoints.length===route.length &&
      route.every((p,i)=>p.east_m===recorded.waypoints[i].east_m && p.north_m===recorded.waypoints[i].north_m);
    root.querySelectorAll('.exp-steps [data-step]').forEach((button,i)=>{
      if(i===stage)button.setAttribute('aria-current','step');else button.removeAttribute('aria-current');
      button.disabled=busy||(i===1&&!flight)||(i>=2&&!matchesReplay);
    });
  }
  $('.exp-steps').onclick=e=>{
    const button=e.target.closest('[data-step]');if(!button||button.disabled||busy)return;
    const next=Number(button.dataset.step);if(next===stage)return;
    if(next===0){url('flight',flight.id);flightReview();}
    if(next===1){url('route',flight.id);traverseForm();}
    if(next===2){url('mission',run.id);replay();}
    if(next===3)analysis();
  };
  function resetFlight(){
    flight=null;run=null;savedPlan=null;route=[{east_m:2,north_m:0},{east_m:4,north_m:0}];
  }
  function caption(name,detail){
    $('.exp-caption h2').textContent=name;$('.exp-caption p').textContent=detail;
  }
  function ensureSurface(){
    if(scene)return;
    try{scene=new ExpeditionScene($('.exp-view'),$('.exp-pin'),onTime);}
    catch(e){viewerError('3D requires WebGL. Mission calculations and results remain available.');}
  }
  function selectSite(){
    const site=sites.find(s=>s.id===siteId);
    if(site){scene?.setSite(site.latitude_deg,site.longitude_deg);caption(site.name,formatCoordinate(site.latitude_deg)+'  /  '+site.longitude_deg.toFixed(3)+'° E');}
  }
  function plannerForm(){
    resetFlight();setStage(0,'Plan your landing');ensureSurface();scene?.reset();
    $('.exp-pin').hidden=true;caption('Lunar south pole','Connecting Ridge and Shackleton rim');
    landingForm(form,searchDraft,btn,request=>{searchDraft=request;launch('landing-plans',request);},flightForm);icons();
  }
  function comparison(plan,optionKey){
    savedPlan=plan;setStage(0,'Compare landings');searchDraft=plan.request;
    scene?.dispose();scene=null;
    const host=$('.exp-orbit');host.hidden=false;$('.exp-pin').hidden=true;$('.exp-caption').hidden=true;
    if(!plan.request.array_mount){
      plannerForm();showError('Run this older comparison again to include the panel orientation.');url();return;
    }
    showLandingOptions({plan,form,host,btn,safe,icons,optionKey,onEdit:()=>{url();plannerForm();},onUse:async key=>{
      const version=viewVersion;
      try{
        const selected=await api('landing-plans/'+encodeURIComponent(plan.id)+'/options/'+encodeURIComponent(key),{});
        if(signal.aborted||version!==viewVersion)return;
        flight=selected;url('flight',flight.id);await flightReview();
      }catch(e){if(!signal.aborted&&version===viewVersion)showError(e.message);}
    }});
  }
  function flightForm(){
    resetFlight();setStage(0,'Plan your flight');ensureSurface();scene?.reset();selectSite();
    form.insertAdjacentHTML('beforeend',`<form id="flight-fields"><label>Departure <span>UTC · Earth orbit</span><input type="datetime-local" id="exp-date" min="2000-01-01T00:00" max="2049-12-31T23:59" required></label>
    <label>Landing site<select id="exp-site">${sites.map(s=>`<option value="${safe(s.id)}" ${s.available?'':'disabled'}>${safe(s.name)}${s.available?'':' · unavailable'}</option>`).join('')}</select></label>
    <label>Time to approach<select id="exp-hours">${[72,84,96,108,120].map(h=>`<option value="${h}">${h} hours</option>`).join('')}</select></label>
    ${btn('exp-plan','Calculate flight')}</form>
    <details class="exp-notes"><summary>Flight assumptions</summary><p>Depart a 200 km circular Earth orbit. Two targeted coasts lead to a braking maneuver 100 km above the selected site. A prescribed 15-minute powered descent sets the surface start. Vehicle thrust and fuel limits are unassessed.</p></details>`);
    form.insertAdjacentHTML('beforeend','<button class="exp-back" id="exp-compare">Compare landing options</button>');
    $('#exp-compare').onclick=()=>{url();plannerForm();};
    $('#exp-date').value=departure;$('#exp-site').value=siteId;$('#exp-hours').value=hours;
    $('#exp-site').onchange=e=>{siteId=e.target.value;selectSite();};
    $('#flight-fields').onsubmit=e=>{e.preventDefault();departure=$('#exp-date').value;hours=Number($('#exp-hours').value);
      launch('flights',{site_id:siteId,departure_utc:departure+'Z',transfer_hours:hours});};
    icons();
  }
  function routeEditor(){
    return `<div class="exp-map-head"><b>Waypoints</b><span>East / north · meters</span></div>
      <div class="exp-waypoints">${route.map((p,i)=>`<div><span>${i+1}</span>${['east_m','north_m'].map(k=>`<input type="number" step=".1" min="-12" max="12" required value="${p[k]}" data-axis="${k}" data-point="${i}" aria-label="Waypoint ${i+1} ${k==='east_m'?'east':'north'} meters">`).join('')}<button type="button" data-remove="${i}" aria-label="Remove waypoint ${i+1}">×</button></div>`).join('')}</div>
      <button class="exp-add" type="button" id="exp-add" ${route.length>=5?'disabled':''}>+ Add waypoint</button>`;
  }
  function bindRoute(){
    $('#route-editor').innerHTML=routeEditor();
    root.querySelectorAll('[data-axis]').forEach(input=>input.onchange=()=>{
      if(!input.checkValidity())return;
      route=route.map((p,i)=>i===Number(input.dataset.point)?{...p,[input.dataset.axis]:input.valueAsNumber}:p);
      syncTabs();surfaceMap?.update(route);
    });
    root.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{route=route.filter((_,i)=>i!==Number(b.dataset.remove));bindRoute();});
    $('#exp-add').onclick=()=>{
      const last=route.at(-1)||flight.landing;
      route=[...route,{east_m:Math.min(12,last.east_m+1),north_m:last.north_m}];bindRoute();
    };
    syncTabs();$('#exp-run').disabled=!route.length;
    surfaceMap?.update(route);
  }
  function comparisonLink(){
    const selection=flight.planning_selection;
    if(!selection)return '';
    const query=new URLSearchParams({plan:selection.plan_id,option:selection.candidate_key});
    return '<a class="lp-backlink" href="/app?'+query+'">View landing comparison ↗</a>';
  }
  function flightDetails(){
    const selection=flight.planning_selection;
    const conditions=selection?.surface_hours?`<details class="exp-notes"><summary>Landing conditions · ${selection.surface_hours} h</summary>
      <dl>${metric('Incident energy · '+selection.array_mount+' panel',selection.incident_wh_m2.toFixed(0)+' Wh/m²')}
      ${metric('Earth in view',selection.contact_hours.toFixed(1)+' h')}${metric('Longest outage',selection.longest_outage_hours.toFixed(1)+' h')}
      ${metric('Local slope',selection.slope_deg.toFixed(1)+'°')}</dl><p>Screened at the landing origin. The traverse calculates rover power along the driven route.</p></details>`:'';
    return conditions+ `<details class="exp-notes"><summary>Flight solution</summary><dl>${metric('From Earth orbit',dateLabel(flight.departure_utc))}${metric('Touchdown',dateLabel(flight.landing.utc))}${Object.entries(flight.maneuvers_km_s).map(([k,v])=>metric(k.replaceAll('_',' '),v.toFixed(3)+' km/s')).join('')}</dl><p>${safe(flight.model)}</p></details>`;
  }
  async function flightReview(){
    setStage(0,'Your flight');
    const version=viewVersion;
    scene?.dispose();scene=null;
    const host=$('.exp-orbit');host.hidden=false;
    $('.exp-pin').hidden=true;$('.exp-caption').hidden=true;
    host.textContent='Loading flight path…';
    siteId=flight.landing.site_id;departure=flight.departure_utc.slice(0,16);hours=flight.request.transfer_hours;
    form.insertAdjacentHTML('beforeend',`<section class="exp-outcome"><h2>Earth to ${safe(flight.landing.name)}</h2>
      <dl>${metric('Departure',dateLabel(flight.departure_utc))}${metric('Landing',dateLabel(flight.landing.utc))}
      ${metric('Flight time',(flight.transfer_s/3600).toFixed(2)+' h')}${metric('Total Δv',flight.total_delta_v_km_s.toFixed(2)+' km/s')}</dl></section>
      ${comparisonLink()}
      ${btn('exp-continue','Plan traverse')}${flightDetails()}
      <details class="exp-notes"><summary>About this visualization</summary><p>Positions and velocities use Earth-centered J2000 coordinates. Earth uses NASA’s July 2004 Blue Marble mosaic. The Moon uses the LROC WAC mosaic with LOLA polar fill. SPICE orients both maps at each flight sample. Both globes use their reference radii. The dashed orbit is a guide. Lunar altitude is relative to the 1,737.4 km sphere. The white ring marks the braking point 100 km above the selected landing site.</p><a href="https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map/" target="_blank" rel="noopener">Earth imagery ↗</a> · <a href="https://svs.gsfc.nasa.gov/4720/" target="_blank" rel="noopener">Moon imagery ↗</a><br><a href="https://github.com/prollyAditya/Clavius/tree/3f26903fad64ae961b1464597d83d3a86ef02663/frontend/src/components/views" target="_blank" rel="noopener">Original flight visualizations ↗</a></details>
      <button class="exp-back" id="exp-edit">Edit flight</button>`);
    $('#exp-continue').onclick=()=>{url('route',flight.id);traverseForm();};
    $('#exp-edit').onclick=()=>{url();flightForm();};
    icons();
    try{
      const [module,data]=await Promise.all([import('./flight/viewer.tsx'),flight.trajectory_3d?.globe_frames ? flight.trajectory_3d : api('flights/'+encodeURIComponent(flight.id)+'/trajectory')]);
      if(signal.aborted||version!==viewVersion)return;
      host.replaceChildren();closeOrbit=module.mountFlightViewer(host,data);
    }catch(e){
      if(signal.aborted||version!==viewVersion)return;
      host.textContent='';showError(e.message);
    }
  }
  function traverseForm(){
    setStage(1,'Set the traverse');scene?.dispose();scene=null;
    $('.exp-caption').hidden=true;$('.exp-pin').hidden=true;mapHost.hidden=false;
    siteId=flight.landing.site_id;departure=flight.departure_utc.slice(0,16);hours=flight.request.transfer_hours;
    form.insertAdjacentHTML('beforeend',`<p class="exp-arrival">Landing ${safe(dateLabel(flight.landing.utc))}</p>
      <form id="traverse-fields"><label>Rover<select id="exp-robot">${robots.map(r=>`<option value="${safe(r.id)}">${safe(r.name)}</option>`).join('')}<option value="import">Import rover…</option></select></label>
      <div id="route-editor"></div><div class="exp-pair"><label>At destination<select id="exp-task"><option value="science">Science dwell</option><option value="wait">Park</option></select></label><label>Duration (s)<input id="exp-dwell" required type="number" min="1" max="30" value="${dwell}"></label></div>
      ${btn('exp-run','Simulate traverse')}</form>${flightDetails()}${comparisonLink()}`);
    form.insertAdjacentHTML('beforeend',`<dialog class="exp-import" aria-labelledby="exp-import-title"><h2 id="exp-import-title">Import rover</h2>
      <form><label>URDF or model ZIP<input type="file" name="package" accept=".zip,.urdf" required></label>
      <label>Power and mobility profile<input type="file" name="profile" accept=".json"></label><p>Include a profile here or a clavius-profile.json inside the ZIP.</p>
      <p role="alert" hidden></p>${btn('exp-import-submit','Import rover')}<button class="exp-back" type="button">Cancel</button></form></dialog>`);
    const robotSelect=$('#exp-robot'),dialog=$('.exp-import');
    robotSelect.onchange=()=>{
      if(robotSelect.value==='import'){robotSelect.value=robotId;dialog.showModal();}
      else {robotId=robotSelect.value;syncTabs();}
    };
    dialog.querySelector('.exp-back').onclick=()=>dialog.close();
    dialog.querySelector('form').onsubmit=async event=>{
      event.preventDefault();
      const fields=event.currentTarget.elements,button=dialog.querySelector('.exp-primary'),alert=dialog.querySelector('[role=alert]');
      button.disabled=true;alert.hidden=true;
      try{
        const data=new FormData();data.set('package',fields.package.files[0]);
        if(fields.profile.files[0])data.set('profile_json',await fields.profile.files[0].text());
        const imported=await api('robots',data);
        if(!imported.profile)throw Error('Add the capability profile to use this rover for the traverse.');
        if(!imported.model.physical_ready)throw Error('The URDF needs valid masses and inertias for rigid-contact driving.');
        if(!robots.some(r=>r.id===imported.id)){
          robots.push(imported);robotSelect.add(new Option(imported.name,imported.id),robotSelect.options.length-1);
        }
        robotId=imported.id;robotSelect.value=robotId;syncTabs();dialog.close();
      }catch(e){if(!signal.aborted){alert.textContent=e.message;alert.hidden=false;}}
      finally{button.disabled=false;}
    };
    $('#exp-task').value=task;$('#exp-robot').value=robotId;bindRoute();icons();
    $('#exp-task').onchange=e=>{task=e.target.value;syncTabs();};
    $('#exp-dwell').onchange=e=>{if(e.target.checkValidity()){dwell=e.target.valueAsNumber;syncTabs();}};
    surfaceMap=mountTraverseMap(mapHost,flight,route,points=>{
      if(stage===1&&!busy){route=points;bindRoute();}
    });
    $('#traverse-fields').onsubmit=e=>{
      e.preventDefault();robotId=$('#exp-robot').value;task=$('#exp-task').value;dwell=Number($('#exp-dwell').value);
      launch('traverses',{flight_id:flight.id,robot_id:robotId,waypoints:route,task,dwell_s:dwell});
    };
  }
  function onTime(t,row,playing){
    if(stage!==2)return;
    player.hidden=false;$('#exp-play').dataset.playing=String(playing);$('#exp-play').setAttribute('aria-label',playing?'Pause playback':'Play replay');
    $('#exp-scrub').value=t;player.querySelector('time').textContent=timeLabel(t);
    if(row.utc)$('.exp-caption p').textContent=row.utc.slice(0,19).replace('T',' ')+' UTC';
    $('#exp-activity').textContent=row.activity==='drive'?'To waypoint '+row.waypoint:row.activity==='science'?'Science dwell':'Parked';
    $('#exp-battery').textContent=row.battery_wh.toFixed(2)+' Wh';$('#exp-velocity').textContent=(row.speed_m_s*100).toFixed(1)+' cm/s';
  }
  async function analysis(){
    url('analysis',run.id);setStage(3,'Mission analysis');
    scene?.dispose();scene=null;
    const version=viewVersion,selection=flight.planning_selection;
    const render=(plan,message)=>renderMissionAnalysis(report,{run,flight,plan,message,safe,dateLabel});
    if(run.flight_id!==flight.id || (run.flight_sha256 && run.flight_sha256!==flight.artifact_sha256)){
      report.textContent='The saved flight does not match this traverse.';return;
    }
    render(null,selection?'Loading the saved landing comparison…':'This flight was planned directly. No site/date comparison was recorded.');
    if(!selection)return;
    try{
      const plan=savedPlan?.id===selection.plan_id?savedPlan:await api('runs/'+encodeURIComponent(selection.plan_id));
      if(signal.aborted||version!==viewVersion)return;
      if(!selectedScenario(flight,plan))throw Error('The saved comparison does not match this landing.');
      savedPlan=plan;render(plan,'');
    }catch(e){if(!signal.aborted&&version===viewVersion)render(null,'Landing comparison unavailable. '+e.message);}
  }
  async function replay(autoAdvance=false){
    setStage(2,'Mission replay');ensureSurface();
    const version=viewVersion;
    const m=run.metrics;
    form.insertAdjacentHTML('beforeend',`<p class="exp-arrival">${safe(run.robot_snapshot.model.name)}</p>
    <section class="exp-outcome"><h2>${run.task_completed?(run.request.task==='science'?'Science dwell completed':'Parking dwell completed'):'Task unfinished'}</h2>
    <dl>${metric('Distance driven',m.distance_m.toFixed(2)+' m')}${metric('Elapsed',m.duration_s.toFixed(1)+' s')}${metric('Peak roll',m.maximum_roll_deg.toFixed(1)+'°')}${metric('Minimum battery',m.minimum_battery_wh.toFixed(2)+' Wh')}</dl>
    ${run.issues.map(v=>'<p>'+safe(v)+'</p>').join('')}</section>
    <div class="exp-telemetry"><strong id="exp-activity">At landing site</strong><span id="exp-velocity"></span><span id="exp-battery"></span></div>
    ${btn('exp-analysis','View mission analysis')}<button class="exp-back" id="exp-reroute">Edit traverse</button>
    ${flightDetails()}${comparisonLink()}<details class="exp-notes"><summary>Simulation details</summary><p>MuJoCo rigid contact on 5 m LOLA terrain. Solar power uses dated DE421 directions, local terrain horizons and the recorded body attitude. Scene fill light helps reveal terrain in shadow. Friction and power properties are engineering assumptions. The controller has 180 s to reach the route and finish its dwell within 0.18 m.</p><a href="/api/v1/runs/${encodeURIComponent(run.id)}" target="_blank" rel="noopener">Open run data ↗</a></details>
    <button id="exp-orbit-replay" class="exp-back">View flight path</button> <button id="exp-new" class="exp-back">New flight</button>`);
    caption(run.landing.name,dateLabel(run.landing.utc));icons();
    $('#exp-analysis').onclick=analysis;
    $('#exp-reroute').onclick=()=>{url('route',flight.id);traverseForm();};
    $('#exp-orbit-replay').onclick=()=>{url('flight',flight.id);flightReview();};
    $('#exp-new').onclick=()=>{url();plannerForm();};
    if(!scene)return;
    scene.onPlaybackEnd=autoAdvance?()=>{if(stage===2&&viewVersion===version)analysis();}:null;
    const selected=run;
    try{
      await scene.prepare(selected);
      if(signal.aborted||version!==viewVersion||selected!==run)return;
      $('#exp-scrub').max=run.trace.at(-1).t_s;scene.seek(0);player.hidden=true;scene.startFly();
    }catch(e){if(!signal.aborted&&version===viewVersion)viewerError('Replay view unavailable. '+e.message);}
  }
  $('#exp-play').onclick=()=>{if(scene.time>=run.trace.at(-1).t_s)scene.seek(0);scene.playing=!scene.playing;scene.seek(scene.time);};
  $('#exp-scrub').oninput=e=>{scene.playing=false;scene.seek(Number(e.target.value));};
  $('#exp-speed').onchange=e=>scene.speed=Number(e.target.value);
  $('#exp-fly').onclick=()=>{player.hidden=true;scene.startFly();};
  function restoreRoute(request){
    route=request.waypoints.map(p=>({...p}));robotId=request.robot_id;task=request.task;dwell=request.dwell_s;
  }
  async function finishJob(id){
    let job;
    do{
      job=await api('jobs/'+encodeURIComponent(id));
      if(job.state==='failed'||job.state==='cancelled')throw Error(job.message||job.error||'Run stopped.');
      if(job.state!=='completed'){
        if(signal.aborted)return;
        $('.exp-progress span').textContent=job.message;
        $('.exp-progress progress').value=job.progress;
        await new Promise(resolve=>setTimeout(resolve,450));
      }
    }while(job.state!=='completed');
    const result=await api('runs/'+encodeURIComponent(job.result_id));
    if(result.kind==='flight'){flight=result;url('flight',flight.id);await flightReview();}
    else if(result.kind==='landing_plan'){url('plan',result.id);comparison(result);}
    else if(result.kind==='traverse'){run=result;restoreRoute(run.request);flight=await api('runs/'+encodeURIComponent(run.flight_id));url('mission',run.id);await replay(true);}
    else throw Error('This job belongs to a different workspace.');
  }
  async function launch(path,body,resumeId){
    if(busy)return;
    busy=true;syncTabs();mapHost.inert=true;showError('');
    try{
      if(resumeId){
        const saved=await api('jobs/'+encodeURIComponent(resumeId));
        if(saved.kind==='traverse'){
          path='traverses';flight=await api('runs/'+encodeURIComponent(saved.request.flight_id));
          restoreRoute(saved.request);
        }else if(saved.kind==='flight'){
          path='flights';siteId=saved.request.site_id;departure=saved.request.departure_utc.slice(0,16);hours=saved.request.transfer_hours;
        }else if(saved.kind==='landing_plan'){
          path='landing-plans';searchDraft=saved.request;
        }else throw Error('This job belongs to a different workspace.');
      }
      const id=resumeId||(await api(path,body)).id;
      url('job',id);
      form.innerHTML=`<h1>${path==='landing-plans'?'Comparing landings':path==='flights'?'Calculating flight':'Running mission'}</h1><div class="exp-progress" role="status"><progress max="1"></progress><span>Preparing inputs</span></div><button id="exp-cancel" class="exp-back">Cancel run</button>`;
      $('#exp-cancel').onclick=()=>api('jobs/'+encodeURIComponent(id)+'/cancel',{}).catch(e=>showError(e.message));
      await finishJob(id);
    }catch(e){if(!signal.aborted){if(path==='landing-plans'){url();plannerForm();}else if(flight && path==='traverses'){url('route',flight.id);traverseForm();}else{url();flightForm();}showError(e.message);}}
    finally{busy=false;mapHost.inert=false;syncTabs();}
  }
  async function init(){
    setStage(0,'Plan your flight');
    try{
      [sites,robots]=await Promise.all([api('sites'),api('robots')]);
      robots=robots.filter(r=>r.profile&&r.model?.physical_ready);
      robotId=(robots.find(r=>r.source_class==='hypothetical_reference')||robots[0])?.id;
      if(!sites.some(s=>s.available))throw Error('Prepare the lunar terrain before comparing landings.');
      siteId=sites.find(s=>s.available).id;
      const params=new URLSearchParams(location.search);
      if(params.has('job')){await launch(null,null,params.get('job'));return;}
      if(params.has('plan')){
        const plan=await api('runs/'+encodeURIComponent(params.get('plan')));
        if(plan.kind!=='landing_plan')throw Error('This link requires a saved landing comparison.');
        comparison(plan,params.get('option'));
      }else if(params.has('mission')||params.has('analysis')){
        run=await api('runs/'+encodeURIComponent(params.get('analysis')||params.get('mission')));
        if(run.kind!=='traverse')throw Error('This link requires a recorded traverse.');
        restoreRoute(run.request);flight=await api('runs/'+encodeURIComponent(run.flight_id));
        if(params.has('analysis'))await analysis();else await replay();
      }else if(params.has('flight')||params.has('route')){
        flight=await api('runs/'+encodeURIComponent(params.get('flight')||params.get('route')));
        if(flight.kind!=='flight')throw Error('This link requires a solved flight.');
        if(params.has('route'))traverseForm();else await flightReview();
      }else plannerForm();
    }catch(e){
      if(!signal.aborted){showError(e.message);form.insertAdjacentHTML('beforeend','<button id="exp-retry" class="exp-back">Start again</button>');$('#exp-retry').onclick=()=>{url();init();};}
    }
  }
  icons();init();
  return ()=>{abort.abort();surfaceMap?.dispose();closeOrbit?.();scene?.dispose();};
}
