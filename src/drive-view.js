import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {advanceDrive, parkedDrive, loadViper, nominalSpeed, radius} from './viper-drive.js';
import {groundHeight, loadGround, loadDriveImage, terrainMesh} from './drive-ground.js';
import {applyReplay,drawReplayPaths,loadReplay,replayAssembly} from './viper-replay.js';
import {arrayPower,replayArrayEnergy,manualBodyToEnu} from './viper-array.js';
import {DriveSunlight,loadDriveSource} from './drive-sunlight.js';
import {geometryReferenceMarkup,mountGeometryReference} from './drive-geometry-reference.js';
import {terrainComparisonMarkup,renderTerrainComparison} from './drive-terrain-comparison.js';
import {wheelPanelMarkup, renderWheelSample} from './drive-wheels.js';
import {mountParkedPower} from './parked-view.js';
import './drive.css';

const directions={w:'forward',s:'reverse',a:'left',d:'right',arrowup:'forward',arrowdown:'reverse',arrowleft:'left',arrowright:'right'};
function release(object) {
  const materials=new Set(), geometries=new Set();
  object.traverse(n=>{n.userData.texture?.dispose();if(n.geometry)geometries.add(n.geometry);if(n.material)for(const m of [].concat(n.material))materials.add(m);});
  for(const m of materials)m.dispose();
  for(const g of geometries)g.dispose();
}

export function mountDrive(root,{logo,icon,icons}) {
  root.innerHTML=`<main class="drive-page"><header class="app-header"><a class="brand" href="/" aria-label="Clavius home">${logo}</a><nav class="drive-nav" aria-label="Workspace"><a href="/app">Explorer</a><span aria-current="page">Rover drive</span><a href="/app/simulation">Simulation</a></nav></header>
  <section class="drive-stage" aria-label="Lunar driving surface"><div class="drive-canvas"></div><button class="drive-rover-pin" aria-label="Return to rover camera" hidden>VIPER</button>
  <div class="drive-hud"><div><span class="eyebrow">LUNAR SOUTH POLE</span><h1>VIPER surface drive</h1></div><label>Terrain site<select data-site><option value="connecting-ridge">Connecting Ridge</option><option value="shackleton-rim">Shackleton rim</option></select></label></div>
  <div class="drive-camera"><button data-camera aria-label="Change to site overview">${icon('maximize')} Site overview</button><button data-image aria-pressed="true">LROC mosaic</button><button data-contours aria-pressed="false">${icon('layers')} Contours</button></div>
  <div class="drive-sun-readout" hidden><strong data-disk></strong><span data-sun-angles></span><span data-earth></span><details data-array hidden><summary>Solar array estimate <b data-array-total></b></summary><dl><dt>Port</dt><dd data-watts="port"></dd><dt>Starboard</dt><dd data-watts="starboard"></dd><dt>Aft</dt><dd data-watts="aft"></dd></dl><span data-array-energy></span></details><small data-sun-stamp></small></div><p class="drive-loading" role="status">Loading NASA terrain and rover geometry…</p></section>
  <section class="drive-console" aria-label="Drive controls"><div class="drive-instruments"><div><small>Ground speed</small><strong data-speed>0.00 m/s</strong></div><div><small>Distance</small><strong data-distance>0.0 m</strong></div><div><small>Front-left steer</small><strong data-steer>0.0°</strong></div><div><small>Local slope</small><strong data-slope>—</strong></div></div>
  <div class="drive-buttons"><select data-motion aria-label="Motion model"><option value="manual">Manual drive</option><option value="native">Recorded dynamics</option></select><select data-realization aria-label="Terrain surface"><option value="nominal">Nominal terrain</option><option value="pgda78-0001">Terrain clone 001</option></select><select data-maneuver aria-label="Steering maneuver"><option value="turn">Coordinated turn</option><option value="crab">Crab steering</option></select><button data-demo disabled>Start traverse</button><select data-rate aria-label="Simulation rate"><option value="1">Real time</option><option value="10" selected>10× time</option><option value="30">30× time</option></select>
  <div class="drive-pad" aria-label="Hold to drive">${[['left','←'],['forward','↑'],['reverse','↓'],['right','→']].map(([d,k])=>`<button data-dir="${d}" aria-label="Drive ${d}">${k}</button>`).join('')}</div><button data-reset aria-label="Reset rover position">${icon('rotate-ccw')}</button></div><label class="drive-clock" hidden>Replay time <input type="range" data-scrub min="0" max="20" step=".05" value="0"><output data-time>0.00 / 20 s</output></label>
  <details class="drive-paths" hidden><summary>Compare recorded paths</summary><div><canvas width="520" height="260" aria-label="Plan view of both recorded paths. East is right and north is up."></canvas><dl><dt>Straight · dashed</dt><dd data-path-turn></dd><dt>Crab · solid</dt><dd data-path-crab></dd></dl></div></details>
  ${wheelPanelMarkup}${terrainComparisonMarkup}</section>
  <footer class="drive-foot"><span data-navigation-hint>WASD to drive · Drag to orbit · Scroll to zoom</span><div><button data-park disabled>Parked power</button><button data-sky>Sun at rover</button><button data-info>Data & rover model</button></div></footer>
  <dialog class="drive-sky-dialog drive-info" aria-labelledby="sky-heading"><form data-sky-form><button type="button" data-sky-close>Close</button><h2 id="sky-heading">Sun at the rover</h2><p>Choose a UTC start for the drive. Clavius samples the Sun and Earth from 0.5 m above the selected terrain at the rover’s position.</p>
  <label>Lighting<select data-lighting><option value="survey">Survey light</option><option value="dated">Mission sunlight</option></select></label>
  <fieldset data-epochs><legend>Drive start (UTC)</legend><select data-epoch-choice aria-label="Choose an epoch"><option value="2028-01-01T12:00">1 Jan 2028 · 12:00 UTC</option><option value="2028-01-21T12:00" selected>21 Jan 2028 · 12:00 UTC</option><option value="2028-01-27T12:00">27 Jan 2028 · 12:00 UTC</option><option value="custom">Custom UTC start</option></select>
  <input type="datetime-local" data-utc aria-label="Custom UTC start" min="2000-01-01T00:00" max="2049-12-31T23:59" value="2028-01-21T12:00" hidden></fieldset>
  <p>The directional light follows visibility at the rover. Other locations in the view share this lighting approximation. The three listed epochs ship with Recorded dynamics. Manual driving and custom dates use the local simulation service. Mission sunlight uses shaded terrain with a display fill light. The historical photo layer is available in survey light. Expand Solar array estimate to see how heading, tilt and terrain shadow affect each of VIPER’s three panels. The estimate is gross generation before electrical loads. It assumes clean panels and omits temperature losses and shading by the rover.</p>${geometryReferenceMarkup}<button type="submit">Apply lighting</button></form></dialog>
  <dialog class="drive-info drive-model-dialog"><button data-close>Close</button><h2>VIPER surface drive</h2><p>The articulated chassis, suspension and wheels come from Project Chrono’s VIPER model. Four-wheel steering follows an ideal rolling path at the documented nominal speed of 0.1 m/s. In a coordinated turn the wheels follow different arcs. Crab steering points all four wheels the same way so you can travel diagonally while the chassis keeps its heading. Hold forward and left or right together to steer. Manual steering angles can reach the documented ±50°. Pitch and roll follow the terrain. The drive clock can be accelerated.</p><p>Recorded dynamics replays 20 seconds of Project Chrono rigid-contact simulation on this site. Choose a straight traverse or a 25° crab traverse to inspect the solver’s chassis, suspension and wheel poses. Both use the native model’s 30° steering limit. The 434.92 kg model uses assumed friction, a 1 ms step and ideal wheel-speed control under 1.62 m/s² gravity.</p><p>The photographed surface comes from the LROC controlled south-pole average mosaic at 1 m/pixel. It combines historical exposures. Missing coverage shows shaded topography. The local surface uses NASA PGDA78 with 5 m posting. Terrain clone 001 is a published reconstruction of possible elevations. Switching surfaces recalculates wheel contact in recorded drives and uses the corresponding sunlight horizon. The surrounding 40.96 km landscape uses PGDA90 with 80 m posting. Survey lighting and fine material grain are illustrative. Mission sunlight uses a dated Sun direction and terrain horizon at the rover. Recorded wheel slip estimates use nominal wheel radius and rigid terrain. Soil deformation, sinkage and flight suspension response remain unresolved.</p><label class="grain-setting"><input type="checkbox" data-grain checked> Show illustrative surface grain</label><a href="/data/drive/index.json" target="_blank" rel="noreferrer">Terrain files and source hashes</a><a href="/data/drive/sunlight.json" target="_blank" rel="noreferrer">Dated sunlight samples and source hashes</a><a href="/robots/viper/source.json" target="_blank" rel="noreferrer">Rover geometry and hardware sources</a></dialog></main>`;
  icons();
  const $=s=>root.querySelector(s), host=$('.drive-canvas'), status=$('.drive-loading'), lifetime=new AbortController();
  let renderer;
  try {renderer=new THREE.WebGLRenderer({antialias:true,logarithmicDepthBuffer:true});}
  catch {status.textContent='The rover view requires WebGL 2. Enable hardware acceleration and reload.';return ()=>{};}
  renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));
  renderer.setClearColor(0x06080a);renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;host.append(renderer.domElement);
  const scene=new THREE.Scene(), camera=new THREE.PerspectiveCamera(44,1,.08,350000);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.enablePan=false;controls.minDistance=2.1;controls.maxDistance=22000;controls.maxPolarAngle=Math.PI*.48;
  const light=new THREE.DirectionalLight(0xfff6e5,2.75);
  light.castShadow=true;light.shadow.mapSize.set(2048,2048);
  Object.assign(light.shadow.camera,{left:-5,right:5,top:5,bottom:-5,near:.1,far:120});
  light.shadow.camera.updateProjectionMatrix();light.shadow.normalBias=.007;light.shadow.bias=-.00015;
  const fill=new THREE.HemisphereLight(0xdde7ff,0x92918a,1.05);scene.add(light,light.target,fill);
  const terrain=new THREE.Group();scene.add(terrain);
  const held=new Set(), target=new THREE.Vector3(), up=new THREE.Vector3(), forward=new THREE.Vector3(), side=new THREE.Vector3(), basis=new THREE.Matrix4(), lastTarget=new THREE.Vector3();
  const sunOffset=new THREE.Vector3(-34,18,22);
  let dated=false,startUtc='2028-01-21T12:00:00Z',manualTime=0,lightingSite;
  let observation, hardware, cachedEnergy;
  const manualOrientation = new THREE.Quaternion();
  const sky=new DriveSunlight(result=>{
    observation = result;
    if (!result?.sample) $('[data-array]').hidden=true;
    const readout=$('.drive-sun-readout');
    readout.hidden=!dated;
    const sample=result?.sample;
    if(!dated || !sample){
      sunOffset.set(-34,18,22);light.intensity=2.75;fill.intensity=1.05;
      $('[data-disk]').textContent=result?.unavailable?'Sunlight unavailable':'Computing sunlight…';
      $('[data-sun-angles]').textContent='Survey light shown';
      $('[data-earth]').textContent='';
      $('[data-sun-stamp]').textContent=result?.unavailable?'Start the simulation service or use a packaged replay epoch.':'';
      return;
    }
    const [east,north,up]=sample.sun_site_enu;
    sunOffset.set(east,up,-north).multiplyScalar(46);
    light.intensity=2.75*sample.disk_fraction;fill.intensity=.34;
    $('[data-disk]').textContent=(sample.disk_fraction*100).toFixed(1)+'% of solar disk visible';
    $('[data-sun-angles]').textContent='Sun '+sample.sun_elevation_deg.toFixed(2)+'° · Horizon '+sample.sun_horizon_deg.toFixed(2)+'°';
    $('[data-earth]').textContent='Earth center '+(sample.earth_center_visible?'visible':'occluded');
    $('[data-sun-stamp]').textContent=sample.utc+' · '+result.source+' · E '+sample.east_m.toFixed(1)+' / N '+sample.north_m.toFixed(1)+' m';
  });
  let imageryIndex,showImage=true,showGrain=true,replayIndex,recording,assembly,native=false,replayTime=0;
  let plottedTime, plottedRecording, comparison, realization='nominal';
  const comparisonPanel=$('.drive-comparison');
  function showComparison(){
    comparisonPanel.hidden=!native||!active;
    if(comparisonPanel.hidden)return;
    const mode=$('[data-maneuver]').value==='crab'?'crab':'straight';
    renderTerrainComparison(comparisonPanel,comparison.sites[lightingSite].comparison[mode],comparison.realization);
  }
  let state=parkedDrive(), local, rover, catalog, currentRequest, active=false, demo=false, overview=false, contour=false, frame,last=performance.now(),hudTime=0;
  const parked = mountParkedPower(root,()=>{
    if(!active)return;
    setDemo(false);held.clear();
    const chassis=native?assembly.children[0]:null;
    const axis=chassis?new THREE.Vector3(1,0,0).applyQuaternion(chassis.quaternion):null;
    const heading=axis?Math.atan2(axis.x,axis.y):Math.PI/2-state.heading;
    return {site:lightingSite,realization,name:catalog.sites[lightingSite].name,utc:startUtc,
      east:chassis?chassis.position.x:state.east,north:chassis?chassis.position.y:state.north,
      heading:(heading*180/Math.PI%360+360)%360};
  });
  $('[data-park]').onclick=()=>parked.open();
  const resize=()=>{const w=host.clientWidth,h=host.clientHeight;if(w&&h){camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h,false);}};
  const observer=new ResizeObserver(resize);observer.observe(host);resize();
  const pinPoint=new THREE.Vector3(), planCenter=new THREE.Vector3(), cameraOffset=new THREE.Vector3();
  let regionalHalf=0, regionalGrid;
  function cameraMode(wide) {
    overview=wide;
    controls.enablePan=wide;controls.screenSpacePanning=false;
    if(wide){
      const halfFov=THREE.MathUtils.degToRad(camera.fov/2);
      const tightFov=Math.min(halfFov,Math.atan(Math.tan(halfFov)*camera.aspect));
      const fit=regionalHalf*Math.SQRT2/Math.sin(tightFov);
      controls.maxDistance=fit*1.5;
      camera.far=Math.max(350000,fit*2);camera.updateProjectionMatrix();
      controls.target.set(0,groundHeight(local,0,0),0);
      camera.position.copy(controls.target).addScaledVector(cameraOffset.set(.12,1,.42).normalize(),fit);
    }else{
      controls.maxDistance=22000;controls.target.copy(target);
      camera.position.copy(target).add(cameraOffset.set(3.1,1.15,3.7).multiplyScalar(camera.aspect<1?1.35:1));
    }
    $('.drive-rover-pin').hidden=!wide;
    $('[data-navigation-hint]').textContent=wide?'40.96 km site · Shift-drag or use two fingers to pan · Double-click terrain to inspect':'WASD to drive · Drag to orbit · Scroll to zoom';
    controls.update();lastTarget.copy(target);
    $('[data-camera]').textContent=wide?'Follow rover':'Site overview';
    $('[data-camera]').setAttribute('aria-label',wide?'Follow rover':'Change to site overview');
  }
  function setDemo(on) {demo=on;$('[data-demo]').textContent=on?(native?'Pause replay':'Pause traverse'):(native?'Play replay':'Start traverse');$('[data-demo]').setAttribute('aria-pressed',String(on));}
  function pose(){
    const {east:e,north:n,heading:h}=state;
    const dx=(groundHeight(local,e+.55,n)-groundHeight(local,e-.55,n))/1.1;
    const dn=(groundHeight(local,e,n+.55)-groundHeight(local,e,n-.55))/1.1;
    up.set(-dx,1,dn).normalize();
    forward.set(Math.cos(h),dx*Math.cos(h)+dn*Math.sin(h),-Math.sin(h)).normalize();
    side.crossVectors(up,forward).normalize();
    rover.body.quaternion.setFromRotationMatrix(basis.makeBasis(forward,side,up));
    rover.body.position.set(e,groundHeight(local,e,n),-n).addScaledVector(up,radius);
    rover.wheels.forEach(({steering,spin},i)=>{steering.rotation.z=state.wheels[i].steer;spin.rotation.y=state.wheels[i].spin;});
    target.copy(rover.body.position).addScaledVector(up,.8);
    follow();
    return Math.atan(Math.hypot(dx,dn))*180/Math.PI;
  }
  function showArray(maneuver) {
    const panel = $('[data-array]');
    const sun = observation?.sample;
    const orientation = native ? assembly.children[0].quaternion : observation?.orientation;
    const watts = orientation && arrayPower(hardware, sun, orientation);
    panel.hidden = !watts;
    if (!watts) return;
    $('[data-array-total]').textContent=Math.round(watts.total)+' W';
    for (const [face,w] of Object.entries(watts.faces)) {
      $('[data-watts="'+face+'"]').textContent=Math.round(w)+' W';
    }
    const series = observation.series;
    const energy = $('[data-array-energy]');
    energy.hidden = !native || !series;
    if (native && series) {
      const trace = recording[maneuver];
      if (cachedEnergy?.series !== series || cachedEnergy.trace !== trace) {
        cachedEnergy = {series, trace, valueAt:replayArrayEnergy(hardware,series,trace.poses)};
      }
      energy.hidden = !cachedEnergy.valueAt;
      if (cachedEnergy.valueAt) energy.textContent = 'Generated since start · '+cachedEnergy.valueAt(replayTime).toFixed(3)+' Wh';
    }
  }
  function follow(){
    light.target.position.copy(target);light.position.copy(target).add(sunOffset);
    if(!overview){camera.position.add(target.clone().sub(lastTarget));controls.target.copy(target);}
    lastTarget.copy(target);
  }
  function reset(){manualTime=0;sky.reset();state=parkedDrive();held.clear();pose();cameraMode(false);}
  const wheelPanel=$('.drive-wheels');
  let lastWheelData, lastWheelFrame;
  function syncWheelPanel(){
    if(!active || !native || !wheelPanel.open)return;
    const data=recording[$('[data-maneuver]').value].wheels;
    const frame=Math.floor(replayTime*20+1e-10);
    if(data===lastWheelData && frame===lastWheelFrame)return;
    renderWheelSample(wheelPanel,data,replayTime,replayIndex.wheel_telemetry.min_rim_speed_m_s);
    lastWheelData=data;lastWheelFrame=frame;
  }
  wheelPanel.ontoggle=syncWheelPanel;
  function tick(now) {
    frame=requestAnimationFrame(tick);
    const dt=Math.max(0,(now-last)/1000);last=now;
    if(!active)return;
    let slope,speed,distance,east,north,leftFrontSteer;
    const maneuver = $('[data-maneuver]').value;
    const elapsed=(document.hidden?0:Math.min(dt,1))*Number($('[data-rate]').value);
    if(native){
      if(demo)replayTime=Math.min(20,replayTime+elapsed);
      const measured=applyReplay(assembly,recording[maneuver],replayTime);
      leftFrontSteer=measured.leftFrontSteer;
      const p=assembly.children[0].position;east=p.x;north=p.y;
      target.set(p.x,p.z+.8,-p.y);follow();
      const dx=groundHeight(local,p.x+.5,p.y)-groundHeight(local,p.x-.5,p.y);
      const dn=groundHeight(local,p.x,p.y+.5)-groundHeight(local,p.x,p.y-.5);
      slope=Math.atan(Math.hypot(dx,dn))*180/Math.PI;
      speed=measured.speed;distance=measured.distance;
      if(now-hudTime>100){
        syncWheelPanel();
        if($('.drive-paths').open && (plottedTime!==replayTime || plottedRecording!==recording)){
          drawReplayPaths($('.drive-paths canvas'),recording,replayTime);
          plottedTime=replayTime;plottedRecording=recording;
        }
        $('[data-scrub]').value=replayTime;$('[data-time]').textContent=replayTime.toFixed(2)+' / 20 s';}
      if(replayTime===20&&demo)setDemo(false);
    }else{
      let throttle=demo?1:Number(held.has('forward'))-Number(held.has('reverse'));
      const demoSteer = maneuver === 'crab' ? .5 : .28*Math.sin(state.distance/7);
      const steering = demo ? demoSteer : Number(held.has('left'))-Number(held.has('right'));
      const next=advanceDrive(state,throttle,steering,elapsed,maneuver);
      if(Math.max(Math.abs(next.east),Math.abs(next.north))<local.half_extent_m-81)state=next;
      else {throttle=0;setDemo(false);status.textContent='Edge of the drive area. Reverse or reset the rover.';status.hidden=false;}
      if(throttle)manualTime+=elapsed;east=state.east;north=state.north;
      leftFrontSteer=state.wheels[0].steer;
      slope=pose();speed=Math.abs(throttle)*nominalSpeed;distance=state.distance;
    }
    if(dated && !document.hidden)sky.update({site:lightingSite,realization,start:startUtc,elapsed:native?replayTime:manualTime,
      east,north,native,replayHash:recording[maneuver].sha256,
      orientation:native?null:manualBodyToEnu(rover.body.quaternion,manualOrientation)},now);
    if(now-hudTime>100){
      if(dated)showArray(maneuver);
      $('[data-speed]').textContent=speed.toFixed(2)+' m/s';
      $('[data-distance]').textContent=distance.toFixed(1)+' m';
      $('[data-steer]').textContent=(leftFrontSteer*180/Math.PI).toFixed(1)+'°';
      $('[data-slope]').textContent=slope.toFixed(1)+'°';hudTime=now;
    }
    controls.update();
    if(!overview && Math.abs(camera.position.x)<local.half_extent_m && Math.abs(camera.position.z)<local.half_extent_m)
      camera.position.y=Math.max(camera.position.y,groundHeight(local,camera.position.x,-camera.position.z)+.18);
    if(overview){
      planCenter.copy(controls.target);
      controls.target.x=THREE.MathUtils.clamp(controls.target.x,-regionalHalf,regionalHalf);
      controls.target.z=THREE.MathUtils.clamp(controls.target.z,-regionalHalf,regionalHalf);
      const focusGrid=Math.max(Math.abs(controls.target.x),Math.abs(controls.target.z))<local.half_extent_m-80 ? local : regionalGrid;
      controls.target.y=groundHeight(focusGrid,controls.target.x,-controls.target.z);
      camera.position.add(planCenter.subVectors(controls.target,planCenter));
      camera.updateMatrixWorld();
      pinPoint.copy(target).project(camera);
      const marker=$('.drive-rover-pin');
      marker.hidden=Math.abs(pinPoint.x)>.96 || Math.abs(pinPoint.y)>.94 || Math.abs(pinPoint.z)>1;
      marker.style.left=(50+50*pinPoint.x)+'%';marker.style.top=(50-50*pinPoint.y)+'%';
    }
    renderer.render(scene,camera);
  }
  async function siteChange(){
    const id=$('[data-site]').value, selected=$('[data-realization]').value;
    const sameSite=id===lightingSite;
    const savedTime=sameSite ? replayTime : 0;
    const savedDemo=demo;
    currentRequest?.abort();const request=currentRequest=new AbortController();
    active=false;$('[data-park]').disabled=true;sky.reset();held.clear();setDemo(false);$('[data-demo]').disabled=true;
    comparisonPanel.hidden=true;$('.drive-rover-pin').hidden=true;$('.drive-wheels').hidden=true;$('.drive-paths').hidden=true;
    for(const indicator of root.querySelectorAll('.drive-instruments strong'))indicator.textContent='—';
    status.hidden=false;status.textContent='Loading '+catalog.sites[id].name+'…';
    try{
      const alternative=selected===comparison.realization ? comparison.sites[id] : null;
      const [nominal,regional]=catalog.sites[id].levels;
      const near=await loadGround(alternative?.grid ?? nominal,request.signal);
      const straight=alternative?.replays ?? replayIndex.sites[id];
      const [turnTrace,crabTrace]=await Promise.all([straight,straight.maneuvers.crab].map(entry=>loadReplay(entry,near,request.signal)));
      if(request.signal.aborted)return;
      if(sameSite){
        const old=terrain.children[1];
        const updated=terrainMesh(near,near.half_extent_m,regionalGrid,old.userData.texture);
        delete old.userData.texture;
        terrain.remove(old);release(old);terrain.add(updated);
      }else{
        const far=await loadGround(regional,request.signal);
        const images=await Promise.all(['drive','horizon'].map(level=>loadDriveImage(imageryIndex.sites[id][level],request.signal)));
        if(request.signal.aborted){images.forEach(t=>t.dispose());return;}
        release(terrain);terrain.clear();regionalGrid=far;regionalHalf=far.half_extent_m;
        terrain.add(terrainMesh(far,near.half_extent_m,null,images[1]),terrainMesh(near,near.half_extent_m,far,images[0]));
      }
      local=near;
      for(const mesh of terrain.children){mesh.userData.grain.value=Number(showGrain);mesh.userData.contours.value=Number(contour);mesh.userData.imagery.value=Number(showImage&&!dated);}
      recording = {turn:turnTrace, crab:crabTrace};
      realization=selected;lightingSite=id;active=true;$('[data-park]').disabled=false;replayTime=savedTime;$('.drive-wheels').hidden=!native;$('.drive-paths').hidden=!native;if(sameSite){pose();cameraMode(false);}else{reset();}
      setDemo(sameSite?savedDemo:!matchMedia('(prefers-reduced-motion: reduce)').matches);showComparison();
      syncWheelPanel();$('[data-demo]').disabled=false;status.hidden=true;
      const url=new URL(location.href);url.searchParams.set('site',id);
      if(selected==='nominal')url.searchParams.delete('surface');else url.searchParams.set('surface',selected);
      history.replaceState({},'',url);
    }catch(err){if(!request.signal.aborted)status.textContent='Could not load this site. '+err.message;}
  }
  function press(dir){if(!active||native)return;setDemo(false);held.add(dir);status.hidden=true;}
  function listen(node,type,fn){node.addEventListener(type,fn,{signal:lifetime.signal});}
  for(const b of root.querySelectorAll('[data-dir]')){
    listen(b,'pointerdown',e=>{e.preventDefault();b.setPointerCapture(e.pointerId);press(b.dataset.dir);});
    listen(b,'lostpointercapture',()=>held.delete(b.dataset.dir));
  }
  listen(window,'keydown',e=>{
    if(e.altKey||e.metaKey||e.ctrlKey||e.target.closest('input,dialog')||root.querySelector('dialog[open]'))return;
    if(e.target.closest('select') && e.key.startsWith('Arrow'))return;
    const d=directions[e.key.toLowerCase()];if(d){e.preventDefault();press(d);}
  });
  listen(window,'keyup',e=>held.delete(directions[e.key.toLowerCase()]));
  listen(window,'blur',()=>held.clear());
  $('[data-motion]').onchange=e=>{
    sky.reset();native=e.target.value==='native';held.clear();replayTime=0;
    $('[data-maneuver]').options[0].textContent = native ? 'Straight traverse' : 'Coordinated turn';
    $('[data-maneuver]').options[1].textContent = native ? '25° crab traverse' : 'Crab steering';
    if(rover){rover.body.visible=!native;assembly.visible=native;}
    $('.drive-wheels').hidden=!active||!native;$('.drive-paths').hidden=!active||!native;$('.drive-pad').hidden=native;$('.drive-clock').hidden=!native;$('[data-rate]').value=native?'1':'10';
    setDemo(active&&!matchMedia('(prefers-reduced-motion: reduce)').matches);
    showComparison();if(active){cameraMode(false);syncWheelPanel();}
  };
  $('[data-maneuver]').onchange=()=>{
    held.clear();sky.reset();
    if(native){replayTime=0;syncWheelPanel();showComparison();}
  };
  $('[data-scrub]').oninput=e=>{sky.reset();replayTime=Number(e.target.value);setDemo(false);syncWheelPanel();};
  listen(document,'visibilitychange',()=>{last=performance.now();held.clear();});
  $('[data-demo]').onclick=()=>{held.clear();if(native&&replayTime===20){replayTime=0;sky.reset();}setDemo(!demo);};
  $('.drive-rover-pin').onclick=()=>{if(active)cameraMode(false);};
  listen(renderer.domElement,'dblclick',e=>{
    if(!active || !overview)return;
    const bounds=renderer.domElement.getBoundingClientRect(), ray=new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2(2*(e.clientX-bounds.left)/bounds.width-1,1-2*(e.clientY-bounds.top)/bounds.height),camera);
    const [hit]=ray.intersectObjects(terrain.children,false);
    if(!hit)return;
    cameraOffset.subVectors(camera.position,controls.target).normalize();
    controls.target.copy(hit.point);
    camera.position.copy(hit.point).addScaledVector(cameraOffset,180);
    controls.update();
  });
  $('[data-camera]').onclick=()=>{if(active)cameraMode(!overview);};
  $('[data-reset]').onclick=()=>{if(active){status.hidden=true;replayTime=0;setDemo(false);reset();syncWheelPanel();}};
  $('[data-grain]').onchange=e=>{
    showGrain=e.target.checked;
    for(const mesh of terrain.children)mesh.userData.grain.value=Number(showGrain);
  };
  $('[data-image]').onclick=e=>{showImage=!showImage;e.currentTarget.setAttribute('aria-pressed',String(showImage));for(const m of terrain.children)m.userData.imagery.value=Number(showImage);};
  $('[data-contours]').onclick=e=>{contour=!contour;e.currentTarget.setAttribute('aria-pressed',String(contour));for(const m of terrain.children)m.userData.contours.value=Number(contour);};
  const skyDialog=$('.drive-sky-dialog');
  const refreshReference=mountGeometryReference($('.geometry-reference'),()=>{
    const site=$('[data-site]').value;
    return {site,name:$('[data-site]').selectedOptions[0].textContent,start:startUtc};
  },lifetime.signal);
  const epochChoice=$('[data-epoch-choice]'),utcInput=$('[data-utc]'),lighting=$('[data-lighting]');
  function editLighting(){
    $('[data-epochs]').disabled=lighting.value==='survey';utcInput.hidden=epochChoice.value!=='custom';
    utcInput.required=!utcInput.hidden;utcInput.disabled=utcInput.hidden;
  }
  $('[data-sky]').onclick=()=>{
    held.clear();lighting.value=dated?'dated':'survey';
    const current=startUtc.slice(0,16);
    epochChoice.value=[...epochChoice.options].some(o=>o.value===current)?current:'custom';
    utcInput.value=current;editLighting();skyDialog.showModal();refreshReference();
  };
  lighting.onchange=editLighting;epochChoice.onchange=editLighting;
  $('[data-sky-close]').onclick=()=>skyDialog.close();
  $('[data-sky-form]').onsubmit=e=>{
    e.preventDefault();dated=lighting.value==='dated';
    if(dated)startUtc=(epochChoice.value==='custom'?utcInput.value:epochChoice.value)+':00Z';
    sky.reset();$('[data-image]').disabled=dated;$('[data-image]').setAttribute('aria-pressed',String(showImage&&!dated));
    for(const m of terrain.children)m.userData.imagery.value=Number(showImage&&!dated);
    skyDialog.close();
  };
  $('[data-info]').onclick=()=>{setDemo(false);held.clear();$('.drive-model-dialog').showModal();};$('[data-close]').onclick=()=>$('.drive-model-dialog').close();
  $('[data-realization]').onchange=$('[data-site]').onchange=()=>{if(catalog&&rover)siteChange();};
  (async()=>{
    try{
      const r=await fetch('/data/drive/index.json',{signal:lifetime.signal});if(!r.ok)throw new Error('Terrain catalogue unavailable.');
      catalog=await r.json();
      [replayIndex,comparison]=await Promise.all(['recordings','terrain_comparison'].map(name=>loadDriveSource(name,lifetime.signal)));
      sky.alternative=comparison;
      loadDriveSource('rover',lifetime.signal)
        .then(source=>{if(!lifetime.signal.aborted)hardware=source.solar_array;}).catch(()=>{});
      loadDriveSource('sunlight',lifetime.signal)
        .then(catalog=>{if(!lifetime.signal.aborted){sky.catalog=catalog;sky.reset();}}).catch(()=>{});
      const images=await fetch('/data/drive/imagery.json',{signal:lifetime.signal});
      if(!images.ok)throw new Error('LROC catalogue unavailable.');
      imageryIndex=await images.json();rover=await loadViper();
      if(lifetime.signal.aborted){release(rover.body);return;}
      assembly=replayAssembly(rover);assembly.visible=native;rover.body.visible=!native;scene.add(rover.body,assembly);const id=new URLSearchParams(location.search).get('site');
      if(Object.hasOwn(catalog.sites,id))$('[data-site]').value=id;
      if(new URLSearchParams(location.search).get('surface')===comparison.realization)$('[data-realization]').value=comparison.realization;
      await siteChange();
    }catch(err){if(!lifetime.signal.aborted)status.textContent='Could not open the drive view. '+err.message;}
  })();
  frame=requestAnimationFrame(tick);
  return ()=>{parked.dispose();dated=false;sky.reset();lifetime.abort();currentRequest?.abort();cancelAnimationFrame(frame);observer.disconnect();controls.dispose();release(scene);light.shadow.dispose();renderer.dispose();};
}
