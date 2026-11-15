import * as THREE from 'three';

// Each visual uses the CAD reference frame of its recorded body. The left
// wheel's mesh-frame half turn stays beneath its recorded wheel transform.
export function replayAssembly(rover) {
  const group=new THREE.Group();
  group.rotation.x=-Math.PI/2;
  for(const part of rover.parts){
    const ref=new THREE.Group(),visual=part.clone();
    visual.position.set(0,0,0);
    ref.add(visual);group.add(ref);
  }
  group.visible=false;
  return group;
}

export async function loadReplay(record,grid,signal) {
  if(record.terrain_sha256!==grid.sha256)throw new Error('Replay and terrain identities differ.');
  const response=await fetch('/data/drive/'+record.file,{signal});
  if(!response.ok)throw new Error('Drive recording unavailable.');
  const bytes=await response.arrayBuffer();
  const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  if(sha!==record.sha256||bytes.byteLength!==401*17*7*4)throw new Error('Invalid drive recording.');
  const poses=new Float32Array(bytes), distance=new Float64Array(401);
  for(let i=1;i<401;i++){
    const a=(i-1)*119,b=i*119;
    distance[i]=distance[i-1]+Math.hypot(poses[b]-poses[a],poses[b+1]-poses[a+1]);
  }
  return {poses,distance,sha256:sha};
}

const nextRotation=new THREE.Quaternion();
const bodyInverse=new THREE.Quaternion(), axle=new THREE.Vector3();
export function applyReplay(group,replay,t){
  const u=Math.min(400,Math.max(0,t*20)),i=Math.min(399,Math.floor(u)),f=u-i;
  for(let part=0;part<17;part++){
    const node=group.children[part],a=7*(i*17+part),b=a+119, data=replay.poses;
    node.position.set(data[a]+f*(data[b]-data[a]),data[a+1]+f*(data[b+1]-data[a+1]),data[a+2]+f*(data[b+2]-data[a+2]));
    node.quaternion.fromArray(data,a+3).slerp(nextRotation.fromArray(data,b+3),f);
  }
  bodyInverse.copy(group.children[0].quaternion).invert();
  axle.set(0,1,0).applyQuaternion(group.children[4].quaternion).applyQuaternion(bodyInverse);
  const leftFrontSteer = Math.atan2(-axle.x, axle.y);
  return {leftFrontSteer, speed:(replay.distance[i+1]-replay.distance[i])*20,distance:THREE.MathUtils.lerp(replay.distance[i],replay.distance[i+1],f)};
}

// Both paths share a metre scale and a site origin. The two markers share a clock.
export function drawReplayPaths(canvas, traces, time) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const width = 260, height = 130, padding = 14;
  const scale = Math.min(canvas.width/width, canvas.height/height);
  ctx.setTransform(scale,0,0,scale,0,0);
  ctx.clearRect(0,0,width,height);
  let minE=0, maxE=0, minN=0, maxN=0;
  for (const {poses} of Object.values(traces)) {
    for (let offset=0; offset<poses.length; offset+=119) {
      minE=Math.min(minE,poses[offset]); maxE=Math.max(maxE,poses[offset]);
      minN=Math.min(minN,poses[offset+1]); maxN=Math.max(maxN,poses[offset+1]);
    }
  }
  const px = Math.min((width-2*padding)/(maxE-minE || 1), (height-2*padding)/(maxN-minN || 1));
  const x = east=>padding+(east-minE)*px, y = north=>height-padding-(north-minN)*px;
  ctx.strokeStyle='#445051'; ctx.lineWidth=1; ctx.setLineDash([]);
  ctx.beginPath(); ctx.moveTo(x(0),0); ctx.lineTo(x(0),height); ctx.moveTo(0,y(0)); ctx.lineTo(width,y(0)); ctx.stroke();
  ctx.font='10px sans-serif'; ctx.fillStyle='#b7c1bd'; ctx.fillText('N',x(0)+3,10);ctx.fillText('E',width-9,y(0)-3);
  const frame=Math.min(400,Math.max(0,time*20)), index=Math.min(399,Math.floor(frame)), blend=frame-index;
  for (const [maneuver,{poses}] of Object.entries(traces)) {
    ctx.strokeStyle = ctx.fillStyle = maneuver==='crab'?'#d7edb0':'#93bdde';
    ctx.setLineDash(maneuver==='crab'?[]:[4,3]); ctx.lineWidth=2; ctx.beginPath();
    ctx.moveTo(x(poses[0]),y(poses[1]));
    for (let offset=119;offset<poses.length;offset+=119) ctx.lineTo(x(poses[offset]),y(poses[offset+1]));
    ctx.stroke();
    const a=index*119,b=a+119;
    const east=THREE.MathUtils.lerp(poses[a],poses[b],blend), north=THREE.MathUtils.lerp(poses[a+1],poses[b+1],blend);
    ctx.beginPath();ctx.arc(x(east),y(north),3.5,0,Math.PI*2);ctx.fill();
    const output=canvas.parentElement.querySelector('[data-path-'+maneuver+']');
    output.textContent='E '+east.toFixed(2)+' / N '+north.toFixed(2)+' m';
  }
}
