"""Content identity for numerical implementations in this non-Git checkout."""
import hashlib
from functools import lru_cache
from importlib.metadata import version
from pathlib import Path
from .paths import RUNTIME,ROOT
@lru_cache(maxsize=1)
def implementation():
 paths=sorted(Path(__file__).parent.glob('*.py'))
 h=hashlib.sha256()
 for p in paths:h.update(p.name.encode());h.update(p.read_bytes())
 identity=h.hexdigest();snapshot=RUNTIME/'implementations'/identity/'clavius';snapshot.mkdir(parents=True,exist_ok=True)
 for p in paths:
  target=snapshot/p.name
  if not target.exists():target.write_bytes(p.read_bytes())
 requirement=ROOT/'requirements-simulation.txt'
 if requirement.exists():(snapshot.parent/'requirements-simulation.txt').write_bytes(requirement.read_bytes())
 from . import store
 store.persist_directory(snapshot.parent)
 return {'source_sha256':identity,'libraries':{name:version(name) for name in ['numpy','scipy','rasterio','spiceypy','mujoco']},'utc_assumption':'Future UTC conversion uses the pinned naif0012 LSK; no future leap seconds beyond its announcements are assumed.'}
