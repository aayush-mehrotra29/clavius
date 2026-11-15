"""Check cached scientific inputs against the tracked content-pinned source record."""
import hashlib,json,threading
from .paths import ROOT,DATA

_lock=threading.RLock()
_verified={}

def verify_sources(group,asset_ids=None):
 manifest=json.loads((ROOT/'public/data/simulation-manifest.json').read_text())
 if group=='terrain':
  from .terrain import scientific_manifest
  manifest=scientific_manifest()
 if group=='diviner':
  from .diviner import specification
  manifest={'diviner':specification()}
 directory=DATA/{'terrain':'raw','kernels':'kernels','diviner':'raw/diviner'}[group]
 selected=dict(manifest[group])
 if asset_ids is not None:
  selected['assets']=[a for a in selected['assets'] if a['id'] in asset_ids]
  if {a['id'] for a in selected['assets']}!=set(asset_ids):raise ValueError('Unknown required scientific asset identity.')
 with _lock:
  for asset in selected['assets']:
   path=directory/asset['file']
   if not path.is_file():raise ValueError(f'Missing scientific input: {asset["file"]}. Run scripts/setup_simulation.py.')
   stat=path.stat();fingerprint=(stat.st_size,stat.st_mtime_ns,asset['sha256'])
   if _verified.get(str(path))==fingerprint:continue
   h=hashlib.sha256()
   with path.open('rb') as source:
    while chunk:=source.read(1024*1024):h.update(chunk)
   if h.hexdigest()!=asset['sha256']:raise ValueError(f'Scientific input checksum mismatch: {asset["file"]}. No altered data accepted.')
   _verified[str(path)]=fingerprint
 return selected
