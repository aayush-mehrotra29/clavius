import * as THREE from 'three';
import {MOON_RADIUS_KM as R, xyzToLatLon} from './lunar.js';

// Four strips start at exactly the same tangent-plane samples as the local
// mesh. Outward samples spread with distance toward the physical horizon.
export function buildSurround({segments,east,north,up,lon,relief,grid,innerGrid}) {
  const bands=32, positions=[],uv=[],indices=[],dir=new THREE.Vector3();
  const sides=[(t,r)=>[t*r,r],(t,r)=>[r,-t*r],(t,r)=>[-t*r,-r],(t,r)=>[-r,t*r]];
  for(const side of sides){
    const start=positions.length/3;
    for(let j=0;j<=bands;j++){
      const edge=200+8*Math.expm1(j/5);
      for(let i=0;i<=segments;i++){
        const [e,n]=side(2*i/segments-1,edge);
        dir.copy(up).multiplyScalar(R).addScaledVector(east,e).addScaledVector(north,n).normalize();
        const coord=xyzToLatLon(dir.x,dir.y,dir.z);
        const height=(j===0?innerGrid:grid).sample(coord.lat,coord.lon);
        dir.multiplyScalar(R+height/1000*relief);
        positions.push(dir.dot(east),dir.dot(up)-R,-dir.dot(north));
        const unwrapped=coord.lon+360*Math.round((lon-coord.lon)/360);
        uv.push((unwrapped+180)/360,(coord.lat+90)/180);
        if(i<segments && j<bands){
          const a=start+j*(segments+1)+i,b=a+segments+1;
          indices.push(a,a+1,b,a+1,b+1,b);
        }
      }
    }
  }
  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  g.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));
  g.setIndex(indices);g.computeVertexNormals();splitTextureSeam(g);
  return g;
}

// Preserve the indexed mesh and its smooth normals at the map seam. The same
// vertex can need two U values where neighboring triangles wrap differently.
export function splitTextureSeam(geometry) {
  const uv=geometry.attributes.uv, indices=geometry.index.array, copies=[], lookup=new Map();
  for(let t=0;t<indices.length;t+=3) {
    const anchor=uv.getX(indices[t]);
    for(let k=1;k<3;k++) {
      const original=indices[t+k], shift=Math.round(uv.getX(original)-anchor);
      if(!shift)continue;
      const key=original+','+shift;
      let index=lookup.get(key);
      if(index===undefined){index=uv.count+copies.length;lookup.set(key,index);copies.push({original,shift});}
      indices[t+k]=index;
    }
  }
  if(!copies.length)return;
  for(const [name,attr] of Object.entries(geometry.attributes)){
    const size=attr.itemSize,values=new Float32Array((attr.count+copies.length)*size);
    values.set(attr.array);
    copies.forEach(({original,shift},i)=>{
      const start=(attr.count+i)*size;
      values.set(attr.array.subarray(original*size,(original+1)*size),start);
      if(name==='uv')values[start]-=shift;
    });
    geometry.setAttribute(name,new THREE.BufferAttribute(values,size));
  }
}
