import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
const enuToThree=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),-Math.PI/2);
const rpyQuaternion=rpy=>new THREE.Quaternion().setFromEuler(new THREE.Euler(...rpy,'ZYX'));
// URDF fixed-axis RPY is Rz(yaw) Ry(pitch) Rx(roll), equivalent to Three ZYX.
export function makeRobot(model,{collision=false,assetRoot=''}={}) {
  const result=new THREE.Group(),joints=new Map();
  const links=new Map(model.links.map(link=>[link.name,link]));
  const material=new THREE.MeshStandardMaterial({color:collision?0x87c783:0xd6dfc5,roughness:.7,metalness:.15,wireframe:collision,transparent:collision,opacity:collision?.65:1});
  const wheelMaterial=new THREE.MeshStandardMaterial({color:0x303b3c,roughness:.9});
  function geometry(g) {
    if(g.type==='box')return new THREE.BoxGeometry(...g.size);
    if(g.type==='sphere')return new THREE.SphereGeometry(g.radius,24,16);
    if(g.type==='cylinder'){const geometry=new THREE.CylinderGeometry(g.radius,g.radius,g.length,32);geometry.rotateX(Math.PI/2);return geometry;}
    return null;
  }
  function addLink(name,parent) {
    const link=links.get(name),group=new THREE.Group();group.name=name;parent.add(group);
    for(const g of collision?link.collisions:link.visuals) {
      const holder=new THREE.Group();holder.position.fromArray(g.origin.xyz);holder.quaternion.copy(rpyQuaternion(g.origin.rpy));group.add(holder);
      const shape=geometry(g);
      if(shape){const mesh=new THREE.Mesh(shape,link.name.includes('wheel')&&!collision?wheelMaterial:material);mesh.castShadow=true;mesh.receiveShadow=true;holder.add(mesh);}
      else if(g.file){loadMesh(assetRoot+g.file,g.type,g.scale).then(mesh=>{holder.add(mesh);mesh.traverse(m=>{if(m.isMesh){m.castShadow=true;m.receiveShadow=true;}});}).catch(error=>console.warn('Robot mesh unavailable',g.file,error));}
    }
    for(const j of model.joints.filter(j=>j.parent===name)) {
      const joint=new THREE.Group();joint.position.fromArray(j.origin.xyz);joint.quaternion.copy(rpyQuaternion(j.origin.rpy));group.add(joint);
      const motion=new THREE.Group();joint.add(motion);joints.set(j.name,{motion,axis:new THREE.Vector3(...j.axis),type:j.type});addLink(j.child,motion);
    }
  }
  addLink(model.root_link,result);
  return {group:result,joints};
}
async function loadMesh(url,type,scale=[1,1,1]) {
 const ext=url.split('.').at(-1).toLowerCase();let object;
 if(ext==='stl'){const {STLLoader}=await import('three/addons/loaders/STLLoader.js');const geometry=await new STLLoader().loadAsync(url);object=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:0xbdc9bf,roughness:.7}));}
 else if(ext==='obj'){const {OBJLoader}=await import('three/addons/loaders/OBJLoader.js');object=await new OBJLoader().loadAsync(url);}
 else if(ext==='dae'){const {ColladaLoader}=await import('three/addons/loaders/ColladaLoader.js');object=(await new ColladaLoader().loadAsync(url)).scene;}
 else if(ext==='glb'||ext==='gltf'){const {GLTFLoader}=await import('three/addons/loaders/GLTFLoader.js');object=(await new GLTFLoader().loadAsync(url)).scene;}
 else throw new Error('Unsupported visual mesh extension');
 object.scale.fromArray(scale);return object;
}
async function supportTexture(info){
 const response=await fetch(info.url+'?sha='+info.sha256);if(!response.ok)throw new Error('LOLA support image is unavailable.');
 const raw=await response.arrayBuffer();const actual=[...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(v=>v.toString(16).padStart(2,'0')).join('');
 if(actual!==info.sha256)throw new Error('LOLA support image checksum differs from the pinned source record.');
 const url=URL.createObjectURL(new Blob([raw],{type:'image/png'}));
 try{const texture=await new THREE.TextureLoader().loadAsync(url);texture.colorSpace=THREE.SRGBColorSpace;texture.minFilter=THREE.NearestFilter;texture.magFilter=THREE.NearestFilter;texture.generateMipmaps=false;return texture;}finally{URL.revokeObjectURL(url);}
}
export class SimulationScene {
 constructor(host,{onPoint=()=>{}}={}) {
  this.host=host;this.onPoint=onPoint;this.disposed=false;
  this.renderer=new THREE.WebGLRenderer({antialias:true});this.renderer.setPixelRatio(Math.min(devicePixelRatio,2));this.renderer.setClearColor(0x090d0f);this.renderer.outputColorSpace=THREE.SRGBColorSpace;this.renderer.toneMapping=THREE.ACESFilmicToneMapping;
  this.renderer.shadowMap.enabled=true;this.renderer.shadowMap.type=THREE.PCFSoftShadowMap;host.append(this.renderer.domElement);
  this.renderer.domElement.tabIndex=0;this.renderer.domElement.setAttribute('aria-label','Lunar mission terrain. Drag to orbit, scroll to zoom, click to inspect or place a waypoint.');
  this.scene=new THREE.Scene();this.scene.fog=new THREE.Fog(0x090d0f,1300,2200);this.camera=new THREE.PerspectiveCamera(42,1,.02,4000);this.camera.position.set(210,190,260);
  this.controls=new OrbitControls(this.camera,this.renderer.domElement);this.controls.enableDamping=true;this.controls.minDistance=1;this.controls.maxDistance=1500;this.controls.maxPolarAngle=Math.PI*.49;
  this.ambient=new THREE.AmbientLight(0xb8c9db,.65);this.scene.add(this.ambient);
  this.sun=new THREE.DirectionalLight(0xfff8e9,3);this.sun.position.set(-150,100,120);this.sun.castShadow=true;this.sun.shadow.mapSize.set(2048,2048);Object.assign(this.sun.shadow.camera,{left:-350,right:350,top:350,bottom:-350,near:1,far:2200});this.sun.shadow.camera.updateProjectionMatrix();this.sun.shadow.normalBias=.1;this.scene.add(this.sun,this.sun.target);
  this.routeGroup=new THREE.Group();this.scene.add(this.routeGroup);
  this.marker=new THREE.Mesh(new THREE.RingGeometry(2.5,3.2,48),new THREE.MeshBasicMaterial({color:0xd7edb0,side:THREE.DoubleSide,depthTest:false}));this.marker.rotation.x=-Math.PI/2;this.marker.renderOrder=5;this.scene.add(this.marker);
  this.pointer=new THREE.Vector2();this.raycaster=new THREE.Raycaster();let down;
  this.renderer.domElement.addEventListener('pointerdown',e=>down=[e.clientX,e.clientY]);
  this.renderer.domElement.addEventListener('pointerup',e=>{if(!this.terrain||!down||Math.hypot(e.clientX-down[0],e.clientY-down[1])>5)return;const rect=this.renderer.domElement.getBoundingClientRect();this.pointer.set((e.clientX-rect.left)/rect.width*2-1,-(e.clientY-rect.top)/rect.height*2+1);this.raycaster.setFromCamera(this.pointer,this.camera);const hit=this.raycaster.intersectObject(this.terrain)[0];if(hit)this.onPoint({east_m:hit.point.x,north_m:-hit.point.z,up_m:hit.point.y});});
  this.observer=new ResizeObserver(()=>this.resize());this.observer.observe(host);this.resize();
  this.render=this.render.bind(this);this.render();
 }
 async setTerrain(patch) {
  let support=null;this.supportReason=null;
  if(patch.nominal_support_display){
   const info=patch.nominal_support_display;
   if(Math.max(info.width,info.height)>this.renderer.capabilities.maxTextureSize)this.supportReason='This GPU cannot display the native support texture. Numerical native counts remain available.';
   else try{support=await supportTexture(info);}catch(error){this.supportReason=error.message+' Numerical native counts remain available.';}
  }else this.supportReason='No support display is prepared for this count source. Numerical native counts remain available.';
  if(this.disposed){support?.dispose();return;}
  this.supportTexture?.dispose();this.supportTexture=support;this.patch=patch;
  if(this.terrain){this.scene.remove(this.terrain);this.terrain.geometry.dispose();this.terrain.material.dispose();}
  const geometry=new THREE.PlaneGeometry((patch.width-1)*patch.spacing_m,(patch.height-1)*patch.spacing_m,patch.width-1,patch.height-1),pos=geometry.attributes.position;
  // PlaneGeometry iterates north-to-south, while the API raster is south-to-north.
  const colors=[];
  for(let row=0;row<patch.height;row++)for(let col=0;col<patch.width;col++){
   const i=row*patch.width+col,index=(patch.height-1-row)*patch.width+col;
   const east=patch.west_m+col*patch.spacing_m,north=patch.south_m+(patch.height-1-row)*patch.spacing_m;
   pos.setXYZ(i,east,patch.heights_m[index],-north);
   if(patch.nominal_support_uv)geometry.attributes.uv.setXY(i,patch.nominal_support_uv[index*2],patch.nominal_support_uv[index*2+1]);
   const h=patch.heights_m[index],span=patch.height_range_m[1]-patch.height_range_m[0];const intensity=.34+.25*(h-patch.height_range_m[0])/Math.max(span,1);colors.push(intensity,intensity*1.01,intensity*1.02);
  }
  geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));geometry.computeVertexNormals();
  this.terrain=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({vertexColors:true,roughness:1}));this.terrain.receiveShadow=true;this.terrain.castShadow=true;this.scene.add(this.terrain);
  this.setLayer(this.layer==='support'&&!this.supportTexture?'relief':this.layer||'relief');this.setRoute(this.points||[]);this.controls.target.set(35,this.height(35,0),-10);this.controls.update();
 }
 setLayer(layer) {
  if(layer==='support'&&!this.supportTexture)layer='relief';
  this.layer=layer;if(!this.terrain||!this.patch)return;
  const mapped=layer==='support'&&this.supportTexture;this.terrain.material.map=mapped||null;this.terrain.material.vertexColors=!mapped;this.terrain.material.needsUpdate=true;
  const p=this.patch,colors=this.terrain.geometry.attributes.color,color=new THREE.Color();
  for(let row=0;row<p.height;row++)for(let col=0;col<p.width;col++){
   const i=row*p.width+col,k=(p.height-1-row)*p.width+col;
   if(layer==='slope'){const f=Math.min(1,(p.slopes_deg?.[k]||0)/30);color.setRGB(.2+.65*f,.4-.13*f,.28-.13*f);}
   else if(layer==='uncertainty'){const f=Math.min(1,(p.height_rms_m?.[k]||0)/2);color.setRGB(.12+.58*f,.3+.38*f,.42+.45*f);}
   else{const f=(p.heights_m[k]-p.height_range_m[0])/Math.max(1,p.height_range_m[1]-p.height_range_m[0]),v=.34+.25*f;color.setRGB(v,v*1.01,v*1.02);}
   colors.setXYZ(i,color.r,color.g,color.b);
  }
  colors.needsUpdate=true;
 }
 height(e,n) {
  const p=this.patch;if(!p)return 0;const x=(e-p.west_m)/p.spacing_m,y=(n-p.south_m)/p.spacing_m;
  const i=Math.max(0,Math.min(p.width-2,Math.floor(x))),j=Math.max(0,Math.min(p.height-2,Math.floor(y))),dx=Math.max(0,Math.min(1,x-i)),dy=Math.max(0,Math.min(1,y-j));
  const at=(x,y)=>p.heights_m[y*p.width+x];return (at(i,j)*(1-dx)+at(i+1,j)*dx)*(1-dy)+(at(i,j+1)*(1-dx)+at(i+1,j+1)*dx)*dy;
 }
 setRoute(points) {
  this.points=points;
  for(const child of [...this.routeGroup.children]){child.geometry?.dispose();child.material?.dispose();this.routeGroup.remove(child);}
  if(!this.patch)return;
  const positions=[];
  points.forEach((p,i)=>{
   const point=new THREE.Vector3(p.east_m,this.height(p.east_m,p.north_m)+.35,-p.north_m);
   const marker=new THREE.Mesh(new THREE.SphereGeometry(1.4,12,8),new THREE.MeshBasicMaterial({color:i?0xd7edb0:0xffffff,depthTest:false}));marker.position.copy(point);marker.renderOrder=6;this.routeGroup.add(marker);
   if(i){const a=points[i-1],length=Math.hypot(p.east_m-a.east_m,p.north_m-a.north_m),steps=Math.max(1,Math.ceil(length/2));for(let k=0;k<=steps;k++){const t=k/steps,e=a.east_m+(p.east_m-a.east_m)*t,n=a.north_m+(p.north_m-a.north_m)*t;positions.push(new THREE.Vector3(e,this.height(e,n)+.3,-n));}}
  });
  if(positions.length){const geometry=new THREE.BufferGeometry().setFromPoints(positions);this.routeGroup.add(new THREE.Line(geometry,new THREE.LineBasicMaterial({color:0xd7edb0,transparent:true,opacity:.85,depthTest:false})));}
 }
 setRobot(robot,collision=false) {
  if(this.robotGroup){this.scene.remove(this.robotGroup);this.release(this.robotGroup);}
  this.robot=robot;const built=makeRobot(robot.model,{collision,assetRoot:`/api/v1/robot-assets/${robot.package_sha256}/`});this.robotGroup=built.group;this.joints=built.joints;this.scene.add(this.robotGroup);this.setPose(this.currentPose||{east_m:0,north_m:0,up_m:this.height(0,0)});
 }
 setPose(pose) {
  this.currentPose=pose;const position=new THREE.Vector3(pose.east_m,pose.up_m,-pose.north_m);
  this.marker.position.copy(position).add(new THREE.Vector3(0,.4,0));
  if(this.robotGroup){this.robotGroup.position.copy(position);const q=pose.quaternion_xyzw||pose.body_quaternion_xyzw||[0,0,0,1];this.robotGroup.quaternion.copy(enuToThree).multiply(new THREE.Quaternion(...q));for(const [name,value]of Object.entries(pose.joint_positions||{})){const j=this.joints.get(name);if(j){if(j.type==='prismatic')j.motion.position.copy(j.axis).multiplyScalar(value);else j.motion.quaternion.setFromAxisAngle(j.axis,value);}}}
  if(pose.sun_enu){const d=pose.sun_enu;this.sun.position.set(position.x+d[0]*1000,position.y+d[2]*1000,position.z-d[1]*1000);this.sun.target.position.copy(position);this.sun.intensity=d[2]>0?3:.05;this.sun.target.updateMatrixWorld();}
  if(this.follow){const delta=position.clone().sub(this.controls.target);this.camera.position.add(delta);this.controls.target.copy(position);}
 }
 resetIllumination(){this.sun.position.set(-150,100,120);this.sun.target.position.set(0,0,0);this.sun.intensity=3;this.sun.target.updateMatrixWorld();}
 focusRobot() {const p=this.marker.position.clone();this.follow=true;this.marker.visible=false;this.routeGroup.visible=false;this.controls.target.copy(p);this.camera.position.copy(p).add(new THREE.Vector3(3,2.4,3.5));this.controls.update();}
 overview(){this.follow=false;this.marker.visible=true;this.routeGroup.visible=true;this.controls.target.set(35,this.height(35,0),-10);this.camera.position.set(210,190,260);this.controls.update();}
 resize(){const {width,height}=this.host.getBoundingClientRect();if(width&&height){this.camera.aspect=width/height;this.camera.updateProjectionMatrix();this.renderer.setSize(width,height);}}
 render(){if(this.disposed)return;this.frame=requestAnimationFrame(this.render);this.controls.update();this.renderer.render(this.scene,this.camera);}
 release(group){group.traverse(node=>{node.geometry?.dispose();if(Array.isArray(node.material))node.material.forEach(m=>m.dispose());else node.material?.dispose();});}
 dispose(){this.disposed=true;cancelAnimationFrame(this.frame);this.observer.disconnect();this.controls.dispose();this.release(this.scene);this.sun.shadow.dispose();this.supportTexture?.dispose();this.renderer.dispose();}
}
