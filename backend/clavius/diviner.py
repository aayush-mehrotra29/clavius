"""Content-pinned historical Diviner context; never a mission-date forecast."""
import hashlib,io,json,math,os
from pathlib import Path
from xml.etree import ElementTree as ET
import numpy as np
from .paths import ROOT,DATA
from .terrain import R,stereographic

NS={'p':'http://pds.nasa.gov/pds4/pds/v1'}
MODEL_ID='diviner-pcp-context-v0.1'

class DivinerCoverageError(ValueError):pass

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as source:
  while chunk:=source.read(1024*1024):h.update(chunk)
 return h.hexdigest()

def specification():
 captured=os.environ.get('CLAVIUS_DIVINER_MANIFEST_PATH')
 return json.loads(Path(captured).read_text()) if captured else json.loads((ROOT/'public/data/simulation-manifest.json').read_text())['diviner']

def label_schema(xml_path):
 """Read the actual PDS4 fixed-record layout; reject a changed table contract."""
 root=ET.parse(xml_path);table=root.find('.//p:Table_Character',NS)
 fields=[]
 for field in table.findall('.//p:Field_Character',NS):
  fields.append({'name':field.find('p:name',NS).text,'start':int(field.find('p:field_location',NS).text)-1,'length':int(field.find('p:field_length',NS).text),'unit':field.find('p:unit',NS).text})
 if [f['name'] for f in fields]!=['x','y','clon','clat','tbol'] or fields[-1]['unit']!='K':raise ValueError('Unsupported Diviner table columns or temperature units.')
 records=int(table.find('p:records',NS).text);offset=int(table.find('p:offset',NS).text);length=int(table.find('.//p:record_length',NS).text)
 if offset!=59 or length!=59:raise ValueError('Unsupported Diviner record registration.')
 return {'fields':fields,'records':records,'offset':offset,'record_length':length,'logical_identifier':root.find('.//p:logical_identifier',NS).text}

def derive(spec,directory,output):
 """Clip native records without resampling, preserving their one-based row IDs."""
 x0,y0=map(float,stereographic(spec['selection']['latitude_deg'],spec['selection']['longitude_deg']))
 extent=spec['selection']['half_extent_m'];products=[]
 for product in spec['products']:
  schema=label_schema(directory/product['xml_file']);source=directory/product['table_file']
  expected=schema['offset']+schema['records']*schema['record_length']
  if source.stat().st_size!=expected:raise ValueError('Diviner table size differs from its PDS4 label.')
  rows=[];count=0;maximum_residual=0.
  with source.open('rb') as stream:
   header=stream.read(schema['offset'])
   if header.strip()!=b'x,         y,        clon,       clat,       tbol':raise ValueError('Unexpected Diviner header.')
   while raw:=stream.read(schema['record_length']*100000):
    if len(raw)%schema['record_length']:raise ValueError('Truncated Diviner record.')
    values=np.loadtxt(io.BytesIO(raw),delimiter=',',ndmin=2)
    # PDS special constants are missing values, never physical temperatures.
    valid=np.isfinite(values).all(axis=1)&(values[:,3]>=-90)&(values[:,3]<=-79)&(abs(values[:,2])<=180)&(values[:,4]>0)&(values[:,4]<500)&(abs(values[:,:2])<1).all(axis=1)
    indices=np.flatnonzero(valid);v=values[valid];x,y=stereographic(v[:,3],v[:,2])
    residual=np.hypot(x-v[:,0]*R,y-v[:,1]*R)
    if len(v):maximum_residual=max(maximum_residual,float(residual.max()))
    keep=(abs(x-x0)<=extent)&(abs(y-y0)<=extent)
    for i in np.flatnonzero(keep):
     row=v[i];rows.append({'source_row':int(count+indices[i]+1),'polar_x_m':round(float(x[i]),6),'polar_y_m':round(float(y[i]),6),'latitude_deg':float(row[3]),'longitude_deg':float(row[2]),'temperature_k':float(row[4])})
    count+=len(values)
  if count!=schema['records']:raise ValueError('Diviner record count differs from its label.')
  if maximum_residual>spec['selection']['maximum_projection_residual_m']:raise ValueError('Diviner normalized coordinates disagree with independent lunar stereographic conversion.')
  products.append({'id':product['id'],'samples':rows,'source_records':count,'projection_check_maximum_residual_m':round(maximum_residual,6)})
 result={'schema_version':'clavius-diviner-context-1','model_id':MODEL_ID,'selection':spec['selection'],'products':products}
 raw=canonical(result);actual=hashlib.sha256(raw).hexdigest();expected=spec['derivative'].get('sha256')
 if expected and actual!=expected:raise ValueError('Derived Diviner context differs from the pinned derivative.')
 output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(raw)
 return {'sha256':actual,'bytes':len(raw),'products':[{'id':p['id'],'samples':len(p['samples']),'source_records':p['source_records'],'projection_check_maximum_residual_m':p['projection_check_maximum_residual_m']} for p in products]}

_cache={}
def selected_specification(spec,site_id='connecting-ridge'):
 if spec.get('selected_site_id')==site_id:return spec
 if site_id=='connecting-ridge':return {**spec,'selected_site_id':site_id}
 extra=spec.get('additional_derivatives',{}).get(site_id)
 if extra is None:raise ValueError('No prepared Diviner context for this site.')
 return {**spec,**extra,'selected_site_id':site_id}

def load(site_id='connecting-ridge'):
 from .integrity import verify_sources
 spec=selected_specification(verify_sources('diviner'),site_id);path=Path(os.environ.get('CLAVIUS_DIVINER_CONTEXT_PATH',str(ROOT/'public'/spec['derivative']['file'])))
 if not path.is_file():raise ValueError('Diviner context derivative is missing. Run scripts/prepare_diviner_context.py.')
 stat=path.stat();key=(str(path),stat.st_size,stat.st_mtime_ns,spec['derivative']['sha256'])
 if key not in _cache:
  raw=path.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=spec['derivative']['sha256']:raise ValueError('Diviner context derivative checksum mismatch.')
  _cache.clear();_cache[key]=json.loads(raw)
 return spec,_cache[key]

def sample(latitude_deg,longitude_deg,site_id='connecting-ridge'):
 if not math.isfinite(latitude_deg) or not math.isfinite(longitude_deg) or not -90<=latitude_deg<=90:raise ValueError('Invalid lunar coordinates.')
 spec,data=load(site_id);qx,qy=map(float,stereographic(latitude_deg,longitude_deg));bins=[]
 x0,y0=map(float,stereographic(data['selection']['latitude_deg'],data['selection']['longitude_deg']))
 inside=abs(qx-x0)<=data['selection']['half_extent_m']-spec['native_posting_m'] and abs(qy-y0)<=data['selection']['half_extent_m']-spec['native_posting_m']
 for product,metadata in zip(data['products'],spec['products'],strict=True):
  value={'id':product['id'],'name':metadata['name'],'local_time_hours':metadata['local_time_hours'],'covered':False,'reason':'No observed bin contains this point.' if inside else 'Outside the prepared Diviner context area.'}
  if inside and product['samples']:
   nearest=min(product['samples'],key=lambda s:(s['polar_x_m']-qx)**2+(s['polar_y_m']-qy)**2)
   dx=qx-nearest['polar_x_m'];dy=qy-nearest['polar_y_m'];half=spec['native_posting_m']/2-spec['cell_edge_guard_m']
   # A missing native bin stays missing. Never borrow a distant neighbor.
   if abs(dx)<=half and abs(dy)<=half:
    value.update(covered=True,reason=None,temperature_k=nearest['temperature_k'],temperature_c=nearest['temperature_k']-273.15,cell_center={'latitude_deg':nearest['latitude_deg'],'longitude_deg':nearest['longitude_deg']},center_distance_m=math.hypot(dx,dy),source_row=nearest['source_row'],reference={'product_id':product['id'],'source_row':nearest['source_row'],'derivative_sha256':spec['derivative']['sha256']})
  bins.append(value)
 return {'available':True,'model_id':MODEL_ID,'source_class':spec['source_class'],'query':{'latitude_deg':latitude_deg,'longitude_deg':longitude_deg},'native_posting_m':spec['native_posting_m'],'observation_interval_utc':spec['observation_interval_utc'],'season':spec['season'],'bins':bins,'limitations':spec['limits'],'source_manifest':spec}

def resolve_boundary(config):
 """Validate a retained NASA reference without allowing editable values to forge provenance."""
 ref=config.ground_reference
 if ref is None:return None
 root_spec=specification()
 if root_spec['derivative']['sha256']==ref.derivative_sha256:site_id=root_spec.get('selected_site_id','connecting-ridge')
 else:site_id=next((key for key,value in root_spec.get('additional_derivatives',{}).items() if value['derivative']['sha256']==ref.derivative_sha256),None)
 if site_id is None:raise ValueError('The selected Diviner context version differs from the prepared data.')
 spec,data=load(site_id)
 product=next((p for p in data['products'] if p['id']==ref.product_id),None)
 row=next((s for s in product['samples'] if s['source_row']==ref.source_row),None) if product else None
 if row is None:raise ValueError('Selected Diviner product/row is not in the prepared context.')
 if abs(config.ground_temperature_c-(row['temperature_k']-273.15))>1e-8:raise ValueError('Ground temperature differs from its retained Diviner reference. Clear the reference for a manually declared value.')
 metadata=next(p for p in spec['products'] if p['id']==ref.product_id)
 from .store import artifact
 if artifact(data)!=spec['derivative']['sha256']:raise ValueError('Diviner context artifact encoding differs from the pinned derivative.')
 return {'role':'constant_ground_boundary_scenario','policy':'A historical summer/local-time composite copied to one constant boundary for the entire mission. Not an instantaneous temperature forecast or a battery measurement.','reference':ref.model_dump(),'sample':row,'product':metadata,'source_manifest':spec}
