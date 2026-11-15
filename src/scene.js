import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { DEG, MOON_RADIUS_KM as R, latLonToXYZ, xyzToLatLon } from './lunar.js';

const vector = (lat, lon, radius = 1) => new THREE.Vector3(...latLonToXYZ(lat, lon, radius));
export class LunarScene {
  constructor(host, grid, texture, normalTexture, callbacks) {
    this.host = host; this.grid = grid; this.callbacks = callbacks;
    this.mode = 'globe'; this.relief = 1; this.sunElevation = 25; this.layer = 'imagery'; this.keys = new Set();
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setClearColor(0x080a0c, 1);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.shadowMap.autoUpdate = false;
    host.appendChild(this.renderer.domElement);
    this.renderer.domElement.tabIndex = 0;
    this.renderer.domElement.setAttribute('aria-label', 'Interactive lunar viewport. Drag to orbit, scroll to zoom. Arrow keys rotate the globe; W A S D move in terrain view. Click the surface to inspect a location.');
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, .1, 30000);
    this.camera.position.copy(vector(-18, -12, 5700));
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true; this.controls.dampingFactor = .09;
    this.controls.minDistance = R + 40; this.controls.maxDistance = 11000;
    this.controls.enablePan = false;
    this.ambient = new THREE.AmbientLight(0xffffff, .38); this.scene.add(this.ambient);
    this.sun = new THREE.DirectionalLight(0xfff7ee, 3.5);
    this.scene.add(this.sun, this.sun.target);
    this.sun.shadow.mapSize.set(innerWidth < 700 ? 2048 : 4096, innerWidth < 700 ? 2048 : 4096);
    Object.assign(this.sun.shadow.camera, {left:-290, right:290, top:290, bottom:-290, near:1, far:1700});
    this.sun.shadow.camera.updateProjectionMatrix();
    this.sun.shadow.normalBias = .04;
    this.sun.shadow.bias = -.00015;
    this.texture = texture; texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = Math.min(8, this.renderer.capabilities.getMaxAnisotropy());
    texture.wrapS = THREE.RepeatWrapping;
    this.normalTexture = normalTexture;
    normalTexture.colorSpace = THREE.NoColorSpace;
    normalTexture.wrapS = THREE.RepeatWrapping;
    normalTexture.anisotropy = texture.anisotropy;
    this.normalUniforms = {
      moonNormalBasis: {value: new THREE.Matrix3()},
      moonRelief: {value: 1},
    };
    this.material = new THREE.MeshStandardMaterial({map:texture, normalMap:normalTexture, normalMapType:THREE.ObjectSpaceNormalMap, roughness:1, metalness:0});
    this.material.onBeforeCompile = shader => {
      Object.assign(shader.uniforms, this.normalUniforms);
      shader.fragmentShader = shader.fragmentShader.replace('#include <normalmap_pars_fragment>', `
        #include <normalmap_pars_fragment>
        uniform mat3 moonNormalBasis;
        uniform float moonRelief;
      `);
      // The normal texture records global XYZ. Reorient into the regional
      // east/up/south frame when viewing terrain. Scale only its tangential
      // gradient when height exaggeration changes; never double-count mesh slope.
      const normalChunk = THREE.ShaderChunk.normal_fragment_maps.replace(
        'normal = normalize( normalMatrix * normal );', `
          float moonLat = (vNormalMapUv.y - 0.5) * 3.14159265359;
          float moonLon = (vNormalMapUv.x - 0.5) * 6.28318530718;
          vec3 radial = vec3(cos(moonLat)*cos(moonLon), sin(moonLat), -cos(moonLat)*sin(moonLon));
          normal = normalize(normal);
          vec3 tangentSlope = normal / max(dot(normal, radial), 0.01) - radial;
          normal = normalize(radial + moonRelief * tangentSlope);
          normal = normalize(normalMatrix * moonNormalBasis * normal);
        `);
      shader.fragmentShader = shader.fragmentShader.replace('#include <normal_fragment_maps>',normalChunk);
    };
    this.material.customProgramCacheKey = () => 'lola-object-normals-v1';
    this.globeGeometry = new THREE.SphereGeometry(R, 768, 384);
    this.baseDirections = this.globeGeometry.attributes.position.array.slice();
    this.baseHeights = new Float32Array(this.globeGeometry.attributes.position.count);
    const pos = this.globeGeometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const c = xyzToLatLon(pos.getX(i), pos.getY(i), pos.getZ(i));
      this.baseHeights[i] = grid.sample(c.lat, c.lon) / 1000;
    }
    this.globe = new THREE.Mesh(this.globeGeometry, this.material);
    this.scene.add(this.globe); this.updateGlobeRelief();
    this.graticule = this.makeGrid(); this.scene.add(this.graticule);
    this.marker = new THREE.Group();
    const ring = new THREE.Mesh(new THREE.RingGeometry(17, 20, 64), new THREE.MeshBasicMaterial({ color: 0xd8efac, side: THREE.DoubleSide, depthTest: true }));
    const center = new THREE.Mesh(new THREE.CircleGeometry(5, 24), new THREE.MeshBasicMaterial({ color: 0xd8efac, side: THREE.DoubleSide }));
    this.marker.add(ring, center); this.scene.add(this.marker);
    this.raycaster = new THREE.Raycaster(); this.pointer = new THREE.Vector2();
    this.down = null;
    this.renderer.domElement.addEventListener('pointerdown', e => { this.down = [e.clientX, e.clientY]; this.renderer.domElement.focus({preventScroll:true}); });
    this.renderer.domElement.addEventListener('pointerup', e => {
      if (!this.down || Math.hypot(e.clientX - this.down[0], e.clientY - this.down[1]) > 5) return;
      this.pick(e);
    });
    this.renderer.domElement.addEventListener('keydown', e => {
      if (/^(ArrowUp|ArrowDown|ArrowLeft|ArrowRight|w|a|s|d|W|A|S|D)$/.test(e.key)) { e.preventDefault(); this.keys.add(e.key.toLowerCase()); }
    });
    this.renderer.domElement.addEventListener('keyup', e => this.keys.delete(e.key.toLowerCase()));
    this.renderer.domElement.addEventListener('blur', () => this.keys.clear());
    this.onWindowBlur=()=>this.keys.clear();
    window.addEventListener('blur',this.onWindowBlur);
    this.observer = new ResizeObserver(() => this.resize()); this.observer.observe(host); this.resize();
    this.last = performance.now(); this.frame = this.frame.bind(this); this.frame();
  }
  makeGrid() {
    const points = [], radius = R + 13;
    const add = (a,b) => points.push(...a,...b);
    for (let lat = -60; lat <= 60; lat += 30) for(let lon = -180; lon < 180; lon += 2) add(latLonToXYZ(lat,lon,radius),latLonToXYZ(lat,lon+2,radius));
    for (let lon = -180; lon < 180; lon += 30) for(let lat = -90; lat < 90; lat += 2) add(latLonToXYZ(lat,lon,radius),latLonToXYZ(lat+2,lon,radius));
    const geometry = new THREE.BufferGeometry(); geometry.setAttribute('position', new THREE.Float32BufferAttribute(points,3));
    return new THREE.LineSegments(geometry,new THREE.LineBasicMaterial({color:0xa4b2be,transparent:true,opacity:.15}));
  }
  updateGlobeRelief() {
    const pos = this.globeGeometry.attributes.position;
    for (let i = 0; i < pos.count; i++) {
      const scale = (R + this.baseHeights[i] * this.relief) / R;
      pos.setXYZ(i, this.baseDirections[i*3]*scale, this.baseDirections[i*3+1]*scale, this.baseDirections[i*3+2]*scale);
    }
    pos.needsUpdate = true; this.globeGeometry.computeVertexNormals(); this.globeGeometry.computeBoundingSphere();
  }
  select(site, animate = true) {
    this.site = site;
    if (this.mode === 'terrain') { this.buildTerrain(); this.reset(); }
    else {
      const p = vector(site.lat, site.lon, R + this.grid.sample(site.lat,site.lon)/1000*this.relief + 7);
      this.marker.position.copy(p); this.marker.quaternion.setFromUnitVectors(new THREE.Vector3(0,0,1),p.clone().normalize());
      this.marker.scale.setScalar(1);
      if (animate && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) { this.destination = vector(site.lat,site.lon,Math.max(3300, this.camera.position.length())); this.controls.target.set(0,0,0); }
      else if(animate) { this.camera.position.copy(vector(site.lat,site.lon,5700)); this.controls.target.set(0,0,0); }
    }
  }
  setMode(mode) {
    this.mode = mode; this.destination = null; this.keys.clear();
    this.globe.visible = mode === 'globe'; this.graticule.visible = mode === 'globe' && this.showGrid;
    if (mode === 'terrain') this.buildTerrain();
    else { if(this.terrain) this.terrain.visible = false; this.normalUniforms.moonNormalBasis.value.identity(); this.select(this.site, false); }
    this.updateLighting(); this.renderer.shadowMap.needsUpdate = true;
    this.reset();
  }
  buildTerrain() {
    if (this.terrain) { this.scene.remove(this.terrain); this.terrain.geometry.dispose(); }
    const {lat,lon} = this.site;
    this.up = vector(lat,lon);
    this.east = new THREE.Vector3(-Math.sin(lon*DEG),0,-Math.cos(lon*DEG));
    this.north = new THREE.Vector3().crossVectors(this.up,this.east).negate();
    // north = derivative of spherical position with respect to latitude.
    this.north.set(-Math.sin(lat*DEG)*Math.cos(lon*DEG), Math.cos(lat*DEG), Math.sin(lat*DEG)*Math.sin(lon*DEG));
    const segments = 256, size = 400;
    let geometry = new THREE.PlaneGeometry(size,size,segments,segments);
    const pos = geometry.attributes.position, uv = geometry.attributes.uv;
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i), n = pos.getY(i);
      const dir = this.up.clone().multiplyScalar(R).addScaledVector(this.east,x).addScaledVector(this.north,n).normalize();
      const coord = xyzToLatLon(dir.x,dir.y,dir.z);
      const p = dir.multiplyScalar(R + this.grid.sample(coord.lat,coord.lon)/1000*this.relief);
      pos.setXYZ(i,p.dot(this.east),p.dot(this.up)-R,-p.dot(this.north));
      // Unwrap around the selected longitude to avoid a seam across ±180°.
      let longitude = coord.lon;
      while(longitude-lon>180) longitude-=360;
      while(longitude-lon< -180) longitude+=360;
      uv.setXY(i,(longitude+180)/360,(coord.lat+90)/180);
    }
    geometry.computeVertexNormals();
    // Duplicate triangle vertices at the equirectangular seam so interpolation
    // takes the short way around the texture, including polar patches.
    const indexed = geometry;
    geometry = indexed.toNonIndexed(); indexed.dispose();
    const textureUV = geometry.attributes.uv;
    for (let i = 0; i < textureUV.count; i += 3) {
      const anchor = textureUV.getX(i);
      for (let j = 1; j < 3; j++) {
        let u = textureUV.getX(i + j);
        while (u - anchor > .5) u -= 1;
        while (u - anchor < -.5) u += 1;
        textureUV.setX(i + j, u);
      }
    }
    geometry.computeBoundingSphere();
    this.normalUniforms.moonNormalBasis.value.set(
      this.east.x,this.east.y,this.east.z,
      this.up.x,this.up.y,this.up.z,
      -this.north.x,-this.north.y,-this.north.z,
    );
    this.terrain = new THREE.Mesh(geometry,this.material);
    this.terrain.castShadow = true; this.terrain.receiveShadow = true;
    this.scene.add(this.terrain);
    this.renderer.shadowMap.needsUpdate = true;
    const h = this.grid.sample(lat,lon)/1000*this.relief;
    this.marker.position.set(0,h+.4,0); this.marker.quaternion.setFromAxisAngle(new THREE.Vector3(1,0,0),-Math.PI/2); this.marker.scale.setScalar(.18);
    this.terrainHeight = h;
    this.updateLighting();
  }
  reset() {
    this.destination = null;
    if (this.mode === 'globe') {
      this.controls.minDistance = R + 40; this.controls.maxDistance = 11000; this.controls.maxPolarAngle = Math.PI;
      this.controls.enablePan = false; this.controls.target.set(0,0,0);
      this.camera.position.copy(vector(this.site?.lat ?? -18, this.site?.lon ?? -12,5700));
    } else {
      this.controls.minDistance = 8; this.controls.maxDistance = 550; this.controls.maxPolarAngle = Math.PI*.47;
      this.controls.enablePan = true; this.controls.target.set(0,this.terrainHeight,0); this.camera.position.set(100,145,180);
    }
    this.controls.update();
  }
  setLayer(layer) {
    this.layer = layer;
    this.material.map = layer === 'imagery' ? this.texture : null;
    this.material.color.set(layer === 'imagery' ? 0xffffff : 0xa3a5a6);
    this.material.wireframe = layer === 'wireframe'; this.material.needsUpdate = true;
  }
  setRelief(amount) {
    this.relief = amount; this.normalUniforms.moonRelief.value = amount;
    this.updateGlobeRelief();
    if(this.mode === 'terrain') {
      // Changing display settings must preserve the user's current camera.
      this.buildTerrain();
    } else this.select(this.site,false);
    this.renderer.shadowMap.needsUpdate = true;
  }
  setSunElevation(degrees) {
    this.sunElevation = degrees; this.updateLighting(); this.renderer.shadowMap.needsUpdate = true;
  }
  updateLighting() {
    const angle = this.sunElevation * DEG;
    this.sun.castShadow = this.mode === 'terrain';
    this.ambient.intensity = this.mode === 'terrain' ? .24 : .38;
    if(this.mode === 'terrain') {
      this.sun.target.position.set(0,this.terrainHeight ?? 0,0);
      this.sun.position.set(-Math.cos(angle)*600,Math.sin(angle)*800,Math.cos(angle)*530);
    } else {
      this.sun.target.position.set(0,0,0);
      const radial = this.camera.position.clone().normalize();
      const right = new THREE.Vector3(1,0,0).applyQuaternion(this.camera.quaternion);
      const up = new THREE.Vector3(0,1,0).applyQuaternion(this.camera.quaternion);
      this.sun.position.copy(radial.multiplyScalar(Math.sin(angle)).addScaledVector(right,-.65*Math.cos(angle)).addScaledVector(up,.76*Math.cos(angle)).normalize().multiplyScalar(R*4));
    }
    this.sun.target.updateMatrixWorld();
  }
  setGrid(visible) { this.showGrid = visible; this.graticule.visible = visible && this.mode === 'globe'; }
  zoom(factor) {
    const offset = this.camera.position.clone().sub(this.controls.target);
    offset.setLength(THREE.MathUtils.clamp(offset.length()*factor,this.controls.minDistance,this.controls.maxDistance));
    this.camera.position.copy(this.controls.target).add(offset); this.controls.update();
  }
  pick(event) {
    const rect = this.renderer.domElement.getBoundingClientRect();
    this.pointer.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);
    this.raycaster.setFromCamera(this.pointer,this.camera);
    const hit = this.raycaster.intersectObject(this.mode === 'globe' ? this.globe : this.terrain)[0];
    if (!hit) return;
    let p = hit.point;
    if (this.mode === 'terrain') p = this.up.clone().multiplyScalar(R + p.y).addScaledVector(this.east,p.x).addScaledVector(this.north,-p.z);
    const coords = xyzToLatLon(p.x,p.y,p.z);
    this.callbacks.onPick({...coords,elevation:this.grid.sample(coords.lat,coords.lon)});
  }
  resize() {
    const {width,height} = this.host.getBoundingClientRect();
    if (!width || !height) return;
    this.camera.aspect=width/height; this.camera.updateProjectionMatrix(); this.renderer.setSize(width,height);
  }
  frame() {
    this.frameId = requestAnimationFrame(this.frame);
    const now = performance.now(), dt = Math.min((now-this.last)/1000,.05); this.last=now;
    if (this.destination) {
      // Interpolate direction on a sphere so opposite-side flights never cross the Moon.
      const current = this.camera.position.clone().normalize(), target=this.destination.clone().normalize();
      const rotation = new THREE.Quaternion().setFromUnitVectors(current,target);
      const step = new THREE.Quaternion().slerp(rotation,1-Math.exp(-dt*5));
      current.applyQuaternion(step);
      const distance=THREE.MathUtils.lerp(this.camera.position.length(),this.destination.length(),1-Math.exp(-dt*5));
      this.camera.position.copy(current.multiplyScalar(distance));
      if(current.normalize().distanceTo(target)<.001) this.destination=null;
    }
    if (this.keys.size) {
      this.destination=null;
      const dx = Number(this.keys.has('d')||this.keys.has('arrowright'))-Number(this.keys.has('a')||this.keys.has('arrowleft'));
      const dz = Number(this.keys.has('s')||this.keys.has('arrowdown'))-Number(this.keys.has('w')||this.keys.has('arrowup'));
      if (this.mode==='terrain') {
        const forward=this.controls.target.clone().sub(this.camera.position); forward.y=0; forward.normalize();
        const right=new THREE.Vector3().crossVectors(forward,new THREE.Vector3(0,1,0));
        const delta=right.multiplyScalar(dx*dt*35).addScaledVector(forward,-dz*dt*35);
        this.camera.position.add(delta); this.controls.target.add(delta);
      } else {
        const spherical=new THREE.Spherical().setFromVector3(this.camera.position);
        spherical.theta-=dx*dt*.6; spherical.phi=THREE.MathUtils.clamp(spherical.phi+dz*dt*.6,.01,Math.PI-.01);
        this.camera.position.setFromSpherical(spherical);
      }
    }
    if(this.mode==='terrain') {
      const t=this.controls.target;
      const clamped=t.clone(); clamped.x=THREE.MathUtils.clamp(t.x,-150,150); clamped.z=THREE.MathUtils.clamp(t.z,-150,150);
      const dir=this.up.clone().multiplyScalar(R).addScaledVector(this.east,clamped.x).addScaledVector(this.north,-clamped.z);
      const coord=xyzToLatLon(dir.x,dir.y,dir.z), height=this.grid.sample(coord.lat,coord.lon)/1000*this.relief;
      clamped.y=dir.normalize().multiplyScalar(R+height).dot(this.up)-R;
      this.camera.position.add(clamped.clone().sub(t)); this.controls.target.copy(clamped);
      this.camera.position.y=Math.max(this.camera.position.y,clamped.y+3);
    }
    this.controls.update();
    if(this.mode === 'globe')this.updateLighting();
    this.renderer.render(this.scene,this.camera);
    if(!this.lastReport||now-this.lastReport>180) {
      const distance=this.camera.position.distanceTo(this.controls.target);
      this.callbacks.onCamera({distance,mode:this.mode}); this.lastReport=now;
    }
  }
  dispose() {
    cancelAnimationFrame(this.frameId); window.removeEventListener('blur',this.onWindowBlur); this.observer.disconnect(); this.controls.dispose();
    this.scene.traverse(node => {
      node.geometry?.dispose();
      if(node.material && node.material !== this.material)node.material.dispose();
    });
    this.material.dispose(); this.texture.dispose(); this.normalTexture.dispose(); this.sun.shadow.dispose(); this.renderer.dispose();
  }
}
export async function loadTexture(url) { return new THREE.TextureLoader().loadAsync(url); }
