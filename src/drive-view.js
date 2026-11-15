import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {advanceDrive, parkedDrive, loadViper, nominalSpeed, radius} from './viper-drive.js';
import {groundHeight, loadGround, loadDriveImage, terrainMesh} from './drive-ground.js';
import {applyReplay,loadReplay,replayAssembly} from './viper-replay.js';
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
  <section class="drive-stage" aria-label="Lunar driving surface"><div class="drive-canvas"></div>
  <div class="drive-hud"><div><span class="eyebrow">LUNAR SOUTH POLE</span><h1>VIPER surface drive</h1></div><label>Terrain site<select data-site><option value="connecting-ridge">Connecting Ridge</option><option value="shackleton-rim">Shackleton rim</option></select></label></div>
  <div class="drive-camera"><button data-camera aria-label="Change to site overview">${icon('maximize')} Site overview</button><button data-image aria-pressed="true">LROC mosaic</button><button data-contours aria-pressed="false">${icon('layers')} Contours</button></div>
  <p class="drive-loading" role="status">Loading NASA terrain and rover geometry…</p></section>
  <section class="drive-console" aria-label="Drive controls"><div class="drive-instruments"><div><small>Ground speed</small><strong data-speed>0.00 m/s</strong></div><div><small>Distance</small><strong data-distance>0.0 m</strong></div><div><small>Local slope</small><strong data-slope>—</strong></div></div>
  <div class="drive-buttons"><select data-motion aria-label="Motion model"><option value="manual">Manual drive</option><option value="native">Recorded dynamics</option></select><button data-demo disabled>Start traverse</button><select data-rate aria-label="Simulation rate"><option value="1">Real time</option><option value="10" selected>10× time</option><option value="30">30× time</option></select>
  <div class="drive-pad" aria-label="Hold to drive">${[['left','←'],['forward','↑'],['reverse','↓'],['right','→']].map(([d,k])=>`<button data-dir="${d}" aria-label="Drive ${d}">${k}</button>`).join('')}</div><button data-reset aria-label="Reset rover position">${icon('rotate-ccw')}</button></div><label class="drive-clock" hidden>Replay time <input type="range" data-scrub min="0" max="20" step=".05" value="0"><output data-time>0.00 / 20 s</output></label></section>
  <footer class="drive-foot"><span>WASD to drive · Drag to orbit · Scroll to zoom</span><button data-info>Data & rover model</button></footer>
  <dialog class="drive-info"><button data-close>Close</button><h2>VIPER surface drive</h2><p>The articulated chassis, suspension and wheels come from Project Chrono’s VIPER model. Four-wheel steering follows an ideal rolling path at the documented nominal speed of 0.1 m/s. Pitch and roll follow the terrain. The drive clock can be accelerated.</p><p>Recorded dynamics replays 20 seconds of Project Chrono rigid-contact simulation on this site. It shows the solver’s chassis, suspension and wheel poses. The 434.92 kg model uses assumed friction, a 1 ms step and ideal wheel-speed control under 1.62 m/s² gravity.</p><p>The photographed surface comes from the LROC controlled south-pole average mosaic at 1 m/pixel. It combines historical exposures. Missing coverage shows shaded topography. The local surface uses NASA PGDA78 with 5 m posting. The surrounding 40.96 km landscape uses PGDA90 with 80 m posting. Display lighting and fine material grain are illustrative. Wheel slip, sinkage, battery draw and flight suspension response are unresolved in this preview.</p><a href="/data/drive/index.json" target="_blank" rel="noreferrer">Terrain files and source hashes</a><a href="/robots/viper/source.json" target="_blank" rel="noreferrer">Rover geometry and hardware sources</a></dialog></main>`;
  icons();
  const $=s=>root.querySelector(s), host=$('.drive-canvas'), status=$('.drive-loading'), lifetime=new AbortController();
  let renderer;
  try {renderer=new THREE.WebGLRenderer({antialias:true,logarithmicDepthBuffer:true});}
  catch {status.textContent='The rover view requires WebGL 2. Enable hardware acceleration and reload.';return ()=>{};}
  renderer.setPixelRatio(Math.min(devicePixelRatio,1.7));
  renderer.setClearColor(0x06080a);renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;host.append(renderer.domElement);
  const scene=new THREE.Scene(), camera=new THREE.PerspectiveCamera(44,1,.08,65000);
  const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.enablePan=false;controls.minDistance=2.1;controls.maxDistance=22000;controls.maxPolarAngle=Math.PI*.48;
  const light=new THREE.DirectionalLight(0xfff6e5,2.75);
  light.castShadow=true;light.shadow.mapSize.set(2048,2048);
  Object.assign(light.shadow.camera,{left:-5,right:5,top:5,bottom:-5,near:.1,far:120});
  light.shadow.camera.updateProjectionMatrix();light.shadow.normalBias=.007;light.shadow.bias=-.00015;
  scene.add(light,light.target,new THREE.HemisphereLight(0xdde7ff,0x92918a,1.05));
  const terrain=new THREE.Group();scene.add(terrain);
  const held=new Set(), target=new THREE.Vector3(), up=new THREE.Vector3(), forward=new THREE.Vector3(), side=new THREE.Vector3(), basis=new THREE.Matrix4(), lastTarget=new THREE.Vector3();
  const sunOffset=new THREE.Vector3(-34,18,22);
  let imageryIndex,showImage=true,replayIndex,recording,assembly,native=false,replayTime=0;
  let state=parkedDrive(), local, rover, catalog, currentRequest, active=false, demo=false, overview=false, contour=false, frame,last=performance.now(),hudTime=0;
  const resize=()=>{const w=host.clientWidth,h=host.clientHeight;if(w&&h){camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h);}};
  const observer=new ResizeObserver(resize);observer.observe(host);resize();
  function cameraMode(wide) {
    overview=wide;
    controls.target.copy(target);
    camera.position.copy(target).add(wide?new THREE.Vector3(1700,1900,2300):new THREE.Vector3(3.1,1.15,3.7).multiplyScalar(camera.aspect<1?1.35:1));
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
  function follow(){
    light.target.position.copy(target);light.position.copy(target).add(sunOffset);
    if(!overview){camera.position.add(target.clone().sub(lastTarget));controls.target.copy(target);}
    lastTarget.copy(target);
  }
  function reset(){state=parkedDrive();held.clear();pose();cameraMode(false);}
  function tick(now) {
    frame=requestAnimationFrame(tick);
    const dt=Math.max(0,(now-last)/1000);last=now;
    if(!active)return;
    let slope,speed,distance;
    const elapsed=(document.hidden?0:Math.min(dt,1))*Number($('[data-rate]').value);
    if(native){
      if(demo)replayTime=Math.min(20,replayTime+elapsed);
      const measured=applyReplay(assembly,recording,replayTime);
      const p=assembly.children[0].position;
      target.set(p.x,p.z+.8,-p.y);follow();
      const dx=groundHeight(local,p.x+.5,p.y)-groundHeight(local,p.x-.5,p.y);
      const dn=groundHeight(local,p.x,p.y+.5)-groundHeight(local,p.x,p.y-.5);
      slope=Math.atan(Math.hypot(dx,dn))*180/Math.PI;
      speed=measured.speed;distance=measured.distance;
      if(now-hudTime>100){$('[data-scrub]').value=replayTime;$('[data-time]').textContent=replayTime.toFixed(2)+' / 20 s';}
      if(replayTime===20&&demo)setDemo(false);
    }else{
      let throttle=demo?1:Number(held.has('forward'))-Number(held.has('reverse'));
      const steering=demo ? .28*Math.sin(state.distance/7) : Number(held.has('left'))-Number(held.has('right'));
      const next=advanceDrive(state,throttle,steering,elapsed);
      if(Math.max(Math.abs(next.east),Math.abs(next.north))<local.half_extent_m-81)state=next;
      else {throttle=0;setDemo(false);status.textContent='Edge of the drive area. Reverse or reset the rover.';status.hidden=false;}
      slope=pose();speed=Math.abs(throttle)*nominalSpeed;distance=state.distance;
    }
    if(now-hudTime>100){
      $('[data-speed]').textContent=speed.toFixed(2)+' m/s';
      $('[data-distance]').textContent=distance.toFixed(1)+' m';
      $('[data-slope]').textContent=slope.toFixed(1)+'°';hudTime=now;
    }
    controls.update();
    if(!overview && Math.abs(camera.position.x)<local.half_extent_m && Math.abs(camera.position.z)<local.half_extent_m)
      camera.position.y=Math.max(camera.position.y,groundHeight(local,camera.position.x,-camera.position.z)+.18);
    renderer.render(scene,camera);
  }
  async function siteChange(){
    const id=$('[data-site]').value;
    currentRequest?.abort();const request=currentRequest=new AbortController();
    active=false;held.clear();setDemo(false);$('[data-demo]').disabled=true;
    status.hidden=false;status.textContent='Loading '+catalog.sites[id].name+'…';
    try{
      const [near,far]=await Promise.all(catalog.sites[id].levels.map(l=>loadGround(l,request.signal)));
      const images=await Promise.all(['drive','horizon'].map(level=>loadDriveImage(imageryIndex.sites[id][level],request.signal)));
      if(request.signal.aborted){images.forEach(t=>t.dispose());return;}
      release(terrain);terrain.clear();local=near;
      terrain.add(terrainMesh(far,near.half_extent_m,null,images[1]),terrainMesh(near,near.half_extent_m,far,images[0]));
      for(const mesh of terrain.children){mesh.userData.contours.value=Number(contour);mesh.userData.imagery.value=Number(showImage);}
      recording=await loadReplay(replayIndex.sites[id],near,request.signal);
      if(request.signal.aborted)return;
      active=true;replayTime=0;reset();setDemo(!matchMedia('(prefers-reduced-motion: reduce)').matches);
      $('[data-demo]').disabled=false;status.hidden=true;
      const url=new URL(location.href);url.searchParams.set('site',id);history.replaceState({},'',url);
    }catch(err){if(!request.signal.aborted)status.textContent='Could not load this site. '+err.message;}
  }
  function press(dir){if(!active||native)return;setDemo(false);held.add(dir);status.hidden=true;}
  function listen(node,type,fn){node.addEventListener(type,fn,{signal:lifetime.signal});}
  for(const b of root.querySelectorAll('[data-dir]')){
    listen(b,'pointerdown',e=>{e.preventDefault();b.setPointerCapture(e.pointerId);press(b.dataset.dir);});
    listen(b,'lostpointercapture',()=>held.delete(b.dataset.dir));
  }
  listen(window,'keydown',e=>{
    if(e.altKey||e.metaKey||e.ctrlKey||e.target.closest('select,input,dialog')||$('.drive-info').open)return;
    const d=directions[e.key.toLowerCase()];if(d){e.preventDefault();press(d);}
  });
  listen(window,'keyup',e=>held.delete(directions[e.key.toLowerCase()]));
  listen(window,'blur',()=>held.clear());
  $('[data-motion]').onchange=e=>{
    native=e.target.value==='native';held.clear();replayTime=0;
    if(rover){rover.body.visible=!native;assembly.visible=native;}
    $('.drive-pad').hidden=native;$('.drive-clock').hidden=!native;$('[data-rate]').value=native?'1':'10';
    setDemo(active&&!matchMedia('(prefers-reduced-motion: reduce)').matches);
    if(active)cameraMode(false);
  };
  $('[data-scrub]').oninput=e=>{replayTime=Number(e.target.value);setDemo(false);};
  listen(document,'visibilitychange',()=>{last=performance.now();held.clear();});
  $('[data-demo]').onclick=()=>{held.clear();if(native&&replayTime===20)replayTime=0;setDemo(!demo);};
  $('[data-camera]').onclick=()=>{if(active)cameraMode(!overview);};
  $('[data-reset]').onclick=()=>{if(active){status.hidden=true;replayTime=0;setDemo(false);reset();}};
  $('[data-image]').onclick=e=>{showImage=!showImage;e.currentTarget.setAttribute('aria-pressed',String(showImage));for(const m of terrain.children)m.userData.imagery.value=Number(showImage);};
  $('[data-contours]').onclick=e=>{contour=!contour;e.currentTarget.setAttribute('aria-pressed',String(contour));for(const m of terrain.children)m.userData.contours.value=Number(contour);};
  $('[data-info]').onclick=()=>{setDemo(false);held.clear();$('.drive-info').showModal();};$('[data-close]').onclick=()=>$('.drive-info').close();
  $('[data-site]').onchange=()=>{if(catalog&&rover)siteChange();};
  (async()=>{
    try{
      const r=await fetch('/data/drive/index.json',{signal:lifetime.signal});if(!r.ok)throw new Error('Terrain catalogue unavailable.');
      catalog=await r.json();
      const meta=await fetch('/data/drive/replays.json',{signal:lifetime.signal});
      if(!meta.ok)throw new Error('Native replay catalogue unavailable.');
      replayIndex=await meta.json();
      const images=await fetch('/data/drive/imagery.json',{signal:lifetime.signal});
      if(!images.ok)throw new Error('LROC catalogue unavailable.');
      imageryIndex=await images.json();rover=await loadViper();
      if(lifetime.signal.aborted){release(rover.body);return;}
      assembly=replayAssembly(rover);assembly.visible=native;rover.body.visible=!native;scene.add(rover.body,assembly);const id=new URLSearchParams(location.search).get('site');
      if(Object.hasOwn(catalog.sites,id))$('[data-site]').value=id;
      await siteChange();
    }catch(err){if(!lifetime.signal.aborted)status.textContent='Could not open the drive view. '+err.message;}
  })();
  frame=requestAnimationFrame(tick);
  return ()=>{lifetime.abort();currentRequest?.abort();cancelAnimationFrame(frame);observer.disconnect();controls.dispose();release(scene);light.shadow.dispose();renderer.dispose();};
}
