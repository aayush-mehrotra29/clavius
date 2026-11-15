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
  return {poses,distance};
}

const nextRotation=new THREE.Quaternion();
export function applyReplay(group,replay,t){
  const u=Math.min(400,Math.max(0,t*20)),i=Math.min(399,Math.floor(u)),f=u-i;
  for(let part=0;part<17;part++){
    const node=group.children[part],a=7*(i*17+part),b=a+119, data=replay.poses;
    node.position.set(data[a]+f*(data[b]-data[a]),data[a+1]+f*(data[b+1]-data[a+1]),data[a+2]+f*(data[b+2]-data[a+2]));
    node.quaternion.fromArray(data,a+3).slerp(nextRotation.fromArray(data,b+3),f);
  }
  return {speed:(replay.distance[i+1]-replay.distance[i])*20,distance:THREE.MathUtils.lerp(replay.distance[i],replay.distance[i+1],f)};
}
