import * as T from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';
import {latLonToXYZ} from './lunar.js';
import {finishReferenceRover} from './r1-finish.js';
import {makeRobot} from './simulation-scene.js';
import {loadGround, groundHeight, terrainMesh} from './drive-ground.js';

const globeRadius = 1737.4;
const basisChange = new T.Quaternion().setFromAxisAngle(new T.Vector3(1,0,0), -Math.PI/2);
const smooth = t => t*t*(3-2*t);
const logBlend = (a,b,t) => Math.exp(T.MathUtils.lerp(Math.log(a),Math.log(b),t));
const vector = (lat,lon) => new T.Vector3(...latLonToXYZ(lat,lon));

export class ExpeditionScene {
  constructor(host, pin, onTime) {
    this.host=host; this.pin=pin; this.onTime=onTime;
    this.renderer=new T.WebGLRenderer({antialias:true, powerPreference:'high-performance'});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.6));
    this.renderer.setClearColor(0x090909);
    this.renderer.toneMapping=T.ACESFilmicToneMapping;
    this.renderer.shadowMap.enabled=true;
    host.prepend(this.renderer.domElement);
    this.space=new T.Scene();
    this.globe=new T.Mesh(new T.SphereGeometry(globeRadius,192,128),new T.MeshStandardMaterial({color:0xffffff,roughness:1}));
    this.space.add(this.globe,new T.AmbientLight(0xffffff,1.05));
    const key=new T.DirectionalLight(0xffffff,2.2);key.position.set(-1,-.45,1.4);this.space.add(key);
    const loader=new T.TextureLoader();
    this.texture=loader.load('/data/lroc-color.jpg',tex=>{tex.colorSpace=T.SRGBColorSpace;this.globe.material.map=tex;this.globe.material.needsUpdate=true;});
    this.normals=loader.load('/data/lola-normals.png',tex=>{this.globe.material.normalMap=tex;this.globe.material.normalMapType=T.ObjectSpaceNormalMap;this.globe.material.needsUpdate=true;});
    this.camera=new T.PerspectiveCamera(36,1,.02,20000);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.enablePan=false;this.controls.enableDamping=true;
    this.controls.rotateSpeed=.48;
    this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(host);
    this.abort=new AbortController();
    this.prepareGeneration=0;this.speed=3;this.setSite(-89.44,222.8);this.reset();
    this.frame=requestAnimationFrame(t=>this.tick(t));
  }
  resize(){
    const w=this.host.clientWidth,h=this.host.clientHeight;if(!w||!h)return;
    this.renderer.setSize(w,h);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();
  }
  setSite(lat,lon){
    this.surfaceNormal=vector(lat,lon);
    // North at the target sets the globe orientation at the terrain handoff.
    this.north=vector(lat+90,lon);
  }
  reset(){
    this.fly=null; this.playing=false; this.local=false;this.time=0;
    this.controls.enabled=true;this.controls.target.set(0,0,0);
    this.controls.minDistance=globeRadius+160;this.controls.maxDistance=10000;
    this.camera.up.set(0,1,0);this.camera.near=2;this.camera.far=20000;this.camera.updateProjectionMatrix();
    this.camera.position.copy(vector(-38, -55)).multiplyScalar(6500);
    this.controls.update();this.pin.hidden=false;
  }
  async prepare(run) {
    const generation=++this.prepareGeneration;
    const signal=this.abort.signal;
    const response=await fetch('/data/drive/index.json',{signal});
    if(!response.ok)throw Error('Lunar terrain catalogue is unavailable.');
    const site=(await response.json()).sites[run.landing.site_id];
    const [local,regional]=await Promise.all(site.levels.map(level=>loadGround(level,signal)));
    if(signal.aborted||generation!==this.prepareGeneration)return;
    this.run=run;
    if(!Object.values(run.sources.terrain_sha256).includes(local.source_sha256) ||
       !Object.values(run.sources.terrain_sha256).includes(regional.source_sha256))
      throw Error('Replay and display terrain sources differ.');
    this.clearSurface();
    this.surface=new T.Scene();this.surface.background=new T.Color(0x080808);
    this.surface.add(new T.HemisphereLight(0xf3f3f3,0x868686,1.15));
    this.sun=new T.DirectionalLight(0xffffff,2);this.sun.castShadow=true;
    Object.assign(this.sun.shadow.camera,{left:-8,right:8,top:8,bottom:-8,near:.1,far:170});
    this.sun.shadow.camera.updateProjectionMatrix();
    this.sun.shadow.mapSize.set(1024,1024);this.sun.shadow.normalBias=.009;
    this.surface.add(this.sun,this.sun.target);
    for(const mesh of [terrainMesh(regional,local.half_extent_m,null,null),terrainMesh(local,local.half_extent_m,regional,null)]){
      mesh.userData.imagery.value=0;this.surface.add(mesh);
    }
    this.rover=makeRobot(run.robot_snapshot.model,{assetRoot:'/api/v1/robot-assets/'+run.robot_package_sha256+'/'});
    if(run.robot_snapshot.source_class==='hypothetical_reference' && run.robot_snapshot.model.name==='Clavius R1 (hypothetical)')
      finishReferenceRover(this.rover.group,run.robot_snapshot.model);
    this.surface.add(this.rover.group);
    // Diffuse contact shading under a chassis helps read its height in polar light.
    const canvas=document.createElement('canvas');canvas.width=canvas.height=96;
    const ctx=canvas.getContext('2d'),falloff=ctx.createRadialGradient(48,48,5,48,48,47);
    falloff.addColorStop(0,'rgba(0,0,0,.5)');falloff.addColorStop(.65,'rgba(0,0,0,.23)');falloff.addColorStop(1,'transparent');
    ctx.fillStyle=falloff;ctx.fillRect(0,0,96,96);
    const [length,width]=run.robot_snapshot.profile.dimensions_m;
    this.contact=new T.Mesh(new T.PlaneGeometry(length*1.6,width*1.6),new T.MeshBasicMaterial({
      map:new T.CanvasTexture(canvas),transparent:true,depthWrite:false,polygonOffset:true,polygonOffsetFactor:-1}));
    this.ground=local;this.surface.add(this.contact);
    const points=[{east_m:run.landing.east_m,north_m:run.landing.north_m},...run.request.waypoints];
    const vertices=points.map(p=>new T.Vector3(p.east_m,groundHeight(local,p.east_m,p.north_m)+.035,-p.north_m));
    const driven=run.trace.map(row=>new T.Vector3(row.east_m,groundHeight(local,row.east_m,row.north_m)+.045,-row.north_m));
    this.trail=new T.Line(new T.BufferGeometry().setFromPoints(driven),new T.LineBasicMaterial({color:0xffffff,transparent:true,opacity:.8}));
    this.trail.geometry.setDrawRange(0,0);this.surface.add(this.trail);
    const route=new T.Line(new T.BufferGeometry().setFromPoints(vertices),new T.LineDashedMaterial({color:0xffffff,dashSize:.12,gapSize:.09,transparent:true,opacity:.65}));
    route.computeLineDistances();this.surface.add(route);
    for(const v of vertices.slice(1)){
      const ring=new T.Mesh(new T.RingGeometry(.14,.16,48),new T.MeshBasicMaterial({color:0xffffff,side:T.DoubleSide}));
      ring.rotation.x=-Math.PI/2;ring.position.copy(v);this.surface.add(ring);
    }
    this.setSite(run.landing.latitude_deg,run.landing.longitude_deg);
  }
  startFly(){
    this.seek(0,false);this.reset();this.controls.enabled=false;
    this.fly={start:performance.now(),origin:unitPosition(this.camera),short:matchMedia('(prefers-reduced-motion: reduce)').matches};
  }
  flyFrame(now){
    const p=this.fly.short?1:Math.min(1,(now-this.fly.start)/5200);
    if(p<.62){
      const t=smooth(p/.62);
      const direction=this.fly.origin.clone().lerp(this.surfaceNormal,t).normalize();
      this.camera.position.copy(direction).multiplyScalar(globeRadius+logBlend(6500-globeRadius,14,t));
      this.camera.up.set(0,1,0).lerp(this.north,t).normalize();this.camera.lookAt(0,0,0);
    }else{
      this.local=true;this.pin.hidden=true;
      const t=smooth((p-.62)/.38), distance=logBlend(14000,3.3,t);
      this.camera.near=Math.max(.02,distance/5000);this.camera.far=55000;this.camera.updateProjectionMatrix();
      const target=this.position(this.run.trace[0]);this.controls.target.copy(target);
      // Local display coordinates are east, up, south. North stays at screen top.
      this.camera.position.copy(target).add(new T.Vector3(.78*t,1-.54*t,.005+1.15*t).normalize().multiplyScalar(distance));
      this.camera.up.set(0,1,0);this.camera.lookAt(target);
    }
    if(p>=1){
      this.fly=null;this.controls.minDistance=.8;this.controls.maxDistance=8000;this.controls.enabled=true;
      this.controls.update();this.playing=!matchMedia('(prefers-reduced-motion: reduce)').matches;
      this.seek(0);
    }
  }
  position(row){return new T.Vector3(row.east_m,row.up_m,-row.north_m);}
  seek(time,notify=true){
    if(!this.run||!this.surface)return;
    const rows=this.run.trace;
    this.time=Math.min(Math.max(0,time),rows.at(-1).t_s);
    let lo=0,hi=rows.length-1;
    while(lo<hi){const i=(lo+hi+1)>>1;if(rows[i].t_s<=this.time)lo=i;else hi=i-1;}
    this.trail.geometry.setDrawRange(0,lo+1);
    const a=rows[lo],b=rows[Math.min(lo+1,rows.length-1)];
    const f=T.MathUtils.clamp((this.time-a.t_s)/(b.t_s-a.t_s||1),0,1);
    const pos=this.position(a).lerp(this.position(b),f);
    this.rover.group.position.copy(pos);
    const q=new T.Quaternion(...a.quaternion_xyzw).slerp(new T.Quaternion(...b.quaternion_xyzw),f);
    this.rover.group.quaternion.copy(basisChange).multiply(q);
    const east=pos.x,north=-pos.z;
    const ground=(e,n)=>groundHeight(this.ground,e,n);
    const normal=new T.Vector3(ground(east-.5,north)-ground(east+.5,north),1,ground(east,north+.5)-ground(east,north-.5)).normalize();
    const forward=new T.Vector3(1,0,0).applyQuaternion(this.rover.group.quaternion).projectOnPlane(normal).normalize();
    this.contact.quaternion.setFromRotationMatrix(new T.Matrix4().makeBasis(forward,normal.clone().cross(forward),normal));
    this.contact.position.set(east,ground(east,north)+.003,-north);this.contact.visible=a.contact_count>0;
    for(const [name,value] of Object.entries(a.joint_positions)){
      const joint=this.rover.joints.get(name);if(!joint)continue;
      const angle=T.MathUtils.lerp(value,b.joint_positions[name],f);
      if(joint.type==='prismatic')joint.motion.position.copy(joint.axis).multiplyScalar(angle);
      else joint.motion.quaternion.setFromAxisAngle(joint.axis,angle);
    }
    this.sun.position.copy(pos).add(new T.Vector3(a.sun_enu[0],a.sun_enu[2],-a.sun_enu[1]).multiplyScalar(60));
    this.sun.target.position.copy(pos);this.sun.intensity=2.5*a.disk_fraction;
    if(this.local&&!this.fly){this.camera.position.add(pos.clone().sub(this.controls.target));this.controls.target.copy(pos);}
    if(this.time>=rows.at(-1).t_s)this.playing=false;
    if(notify)this.onTime(this.time,a,this.playing);
  }
  tick(now){
    if(this.disposed)return;
    if(this.fly)this.flyFrame(now);
    else {
      if(this.local && this.playing){
        this.seek(this.time+Math.min(.1,(now-(this.previous||now))/1000)*this.speed);
        if(!this.playing&&this.onPlaybackEnd)queueMicrotask(this.onPlaybackEnd);
      }
      this.controls.update();
    }
    this.previous=now;
    if(!this.local){
      const point=this.surfaceNormal.clone().multiplyScalar(globeRadius);
      const visible=point.clone().sub(this.camera.position).dot(this.surfaceNormal)<0;
      point.project(this.camera);this.pin.hidden=!visible||Math.abs(point.x)>.96||Math.abs(point.y)>.96;
      this.pin.style.left=(point.x*.5+.5)*100+'%';this.pin.style.top=(-point.y*.5+.5)*100+'%';
    }
    this.renderer.render(this.local?this.surface:this.space,this.camera);
    this.frame=requestAnimationFrame(t=>this.tick(t));
  }
  clearSurface(){
    this.surface?.traverse(node=>{node.geometry?.dispose();if(node.material)[node.material].flat().forEach(m=>{m.map?.dispose();m.dispose();});});
    this.sun?.shadow.dispose();this.surface=null;
  }
  dispose(){
    this.disposed=true;cancelAnimationFrame(this.frame);this.abort.abort();this.observer.disconnect();
    this.controls.dispose();this.clearSurface();this.globe.geometry.dispose();this.globe.material.dispose();
    this.texture.dispose();this.normals.dispose();this.renderer.dispose();this.renderer.domElement.remove();
  }
}
const unitPosition=camera=>camera.position.clone().normalize();
