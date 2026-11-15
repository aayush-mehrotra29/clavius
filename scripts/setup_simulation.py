"""Fetch content-pinned NASA simulation assets; never substitute synthetic data."""
from pathlib import Path
from urllib.request import urlretrieve
from concurrent.futures import ThreadPoolExecutor
import argparse,hashlib,json,sys
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--diviner',action='store_true',help='Also prepare the optional historical Diviner context (~410 MB).');parser.add_argument('--observed-shadows',action='store_true',help='Also fetch the optional pinned NAC validation images, renderings and acquisition labels (~153 MB).');args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'public/data/simulation-manifest.json').read_text())
def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  while chunk:=f.read(1024*1024):h.update(chunk)
 return h.hexdigest()
def fetch(task):
 asset,directory=task;directory.mkdir(parents=True,exist_ok=True);path=directory/asset['file']
 if not path.exists() or digest(path)!=asset['sha256']:
  temporary=path.with_suffix(path.suffix+'.part');urlretrieve(asset['url'],temporary)
  if digest(temporary)!=asset['sha256']:raise ValueError(f'NASA source checksum mismatch: {asset["file"]}. No altered data accepted.')
  temporary.replace(path)
 print('Verified',asset['file'],flush=True)
tasks=[(a,root/'data/raw') for a in manifest['terrain']['assets']]+[(a,root/'data/kernels') for a in manifest['kernels']['assets']]
if manifest['terrain'].get('documentation'):tasks.append((manifest['terrain']['documentation'],root/'data/raw'))
if args.diviner:tasks.extend((a,root/'data/raw/diviner') for a in manifest['diviner']['assets'])
with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(fetch,tasks))
(root/'data/kernels/manifest.json').write_text(json.dumps(manifest['kernels'],indent=2)+'\n')
sys.path.insert(0,str(root/'backend'))
from clavius.terrain import prepare_manifest,catalogue
for entry in catalogue():prepare_manifest(entry['id'])
sys.path.insert(0,str(root/'scripts'))
from derive_lola_support import derive as derive_support
derive_support()
if args.diviner:
 from clavius.diviner import derive,selected_specification
 spec=manifest['diviner']
 for key in ['connecting-ridge',*spec.get('additional_derivatives',{})]:
  selected=selected_specification(spec,key);print(derive(selected,root/'data/raw/diviner',root/'public'/selected['derivative']['file']))
if args.observed_shadows:
 from validate_observed_shadows import verify_assets
 verify_assets(manifest['observed_shadow_validation'],fetch=True)
print('Simulation sources are prepared. Run npm run dev:simulation.')
