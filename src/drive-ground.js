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

export async function driveImageBlob(record, signal, name = 'LROC mosaic') {
  const r=await fetch('/data/drive/'+record.file,{signal});
  if(!r.ok)throw new Error(name+' download failed.');
  const bytes=await r.arrayBuffer();
  const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');
  if(digest!==record.sha256)throw new Error(name+' checksum mismatch.');
  return new Blob([bytes],{type:'image/png'});
}

export async function loadDriveImage(record, signal) {
  const url=URL.createObjectURL(await driveImageBlob(record,signal));
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
  const contours={value:0}, imagery={value:1}, grain={value:1};
  mat.onBeforeCompile=shader=>{
    shader.uniforms.drawContours=contours;
    shader.uniforms.showImage=imagery;
    shader.uniforms.showGrain=grain;
    shader.uniforms.mosaic={value:image};
    shader.uniforms.footprint={value:2*grid.half_extent_m};
    shader.vertexShader='varying vec3 surfacePoint;\n'+shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nsurfacePoint = position;');
    shader.fragmentShader=`
      varying vec3 surfacePoint;
      uniform float drawContours, showImage, showGrain, footprint;
      uniform sampler2D mosaic;
      float randomCell(vec2 cell) {
        vec3 p=fract(vec3(cell.xyx)*vec3(.1031,.1030,.0973));
        p+=dot(p,p.yzx+33.33);
        return fract((p.x+p.y)*p.z);
      }
      // Color variation only. Fade each band before it becomes subpixel.
      float surfaceGrain(vec2 p) {
        vec2 pixel=fwidth(p);
        float visible=1.-smoothstep(.25,1.,max(pixel.x,pixel.y));
        if(visible<=0.)return 0.;
        vec2 cell=floor(p), f=fract(p);
        f=f*f*(3.-2.*f);
        float a=mix(randomCell(cell),randomCell(cell+vec2(1,0)),f.x);
        float b=mix(randomCell(cell+vec2(0,1)),randomCell(cell+vec2(1,1)),f.x);
        return (mix(a,b,f.y)-.5)*visible;
      }
    `+shader.fragmentShader.replace('#include <color_fragment>',`
      #include <color_fragment>
      vec2 lunarUV=vec2(surfacePoint.x,-surfacePoint.z)/footprint+.5;
      vec4 observation=texture2D(mosaic,lunarUV);
      float brightness=.26+1.55*sqrt(observation.r);
      diffuseColor.rgb*=mix(1.,brightness,observation.a*showImage);
      vec2 p=surfacePoint.xz;
      float variation=.52*surfaceGrain(p*7.3)+.82*surfaceGrain(p*34.+13.)+.65*surfaceGrain(p*120.+37.);
      diffuseColor.rgb*=1.+showGrain*variation;
      float level=surfacePoint.y/10.0;
      float line=1.0-smoothstep(.0,max(.012,fwidth(level)),abs(fract(level+.5)-.5));
      diffuseColor.rgb=mix(diffuseColor.rgb,vec3(.23,.35,.28),drawContours*line*.75);
    `);
  };
  const mesh=new THREE.Mesh(g,mat);mesh.receiveShadow=!!regional;
  mesh.userData.contours=contours;mesh.userData.imagery=imagery;mesh.userData.texture=image;mesh.userData.grain=grain;
  return mesh;
}
