"""Pinned DE421 solar/Earth geometry with a shared elapsed-SI-seconds clock."""
import json,threading
import re
from functools import lru_cache
import numpy as np
import spiceypy as spice
from .paths import DATA
from .terrain import R,DEG,basis,latlon_body
_lock=threading.RLock();_loaded=False

def load_kernels():
 global _loaded
 with _lock:
  if not _loaded:
   from .integrity import verify_sources
   manifest=verify_sources('kernels')
   for asset in manifest['assets']:spice.furnsh(str(DATA/'kernels'/asset['file']))
   _loaded=True

def epoch(utc):
 load_kernels()
 with _lock:return float(spice.str2et(utc))

def utc_from_et(et):
 load_kernels()
 with _lock:return spice.et2utc(float(et),'ISOC',3)+'Z'

@lru_cache(maxsize=1)
def leap_ends():
 """Known positive leap-second ends from the pinned leap-second kernel."""
 text=(DATA/'kernels/naif0012.tls').read_text()
 dates=re.findall(r'@([0-9]{4}-[A-Z]{3}-[0-9]{1,2})',text.split('DELTET/DELTA_AT')[-1])
 return tuple(epoch(date+' 00:00:00 UTC') for date in dates[1:])

def utc_clock_boundaries(start,duration):
 return [value-start for end in leap_ends() for value in [end-1,end] if start<value<start+duration]

def directions(et,lat,lon,elevation_m):
 load_kernels();observer=latlon_body(lat,lon,R+elevation_m)/1000;rotation=basis(lat,lon)
 result={}
 with _lock:
  for name,target,radius in [('sun','SUN',695700),('earth','EARTH',6378.137)]:
   center,_=spice.spkpos(target,float(et),'MOON_ME_DE421','NONE','MOON')
   delta=np.asarray(center)-observer;distance=np.linalg.norm(delta);unit=delta/distance;local=unit@rotation
   result[name]={'enu':local.tolist(),'azimuth_deg':float(np.mod(np.arctan2(local[0],local[1])/DEG,360)),'elevation_deg':float(np.arcsin(local[2])/DEG),'angular_radius_deg':float(np.arcsin(radius/distance)/DEG),'distance_km':float(distance)}
 result['earth_light_time_s']=result['earth']['distance_km']/299792.458
 return result

def horizon_elevation(profile,azimuth_deg):
 values=np.asarray(profile['elevations_deg']);u=(azimuth_deg%360)/profile['azimuth_step_deg'];i=int(np.floor(u));f=u-i
 return float(values[i%len(values)]*(1-f)+values[(i+1)%len(values)]*f)

def solar_disk_fraction(elevation_deg,horizon_deg,radius_deg):
 """Uniform-brightness circular disk cut by a locally straight horizon."""
 x=(elevation_deg-horizon_deg)/radius_deg
 if x>=1:return 1.
 if x<=-1:return 0.
 return float((np.arccos(-x)+x*np.sqrt(1-x*x))/np.pi)

def visibility(geometry,profile):
 sun=geometry['sun'];earth=geometry['earth']
 sh=horizon_elevation(profile,sun['azimuth_deg']);eh=horizon_elevation(profile,earth['azimuth_deg'])
 return {'solar_visible_fraction':solar_disk_fraction(sun['elevation_deg'],sh,sun['angular_radius_deg']),'sun_horizon_deg':sh,'earth_center_visible':earth['elevation_deg']>eh,'earth_horizon_deg':eh}
