"""NASA polar stereographic elevations normalized to local east/north/up metres."""
import hashlib,json,math,os
from functools import lru_cache
from pathlib import Path
import numpy as np
import rasterio
from scipy.ndimage import map_coordinates
from typing import Literal
from .paths import DATA,ROOT
SiteId=Literal['connecting-ridge','shackleton-rim']
TerrainRealization=Literal['nominal','pgda78-0001','pgda78-0002','pgda78-0003']
R=1737400.
DEG=np.pi/180
class TerrainCoverageError(ValueError):pass

def latlon_body(lat,lon,radius=R):
 lat,lon=np.asarray(lat)*DEG,np.asarray(lon)*DEG
 return np.stack(np.broadcast_arrays(radius*np.cos(lat)*np.cos(lon),radius*np.cos(lat)*np.sin(lon),radius*np.sin(lat)),axis=-1)

def body_latlon(p):
 p=np.asarray(p);return np.arctan2(p[...,2],np.hypot(p[...,0],p[...,1]))/DEG,np.arctan2(p[...,1],p[...,0])/DEG

def stereographic(lat,lon):
 lat,lon=np.asarray(lat)*DEG,np.asarray(lon)*DEG;rho=2*R*np.tan((np.pi/2+lat)/2)
 return rho*np.sin(lon),rho*np.cos(lon)

def basis(lat,lon):
 lat,lon=lat*DEG,lon*DEG
 return np.array([[-np.sin(lon),-np.sin(lat)*np.cos(lon),np.cos(lat)*np.cos(lon)], [np.cos(lon),-np.sin(lat)*np.sin(lon),np.cos(lat)*np.sin(lon)],[0,np.cos(lat),np.sin(lat)]])

class Raster:
 def __init__(self,path):
  with rasterio.open(path) as d:
   self.values=d.read(1).astype(np.float32);self.transform=d.transform;self.path=path
   self.width=d.width;self.height=d.height;self.crs=d.crs.to_wkt();self.projection=d.crs.to_dict();self.pixel_m=abs(d.transform.a)
 def sample(self,x,y):
  col=(np.asarray(x)-self.transform.c)/self.transform.a-.5;row=(np.asarray(y)-self.transform.f)/self.transform.e-.5
  col,row=np.broadcast_arrays(col,row);shape=col.shape
  valid=(col>=0)&(row>=0)&(col<=self.width-1)&(row<=self.height-1)
  sampled=map_coordinates(self.values,np.stack([row.ravel(),col.ravel()]),order=1,mode='nearest',prefilter=False).reshape(shape)
  return np.where(valid,sampled,np.nan).astype(np.float64)

 def contains(self,x,y):
  col=(np.asarray(x)-self.transform.c)/self.transform.a-.5;row=(np.asarray(y)-self.transform.f)/self.transform.e-.5
  return (col>=0)&(row>=0)&(col<=self.width-1)&(row<=self.height-1)
 def native_cell(self,x,y):
  col,row=np.broadcast_arrays((np.asarray(x)-self.transform.c)/self.transform.a,(np.asarray(y)-self.transform.f)/self.transform.e)
  valid=np.isfinite(col)&np.isfinite(row)&(col>=0)&(row>=0)&(col<self.width)&(row<self.height)
  i=np.clip(np.nan_to_num(col,nan=0,posinf=0,neginf=0).astype(int),0,self.width-1);j=np.clip(np.nan_to_num(row,nan=0,posinf=0,neginf=0).astype(int),0,self.height-1)
  return np.where(valid,self.values[j,i],np.nan)

def aligned(reference,candidate):
 # Native WKT labels differ (unnamed vs unknown); numerical CRS parameters agree.
 return reference.projection==candidate.projection and reference.transform==candidate.transform and (reference.width,reference.height)==(candidate.width,candidate.height)

def horizon_distances(local,regional,near_step_m=5,refinement=1):
 """Keep native local posting over the whole curated terrain footprint.

 The previous 1 km switch to 80 m steps skipped narrow ridges within the
 5 m sites. Their projected diagonal, padded by 1% and rounded up to a km,
 conservatively spans these small south-polar patches from any local point.
 In the first km sample local interpolation at <=1/8 native posting: near
 an observer, sub-cell peak position strongly affects angular elevation.
 Keep the original regional/far lattice as well. Interpolated samples do
 not create new measured terrain detail or resolve sub-grid hazards.
 """
 if near_step_m<=0 or refinement<1:raise ValueError('Horizon sampling steps must be positive and refinement at least one.')
 native=min(80.,float(local.pixel_m));limit=16000.;near=near_step_m
 if local.pixel_m<regional.pixel_m:
  limit=min(220000.,max(limit,math.ceil(math.hypot(local.width,local.height)*local.pixel_m*1.01/1000)*1000.))
  near=min(near,native/8)
 return np.unique(np.r_[np.arange(5,1000,near/refinement),np.arange(1000,limit,native/refinement),np.arange(1000,16000,80/refinement),np.geomspace(16000,220000,130*refinement)])

def realization_catalogue(entry):
 assets={a['id']:a for a in scientific_manifest()['terrain']['assets']}
 captured=scientific_manifest().get('site_manifests',{}).get(entry['id'],{})
 for record in captured.get('realization_catalogue',[]):assets[record['asset']['id']]=record['asset']
 return [{**r,'asset':assets[r['asset_id']]} for r in entry.get('terrain_realizations',[]) if r['asset_id'] in assets]

def scientific_manifest():
 path=Path(os.environ.get('CLAVIUS_TERRAIN_MANIFEST_PATH',str(ROOT/'public/data/simulation-manifest.json')))
 return json.loads(path.read_text())

def catalogue():return scientific_manifest()['sites']
def definition(identity):
 result=next((d for d in catalogue() if d['id']==identity),None)
 if result is None:raise TerrainCoverageError('Unknown scientific simulation site: '+identity)
 return result

def dependencies(entry):return [entry[key] for key in ['local_asset_id','error_asset_id','regional_asset_id','roi_asset_id','count_asset_id'] if key in entry]

@lru_cache(maxsize=12)
def cached_raster(filename,sha256):return Raster(DATA/'raw'/filename)

class Site:
 def __init__(self,identity='connecting-ridge',realization='nominal'):
  from .integrity import verify_sources
  entry=definition(identity);source=verify_sources('terrain',dependencies(entry));assets={a['id']:a for a in source['assets']}
  self.definition=entry;self.id=identity;self.name=entry['name'];self.lat=entry['latitude_deg'];self.lon=entry['longitude_deg'];self.source_id=entry['source_id']
  load=lambda key:cached_raster(assets[entry[key]]['file'],assets[entry[key]]['sha256'])
  self.local=load('local_asset_id');self.nominal=self.local;self.error=load('error_asset_id');self.regional=load('regional_asset_id');self.counts=load('count_asset_id') if 'count_asset_id' in entry else None
  if self.counts is not None and not aligned(self.nominal,self.counts):raise TerrainCoverageError('LOLA count grid differs from the nominal native grid.')
  self.rotation=basis(self.lat,self.lon)
  x,y=stereographic(self.lat,self.lon);height=float(self.local.sample(x,y))
  if not math.isfinite(height):raise TerrainCoverageError('Selected site origin has no finite source elevation.')
  self.origin=latlon_body(self.lat,self.lon,R+height);self.origin_height_m=height
  captured=scientific_manifest().get('site_manifests',{}).get(identity)
  path=DATA/'sites'/entry['manifest_file']
  self.manifest=captured or (json.loads(path.read_text()) if path.is_file() else {})
  if self.manifest.get('site_id')!=identity:raise TerrainCoverageError('Prepare the normalized site manifest before simulation.')
  required={a['id']:a['sha256'] for a in source['assets']}
  if self.manifest.get('definition')!=entry or {a['id']:a['sha256'] for a in self.manifest['assets'] if a['id'] in required}!=required:raise TerrainCoverageError('Normalized site definition or source identities differ. Prepare the site manifest again.')
  self.realization_id=realization;registry=realization_catalogue(entry);active_assets=list(source['assets'])
  descriptor={'id':'nominal','source_class':'nominal_lola_surface','value_convention':'Published nominal elevation surface.'}
  if realization!='nominal':
   record=next((r for r in registry if r['id']==realization),None)
   if record is None:raise TerrainCoverageError('No pinned terrain realization for this site: '+realization)
   selected=verify_sources('terrain',[record['asset_id']])['assets'][0];clone=cached_raster(selected['file'],selected['sha256'])
   if not aligned(self.nominal,clone):raise TerrainCoverageError('Terrain realization projection or pixel registration differs from its nominal source.')
   self.local=clone;active_assets.append(selected)
   descriptor={**record,'source_class':'published_statistical_terrain_realization','value_convention':'Complete cloned height surface used directly, not an additive offset.'}
  self.manifest={**self.manifest,'assets':active_assets,'realization':descriptor,'realization_catalogue':registry,'analysis_origin':{'latitude_deg':self.lat,'longitude_deg':self.lon,'nominal_elevation_m':self.origin_height_m,'policy':'Fixed nominal origin and local ENU basis for all realizations; cloned ground height is not recentered.'},'regional_uncertainty':'PGDA90 remains nominal; no regional error realization is applied.'}

 def location(self,east,north):
  e,n=np.broadcast_arrays(np.asarray(east),np.asarray(north));local=np.stack([e,n,np.zeros_like(e)],axis=-1)
  trial=self.origin+local@self.rotation.T;lat,lon=body_latlon(trial);return lat,lon
 def sample(self,east,north,allow_regional=False):
  lat,lon=self.location(east,north);x,y=stereographic(lat,lon);height=self.local.sample(x,y)
  nominal_supported=np.isfinite(self.nominal.sample(x,y));height=np.where(nominal_supported,height,np.nan)
  if allow_regional:height=np.where(np.isfinite(height),height,self.regional.sample(x,y))
  world=latlon_body(lat,lon,R+height);local=(world-self.origin)@self.rotation
  error=self.error.sample(x,y)
  return {'east_m':np.asarray(east),'north_m':np.asarray(north),'up_m':local[...,2],'elevation_m':height,'lat_deg':lat,'lon_deg':np.mod(lon,360),'height_rms_m':error,'covered':np.isfinite(height),'nominal_height_supported':nominal_supported,'height_uncertainty_supported':np.isfinite(error),'nominal_lola_return_count':self.counts.native_cell(x,y) if self.counts is not None else np.full(np.shape(height),np.nan)}
 def height(self,e,n):
  result=self.sample(e,n)
  if not np.isfinite(result['up_m']).all():raise TerrainCoverageError('Route leaves the supported local surface coverage.')
  return result['up_m']
 def slope(self,e,n):
  dx=(self.height(np.asarray(e)+5,n)-self.height(np.asarray(e)-5,n))/10
  dy=(self.height(e,np.asarray(n)+5)-self.height(e,np.asarray(n)-5))/10
  return np.arctan(np.hypot(dx,dy))/DEG
 def patch(self,e=0,n=0,size=640,spacing=5):
  axis=np.linspace(-size/2,size/2,int(size/spacing)+1);xx,yy=np.meshgrid(axis+e,axis+n)
  result=self.sample(xx,yy);heights=result['up_m']
  if not np.isfinite(heights).all():raise TerrainCoverageError('The requested patch includes terrain without local data.')
  support=scientific_manifest()['terrain'].get('support_derivatives',{}).get(self.id)
  count_asset=next((a for a in self.manifest['assets'] if a['id']==self.definition.get('count_asset_id')),None)
  uv=None
  if support and count_asset and support['source_sha256']==count_asset['sha256']:
   x,y=stereographic(result['lat_deg'],result['lon_deg']);u=(x-self.counts.transform.c)/self.counts.transform.a/self.counts.width;v=1-(y-self.counts.transform.f)/self.counts.transform.e/self.counts.height
   uv=np.round(np.stack([u,v],axis=-1),10).ravel().tolist()
  else:support=None
  north_gradient,east_gradient=np.gradient(heights,spacing)
  slopes=np.arctan(np.hypot(east_gradient,north_gradient))/DEG
  return {'site_id':self.id,'width':len(axis),'height':len(axis),'spacing_m':spacing,'west_m':float(axis[0]+e),'south_m':float(axis[0]+n),'heights_m':np.round(heights,4).ravel().tolist(),'slopes_deg':np.round(slopes,3).ravel().tolist(),'height_rms_m':np.round(result['height_rms_m'],3).ravel().tolist(),'origin_lat_deg':self.lat,'origin_lon_deg':self.lon,'origin_elevation_m':self.origin_height_m,'frame':'ENU','native_resolution_m':5,'source_id':self.source_id,'height_range_m':[float(heights.min()),float(heights.max())],'slope_method':'finite differences at 5 m posting; not rover-scale hazard slopes','nominal_support_display':support,'nominal_support_uv':uv,'count_asset_sha256':count_asset['sha256'] if count_asset else None,'surface_asset_sha256':next(a['sha256'] for a in self.manifest['assets'] if a['id']==(self.manifest['realization'].get('asset_id') or self.definition['local_asset_id'])),'nominal_origin_asset_sha256':next(a['sha256'] for a in self.manifest['assets'] if a['id']==self.definition['local_asset_id']),'terrain_realization':self.manifest['realization'],'analysis_origin':self.manifest['analysis_origin'],'nominal_lola_return_counts':[float(v) if np.isfinite(v) else None for v in result['nominal_lola_return_count'].ravel()],'nominal_height_supported':result['nominal_height_supported'].ravel().tolist(),'height_uncertainty_supported':result['height_uncertainty_supported'].ravel().tolist(),'support_policy':'Counts are sampled from the containing native nominal cell, never bilinearly averaged. Zero means interpolated; positive means the cell contains LOLA returns; missing count evidence is null.'}
 def local_horizon_sample(self,x,y):
  near=self.local.sample(x,y)
  if self.realization_id!='nominal':
   required=self.nominal.contains(x,y)
   if np.any(required&(~np.isfinite(near)|~np.isfinite(self.nominal.sample(x,y)))):raise TerrainCoverageError('A horizon ray crosses missing local realization support; nominal terrain cannot fill that uncertainty case.')
  return near
 def horizon_directions(self,e,n,azimuths_deg,observer_height=.5,near_step_m=5,refinement=1):
  """Trace exactly the requested azimuths at the actual observer position."""
  point=self.sample(e,n)
  if not point['covered']:raise TerrainCoverageError('Observer is outside local terrain coverage.')
  lat,lon=float(point['lat_deg']),float(point['lon_deg']);rot=basis(lat,lon)
  obs=latlon_body(lat,lon,R+float(point['elevation_m'])+observer_height)
  az=np.asarray(azimuths_deg)*DEG
  distances=horizon_distances(self.local,self.regional,near_step_m,refinement)
  east=np.sin(az)[:,None]*distances;north=np.cos(az)[:,None]*distances
  rays=obs+np.stack([east,north,np.zeros_like(east)],axis=-1)@rot.T
  llat,llon=body_latlon(rays);x,y=stereographic(llat,llon)
  near=self.local_horizon_sample(x,y);height=np.where(np.isfinite(near),near,self.regional.sample(x,y))
  if not np.isfinite(height).all():raise TerrainCoverageError('A horizon ray crosses missing regional terrain.')
  delta=(latlon_body(llat,llon,R+height)-obs)@rot
  return np.max(np.arctan2(delta[...,2],np.hypot(delta[...,0],delta[...,1]))/DEG,axis=1)
 def horizons(self,e,n,observer_height=0.5,azimuth_step_deg=2):
  """Terrain horizon with near 5 m data and far 80 m context, including curvature."""
  point=self.sample(e,n)
  if not point['covered']:raise TerrainCoverageError('Observer is outside local data coverage.')
  lat,lon=float(point['lat_deg']),float(point['lon_deg']);rot=basis(lat,lon)
  obs=latlon_body(lat,lon,R+float(point['elevation_m'])+observer_height)
  az=np.arange(0,360,azimuth_step_deg)*DEG
  distances=horizon_distances(self.local,self.regional)
  east=np.sin(az)[:,None]*distances;north=np.cos(az)[:,None]*distances
  tangent=np.stack([east,north,np.zeros_like(east)],axis=-1)
  rays=obs+tangent@rot.T;llat,llon=body_latlon(rays);x,y=stereographic(llat,llon)
  near=self.local_horizon_sample(x,y);far=self.regional.sample(x,y);h=np.where(np.isfinite(near),near,far)
  if not np.isfinite(h).all():raise TerrainCoverageError('Regional horizon ray crosses missing data; visibility cannot be asserted.')
  world=latlon_body(llat,llon,R+h);local=(world-obs)@rot
  elevation=np.arctan2(local[...,2],np.hypot(local[...,0],local[...,1]))/DEG
  return {'azimuth_step_deg':azimuth_step_deg,'elevations_deg':np.max(elevation,axis=1).tolist(),'max_distance_m':220000,'observer_height_m':observer_height,'method':'finite terrain rays, native local posting over the curated footprint and 80 m regional context, sampled azimuth grid'}

@lru_cache(maxsize=8)
def _site(identity,realization,identity_key):return Site(identity,realization)

def site(identity='connecting-ridge',realization='nominal'):
 from .integrity import verify_sources
 entry=definition(identity);required=dependencies(entry)
 if realization!='nominal':
  record=next((r for r in entry.get('terrain_realizations',[]) if r['id']==realization),None)
  if record is None:raise TerrainCoverageError('Unknown terrain realization: '+realization)
  required=[*required,record['asset_id']]
 verified=verify_sources('terrain',required)
 identity_key=json.dumps({'definition':entry,'assets':verified['assets'],'captured':scientific_manifest().get('site_manifests',{}).get(identity)},sort_keys=True)
 return _site(identity,realization,identity_key)

def roi_origin(archive_path,record):
 """Read the published X/Y anchor attributes without extracting an archive."""
 import tarfile,struct
 with tarfile.open(archive_path) as archive:
  member=next(m for m in archive.getmembers() if m.name.endswith('.dbf'));raw=archive.extractfile(member).read()
 count=struct.unpack('<I',raw[4:8])[0];header,length=struct.unpack('<HH',raw[8:12]);fields=[];offset=32
 while raw[offset]!=13:
  item=raw[offset:offset+32];fields.append((item[:11].split(b'\0')[0].decode(),item[16]));offset+=32
 if not 1<=record<=count:raise ValueError('Unknown ROI anchor record.')
 data=raw[header+(record-1)*length:header+record*length]
 if data[:1]!=b' ':raise ValueError('Selected ROI anchor is deleted.')
 values={};offset=1
 for name,size in fields:values[name]=float(data[offset:offset+size]);offset+=size
 return values['X'],values['Y']

def prepare_manifest(identity='connecting-ridge'):
 from .integrity import verify_sources
 entry=definition(identity);group=verify_sources('terrain',dependencies(entry));assets=group['assets'];lookup={a['id']:a for a in assets}
 local=cached_raster(lookup[entry['local_asset_id']]['file'],lookup[entry['local_asset_id']]['sha256']);regional=cached_raster(lookup[entry['regional_asset_id']]['file'],lookup[entry['regional_asset_id']]['sha256'])
 for key in ['local_asset_id','error_asset_id']:
  with rasterio.open(DATA/'raw'/lookup[entry[key]]['file']) as source:
   crs=source.crs.to_dict()
   if crs.get('proj')!='stere' or float(crs.get('lat_0',0))!=-90 or float(crs.get('R',crs.get('a',0)))!=R or abs(source.transform.a)!=5 or abs(source.transform.e)!=5:raise ValueError('Source projection/radius/posting differs from the supported lunar site format.')
   if source.nodata is None or not np.isnan(source.nodata):raise ValueError('Expected native NaN coverage mask.')
 origin_check=None
 if entry.get('roi_asset_id'):
  selected=entry['origin_selection'];x,y=roi_origin(DATA/'raw'/lookup[entry['roi_asset_id']]['file'],selected['record']);expected=stereographic(entry['latitude_deg'],entry['longitude_deg'])
  if np.linalg.norm(np.array([x,y])-expected)>1e-5:raise ValueError('Site origin differs from its published ROI anchor.')
  col=(x-local.transform.c)/local.transform.a-.5;row=(y-local.transform.f)/local.transform.e-.5
  if abs(col-round(col))+abs(row-round(row))>1e-6:raise ValueError('ROI anchor is not a native pixel center.')
  origin_check={'roi_record':selected['record'],'source_x_m':x,'source_y_m':y,'pixel_column':round(col),'pixel_row':round(row),'conversion_residual_m':float(np.linalg.norm(np.array([x,y])-expected))}
 if identity=='connecting-ridge':points=[(-89.44,222.8),(-89.45,222.8),(-89.44,223.2),(-89.43,222.5),(-89.46,222.7)]
 else:
  x,y=stereographic(entry['latitude_deg'],entry['longitude_deg']);points=[]
  for dx,dy in [(0,0),(-200,0),(200,0),(0,-200),(0,200)]:
   px,py=x+dx,y+dy;points.append((float((2*np.arctan(np.hypot(px,py)/(2*R))-np.pi/2)/DEG),float(np.arctan2(px,py)/DEG%360)))
 checks=[]
 for lat,lon in points:
  x,y=stereographic(lat,lon);a=float(local.sample(x,y));b=float(regional.sample(x,y))
  if not math.isfinite(a) or not math.isfinite(b):raise ValueError('Vertical convention check crosses missing data.')
  checks.append({'lat_deg':lat,'lon_deg':lon,'local_elevation_m':a,'regional_elevation_m':b,'difference_m':a-b})
 if max(abs(c['difference_m']) for c in checks)>30:raise ValueError('Local/regional vertical convention comparison failed against the preset 30 m tolerance.')
 registry=realization_catalogue(entry);clone_checks=[]
 for record in registry:
  asset=verify_sources('terrain',[record['asset_id']])['assets'][0];clone=cached_raster(asset['file'],asset['sha256'])
  if not aligned(local,clone):raise ValueError('Clone grid does not match native projection/registration.')
  delta=clone.values.astype(np.float64)-local.values;valid=delta[np.isfinite(delta)];rms=float(np.sqrt(np.mean(valid**2)))
  if rms>20:raise ValueError('Published clone fails the predeclared complete-surface convention check (20 m RMS); do not infer an offset convention automatically.')
  clone_checks.append({'id':record['id'],'asset_sha256':asset['sha256'],'grid_aligned':True,'clone_minus_nominal_rms_m':rms,'clone_minus_nominal_range_m':[float(valid.min()),float(valid.max())],'format_check_rms_limit_m':20,'limit':'Format/convention check, not an accuracy estimate or the complete 100-member error distribution.'})
 count_check=None
 if entry.get('count_asset_id'):
  a=lookup[entry['count_asset_id']];counts=cached_raster(a['file'],a['sha256'])
  if not aligned(local,counts):raise ValueError('Count grid does not match the native surface.')
  valid=counts.values[np.isfinite(counts.values)]
  if np.any(valid<0) or np.any(valid!=np.floor(valid)):raise ValueError('LOLA return count source contains invalid counts.')
  count_check={'finite_cells':int(len(valid)),'cells_with_returns':int((valid>0).sum()),'empty_interpolated_cells':int((valid==0).sum()),'sampling':'Native containing cell, no interpolation of count categories.'}
 manifest={'realization_catalogue':registry,'clone_registration_checks':clone_checks,'count_map_check':count_check,'site_id':identity,'definition':entry,'frame':'MOON_ME_DE421','reference_radius_m':R,'vertical_definition':'metres above 1737400 m sphere, checked against regional PGDA90 at five matching coordinates','assets':assets,'vertical_checks':checks,'vertical_check_tolerance_m':30,'origin_registration_check':origin_check,'limits':['5 m posting does not resolve wheel-scale hazards; many source cells are interpolated between LOLA tracks','height RMS is not a complete terrain error model','horizon sampling requires numerical convergence/observed-shadow validation before mission reliance']}
 (DATA/'sites').mkdir(exist_ok=True);(DATA/'sites'/entry['manifest_file']).write_text(json.dumps(manifest,indent=2)+'\n')
 return manifest
if __name__=='__main__':
 for entry in catalogue():print(json.dumps(prepare_manifest(entry['id'])['vertical_checks'],indent=2))
