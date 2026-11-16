// Adapted from prollyAditya/Clavius, FlightSimulator3D.tsx (3f26903).
import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { Play, Pause, RotateCcw } from 'lucide-react';
import type { FlightSamples } from './types';

// Procedural texture generator for Earth
function createEarthTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 1024;
  canvas.height = 512;
  const ctx = canvas.getContext('2d')!;

  // Deep ocean blue gradient
  const oceanGrad = ctx.createLinearGradient(0, 0, 0, 512);
  oceanGrad.addColorStop(0, '#0a1d37');
  oceanGrad.addColorStop(0.5, '#0d2d59');
  oceanGrad.addColorStop(1, '#0a1d37');
  ctx.fillStyle = oceanGrad;
  ctx.fillRect(0, 0, 1024, 512);

  // Continents stylized shapes
  ctx.fillStyle = '#1c4a38';
  // North America
  ctx.beginPath();
  ctx.ellipse(250, 160, 100, 70, -0.2, 0, Math.PI * 2);
  ctx.fill();
  // South America
  ctx.beginPath();
  ctx.ellipse(320, 320, 60, 110, 0.3, 0, Math.PI * 2);
  ctx.fill();
  // Eurasia
  ctx.beginPath();
  ctx.ellipse(650, 150, 160, 80, 0.1, 0, Math.PI * 2);
  ctx.fill();
  // Africa
  ctx.beginPath();
  ctx.ellipse(540, 260, 80, 100, 0, 0, Math.PI * 2);
  ctx.fill();
  // Australia
  ctx.beginPath();
  ctx.ellipse(820, 340, 50, 40, -0.2, 0, Math.PI * 2);
  ctx.fill();

  // Ice caps
  ctx.fillStyle = '#d6e6ff';
  ctx.fillRect(0, 0, 1024, 30);
  ctx.fillRect(0, 485, 1024, 27);

  // Cloud swirls
  ctx.fillStyle = 'rgba(255, 255, 255, 0.25)';
  for (let i = 0; i < 40; i++) {
    const x = (i * 37) % 1024;
    const y = 80 + (i * 17) % 350;
    ctx.beginPath();
    ctx.ellipse(x, y, 40 + (i % 30), 10 + (i % 15), 0.2, 0, Math.PI * 2);
    ctx.fill();
  }

  // Lat/Lon subtle grid
  ctx.strokeStyle = 'rgba(56, 189, 248, 0.12)';
  ctx.lineWidth = 1;
  for (let x = 0; x <= 1024; x += 128) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, 512);
    ctx.stroke();
  }
  for (let y = 0; y <= 512; y += 64) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(1024, y);
    ctx.stroke();
  }

  return new THREE.CanvasTexture(canvas);
}

// Procedural texture generator for Moon
function createMoonTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 512;
  canvas.height = 256;
  const ctx = canvas.getContext('2d')!;

  ctx.fillStyle = '#8a929a';
  ctx.fillRect(0, 0, 512, 256);

  // Lunar maria (dark basalt plains)
  ctx.fillStyle = '#555b63';
  ctx.beginPath();
  ctx.ellipse(180, 90, 70, 50, 0.2, 0, Math.PI * 2); // Oceanus Procellarum / Imbrium
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(280, 95, 45, 40, -0.1, 0, Math.PI * 2); // Serenitatis
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(320, 130, 40, 35, 0, 0, Math.PI * 2); // Tranquillitatis
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(350, 160, 30, 25, 0.1, 0, Math.PI * 2); // Fecunditatis
  ctx.fill();

  // Impact craters
  ctx.fillStyle = '#b0b8c2';
  for (let i = 0; i < 50; i++) {
    const x = (i * 61) % 512;
    const y = (i * 47) % 256;
    const r = 3 + (i % 8);
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#43474c';
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  return new THREE.CanvasTexture(canvas);
}

export function FlightSimulator3D({trajData, active}: {trajData: FlightSamples, active: boolean}) {
  const mountRef = useRef<HTMLDivElement>(null);

  // Simulation playback state
  const [isPlaying, setIsPlaying] = useState<boolean>(() => !matchMedia("(prefers-reduced-motion: reduce)").matches);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(50); // steps per second
  const [timeIndex, setTimeIndex] = useState<number>(0);
  const [cameraMode, setCameraMode] = useState<'inertial' | 'earth' | 'moon' | 'spacecraft'>('inertial');
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
  // Visual exaggeration for celestial body radii to make them easily visible at transfer scale
  const EARTH_VIS_RADIUS = 6.378 * 2.2; // ~14 units
  const MOON_VIS_RADIUS = 1.737 * 3.5;  // ~6 units

  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x030712);

    // Camera
    const camera = new THREE.PerspectiveCamera(
      45,
      container.clientWidth / container.clientHeight,
      0.1,
      5000
    );
    cameraRef.current = camera;
    camera.position.set(0, -450, 320);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.innerHTML = '';
    container.appendChild(renderer.domElement);

    // OrbitControls
    const controls = new OrbitControls(camera, renderer.domElement);
    controlsRef.current = controls;
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxDistance = 2500;
    controls.minDistance = 15;

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.4);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xffffff, 1.8);
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
    const starMaterial = new THREE.PointsMaterial({ color: 0x94a3b8, size: 1.5, sizeAttenuation: false });
    const starField = new THREE.Points(starGeometry, starMaterial);
    scene.add(starField);

    // Coordinate grid on the J2000 equatorial plane (Z=0)
    const gridHelper = new THREE.GridHelper(900, 36, 0x06b6d4, 0x1e293b);
    gridHelper.rotation.x = Math.PI / 2;
    gridHelper.position.set(0, 0, 0);
    scene.add(gridHelper);

    // Earth Sphere
    const earthGeo = new THREE.SphereGeometry(EARTH_VIS_RADIUS, 48, 48);
    const earthTex = createEarthTexture();
    const earthMat = new THREE.MeshStandardMaterial({
      map: earthTex,
      roughness: 0.7,
      metalness: 0.1,
    });
    const earthMesh = new THREE.Mesh(earthGeo, earthMat);
    earthMesh.position.set(0, 0, 0);
    scene.add(earthMesh);

    // Atmosphere Glow Rim
    const atmoGeo = new THREE.SphereGeometry(EARTH_VIS_RADIUS * 1.08, 32, 32);
    const atmoMat = new THREE.MeshBasicMaterial({
      color: 0x00f0ff,
      transparent: true,
      opacity: 0.18,
      side: THREE.BackSide,
    });
    const atmoMesh = new THREE.Mesh(atmoGeo, atmoMat);
    scene.add(atmoMesh);

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
      color: 0x334155,
      dashSize: 6,
      gapSize: 4,
    });
    const moonOrbitRing = new THREE.Line(orbitRingGeo, orbitRingMat);
    moonOrbitRing.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1), orbitNormal);
    moonOrbitRing.computeLineDistances();
    scene.add(moonOrbitRing);

    // Moon Sphere
    const moonGeo = new THREE.SphereGeometry(MOON_VIS_RADIUS, 32, 32);
    const moonTex = createMoonTexture();
    const moonMat = new THREE.MeshStandardMaterial({
      map: moonTex,
      roughness: 0.9,
    });
    const moonMesh = new THREE.Mesh(moonGeo, moonMat);
    moonMeshRef.current = moonMesh;
    scene.add(moonMesh);

    // Spacecraft Indicator (Small Glowing Octahedron + Beacon)
    const scGeo = new THREE.OctahedronGeometry(2.5, 0);
    const scMat = new THREE.MeshBasicMaterial({ color: 0x00f0ff, wireframe: false });
    const scMesh = new THREE.Mesh(scGeo, scMat);
    scMeshRef.current = scMesh;
    scene.add(scMesh);

    // Spacecraft Beacon Halo
    const haloGeo = new THREE.RingGeometry(3.5, 5.0, 16);
    const haloMat = new THREE.MeshBasicMaterial({
      color: 0x22d3ee,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.7,
    });
    scMat.depthTest = false;
    scMesh.renderOrder = 3;
    const haloMesh = new THREE.Mesh(haloGeo, haloMat);
    scMesh.add(haloMesh);

    // Full planned/simulated trajectory ribbon (all points)
    if (trajData && trajData.spacecraft_coords_km.length > 0) {
      const pts = trajData.spacecraft_coords_km.map(
        (c) => new THREE.Vector3(c[0] * DIST_SCALE, c[1] * DIST_SCALE, c[2] * DIST_SCALE)
      );
      const fullTrajGeo = new THREE.BufferGeometry().setFromPoints(pts);
      const fullTrajMat = new THREE.LineBasicMaterial({
        color: 0x1e3a8a, // Deep blue planned trajectory
        transparent: true,
        opacity: 0.6,
      });
      const fullLine = new THREE.Line(fullTrajGeo, fullTrajMat);
      scene.add(fullLine);

      // Traversed past trajectory (bright cyan)
      const pastGeo = new THREE.BufferGeometry().setFromPoints(pts);
      const pastMat = new THREE.LineBasicMaterial({
        color: 0x06b6d4, // Bright neon cyan
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
          color: 0xf59e0b, // Amber marker
          side: THREE.DoubleSide,
        });
        const periMarker = new THREE.Mesh(periMarkerGeo, periMarkerMat);
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
        new THREE.Vector3(0,-450,320).normalize(), (sphere.radius+EARTH_VIS_RADIUS)*1.1/Math.sin(limitingFov)
      );
      controls.update();
    };
    fitOverview.current();
    const resize = new ResizeObserver(() => {
      if (!container.clientWidth || !container.clientHeight) return;
      camera.aspect = container.clientWidth / container.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
      if(cameraModeRef.current === 'inertial') fitOverview.current();
    });
    resize.observe(container);
    let followed = new THREE.Vector3();
    let lastMode = '';
    // Animation Loop
    let lastTime = performance.now();
    let animId: number;

    const animate = (now: number) => {
      animId = requestAnimationFrame(animate);

      const dt = Math.min((now - lastTime) / 1000, .25);
      lastTime = now;
      if (!activeRef.current || document.hidden) return;

      // Earth slow rotation
      earthMesh.rotation.z += 0.001;

      // Update trajectory playback
      if (isPlayingRef.current && trajData && trajData.spacecraft_coords_km.length > 0) {
        const total = trajData.spacecraft_coords_km.length;
        const advance = speedRef.current * dt;
        let nextIdx = timeIndexRef.current + advance;
        if (nextIdx >= total) {
          nextIdx = 0; // loop
        }
        timeIndexRef.current = nextIdx;
        setTimeIndex(Math.floor(nextIdx));
      }

      // Update positions of spacecraft and moon based on current timeIndex
      const idx = Math.min(Math.floor(timeIndexRef.current), (trajData?.spacecraft_coords_km.length || 1) - 1);
      if (trajData && trajData.spacecraft_coords_km[idx]) {
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
        haloMesh.quaternion.copy(camera.quaternion);
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
      renderer.render(scene, camera);
    };

    animId = requestAnimationFrame(animate);

    return () => {
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
      renderer.forceContextLoss();
      renderer.dispose();
      container.innerHTML = '';
    };
  }, [trajData]);

  // Handle camera view preset changes
  const setCameraView = (mode: 'inertial' | 'earth' | 'moon' | 'spacecraft') => {
    setCameraMode(mode);
    cameraModeRef.current=mode;
    if (!cameraRef.current || !controlsRef.current) return;

    if (mode === 'inertial') {
      fitOverview.current();
    } else if (mode === 'earth') {
      controlsRef.current.target.set(0, 0, 0);
      cameraRef.current.position.set(0, -50, 30);
    } else if (mode === 'moon' && trajData && moonMeshRef.current) {
      const idx = Math.min(Math.floor(timeIndexRef.current), trajData.moon_coords_km.length - 1);
      const mCoord = trajData.moon_coords_km[idx];
      const mPos = new THREE.Vector3(mCoord[0] * DIST_SCALE, mCoord[1] * DIST_SCALE, mCoord[2] * DIST_SCALE);
      controlsRef.current.target.copy(mPos);
      cameraRef.current.position.set(mPos.x + 30, mPos.y - 30, mPos.z + 20);
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
      <details className="orb-hud orbital-panel" open={!matchMedia('(max-width: 900px)').matches}>
        <summary>Flight telemetry <span>J2000</span></summary>
        <div className="orb-clock">T+ {[currDays,currHours,currMins,currSecs].map((n,i)=>String(n).padStart(2,'0')+['d','h','m','s'][i]).join(' ')}</div>
        <dl className="orb-metrics">
          <div><dt>Velocity</dt><dd>{velMag.toFixed(3)} km/s</dd></div>
          <div><dt>Earth altitude</dt><dd>{Math.round(earthDist-trajData.earth_reference_radius_km).toLocaleString()} km</dd></div>
          <div><dt>Moon range</dt><dd>{Math.round(moonDist).toLocaleString()} km</dd></div>
          <div><dt>Lunar datum altitude</dt><dd>{moonAlt.toFixed(1)} km</dd></div>
        </dl>
        <div className="orb-vectors">R (km) [{currPos.map(v=>v.toFixed(0)).join(', ')}]<br/>V (km/s) [{currVel.map(v=>v.toFixed(2)).join(', ')}]</div>
      </details>
      <div className="orb-cameras orbital-panel" aria-label="Camera perspective">
        {(['inertial','earth','moon','spacecraft'] as const).map((mode,i)=>
          <button key={mode} aria-label={['Inertial system','Earth focus','Moon focus','Spacecraft cam'][i]} aria-pressed={cameraMode===mode} onClick={()=>setCameraView(mode)}>
            <span className="orb-camera-full">{['Inertial system','Earth focus','Moon focus','Spacecraft cam'][i]}</span>
            <span className="orb-camera-short">{['System','Earth','Moon','Spacecraft'][i]}</span>
          </button>)}
      </div>
      <div className="orb-timeline orbital-panel">
        <div className="orb-playbar">
          <button className="orb-play" aria-label={isPlaying?'Pause flight':'Play flight'} onClick={()=>setIsPlaying(!isPlaying)}>
            {isPlaying?<Pause/>:<Play/>}
          </button>
          <button aria-label="Restart flight timeline" onClick={()=>{timeIndexRef.current=0;setTimeIndex(0);}}><RotateCcw/></button>
          <div className="orb-rates" aria-label="Playback speed in samples per second">
            {[10,50,150,400].map(spd=><button key={spd} title={spd+' samples per second'} aria-pressed={playbackSpeed===spd} onClick={()=>setPlaybackSpeed(spd)}>{spd}×</button>)}
          </div>
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
