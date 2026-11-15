from pathlib import Path
from urllib.request import urlretrieve
from concurrent.futures import ThreadPoolExecutor
import hashlib,json
root=Path(__file__).resolve().parents[1]/'data/kernels'
sources={
'de421.bsp':'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/a_old_versions/de421.bsp',
'moon_pa_de421_1900-2050.bpc':'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/moon_pa_de421_1900-2050.bpc',
'moon_080317.tf':'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_080317.tf',
'naif0012.tls':'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/naif0012.tls',
'pck00011.tpc':'https://naif.jpl.nasa.gov/pub/naif/generic_kernels/pck/pck00011.tpc'}
def fetch(item):
 name,url=item;p=root/name
 if not p.exists():urlretrieve(url,p)
 return {'file':name,'url':url,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
root.mkdir(parents=True,exist_ok=True)
with ThreadPoolExecutor(max_workers=3) as executor: assets=list(executor.map(fetch,sources.items()))
(root/'manifest.json').write_text(json.dumps({'frame':'MOON_ME_DE421','ephemeris':'DE421','assets':assets},indent=2)+'\n')
print(json.dumps(assets,indent=2))
