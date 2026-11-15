// Project a fixed-site ENU Sun vector onto the rover's port, starboard and aft faces.
import {Quaternion, Vector3} from 'three';

const auKm = 149597870.7;
const sunBody = new Vector3(), inverse = new Quaternion();
const replayOrientation = new Quaternion(), nextOrientation = new Quaternion();

export function arrayPower(hardware, sample, bodyToEnu) {
  if (!hardware || !sample || !(sample.sun_distance_km > 0)) return null;
  sunBody.fromArray(sample.sun_site_enu).applyQuaternion(inverse.copy(bodyToEnu).normalize().invert());
  const scale = hardware.panel_reference_w * sample.disk_fraction *
    (hardware.reference_distance_au * auKm / sample.sun_distance_km) ** 2;
  const faces = {};
  let total = 0;
  for (const [name, [x, y, z]] of Object.entries(hardware.faces)) {
    faces[name] = scale * Math.max(0, sunBody.x*x + sunBody.y*y + sunBody.z*z);
    total += faces[name];
  }
  return {faces, total};
}

// Three.js world axes are east/up/south. Native replay poses already use ENU.
const sceneToEnu = new Quaternion().setFromAxisAngle(new Vector3(1,0,0),Math.PI/2);
export function manualBodyToEnu(sceneOrientation, out) {
  return out.multiplyQuaternions(sceneToEnu,sceneOrientation).normalize();
}

// Integrate at the native recording cadence. Use the same preceding-second
// environment for both ends of each frame interval, including at a second boundary.
export function replayArrayEnergy(hardware, samples, poses, samplesPerSecond = 20) {
  const count = poses.length / (17*7);
  if (!samples || samples.length !== 1 + (count-1)/samplesPerSecond) return null;
  const cumulative = new Float64Array(count), wattsStart = [], wattsEnd = [];
  for (let i=0; i<count-1; i++) {
    const sun = samples[Math.floor(i/samplesPerSecond)];
    const first = arrayPower(hardware, sun, replayOrientation.fromArray(poses, i*119+3));
    const last = arrayPower(hardware, sun, nextOrientation.fromArray(poses, (i+1)*119+3));
    if (!first || !last) return null;
    wattsStart.push(first.total); wattsEnd.push(last.total);
    cumulative[i+1] = cumulative[i] + (first.total+last.total)/(2*samplesPerSecond*3600);
  }
  return elapsed => {
    const frame = Math.max(0, Math.min(count-1, elapsed*samplesPerSecond));
    const i = Math.min(Math.floor(frame),count-2), f = frame-i;
    return cumulative[i] + (wattsStart[i]*f + (wattsEnd[i]-wattsStart[i])*f*f/2)/(samplesPerSecond*3600);
  };
}
