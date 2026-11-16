import * as T from 'three';

// Display finishes sit on the existing hypothetical R1 visual primitives.
function painted(width,height,draw){
  const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  const ctx=canvas.getContext('2d');draw(ctx,width,height);
  const texture=new T.CanvasTexture(canvas);texture.colorSpace=T.SRGBColorSpace;texture.anisotropy=4;
  return new T.MeshStandardMaterial({map:texture,roughness:.68,metalness:.16});
}

export function finishReferenceRover(group,model){
  const deck=painted(768,512,(c,w,h)=>{
    c.fillStyle='#b2b2b2';c.fillRect(0,0,w,h);
    c.fillStyle='#242628';c.fillRect(38,30,w-76,h-100);
    for(let j=0;j<5;j++)for(let i=0;i<8;i++){
      const x=45+i*85,y=37+j*80;
      c.fillStyle='#44484a';c.fillRect(x,y,80,74);
      c.fillStyle='#606467';for(let k=1;k<12;k++)c.fillRect(x+3,y+6*k,74,1);
    }
    c.fillStyle='#242424';c.font='600 22px sans-serif';c.fillText('CLAVIUS   R1',40,h-27);
    for(const x of [13,w-13])for(const y of [13,h-13]){
      c.fillStyle='#656565';c.beginPath();c.arc(x,y,4,0,2*Math.PI);c.fill();
    }
  });
  const body=painted(512,160,(c,w,h)=>{
    const finish=c.createLinearGradient(0,0,0,h);finish.addColorStop(0,'#bababa');finish.addColorStop(.78,'#989898');finish.addColorStop(1,'#777');
    c.fillStyle=finish;c.fillRect(0,0,w,h);c.strokeStyle='#767676';c.strokeRect(12,12,w-24,h-24);
    for(let i=0;i<12;i++){c.fillStyle='#65686a';c.fillRect(310+11*i,36,4,78);}
    c.fillStyle='#323232';c.font='600 20px sans-serif';c.fillText('R1',29,h-30);
  });
  const rim=painted(256,256,(c,w,h)=>{
    const grad=c.createRadialGradient(128,128,8,128,128,127);
    for(const [offset,color] of [[0,'#797979'],[.18,'#a2a2a2'],[.20,'#454545'],[.65,'#6a6a6a'],[.70,'#888888'],[.74,'#373737'],[.98,'#343434'],[1,'#6b6b6b']])grad.addColorStop(offset,color);
    c.fillStyle=grad;c.fillRect(0,0,w,h);
    c.translate(128,128);for(let i=0;i<12;i++){
      c.rotate(Math.PI/6);c.fillStyle='#353535';c.beginPath();c.ellipse(0,58,7,17,0,0,2*Math.PI);c.fill();
    }
  });
  const tread=painted(512,96,(c,w,h)=>{
    c.fillStyle='#343434';c.fillRect(0,0,w,h);
    for(let i=-1;i<33;i++){c.strokeStyle='#696969';c.lineWidth=3;c.beginPath();c.moveTo(i*16,0);c.lineTo(i*16+7,h/2);c.lineTo(i*16,h);c.stroke();}
  });
  const old=new Set();
  group.traverse(node=>{
    if(!node.isMesh)return;
    if(node.geometry.type==='BoxGeometry'){old.add(node.material);node.material=[body,body,body,body,deck,body];}
    if(node.geometry.type==='CylinderGeometry'){old.add(node.material);node.material=[tread,rim,rim];}
  });
  old.forEach(m=>m.dispose());
  // Connect the four rigid wheel locations to the authored chassis visually.
  const brace=new T.MeshStandardMaterial({color:0x555658,metalness:.45,roughness:.6});
  for(const link of model.links.filter(l=>l.name.endsWith('_wheel'))){
    const [x,y,z]=link.zero_pose_matrix.slice(0,3).map(row=>row[3]);
    const hub=new T.Vector3(x,y,z),mount=new T.Vector3(x*.82,y*.66,.32);
    const axis=mount.clone().sub(hub);
    const strut=new T.Mesh(new T.CylinderGeometry(.028,.033,axis.length(),12),brace);
    strut.position.copy(hub).lerp(mount,.5);strut.quaternion.setFromUnitVectors(new T.Vector3(0,1,0),axis.normalize());
    strut.castShadow=true;group.add(strut);
  }
}
