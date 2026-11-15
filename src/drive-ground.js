import * as THREE from 'three';

export async function loadGround(info, signal) {
  const response = await fetch('/data/drive/'+info.file,{signal});
  if(!response.ok)throw new Error('Terrain download failed.');
  const bytes = await response.arrayBuffer();
  if(bytes.byteLength!==info.count**2*4)throw new Error('Incomplete terrain file.');
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  if(digest!==info.sha256)throw new Error('Terrain checksum mismatch.');
  return {...info, values:new Float32Array(bytes)};
}

// Match the same triangular facets used for rendering, including at cell edges.
export function groundHeight(grid,east,north) {
  const n=grid.count, x=(east+grid.half_extent_m)/grid.spacing_m, y=(north+grid.half_extent_m)/grid.spacing_m;
  if(x<0||y<0||x>n-1||y>n-1)throw new RangeError('Outside drive terrain.');
  const i=Math.min(n-2,Math.floor(x)),j=Math.min(n-2,Math.floor(y)),a=x-i,b=y-j;
  const k=j*n+i,v=grid.values;
  if(a+b<=1)return v[k]+a*(v[k+1]-v[k])+b*(v[k+n]-v[k]);
  return v[k+n+1]+(1-a)*(v[k+n]-v[k+n+1])+(1-b)*(v[k+1]-v[k+n+1]);
}

export async function loadDriveImage(record, signal) {
  const r=await fetch('/data/drive/'+record.file,{signal});
  if(!r.ok)throw new Error('LROC mosaic download failed.');
  const bytes=await r.arrayBuffer();
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  if(digest!==record.sha256)throw new Error('LROC mosaic checksum mismatch.');
  const url=URL.createObjectURL(new Blob([bytes],{type:'image/png'}));
  try{
    const texture=await new THREE.TextureLoader().loadAsync(url);
    texture.colorSpace=THREE.NoColorSpace;texture.anisotropy=4;
    return texture;
  }finally{URL.revokeObjectURL(url);}
}

export function terrainMesh(grid, localHalf, regional, image) {
  const n=grid.count, vertices=new Float32Array(n*n*3), indices=[];
  for(let j=0;j<n;j++)for(let i=0;i<n;i++){
    const k=j*n+i, e=i*grid.spacing_m-grid.half_extent_m, north=j*grid.spacing_m-grid.half_extent_m;
    const edge=Math.max(Math.abs(e),Math.abs(north));
    let up=grid.values[k];
    // Match the two independent DEMs along the perimeter outside the drive area.
    if(regional && edge>localHalf-80){
      const f=(edge-localHalf+80)/80;
      up=THREE.MathUtils.lerp(up,groundHeight(regional,e,north),f);
    }
    vertices.set([e,up,-north],3*k);
    if(i===n-1||j===n-1)continue;
    if(!regional && Math.abs(e+grid.spacing_m/2)<localHalf && Math.abs(north+grid.spacing_m/2)<localHalf)continue;
    indices.push(k,k+1,k+n,k+1,k+n+1,k+n);
  }
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(vertices,3));g.setIndex(indices);g.computeVertexNormals();
  const mat=new THREE.MeshStandardMaterial({color:0x999893,roughness:1});
  const contours={value:0}, imagery={value:1};
  mat.onBeforeCompile=shader=>{
    shader.uniforms.drawContours=contours;
    shader.uniforms.showImage=imagery;
    shader.uniforms.mosaic={value:image};
    shader.uniforms.footprint={value:2*grid.half_extent_m};
    shader.vertexShader='varying vec3 surfacePoint;\n'+shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nsurfacePoint = position;');
    shader.fragmentShader='varying vec3 surfacePoint;\nuniform float drawContours; uniform float showImage; uniform float footprint; uniform sampler2D mosaic;\n'+shader.fragmentShader.replace('#include <color_fragment>',`
      #include <color_fragment>
      vec2 lunarUV=vec2(surfacePoint.x,-surfacePoint.z)/footprint+.5;
      vec4 observation=texture2D(mosaic,lunarUV);
      float brightness=.26+1.55*sqrt(observation.r);
      diffuseColor.rgb*=mix(1.,brightness,observation.a*showImage);
      vec2 p=surfacePoint.xz*85.0;
      float seed=fract(sin(dot(mod(floor(p),256.0),vec2(12.9898,78.233)))*43758.5453);
      float grain=(seed-.5)*(1.0-smoothstep(.35,1.3,max(fwidth(p.x),fwidth(p.y))));
      diffuseColor.rgb*=1.0+.16*grain;
      float level=surfacePoint.y/10.0;
      float line=1.0-smoothstep(.0,max(.012,fwidth(level)),abs(fract(level+.5)-.5));
      diffuseColor.rgb=mix(diffuseColor.rgb,vec3(.23,.35,.28),drawContours*line*.75);
    `);
  };
  const mesh=new THREE.Mesh(g,mat);mesh.receiveShadow=!!regional;
  mesh.userData.contours=contours;mesh.userData.imagery=imagery;mesh.userData.texture=image;
  return mesh;
}
