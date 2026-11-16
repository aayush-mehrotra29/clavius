"""Prepare pinned inputs without regenerating the public display derivatives."""
import subprocess,sys,hashlib,json
from concurrent.futures import ThreadPoolExecutor
from urllib.request import urlretrieve
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(ROOT/'scripts/setup_simulation.py'),'--skip-support-derivatives'],check=True)

# Verify original Diviner context sources without deriving or replacing the
# already-pinned, site-specific public clips on a different platform.
manifest=json.loads((ROOT/'public/data/simulation-manifest.json').read_text())
directory=ROOT/'data/raw/diviner';directory.mkdir(parents=True,exist_ok=True)
def prepare(asset):
 path=directory/asset['file']
 def digest():
  h=hashlib.sha256()
  with path.open('rb') as source:
   while chunk:=source.read(1024*1024):h.update(chunk)
  return h.hexdigest()
 if not path.is_file() or digest()!=asset['sha256']:
  temporary=path.with_suffix(path.suffix+'.part');urlretrieve(asset['url'],temporary);temporary.replace(path)
 if digest()!=asset['sha256']:raise ValueError('Diviner source hash mismatch: '+asset['file'])
 print('Verified',asset['file'],flush=True)
with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(prepare,manifest['diviner']['assets']))
