"""Create source-pinned, nearest-cell display textures from NASA LDEC counts."""
import argparse,hashlib,json,struct,sys,zlib
from pathlib import Path
import numpy as np
import rasterio
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from clavius.integrity import verify_sources
COLORS={'returns':[173,203,151],'interpolated':[148,154,159],'unknown':[193,147,88]}
def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body)&0xffffffff)
def png(colors):
 height,width,_=colors.shape;rows=b''.join(b'\0'+row.tobytes() for row in colors)
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b'')
def derive(write_manifest=False):
 path=ROOT/'public/data/simulation-manifest.json';manifest=json.loads(path.read_text());outputs={}
 for entry in manifest['sites']:
  asset=verify_sources('terrain',[entry['count_asset_id']])['assets'][0]
  with rasterio.open(ROOT/'data/raw'/asset['file']) as source:counts=source.read(1)
  rgb=np.empty((*counts.shape,3),dtype=np.uint8);rgb[:]=COLORS['unknown'];rgb[np.isfinite(counts)&(counts==0)]=COLORS['interpolated'];rgb[np.isfinite(counts)&(counts>0)]=COLORS['returns']
  raw=png(rgb);identity=hashlib.sha256(raw).hexdigest();filename='data/lola-support/'+entry['id']+'.png';target=ROOT/'public'/filename
  prior=manifest['terrain'].get('support_derivatives',{}).get(entry['id'])
  if prior and not write_manifest and identity!=prior['sha256']:raise ValueError('Support image differs from the pinned derivative. Review source/script/compressor changes before updating the manifest.')
  target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
  outputs[entry['id']]={'file':filename,'url':'/'+filename,'sha256':identity,'bytes':len(raw),'width':counts.shape[1],'height':counts.shape[0],'source_asset_id':asset['id'],'source_sha256':asset['sha256'],'colors_srgb8':COLORS,'script':'scripts/derive_lola_support.py','encoding':'RGB8 PNG, filter 0, zlib level 9; north-to-south native row order','registration':'One image pixel per native nominal LDEC cell. Map via source south-polar stereographic coordinates; nearest filtering, no mipmaps.','limit':'A nominal-cell return-support display, not a terrain safety or wheel-scale coverage map.'}
 if write_manifest:
  manifest['terrain']['support_derivatives']=outputs;path.write_text(json.dumps(manifest,indent=2)+'\n')
 return outputs
if __name__=='__main__':
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write-manifest',action='store_true');args=parser.parse_args()
 print(json.dumps(derive(args.write_manifest),indent=2))
