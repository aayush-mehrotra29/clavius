// Adapted from prollyAditya/Clavius, FlightSimulator3D.tsx (3f26903).
import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Play, Pause, RotateCcw, Camera } from 'lucide-react';
import type { FlightSamples } from './types';
import {FlightCanvasRenderer} from './FlightCanvasRenderer';
import {advanceSample} from './playback.js';

// SphereGeometry uses +Y north and -Z east at the prime meridian.
const sphereToBody = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI / 2);
const cameras = {inertial: 'System', earth: 'Earth', moon: 'Moon', spacecraft: 'Spacecraft'} as const;

export function FlightSimulator3D({trajData, active}: {trajData: FlightSamples, active: boolean}) {
  const mountRef = useRef<HTMLDivElement>(null);

  // Simulation playback state
  const [isPlaying, setIsPlaying] = useState<boolean>(() => !matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(50); // steps per second
  const [timeIndex, setTimeIndex] = useState<number>(0);
  const [cameraMode, setCameraMode] = useState<'inertial' | 'earth' | 'moon' | 'spacecraft'>('inertial');
  const [missingMap, setMissingMap] = useState('');
  const numPoints = trajData.times_seconds.length;
  const cameraModeRef = useRef(cameraMode);
  const fitOverview = useRef<() => void>(() => {});

  // Animation frame and three refs
  const timeIndexRef = useRef<number>(0);
  // The animation clock keeps its fractional sample between React renders.
  const isPlayingRef = useRef<boolean>(isPlaying);
  isPlayingRef.current = isPlaying;
  const speedRef = useRef<number>(playbackSpeed);
  speedRef.current = playbackSpeed;

  const activeRef = useRef(active);
  activeRef.current = active;
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const scMeshRef = useRef<THREE.Mesh | null>(null);
  const moonMeshRef = useRef<THREE.Mesh | null>(null);
  const pastLineRef = useRef<THREE.Line | null>(null);

  // Scale factor: Real distances are ~384,400 km.
  // We represent 1 Three.js unit = 1000 km for clean numerical stability.
  const DIST_SCALE = 1 / 1000.0;
  const earthRadius = trajData.earth_reference_radius_km * DIST_SCALE;
  const moonRadius = trajData.lunar_reference_radius_km * DIST_SCALE;

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x090909);

    // Camera
    const camera = new THREE.PerspectiveCamera(
      45,
      container.clientWidth / container.clientHeight,
      0.1,
      5000
    );
    camera.up.set(0, 0, 1);
    cameraRef.current = camera;
    camera.position.set(0, -450, 320);

    const canvas = document.createElement('canvas');
    let gpu: THREE.WebGLRenderer | undefined;
    // Probe the same canvas and attributes that Three will use.
    const attributes = {antialias: true, alpha: true, depth: true, stencil: false};
    try {
      const context = canvas.getContext('webgl2', attributes);
      if (context) gpu = new THREE.WebGLRenderer({canvas, context, ...attributes});
    } catch (error) {
      console.warn('Could not initialize the WebGL flight renderer.', error);
    }
    gpu?.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    let renderer: THREE.WebGLRenderer | FlightCanvasRenderer = gpu ?? new FlightCanvasRenderer();
    const mountRenderer = () => {
      renderer.setSize(container.clientWidth, container.clientHeight);
      container.replaceChildren(renderer.domElement);
    };
    mountRenderer();
    let needsFrame = true;
    const useSoftware = () => {
      needsFrame = true;
      renderer = new FlightCanvasRenderer();
      mountRenderer();
      gpu?.dispose();
      gpu = undefined;
    };
    canvas.addEventListener('webglcontextlost', useSoftware, {once: true});

    // Keep the camera controls attached when a lost GPU canvas is replaced.
    const controls = new OrbitControls(camera, container);
    controlsRef.current = controls;
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxDistance = 2500;
    controls.minDistance = 2;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 1.25);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xffffff, 2.5);
    sunLight.position.set(600, 300, 200);
    scene.add(sunLight);

    // Starfield particles
    const starCount = 1500;
    const starGeometry = new THREE.BufferGeometry();
    const starPositions = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount * 3; i += 3) {
      starPositions[i] = (Math.random() - 0.5) * 4000;
      starPositions[i + 1] = (Math.random() - 0.5) * 4000;
      starPositions[i + 2] = (Math.random() - 0.5) * 4000;
    }
    starGeometry.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
    const starMaterial = new THREE.PointsMaterial({ color: 0x858585, size: 1.5, sizeAttenuation: false });
    const starField = new THREE.Points(starGeometry, starMaterial);
    scene.add(starField);

    // Coordinate grid on the J2000 equatorial plane (Z=0)
    const gridHelper = new THREE.GridHelper(900, 36, 0x393939, 0x202020);
    gridHelper.rotation.x = Math.PI / 2;
    gridHelper.position.set(0, 0, 0);
    scene.add(gridHelper);

    let disposed = false;
    const loader = new THREE.TextureLoader();
    const loadMap = (url: string, name: string) => {
      const texture = loader.load(url, () => { needsFrame = true; }, undefined, () => {
        if (!disposed) setMissingMap(previous => previous ? previous + ' and ' + name : name);
      });
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.wrapS = THREE.RepeatWrapping;
      return texture;
    };

    // Earth Sphere
    const earthGeo = new THREE.SphereGeometry(earthRadius, 48, 48);
    const earthTex = loadMap('/data/earth-blue-marble-july.jpg', 'Earth');
    const earthMat = new THREE.MeshStandardMaterial({
      map: earthTex,
      roughness: 1,
      metalness: 0,
    });
    const earthMesh = new THREE.Mesh(earthGeo, earthMat);
    earthMesh.position.set(0, 0, 0);
    scene.add(earthMesh);

    // Moon Orbit Guide Ring (radius = 384.4 units)
    const moonStart = new THREE.Vector3(...trajData.moon_coords_km[0]);
    const moonOrbitRadius = moonStart.length()*DIST_SCALE;
    const orbitNormal = moonStart.clone().cross(new THREE.Vector3(...trajData.moon_velocities_kms[0])).normalize();
    const orbitRingGeo = new THREE.BufferGeometry();
    const ringPts: THREE.Vector3[] = [];
    for (let i = 0; i <= 128; i++) {
      const th = (i / 128) * Math.PI * 2;
      ringPts.push(new THREE.Vector3(moonOrbitRadius * Math.cos(th), moonOrbitRadius * Math.sin(th), 0));
    }
    orbitRingGeo.setFromPoints(ringPts);
    const orbitRingMat = new THREE.LineDashedMaterial({
      color: 0x505050,
      dashSize: 6,
      gapSize: 4,
    });
    const moonOrbitRing = new THREE.Line(orbitRingGeo, orbitRingMat);
    moonOrbitRing.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), orbitNormal);
    moonOrbitRing.computeLineDistances();
    scene.add(moonOrbitRing);

    // Moon Sphere
    const moonGeo = new THREE.SphereGeometry(moonRadius, 32, 32);
    const moonTex = loadMap('/data/lroc-color.jpg', 'Moon');
    const moonMat = new THREE.MeshStandardMaterial({
      map: moonTex,
      roughness: 0.9,
    });
    const moonMesh = new THREE.Mesh(moonGeo, moonMat);
    moonMeshRef.current = moonMesh;
    scene.add(moonMesh);

    // Spacecraft Indicator (Small Glowing Octahedron + Beacon)
    const scGeo = new THREE.OctahedronGeometry(2.5, 0);
    const scMat = new THREE.MeshBasicMaterial({ color: 0xffffff, wireframe: false });
    const scMesh = new THREE.Mesh(scGeo, scMat);
    scMeshRef.current = scMesh;
    scene.add(scMesh);

    // Spacecraft Beacon Halo
    const haloGeo = new THREE.RingGeometry(3.5, 5.0, 16);
    const haloMat = new THREE.MeshBasicMaterial({
      color: 0x779bff,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.7,
    });
    scMat.depthTest = false;
    scMesh.renderOrder = 3;
    const haloMesh = new THREE.Mesh(haloGeo, haloMat);
    scMesh.add(haloMesh);

    let brakeMarker: THREE.Mesh | undefined;
    // Full planned/simulated trajectory ribbon (all points)
    if (trajData && trajData.spacecraft_coords_km.length > 0) {
      const pts = trajData.spacecraft_coords_km.map(
        (c) => new THREE.Vector3(c[0] * DIST_SCALE, c[1] * DIST_SCALE, c[2] * DIST_SCALE)
      );
      const fullTrajGeo = new THREE.BufferGeometry().setFromPoints(pts);
      const fullTrajMat = new THREE.LineBasicMaterial({
        color: 0xa0a0a0,
        transparent: true,
        opacity: 0.6,
      });
      const fullLine = new THREE.Line(fullTrajGeo, fullTrajMat);
      scene.add(fullLine);

      // Traversed past trajectory
      const pastGeo = new THREE.BufferGeometry().setFromPoints(pts);
      const pastMat = new THREE.LineBasicMaterial({
        color: 0x527fff,
        linewidth: 2,
      });
      const pastLine = new THREE.Line(pastGeo, pastMat);
      pastGeo.setDrawRange(0, 1);
      pastLineRef.current = pastLine;
      scene.add(pastLine);

      const closestApproachIdx = trajData.approach_index;
      if (closestApproachIdx >= 0) {
        const periPt = pts[closestApproachIdx];
        const periMarkerGeo = new THREE.RingGeometry(3, 4.5, 16);
        const periMarkerMat = new THREE.MeshBasicMaterial({
          color: 0xffffff,
          side: THREE.DoubleSide,
        });
        const periMarker = new THREE.Mesh(periMarkerGeo, periMarkerMat);
        brakeMarker = periMarker;
        periMarker.position.copy(periPt);
        periMarker.material.depthTest=false;
        periMarker.renderOrder=2;
        scene.add(periMarker);
      }
    }

    const bounds = new THREE.Box3().setFromPoints(
      [...trajData.spacecraft_coords_km, ...trajData.moon_coords_km, [0,0,0]].map(p =>
        new THREE.Vector3(p[0],p[1],p[2]).multiplyScalar(DIST_SCALE))
    );
    const sphere = bounds.getBoundingSphere(new THREE.Sphere());
    fitOverview.current = () => {
      const halfFov = camera.fov*Math.PI/360;
      const limitingFov = Math.min(halfFov, Math.atan(Math.tan(halfFov)*camera.aspect));
      controls.target.copy(sphere.center);
      camera.position.copy(sphere.center).addScaledVector(
        new THREE.Vector3(0,-450,320).normalize(), (sphere.radius+earthRadius)*1.1/Math.sin(limitingFov)
      );
      controls.update();
    };
    fitOverview.current();
    const resize = new ResizeObserver(() => {
      if (!container.clientWidth || !container.clientHeight) return;
      needsFrame = true;
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
      if(cameraModeRef.current === 'inertial') fitOverview.current();
    });
    resize.observe(container);
    let followed = new THREE.Vector3();
    let lastMode = '';
    let lastSample = -1;
    const lastView = new THREE.Matrix4();
    // Animation Loop
    let lastTime: number | undefined;
    let animId: number;

    const animate = (now: number) => {
      animId = requestAnimationFrame(animate);

      const previousFrame = lastTime;
      lastTime = now;
      if (!activeRef.current || document.hidden) return;

      // Update trajectory playback
      if (isPlayingRef.current && trajData && trajData.spacecraft_coords_km.length > 0) {
        const total = trajData.spacecraft_coords_km.length;
        const nextIdx = advanceSample(timeIndexRef.current, previousFrame, now, speedRef.current, total);
        timeIndexRef.current = nextIdx;
        setTimeIndex(Math.floor(nextIdx));
      }

      // Update positions of spacecraft and moon based on current timeIndex
      const idx = Math.min(Math.floor(timeIndexRef.current), (trajData?.spacecraft_coords_km.length || 1) - 1);
      if (trajData && trajData.spacecraft_coords_km[idx]) {
        const frames = trajData.globe_frames;
        earthMesh.quaternion.fromArray(frames.earth_xyzw[idx]).multiply(sphereToBody);
        moonMesh.quaternion.fromArray(frames.moon_xyzw[idx]).multiply(sphereToBody);
        sunLight.position.fromArray(frames.sun_direction_j2000[idx]);
        const scCoord = trajData.spacecraft_coords_km[idx];
        const scPos = new THREE.Vector3(scCoord[0] * DIST_SCALE, scCoord[1] * DIST_SCALE, scCoord[2] * DIST_SCALE);
        if (scMeshRef.current) {
          scMeshRef.current.position.copy(scPos);
        }

        // Update Moon position
        if (trajData.moon_coords_km[idx] && moonMeshRef.current) {
          const mCoord = trajData.moon_coords_km[idx];
          moonMeshRef.current.position.set(mCoord[0] * DIST_SCALE, mCoord[1] * DIST_SCALE, mCoord[2] * DIST_SCALE);
        }

        pastLineRef.current?.geometry.setDrawRange(0, idx+1);
        const focus = cameraModeRef.current;
        const subject = focus==='moon' ? moonMesh : focus==='spacecraft' ? scMesh : null;
        if (subject) {
          if(lastMode===focus) {
            const delta = subject.position.clone().sub(followed);
            camera.position.add(delta);
            controls.target.add(delta);
          }
          followed.copy(subject.position);
        }
        lastMode=focus;
      }

      controls.update();
      camera.updateMatrixWorld();
      // Event glyphs have a fixed screen footprint across camera scales.
      const pixelAngle = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) / Math.max(1, container.clientHeight);
      for (const marker of [scMesh, brakeMarker]) {
        if (!marker) continue;
        const depth = -marker.position.clone().applyMatrix4(camera.matrixWorldInverse).z;
        marker.scale.setScalar(Math.max(camera.near, depth) * pixelAngle);
        marker.quaternion.copy(camera.quaternion);
      }
      if (needsFrame || idx !== lastSample || !camera.matrixWorld.equals(lastView)) {
        renderer.render(scene, camera);
        lastSample = idx;
        lastView.copy(camera.matrixWorld);
        needsFrame = false;
      }
    };

    animId = requestAnimationFrame(animate);

    return () => {
      disposed = true;
      cancelAnimationFrame(animId);
      resize.disconnect();
      controls.dispose();
      scene.traverse(node => {
        const drawable=node as THREE.Mesh;
        drawable.geometry?.dispose();
        for(const mat of [drawable.material ?? []].flat()) mat.dispose();
      });
      earthTex.dispose();
      moonTex.dispose();
      canvas.removeEventListener('webglcontextlost', useSoftware);
      gpu?.dispose();
      gpu?.forceContextLoss();
      container.innerHTML = '';
    };
  }, [trajData]);

  // Handle camera view preset changes
  const setCameraView = (mode: 'inertial' | 'earth' | 'moon' | 'spacecraft') => {
    setCameraMode(mode);
    cameraModeRef.current=mode;
    if (!cameraRef.current || !controlsRef.current) return;

    controlsRef.current.minDistance = mode === 'earth' ? earthRadius * 1.1 : moonRadius * 1.1;
    if (mode === 'inertial') {
      fitOverview.current();
    } else if (mode === 'earth') {
      controlsRef.current.target.set(0, 0, 0);
      cameraRef.current.position.set(0, -4 * earthRadius, 2 * earthRadius);
    } else if (mode === 'moon' && trajData && moonMeshRef.current) {
      const idx = Math.min(Math.floor(timeIndexRef.current), trajData.moon_coords_km.length - 1);
      const mCoord = trajData.moon_coords_km[idx];
      const mPos = new THREE.Vector3(mCoord[0] * DIST_SCALE, mCoord[1] * DIST_SCALE, mCoord[2] * DIST_SCALE);
      controlsRef.current.target.copy(mPos);
      cameraRef.current.position.set(mPos.x + 3*moonRadius, mPos.y - 3*moonRadius, mPos.z + 2*moonRadius);
    } else if (mode === 'spacecraft' && trajData && scMeshRef.current) {
      const idx = Math.min(Math.floor(timeIndexRef.current), trajData.spacecraft_coords_km.length - 1);
      const scCoord = trajData.spacecraft_coords_km[idx];
      const scPos = new THREE.Vector3(scCoord[0] * DIST_SCALE, scCoord[1] * DIST_SCALE, scCoord[2] * DIST_SCALE);
      controlsRef.current.target.copy(scPos);
      cameraRef.current.position.set(scPos.x + 20, scPos.y - 20, scPos.z + 15);
    }
    controlsRef.current.update();
  };

  // Current telemetry at scrubbed position
  const currTimeSec = trajData?.times_seconds[timeIndex] || 0;
  const currDays = Math.floor(currTimeSec / 86400);
  const currHours = Math.floor((currTimeSec % 86400) / 3600);
  const currMins = Math.floor((currTimeSec % 3600) / 60);
  const currSecs = Math.floor(currTimeSec % 60);

  const currPos = trajData?.spacecraft_coords_km[timeIndex] || [0, 0, 0];
  const currVel = trajData?.spacecraft_velocities_kms[timeIndex] || [0, 0, 0];
  const velMag = Math.sqrt(currVel[0] ** 2 + currVel[1] ** 2 + currVel[2] ** 2);
  const earthDist = Math.sqrt(currPos[0] ** 2 + currPos[1] ** 2 + currPos[2] ** 2);

  const moonCoord = trajData.moon_coords_km[timeIndex];
  const moonDist = Math.sqrt(
    (currPos[0] - moonCoord[0]) ** 2 +
    (currPos[1] - moonCoord[1]) ** 2 +
    (currPos[2] - moonCoord[2]) ** 2
  );
  const moonAlt = moonDist - trajData.lunar_reference_radius_km;

  return (
    <section hidden={!active} className="orbital-simulator" aria-label="Earth to Moon flight path">
      <div ref={mountRef} className="orbital-canvas" aria-label="Drag to orbit and scroll to zoom" />
      {missingMap && <p role="status" className="orb-map-error">{missingMap} imagery unavailable.</p>}
      <details className="orb-hud orbital-panel">
        <summary>Telemetry</summary>
        <div className="orb-clock">T+ {[currDays,currHours,currMins,currSecs].map((n,i)=>String(n).padStart(2,'0')+['d','h','m','s'][i]).join(' ')}</div>
        <dl className="orb-metrics">
          <div><dt>Velocity</dt><dd>{velMag.toFixed(3)} km/s</dd></div>
          <div><dt>Earth altitude</dt><dd>{Math.round(earthDist-trajData.earth_reference_radius_km).toLocaleString()} km</dd></div>
          <div><dt>Moon range</dt><dd>{Math.round(moonDist).toLocaleString()} km</dd></div>
          <div><dt>Lunar datum altitude</dt><dd>{moonAlt.toFixed(1)} km</dd></div>
        </dl>
        <div className="orb-vectors">J2000 · R (km) [{currPos.map(v=>v.toFixed(0)).join(', ')}]<br/>V (km/s) [{currVel.map(v=>v.toFixed(2)).join(', ')}]</div>
      </details>
      <label className="orb-camera orbital-panel">
        <Camera size={16} aria-hidden="true"/>
        <select aria-label="Camera perspective" value={cameraMode}
          onChange={e => setCameraView(e.target.value as keyof typeof cameras)}>
          {Object.entries(cameras).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
        </select>
      </label>
      <div className="orb-timeline orbital-panel">
        <div className="orb-playbar">
          <button className="orb-play" aria-label={isPlaying?'Pause flight':'Play flight'} onClick={()=>setIsPlaying(!isPlaying)}>
            {isPlaying?<Pause/>:<Play/>}
          </button>
          <button aria-label="Restart flight timeline" onClick={()=>{timeIndexRef.current=0;setTimeIndex(0);}}><RotateCcw/></button>
          <select className="orb-rate" aria-label="Playback speed in samples per second" value={playbackSpeed}
            onChange={e => setPlaybackSpeed(Number(e.target.value))}>
            {[10,50,150,400].map(rate => <option key={rate} value={rate}>{rate} samples/s</option>)}
          </select>
          <output>T+ {(currTimeSec/3600).toFixed(2)} h</output>
        </div>
        <input aria-label="Flight timeline" type="range" min={0} max={numPoints-1} value={timeIndex}
          onChange={e=>{setIsPlaying(false);timeIndexRef.current=Number(e.target.value);setTimeIndex(timeIndexRef.current);}} />
        <div className="orb-events">
          {[[0,'Injection'],[trajData.approach_index,'Descent braking'],[numPoints-1,'Touchdown']].map(([index,name])=>
            <button key={name} onClick={()=>{setIsPlaying(false);timeIndexRef.current=Number(index);setTimeIndex(Number(index));}}>{name}</button>)}
        </div>
      </div>
    </section>
  );
}
