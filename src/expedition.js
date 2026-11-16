import './expedition.css';
import {ExpeditionScene} from './expedition-scene.js';
import {formatCoordinate} from './lunar.js';

const safe=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const timeLabel=s=>Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0');
const dateLabel=stamp=>new Date(stamp).toLocaleString('en-GB',{timeZone:'UTC',day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',hourCycle:'h23'})+' UTC';
const stages=['Flight','Traverse','Replay'];

export function mountExpedition(root,{logo,icon,icons}){
  root.innerHTML=`<main class="expedition">
  <header class="exp-head"><a class="brand" href="/" aria-label="Clavius home">${logo}</a>
    <ol class="exp-steps" aria-label="Mission sequence">${stages.map((s,i)=>`<li data-step="${i}">${s}</li>`).join('')}</ol>
    <details class="exp-tools"><summary aria-label="Open workspace tools">${icon('menu')}</summary><nav><a href="/app/atlas">Lunar atlas</a><a href="/app/simulation">Simulation lab</a><a href="/app/drive">VIPER reference</a></nav></details>
  </header><div class="exp-layout"><section class="exp-panel"><div id="exp-form"></div><p class="exp-error" role="alert" hidden></p></section>
  <section class="exp-view" aria-label="Lunar mission viewer"><div class="exp-pin" aria-hidden="true" hidden></div>
    <div class="exp-orbit" hidden></div><div class="exp-caption"><h2></h2><p></p></div><div class="exp-view-error" role="status" hidden></div>
    <div class="exp-player" hidden><button id="exp-play" aria-label="Pause playback">${icon('play','play-glyph')}${icon('pause','pause-glyph')}</button><time>0:00</time><input type="range" id="exp-scrub" min="0" value="0" step="any" aria-label="Replay time"><select aria-label="Playback speed" id="exp-speed"><option value="1">1×</option><option value="3" selected>3×</option><option value="8">8×</option></select><button id="exp-fly" title="Replay fly-in" aria-label="Replay fly-in">${icon('rotate-ccw')}</button></div>
  </section></div></main>`;
  const $=selector=>root.querySelector(selector),form=$('#exp-form'),error=$('.exp-error'),player=$('.exp-player');
  const abort=new AbortController(),signal=abort.signal;
  let closeOrbit,viewVersion=0;
  let robots=[],sites=[],flight,run,scene,stage=0,busy=false;
  let siteId='connecting-ridge',departure='2028-01-01T00:00',hours=96,robotId='',route=[{east_m:2,north_m:0},{east_m:4,north_m:0}],task='science',dwell=5;
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
  const btn=(id,text)=>`<button class="exp-primary" id="${id}">${text}<span class="exp-action-mark">${icon('arrow-up')}</span></button>`;
  const metric=(label,value)=>`<div><dt>${label}</dt><dd>${safe(value)}</dd></div>`;
  function setStage(n,title){
    stage=n;viewVersion++;closeOrbit?.();closeOrbit=null;
    $('.exp-orbit').hidden=true;$('.exp-orbit').replaceChildren();$('.exp-caption').hidden=false;viewerError('');showError('');root.querySelectorAll('[data-step]').forEach((el,i)=>{
      el.classList.toggle('past',i<n);if(i===n)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');
    });
    form.innerHTML='<h1 tabindex="-1">'+title+'</h1>';player.hidden=true;
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
  function flightForm(){
    setStage(0,'Plan your flight');ensureSurface();scene?.reset();selectSite();
    form.insertAdjacentHTML('beforeend',`<form id="flight-fields"><label>Departure <span>UTC · Earth orbit</span><input type="datetime-local" id="exp-date" min="2000-01-01T00:00" max="2049-12-31T23:59" required></label>
    <label>Landing site<select id="exp-site">${sites.map(s=>`<option value="${safe(s.id)}" ${s.available?'':'disabled'}>${safe(s.name)}${s.available?'':' · unavailable'}</option>`).join('')}</select></label>
    <label>Time to approach<select id="exp-hours">${[72,84,96,108,120].map(h=>`<option value="${h}">${h} hours</option>`).join('')}</select></label>
    ${btn('exp-plan','Calculate flight')}</form>
    <details class="exp-notes"><summary>Flight assumptions</summary><p>Depart a 200 km circular Earth orbit. Two targeted coasts lead to a braking maneuver 100 km above the selected site. A prescribed 15-minute powered descent sets the surface start. Vehicle thrust and fuel limits are unassessed.</p></details>`);
    $('#exp-date').value=departure;$('#exp-site').value=siteId;$('#exp-hours').value=hours;
    $('#exp-site').onchange=e=>{siteId=e.target.value;selectSite();};
    $('#flight-fields').onsubmit=e=>{e.preventDefault();departure=$('#exp-date').value;hours=Number($('#exp-hours').value);
      launch('flights',{site_id:siteId,departure_utc:departure+'Z',transfer_hours:hours});};
    icons();
  }
  function routeEditor(){
    const points=[{east_m:0,north_m:0},...route];
    const coords=points.map(p=>[100+7*p.east_m,100-7*p.north_m]);
    return `<div class="exp-map-head"><b>Waypoints</b><span>East / north · meters</span></div>
      <svg class="exp-map" viewBox="0 0 200 200" aria-label="Route map. Click to add a waypoint, or enter coordinates below.">
      <defs><pattern id="exp-grid" width="14" height="14" x="2" y="2" patternUnits="userSpaceOnUse"><path d="M14 0H0V14" fill="none" stroke="#343434" stroke-width=".6"/></pattern></defs>
      <rect width="200" height="200" fill="url(#exp-grid)"/><path d="M0 100H200M100 0V200" stroke="#4b4b4b" stroke-width=".7"/>
      <polyline points="${coords.map(c=>c.join(',')).join(' ')}" fill="none" stroke="#eee" stroke-width="1.3"/>
      ${coords.map(([x,y],i)=>`<circle cx="${x}" cy="${y}" r="${i?2.4:3.5}" fill="${i?'white':'#111'}" stroke="white"/>`).join('')}<text x="7" y="13">N ↑</text></svg>
      <div class="exp-waypoints">${route.map((p,i)=>`<div><span>${i+1}</span>${['east_m','north_m'].map(k=>`<input type="number" step=".1" min="-12" max="12" required value="${p[k]}" data-axis="${k}" data-point="${i}" aria-label="Waypoint ${i+1} ${k==='east_m'?'east':'north'} meters">`).join('')}<button type="button" data-remove="${i}" aria-label="Remove waypoint ${i+1}" ${route.length<2?'disabled':''}>×</button></div>`).join('')}</div>
      <button class="exp-add" type="button" id="exp-add" ${route.length>=5?'disabled':''}>+ Add waypoint</button>`;
  }
  function bindRoute(){
    $('#route-editor').innerHTML=routeEditor();
    root.querySelectorAll('[data-axis]').forEach(input=>input.onchange=()=>{
      if(!input.checkValidity())return;
      route[Number(input.dataset.point)][input.dataset.axis]=input.valueAsNumber;bindRoute();
    });
    root.querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>{route.splice(Number(b.dataset.remove),1);bindRoute();});
    $('#exp-add').onclick=()=>{route.push({east_m:Math.min(12,route.at(-1).east_m+1),north_m:route.at(-1).north_m});bindRoute();};
    $('.exp-map').onclick=e=>{
      if(route.length>=5)return;
      const svg=e.currentTarget,point=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());
      if(point.x<0||point.x>200||point.y<0||point.y>200)return;
      const axis=v=>Math.max(-12,Math.min(12,Math.round(v*10)/10));
      route.push({east_m:axis((point.x-100)/7),north_m:axis((100-point.y)/7)});bindRoute();
    };
  }
  function flightDetails(){
    return `<details class="exp-notes"><summary>Flight solution</summary><dl>${metric('From Earth orbit',dateLabel(flight.departure_utc))}${metric('Touchdown',dateLabel(flight.landing.utc))}${Object.entries(flight.maneuvers_km_s).map(([k,v])=>metric(k.replaceAll('_',' '),v.toFixed(3)+' km/s')).join('')}</dl><p>${safe(flight.model)}</p></details>`;
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
      ${btn('exp-continue','Plan traverse')}${flightDetails()}
      <details class="exp-notes"><summary>About this visualization</summary><p>Positions and velocities use Earth-centered J2000 coordinates. The globe textures, body sizes and dashed lunar orbit guide are illustrative. Lunar altitude is relative to the 1,737.4 km sphere. The amber ring marks the braking point 100 km above the selected landing site.</p><a href="https://github.com/prollyAditya/Clavius/tree/3f26903fad64ae961b1464597d83d3a86ef02663/frontend/src/components/views" target="_blank" rel="noopener">Original flight visualizations ↗</a></details>
      <button class="exp-back" id="exp-edit">Edit flight</button>`);
    $('#exp-continue').onclick=()=>{url('route',flight.id);traverseForm();};
    $('#exp-edit').onclick=()=>{url();flightForm();};
    icons();
    try{
      const [module,data]=await Promise.all([import('./flight/viewer.tsx'),flight.trajectory_3d||api('flights/'+encodeURIComponent(flight.id)+'/trajectory')]);
      if(signal.aborted||version!==viewVersion)return;
      host.replaceChildren();closeOrbit=module.mountFlightViewer(host,data);
    }catch(e){
      if(signal.aborted||version!==viewVersion)return;
      host.textContent='';showError(e.message);
    }
  }
  function traverseForm(){
    setStage(1,'Set the traverse');ensureSurface();scene?.reset();
    siteId=flight.landing.site_id;departure=flight.departure_utc.slice(0,16);hours=flight.request.transfer_hours;selectSite();
    form.insertAdjacentHTML('beforeend',`<p class="exp-arrival">Landing ${safe(dateLabel(flight.landing.utc))}</p>
      <form id="traverse-fields"><label>Rover<select id="exp-robot">${robots.map(r=>`<option value="${safe(r.id)}">${safe(r.name)}</option>`).join('')}<option value="import">Import rover…</option></select></label>
      <div id="route-editor"></div><div class="exp-pair"><label>At destination<select id="exp-task"><option value="science">Science dwell</option><option value="wait">Park</option></select></label><label>Duration (s)<input id="exp-dwell" required type="number" min="1" max="30" value="${dwell}"></label></div>
      ${btn('exp-run','Simulate traverse')}</form>${flightDetails()}<button class="exp-back" id="exp-review">View flight path</button>`);
    form.insertAdjacentHTML('beforeend',`<dialog class="exp-import" aria-labelledby="exp-import-title"><h2 id="exp-import-title">Import rover</h2>
      <form><label>URDF or model ZIP<input type="file" name="package" accept=".zip,.urdf" required></label>
      <label>Power and mobility profile<input type="file" name="profile" accept=".json"></label><p>Include a profile here or a clavius-profile.json inside the ZIP.</p>
      <p role="alert" hidden></p>${btn('exp-import-submit','Import rover')}<button class="exp-back" type="button">Cancel</button></form></dialog>`);
    const robotSelect=$('#exp-robot'),dialog=$('.exp-import');
    robotSelect.onchange=()=>{
      if(robotSelect.value==='import'){robotSelect.value=robotId;dialog.showModal();}
      else robotId=robotSelect.value;
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
        robotId=imported.id;robotSelect.value=robotId;dialog.close();
      }catch(e){if(!signal.aborted){alert.textContent=e.message;alert.hidden=false;}}
      finally{button.disabled=false;}
    };
    $('#exp-task').value=task;$('#exp-robot').value=robotId;bindRoute();icons();
    $('#exp-review').onclick=()=>{url('flight',flight.id);flightReview();};
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
  async function replay(){
    setStage(2,'Mission replay');ensureSurface();
    route=run.request.waypoints;robotId=run.robot_id;task=run.request.task;dwell=run.request.dwell_s;
    const m=run.metrics;
    form.insertAdjacentHTML('beforeend',`<p class="exp-arrival">${safe(run.robot_snapshot.model.name)}</p>
    <section class="exp-outcome"><h2>${run.task_completed?(task==='science'?'Science dwell completed':'Parking dwell completed'):'Task unfinished'}</h2>
    <dl>${metric('Distance driven',m.distance_m.toFixed(2)+' m')}${metric('Elapsed',m.duration_s.toFixed(1)+' s')}${metric('Peak roll',m.maximum_roll_deg.toFixed(1)+'°')}${metric('Minimum battery',m.minimum_battery_wh.toFixed(2)+' Wh')}</dl>
    ${run.issues.map(v=>'<p>'+safe(v)+'</p>').join('')}</section>
    <div class="exp-telemetry"><strong id="exp-activity">At landing site</strong><span id="exp-velocity"></span><span id="exp-battery"></span></div>
    ${btn('exp-reroute','Edit traverse')}
    ${flightDetails()}<details class="exp-notes"><summary>Simulation details</summary><p>MuJoCo rigid contact on 5 m LOLA terrain. Solar power uses dated DE421 directions, local terrain horizons and the recorded body attitude. Scene fill light helps reveal terrain in shadow. Friction and power properties are engineering assumptions. The controller has 180 s to reach the route and finish its dwell within 0.18 m.</p><a href="/api/v1/runs/${encodeURIComponent(run.id)}" target="_blank" rel="noopener">Open run data ↗</a></details>
    <button id="exp-orbit-replay" class="exp-back">View flight path</button> <button id="exp-new" class="exp-back">New flight</button>`);
    caption(run.landing.name,dateLabel(run.landing.utc));icons();
    $('#exp-reroute').onclick=()=>{url('route',flight.id);traverseForm();};
    $('#exp-orbit-replay').onclick=()=>{url('flight',flight.id);flightReview();};
    $('#exp-new').onclick=()=>{url();flightForm();};
    if(!scene)return;
    const selected=run;
    try{
      await scene.prepare(selected);
      if(signal.aborted||stage!==2||selected!==run)return;
      $('#exp-scrub').max=run.trace.at(-1).t_s;scene.seek(0);player.hidden=true;scene.startFly();
    }catch(e){if(!signal.aborted)viewerError('Replay view unavailable. '+e.message);}
  }
  $('#exp-play').onclick=()=>{if(scene.time>=run.trace.at(-1).t_s)scene.seek(0);scene.playing=!scene.playing;scene.seek(scene.time);};
  $('#exp-scrub').oninput=e=>{scene.playing=false;scene.seek(Number(e.target.value));};
  $('#exp-speed').onchange=e=>scene.speed=Number(e.target.value);
  $('#exp-fly').onclick=()=>{player.hidden=true;scene.startFly();};
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
    else if(result.kind==='traverse'){run=result;flight=await api('runs/'+encodeURIComponent(run.flight_id));url('mission',run.id);await replay();}
    else throw Error('This job belongs to a different workspace.');
  }
  async function launch(path,body,resumeId){
    if(busy)return;
    busy=true;showError('');
    try{
      if(resumeId){
        const saved=await api('jobs/'+encodeURIComponent(resumeId));
        if(saved.kind==='traverse'){
          path='traverses';flight=await api('runs/'+encodeURIComponent(saved.request.flight_id));
          ({waypoints:route,task,dwell_s:dwell,robot_id:robotId}=saved.request);
        }else if(saved.kind==='flight'){
          path='flights';siteId=saved.request.site_id;departure=saved.request.departure_utc.slice(0,16);hours=saved.request.transfer_hours;
        }else throw Error('This job belongs to a different workspace.');
      }
      const id=resumeId||(await api(path,body)).id;
      url('job',id);
      form.innerHTML=`<h1>${path==='flights'?'Calculating flight':'Running mission'}</h1><div class="exp-progress" role="status"><progress max="1"></progress><span>Preparing inputs</span></div><button id="exp-cancel" class="exp-back">Cancel run</button>`;
      $('#exp-cancel').onclick=()=>api('jobs/'+encodeURIComponent(id)+'/cancel',{}).catch(e=>showError(e.message));
      await finishJob(id);
    }catch(e){if(!signal.aborted){if(flight && path!=='flights'){url('route',flight.id);traverseForm();}else{url();flightForm();}showError(e.message);}}
    finally{busy=false;}
  }
  async function init(){
    setStage(0,'Plan your flight');
    try{
      [sites,robots]=await Promise.all([api('sites'),api('robots')]);
      robots=robots.filter(r=>r.profile&&r.model?.physical_ready);
      robotId=(robots.find(r=>r.source_class==='hypothetical_reference')||robots[0])?.id;
      if(!sites.some(s=>s.available)||!robotId)throw Error('Prepare the lunar data and a physical rover before running a mission.');
      siteId=sites.find(s=>s.available).id;
      const params=new URLSearchParams(location.search);
      if(params.has('job')){await launch(null,null,params.get('job'));return;}
      if(params.has('mission')){
        run=await api('runs/'+encodeURIComponent(params.get('mission')));
        if(run.kind!=='traverse')throw Error('This link requires a recorded traverse.');
        flight=await api('runs/'+encodeURIComponent(run.flight_id));await replay();
      }else if(params.has('flight')||params.has('route')){
        flight=await api('runs/'+encodeURIComponent(params.get('flight')||params.get('route')));
        if(flight.kind!=='flight')throw Error('This link requires a solved flight.');
        if(params.has('route'))traverseForm();else await flightReview();
      }else flightForm();
    }catch(e){
      if(!signal.aborted){showError(e.message);form.insertAdjacentHTML('beforeend','<button id="exp-retry" class="exp-back">Start again</button>');$('#exp-retry').onclick=()=>{url();init();};}
    }
  }
  icons();init();
  return ()=>{abort.abort();closeOrbit?.();scene?.dispose();};
}
