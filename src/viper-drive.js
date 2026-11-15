import * as THREE from 'three';
import {OBJLoader} from 'three/addons/loaders/OBJLoader.js';

const halfWheelbase = .6418, halfTrack = .6098;
export const radius = .25, nominalSpeed = .1;
const maxSteer = 50 * Math.PI / 180;
const maxCurvature = Math.tan(maxSteer) / (halfWheelbase + halfTrack * Math.tan(maxSteer));
const corners = [[1,1],[1,-1],[-1,1],[-1,-1]];

// Constant-curvature rolling. Positive heading is east toward north.
// Each wheel follows its own arc about the common instantaneous turn center.
export function advanceDrive(state, throttle, steer, seconds, maneuver = 'turn') {
  const speed = nominalSpeed * throttle;
  const command = Math.max(-1, Math.min(1, steer));
  if (maneuver === 'crab') {
    const angle = command * maxSteer;
    const distance = speed * seconds;
    const direction = state.heading + angle;
    return {
      east: state.east + distance * Math.cos(direction),
      north: state.north + distance * Math.sin(direction),
      heading: state.heading,
      distance: state.distance + Math.abs(distance),
      wheels: state.wheels.map(wheel => ({steer: angle, spin: wheel.spin + distance / radius}))
    };
  }
  const curvature = command * maxCurvature;
  const distance = speed * seconds, angle = distance * curvature;
  const mid = state.heading + angle/2;
  const chord = angle === 0 ? distance : distance * Math.sin(angle/2)/(angle/2);
  const wheels = corners.map(([front,left], i) => {
    const forward = 1-curvature*left*halfTrack, lateral=curvature*front*halfWheelbase;
    return {steer:Math.atan2(lateral,forward), spin:state.wheels[i].spin+distance*Math.hypot(forward,lateral)/radius};
  });
  return {east:state.east+chord*Math.cos(mid),north:state.north+chord*Math.sin(mid),
          heading:state.heading+angle, distance:state.distance+Math.abs(distance), wheels};
}
export function parkedDrive() {
  return {east:0,north:0,heading:0,distance:0,wheels:corners.map(()=>({steer:0,spin:0}))};
}

export async function loadViper() {
  const names = ['chassis','wheel','L_up_sus','R_up_sus','L_bt_sus','R_bt_sus','L_steer','R_steer'];
  const loader = new OBJLoader();
  const loaded = await Promise.all(names.map(name=>loader.loadAsync('/robots/viper/viper_'+name+'.obj')));
  const templates = Object.fromEntries(names.map((name,i)=>[name,loaded[i]]));
  const materials = {
    chassis: new THREE.MeshStandardMaterial({color:0xc6c3ae,roughness:.54,metalness:.36}),
    wheel: new THREE.MeshStandardMaterial({color:0x888d8b,roughness:.65,metalness:.42}),
    suspension: new THREE.MeshStandardMaterial({color:0x5e6265,roughness:.5,metalness:.48})
  };
  for(const [name,object] of Object.entries(templates)) object.traverse(node=>{
    if(!node.isMesh) return;
    for(const material of [].concat(node.material)) material.dispose();
    node.material=materials[name]||materials.suspension;
    node.castShadow=true;node.receiveShadow=true;
  });
  const body=new THREE.Group(), wheels=[],parts=[templates.chassis];
  body.add(templates.chassis);
  for(const [front,left] of corners) {
    const side=left===1?'L':'R';
    for(const [suffix,z] of [['up_sus',.0525],['bt_sus',-.0525]]) {
      const arm=templates[side+'_'+suffix].clone();
      arm.position.set(front*halfWheelbase,left*.2067,z);body.add(arm);parts.push(arm);
    }
    const upright=templates[side+'_steer'].clone();
    upright.position.set(front*halfWheelbase,left*halfTrack,0);body.add(upright);parts.push(upright);
    const steering=new THREE.Group(), spin=new THREE.Group(), wheel=templates.wheel.clone();
    steering.position.copy(upright.position);
    if(left===1)wheel.rotation.z=Math.PI;
    parts.push(wheel);spin.add(wheel);steering.add(spin);body.add(steering);wheels.push({steering,spin});
  }
  return {body,wheels,parts};
}
